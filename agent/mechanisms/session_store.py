# -*- coding: utf-8 -*-
"""会话持久化：加密 append-only 事件日志。

- 布局：每会话一条日志 `<data_root>/sessions/<cid>.raw`，每行一条事件 JSON；
- 加密：行级独立 envelope，none / local 两模式（实现与密钥在
  `agent/mechanisms/session_crypto.py`）；密钥文件 `<data_root>/cache/session_encryption.key`；
- 读写：逐行 append + flush；读取容错——坏行跳过、缺文件返回空；
- 并发：同文件写入串行（进程内锁 + 跨进程锁，实现在
  `agent/mechanisms/session_locking.py`）；行格式与坐标语义在
  `agent/mechanisms/session_lines.py`。

纪律：本模块只做"事实持久化"，不做事件语义加工；事件模型见 core/events.py。
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

from agent.core.error_report import report_error
from agent.core.events import Event
from agent.mechanisms.session_crypto import (
    ALG_LOCAL,
    APP_ENTROPY_SALT,
    MAGIC,
    SessionCipher,
)
from agent.mechanisms.session_lines import (
    KEY_DATA,
    KEY_TYPE,
    event_from_obj,
    event_seq,
    event_to_json,
    seq_from_obj,
)
from agent.mechanisms.session_locking import cross_process_lock

__all__ = [
    "ALG_LOCAL",
    "APP_ENTROPY_SALT",
    "KEY_DATA",
    "KEY_TYPE",
    "MAGIC",
    "SessionStore",
    "is_valid_conversation_id",
    "new_conversation_id",
]

_CID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def new_conversation_id() -> str:
    """新会话 ID：UUID4 字符串。"""
    return str(uuid.uuid4())


def is_valid_conversation_id(conversation_id: str) -> bool:
    """校验会话 ID（白名单字符 + 长度 8~128，防路径穿越）。"""
    return bool(_CID_RE.match(str(conversation_id or "").strip()))


#: 待重试队列的批数上限（按会话）。不设上限的话，磁盘长时间不可写会无限吃内存；
#: 超限丢最旧的批并留痕 —— 丢陈年数据、保当下的输入。
_PENDING_MAX_BATCHES = 64


class SessionStore:
    """append-only 事件日志（每会话一档）；可选行级加密。"""

    def __init__(self, data_root: Path, *, encryption: str = "none",
                 durable: bool = False) -> None:
        self.data_root = Path(data_root)
        self.encryption = encryption if encryption in ("none", "local") else "none"
        #: 每次 append 是否 `fsync`（默认关）。
        #:
        #: 关的理由：`fsync` 是这笔写入的绝对大头（4~6ms，去掉后亚毫秒），
        #: 而它只防"断电/蓝屏"——进程崩溃不会丢已 `flush` 的数据；而且事实是
        #: 先广播后落盘的，"最后几次没落盘但界面已渲染"这个窗口本来就存在，
        #: `fsync` 消不掉它。需要更强保证时传 `durable=True`。
        self.durable = bool(durable)
        self._cipher = SessionCipher(self.data_root, self.encryption)
        # 全局存储坐标（跨会话单调递增）。见 `allocate_seq`。
        self._next_global_seq: Optional[int] = None
        self._max_observed: int = -1
        self._seq_lock = threading.Lock()
        # 按文件的写锁：`append` 是"读旧内容 → 写 tmp → replace"的读改写，
        # 同一文件的两个写者必须串行，否则后写的那份会把前一份整份覆盖掉（丢行）。
        # 懒创建 + 复用（按路径字符串索引），避免每次 append 造锁。
        self._file_locks: dict = {}
        self._file_locks_guard = threading.Lock()
        # 落盘失败的事实攒在这里等下次重试（跨回合存活：挂在 store 上；
        # 回合级引擎每回合新建，挂在那里会随 GC 丢光）。
        # 只承诺"同一进程内不丢"：进程重启后磁盘不可写这段本来也无处可存。
        self._pending: dict = {}
        #: 进程内已成功写过的坐标（按会话）—— 见 `_written_seqs`
        self._written: dict = {}
        #: 播种/写入时记下的文件指纹（按会话）：`(st_size, st_mtime_ns)`。
        #: 用来发现「文件被外部动过」（清空/截断/别的进程写了）——见 `_written_seqs`。
        self._written_fp: dict = {}
        self._written_guard = threading.Lock()
        self._pending_guard = threading.Lock()

    def _append_lock(self, path: Path):
        """取该文件的写锁（同一文件串行；不同文件并行）。"""
        key = str(path)
        with self._file_locks_guard:
            lock = self._file_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._file_locks[key] = lock
            return lock

    # ── 存储坐标（全局单调）────────────────────────────────
    #
    # 坐标取全局：SSE 是一条全局流，重连游标
    # （`Last-Event-ID`）就一个。若坐标按会话各从 0 开始，一个游标根本无法表达
    # "所有会话的位置"——就得额外告诉服务端"续哪个会话"，而浏览器原生的
    # `EventSource` 没有地方带这个信息。全局单调后，一个游标就是全部所需。
    #
    # 分配在存储层：坐标必须与"已落盘事实"一一对应，而存储层是
    # 落盘的唯一入口；分配在这里，天然不会与磁盘状态漂移。

    def allocate_seq(self, count: int) -> int:
        """预留 `count` 个连续坐标，返回第一个。

        首次调用时扫一遍现有日志播种（见 `_scan_max_seq`）——否则重启后会从 0
        重新发号，与磁盘上已有的坐标撞号。

        护栏：播种只在首次做，而磁盘可能被别的进程改过。
        所以分配前对比"本实例读过或分配过的最大号"（`_max_observed`），
        发现计数器落后就重扫纠正 —— 内存计数器与磁盘是第二个权威，
        不设这道护栏就会与磁盘漂移。
        """
        need = max(0, int(count))
        with self._seq_lock:
            if self._next_global_seq is None or self._next_global_seq <= self._max_observed:
                self._next_global_seq = self._scan_max_seq() + 1
            start = self._next_global_seq
            self._next_global_seq = start + need
            self._max_observed = self._next_global_seq - 1
            return start

    def _observe(self, seq: int) -> None:
        """记录"见过的最大坐标"（读取路径调用），供 `allocate_seq` 的护栏比较。"""
        if seq > self._max_observed:
            self._max_observed = seq

    def _scan_max_seq(self) -> int:
        """扫所有会话日志，取已被占用的最大坐标；没有则 -1。

        两类都要算进去：
          ① 落盘的 `seq` 字段（全局坐标）；
          ② 每会话行数（没有 `seq` 的行，读取时会按 0..n-1 的位置补号）。
        漏掉 ② 就会让新号与补号撞上——那时一个游标分不清"这是补号还是
        全局号"，续传就会漏帧。取行数上限（而非行数之和）是保守够用的下界：
        没有 `seq` 的行之间本来就可能重号（每个文件都从 0 起），那不影响游标前进，
        真正要防的是新号落进那些补号的区间。
        """
        directory = self.data_root / "sessions"
        if not directory.is_dir():
            return -1
        highest = -1
        for path in directory.glob("*.raw"):
            lines = 0
            try:
                with path.open("r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if not line.strip():
                            continue
                        lines += 1
                        obj = self._parse_obj(line)
                        seq = seq_from_obj(obj)
                        if seq is not None and seq > highest:
                            highest = seq
            except OSError as exc:
                report_error("agent.mechanisms.session_store.SessionStore._scan_max_seq", exc)
                continue
            # 没有 `seq` 的行按位置补号；行号范围 0..lines-1
            if lines - 1 > highest:
                highest = lines - 1
        return highest

    # ── 路径────────────────────────────────

    def raw_path(self, conversation_id: str) -> Path:
        """会话日志路径；非法会话 ID 直接拒绝（防路径穿越）。"""
        cid = str(conversation_id or "").strip()
        if not is_valid_conversation_id(cid):
            raise ValueError(f"非法会话 ID：{conversation_id!r}")
        return self.data_root / "sessions" / f"{cid}.raw"

    # ── 写入────────────────────────────────────────

    def append(self, conversation_id: str, events: Iterable[Event]) -> int:
        """追加一批事件（每行一条）；返回本次请求写入的行数。

        坐标 `seq` 来自事件载荷里的 `_seq`（已在事件产出瞬间由 `emit`、
        经 `App.session` 预分配的全局坐标标好），本方法不另行编号——
        否则就有了第二个权威，两者迟早漂移。
        载荷没有 `_seq` 时（纯内存构造的事件、或直接调 store 的测试），
        在这里补一个全局坐标，保证落盘行总有可用坐标。

        ## 写入是原子的（必须保持）

        实现：记下追加前的偏移量 → 以 `a` 模式追加本批 → 失败则 `truncate(offset)` 回滚。
        常见路径只写本批，而回滚保证"要么整批可见、要么整批不可见"，没有"写了一半"的中间态。

        ⚠️ 不采用「整文件重写 + `os.replace`」（原子但贵）：2.33MB 会话上一次
        append 要 14.3ms（对照 `open('a')` 追加的 0.133ms），11.28MB 时 26.2ms，
        且随会话长度二次增长 —— 每趟都要把全文读一遍再写一遍；而硬要求只有
        "失败后重试同一批不能产生重复行"，那就不必重写全文；细节见 `_write_rows`。

        整批原子写是 `Engine._flush_facts` 补偿的前提：它落盘失败时会把整批放回待重试。
        那个补偿的前提就是写盘原子 —— 若逐行写，半写失败后重试整批会让
        磁盘出现重复行与重复坐标
        （`[turn_started, mark, turn_started, mark, …]`、坐标 `[0,1,0,1,…]`）。

        ## 失败会进待重试队列（跨回合存活）

        写失败时本批进 `self._pending[cid]`，下一次 `append` 时先补投它，再写新批。
        队列挂在 store 上而不是回合级引擎上：后者每回合新建，队列会随引擎被 GC，
        用户发言永久丢失（磁盘上只剩后一回合）；挂在 store 上就跨回合、
        跨引擎实例存活，而 store 本就是落盘的唯一入口。

        队列有界（见 `_PENDING_MAX_BATCHES`）：不设上限的话，磁盘长时间不可写
        会无限吃内存；超限丢最旧的并留痕（丢的是陈年数据，保的是当下的输入）。
        """
        batch = list(events)
        if not batch:
            # 空批也要给"待重试"一个机会（否则最后一个失败的回合永远补不上）。
            self.flush_pending(conversation_id)
            return 0
        queued = self._take_pending(conversation_id)
        return self._write_rows(conversation_id, queued + batch, len(batch))

    # ── 待重试队列（跨回合存活）──────────────────────────
    #
    # 队列是内存的：进程重启后磁盘不可写这段时间的事实本来也无处可存
    # （能存就不叫"写不进去"了）。所以这里的承诺是"同一进程内不丢"，
    # 不是"断电也不丢"。

    def flush_pending(self, conversation_id: str) -> int:
        """把该会话积压的待重试事实补投出去（成功返回写入行数，失败返回 0）。

        调用点：① 每次 `append`（先补旧再写新，保证顺序）；
        ② 会话结束/空闲时主动补一次（见 `SessionRunner`）。
        """
        queued = self._take_pending(conversation_id)
        if not queued:
            return 0
        return self._write_rows(conversation_id, queued, 0)

    def flush_all(self) -> int:
        """把所有会话积压的待重试事实都补投一次（停机时用）。

        `_pending` 只在内存里，进程退出即消失。而
        `flush_pending` 的调用点是"下次 append"与"会话收尾"——
        停机时没有下一次 append，那批就永久丢了（`App.dispose()` 不补投）。
        关页/关进程是常见操作，所以停机必须补一次。

        返回成功补投的总条数；单个会话失败只留痕，继续补其余会话。
        """
        with self._pending_guard:
            cids = list(self._pending.keys())
        written = 0
        for cid in cids:
            try:
                written += self.flush_pending(cid)
            except Exception as exc:
                print(f"[store] 停机补投失败 cid={cid}: {type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)
        return written

    def _pending_only_new(self, conversation_id: str, batch: list) -> list:
        """从 `batch` 里剔除已经排队或已经落盘的事实（按 `_seq` 判）。

        没有 `_seq` 的事件（纯内存构造的测试事件）不做去重 —— 没有坐标就没有身份，
        硬去重反而会误删。
        """
        known: set = set()
        with self._pending_guard:
            for b in self._pending.get(conversation_id) or []:
                for e in b:
                    s = event_seq(e)
                    if s is not None:
                        known.add(s)
        on_disk = self._disk_seqs(conversation_id)
        out: list = []
        for e in batch:
            s = event_seq(e)
            if s is None or (s not in known and s not in on_disk):
                out.append(e)
        return out

    def _written_seqs(self, conversation_id: str) -> set:
        """进程内已成功写过的坐标（按会话）。首次访问读盘播种一次。

        `_disk_seqs` 每趟 append 都整读会话文件 ——
        11MB 会话上单条 append 要 238.6ms（关掉读盘比对只要 3.9ms，放大 60.8 倍），
        而一个回合会调好几次 append，等于每回合多秒级阻塞。
        而同一事实写两次是同进程内的重发问题（`_pending` 也只承诺同进程），
        所以进程内记一份就够；文件里既有的坐标由第一次读盘播种。
        """
        path = self.raw_path(conversation_id)
        fp = self._file_fp(path)
        with self._written_guard:
            known = self._written.get(conversation_id)
            if known is None or self._written_fp.get(conversation_id) != fp:
                # 首次访问、或文件被外部动过（清空/截断/别的进程写了）→ 重新播种。
                # 只做一次 `stat()`，不读全文（读全文才是那个 238ms 的元凶）。
                known = self._disk_seqs(conversation_id)
                self._written[conversation_id] = known
                self._written_fp[conversation_id] = fp
            return known

    @staticmethod
    def _file_fp(path: Path):
        """文件指纹 `(st_size, st_mtime_ns)`；不存在则 `None`。

        `st_mtime_ns` 在 truncate 到 0 字节时也会变，所以这对指纹能可靠地
        发现「文件被外部清空/截断/替换」—— 那是纯外部动作，
        任何"失败即整桶失效"的机制都覆盖不到。
        """
        try:
            st = path.stat()
            return (st.st_size, st.st_mtime_ns)
        except OSError:
            return None

    @staticmethod
    def _last_good_end(path: Path) -> int:
        """返回最后一条完整行的结束偏移（= 可以安全追加的位置）。

        文件以 `\n` 结尾 → 返回文件大小（正常路径，不做任何多余的事）。
        结尾是残行（写到一半留下、或被外部追加出来的）→ 返回该残行之前的偏移，
        调用方据此截断 —— 让文件回到「全好行」状态，而不是留着垃圾让 `load` 每次跳过它。

        读不出来（IO 错）返回文件大小 = 「不修」，那是保守选择：
        `_write_rows` 那边还有防御性换行兜住「粘行」。
        """
        try:
            size = path.stat().st_size
            if size == 0:
                return 0
            with path.open("rb") as fh:
                fh.seek(size - 1)
                if fh.read(1) == b"\n":
                    return size                     # 正常：以换行收尾
                chunk = 64 * 1024
                pos = size
                while pos > 0:
                    start = max(0, pos - chunk)
                    fh.seek(start)
                    buf = fh.read(pos - start)
                    idx = buf.rfind(b"\n")
                    if idx >= 0:
                        return start + idx + 1       # 换行之后就是残行起点
                    pos = start
                return 0                             # 整个文件就是一条残行
        except OSError:
            # 旁路，刻意吞掉：读不出来就「不修」—— 修文件不该让写入失败，
            # 而「不修」的后果只是那一条残行继续留着（有防御性换行保证不粘批）。
            try:
                return path.stat().st_size
            except OSError:
                return 0

    def _disk_seqs(self, conversation_id: str) -> set:
        """盘上已有的 `_seq` 集合（读不出来就当空 —— 调用方还有第二道防线）。"""
        path = self.raw_path(conversation_id)
        if not path.is_file():
            return set()
        out: set = set()
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    obj = self._parse_obj(line)
                    seq = seq_from_obj(obj) if obj is not None else None
                    if isinstance(seq, int):
                        out.add(seq)
        except Exception as exc:
            # 补偿路径：若让异常逃出去会顶掉原始异常、且队列为空 —— 第二道防线被击穿。
            # 读不出来就当"盘上没有已知坐标"（宁可重试也不丢），但必须留痕。
            print(
                f"[store] 读已落盘坐标失败 path={path}: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr, flush=True,
            )
            return set()
        return out

    def _take_pending(self, conversation_id: str) -> list:
        """取出并清空该会话的待重试事实（保持顺序：旧的在前）。"""
        with self._pending_guard:
            queue = self._pending.pop(conversation_id, None)
        if not queue:
            return []
        out: list = []
        for b in queue:
            out.extend(b)
        return out

    def _put_pending(self, conversation_id: str, batch: list) -> None:
        """把失败的批次放回队列尾（放在尾部 = 让更新的数据排在后面，顺序不乱）。

        按 `_seq` 去重：引擎是"整批投递"，而批次会跨多次
        flush 长大 —— `flush#1` 投 `[A]` 失败（A 进队列），`flush#2` 又投 `[A,B]`，
        于是 A 在队列里出现两次、最终写成两行（K=1/2/3 时重复
        `_seq` 1/4/9 个、`turn_started` 4/5/6 次）。
        队列的语义是"还没写进去的事实"——同一事实一次就够。
        """
        fresh = self._pending_only_new(conversation_id, list(batch))
        if not fresh:
            return
        with self._pending_guard:
            queue = self._pending.setdefault(conversation_id, [])
            queue.append(fresh)
            dropped = 0
            while len(queue) > _PENDING_MAX_BATCHES:
                queue.pop(0)
                dropped += 1
        if dropped:
            print(f"[store] 待重试队列超过 {_PENDING_MAX_BATCHES} 批，"
                  f"丢弃最旧的 {dropped} 批（磁盘长期不可写）",
                  file=sys.stderr, flush=True)

    def _write_rows(self, conversation_id: str, rows_events: list,
                    requested: int) -> int:
        """把事实渲染成行并原子写入；任何失败都进待重试队列后抛出。

        `requested` 只用于返回值（"本次请求写入的行数"）—— 补投的旧批次
        不该算进调用方的计数里（否则日志/测试很难读）。

        ## 整段都在 try 里

        行渲染若留在 try 之外，渲染阶段抛异常（编码失败、内存不足）就直接
        逃出函数，队列根本没进（`_put_pending` 不被调用）。
        所以整段包起来：无论在哪一步失败，数据都留在队列里等下次重试。
        """
        if not rows_events:
            return 0
        try:
            missing = sum(1 for e in rows_events if event_seq(e) is None)
            fallback = self.allocate_seq(missing) if missing else 0
            path = self.raw_path(conversation_id)
            path.parent.mkdir(parents=True, exist_ok=True)

            # 先把本批渲染成行（同时补坐标）—— 任何编码/序列化错误都在动文件之前抛出。
            rows: list[str] = []
            # 第二道防线：写过的不再写。用进程内集合（每趟读盘要 238ms@11MB）；
            # 它就是 `_written[cid]` 那个集合本身（引用），而 `_written` 由
            # 「写成功并入 + 失败整桶失效 + 文件指纹不符就重播种」共同维护 ——
            # 它已经等于"盘上坐标 ∪ 本批已并入坐标"，不需要额外的读盘并集核对。
            # 批内重复由下面的 `on_disk.add(seq)` 自己挡住。
            on_disk = self._written_seqs(conversation_id)
            for event in rows_events:
                seq = event_seq(event)
                if seq is None:
                    if isinstance(getattr(event, "data", None), dict):
                        event.data["_seq"] = fallback
                        fallback += 1
                elif seq in on_disk:
                    continue     # 已写过（重复投递/重试）→ 跳过
                else:
                    on_disk.add(seq)
                rows.append(self._encrypt_line(event_to_json(event)))
            if not rows:
                return requested        # 全都写过了：不需要动文件

            # ## 回滚方式：偏移量 + 截断
            #
            # 整文件重写（临时文件 + `os.replace`）正确但有代价：2.33MB 会话上
            # 一次 append 要 14.3 ms（对照 `open('a')` 追加的 0.133 ms），
            # 11.28MB 时 26.2 ms，且随会话长度二次增长 —— 每趟（十几条事件）都要把
            # 全文读一遍再写一遍。
            #
            # 硬要求只有一条：失败后重试同一批不能产生重复行。做到它不必重写全文：
            #   ① 追加前记下文件偏移（`stat().st_size`）；
            #   ② 以 `a` 模式追加本批；
            #   ③ `flush`（可选 `fsync`，见 `durable`）；
            #   ④ 任何一步失败 → `truncate(offset)` 回滚到追加前，再交给待重试队列。
            # "要么整批可见、要么整批不可见"照样成立，而常见路径只写本批。
            #
            # ⚠️ 按文件串行（`self._append_lock`）：偏移量 + 截断是读改写，
            # 两个写者并发会互相截断。不串行的代价：8 线程 × 25 批里
            # 195/200 次抛 `PermissionError [WinError 32]`、只写进 4 行。
            # 进程内锁 + 跨进程锁，两层都要（见 `cross_process_lock` 的说明）
            with self._append_lock(path), cross_process_lock(path):
                offset = path.stat().st_size if path.is_file() else 0
                try:
                    with path.open("a", encoding="utf-8", newline="\n") as fh:
                        # 防御性隔离（边界情况）：
                        # 若文件末尾没有换行（残行出自写到一半、或出自外部追加），
                        # 直接追加会把本批粘到那条残行上，两条一起变成坏行 ——
                        # `load` 会把它们一起跳过，于是本批事实静默丢失：
                        #   '…}\n{"_seq":999,"type":"broken"'  +  本批
                        #   = '…}\n{"_seq":999,"type":"broken"{"type":"input_claimed",…}\n'
                        # 先补一个换行隔离：残行照样是坏的（本来就坏），但本批完好。
                        # 回滚偏移仍取 `offset` —— 失败时本批连同补的换行一起撤掉。
                        # 自愈（见 `_last_good_end` 的说明）：残行不是「隔开」而是「截掉」。
                        # 截断在 `offset` 之前完成，所以 `offset` 仍是截断后的文件尾，
                        # 回滚语义不变。截断失败就退回「补一个换行隔离」以保证本批不被粘坏。
                        good_end = self._last_good_end(path) if offset > 0 else 0
                        if 0 <= good_end < offset:
                            try:
                                with path.open("r+b") as tf:
                                    tf.truncate(good_end)
                                    tf.flush()
                            except OSError:
                                # 旁路，刻意吞掉：截不掉就退回隔离写法 ——
                                # 宁可留一条残行，也不能让本批被粘坏（那会静默丢本批）。
                                fh.write("\n")
                        for row in rows:
                            fh.write(row)
                            fh.write("\n")
                        fh.flush()
                        if self.durable:
                            # 可选：只防断电/蓝屏（见 __init__ 里 durable 的说明）
                            os.fsync(fh.fileno())
                except Exception:
                    # 回滚到追加前 —— 这一步让"重试整批"不会产生重复行。
                    try:
                        if path.is_file() and path.stat().st_size > offset:
                            with path.open("r+b") as fh:
                                fh.truncate(offset)
                    except OSError as exc:
                        # 旁路，刻意吞掉：回滚失败也不能顶掉原始异常
                        # （调用方必须知道"这趟没落盘"）。数据仍在待重试队列里。
                        report_error("agent.mechanisms.session_store.SessionStore._write_rows", exc)
                    # 这里不做坐标撤回 —— 外层 `except` 会无条件整桶失效
                    # （`_written.pop`），那是更强的不变量：
                    #   · 回滚成功 → 那批不在盘上 → 整桶失效后重播种，不会误跳过；
                    #   · 回滚失败 → 那批可能已在盘上 → 撤单个坐标会让重试重复写
                    #     （例如 `seqs=[0,1,1]`）；整桶失效则重新读盘、不会重复。
                    raise
        except Exception as exc:
            # 写不进去 → 进待重试队列（跨回合、跨引擎实例存活），再把异常照常抛出：
            # 调用方（引擎）仍要知道这一趟没落盘，但数据不会随对象被回收而消失。
            #
            # 撤掉刚并入的坐标：`on_disk` 就是 `_written[cid]` 那个集合本身（引用），
            # 而渲染阶段就会往里 `add` —— 任何失败都要撤；否则重试时 `seq in on_disk`
            # 会命中、事件被静默跳过（丢数据）。
            #
            # 这里本就该整桶失效 —— `_written_seqs` 只在首次读盘播种、此后不复核，
            # 所以"外部清空 / 截断了 `.raw`"之后，同坐标重投会被静默跳过（盘上 0 行）。
            # 统一成"任何失败都让该会话的桶失效"：下次 append 重新读盘，
            # 既不误跳过、也不会重复写。多读一次盘的代价远小于静默丢数据。
            report_error("agent.mechanisms.session_store.SessionStore._write_rows", exc)
            with self._written_guard:
                self._written.pop(conversation_id, None)
                self._written_fp.pop(conversation_id, None)
            self._put_pending(conversation_id, rows_events)
            raise
        with self._written_guard:
            self._written_fp[conversation_id] = self._file_fp(self.raw_path(conversation_id))
        return requested if requested else len(rows_events)

    def line_count(self, conversation_id: str, *, path: Optional[Path] = None) -> int:
        """该会话日志的行数（= 下一个可用序号）；文件不存在返回 0。"""
        target = path or self.raw_path(conversation_id)
        if not target.is_file():
            return 0
        count = 0
        try:
            with target.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.strip():
                        count += 1
        except OSError:
            return 0
        return count

    # ── 读取────────────────────────────────────────

    def load(self, conversation_id: str) -> List[Event]:
        """读回全部事件；坏行 / 空行跳过，文件缺失返回空；IO 失败冒泡。"""
        return [event for _seq, event in self.load_with_seq(conversation_id)]

    def load_with_seq(self, conversation_id: str) -> List[Tuple[int, Event]]:
        """读回全部事件，并给出各自的全局存储坐标。

        两种行的坐标来源：
        - 有 `seq` 字段：直接用它——它是全局坐标，跨会话唯一；
        - 没有 `seq` 字段：这一行没有全局坐标可用，按行位置补一个。
          这类坐标只在该会话日志内有意义（可能与别的文件同位置的补号重复），
          但足以让"刷新后从头回放"工作；新事件永远走全局坐标，
          所以续传游标不会与补号混淆。
        """
        path = self.raw_path(conversation_id)
        if not path.is_file():
            return []
        out: List[Tuple[int, Event]] = []
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            position = 0
            for line in fh:
                if not line.strip():
                    continue
                obj = self._parse_obj(line)
                event = event_from_obj(obj, conversation_id) if obj is not None else None
                if event is not None:
                    stored = seq_from_obj(obj)
                    seq = position if stored is None else stored
                    self._observe(seq)
                    out.append((seq, event))
                position += 1
        return out

    def tail_from(self, conversation_id: str, after_seq: int) -> List[Tuple[int, Event]]:
        """取该会话里 `seq > after_seq` 的事件（断线续传用）。

        全局坐标下，一个游标对所有会话都成立，所以传哪个会话都只是在缩小范围；
        `after_seq < 0` 等价于"该会话全量"。
        """
        threshold = int(after_seq)
        return [(seq, event) for seq, event in self.load_with_seq(conversation_id)
                if seq > threshold]

    def tail_across(self, after_seq: int, limit: int = 512) -> List[Tuple[int, str, Event]]:
        """跨会话取 `seq > after_seq` 的事件，按坐标升序（真正的续传原语）。

        返回 `(seq, conversation_id, event)`。`limit` 兜住"游标很旧"的情况——
        宁可分几批补，也不一次把上万条塞进一条连接的队列。
        """
        threshold = int(after_seq)
        rows: List[Tuple[int, str, Event]] = []
        directory = self.data_root / "sessions"
        if not directory.is_dir():
            return rows
        for path in directory.glob("*.raw"):
            cid = path.stem
            if not is_valid_conversation_id(cid):
                continue
            for seq, event in self.load_with_seq(cid):
                if seq > threshold:
                    rows.append((seq, cid, event))
        rows.sort(key=lambda row: row[0])
        return rows[: max(1, int(limit))] if limit else rows

    # ── 加密入口──────────────────────────────────

    def _encrypt_line(self, plain: str) -> str:
        """明文行 → 落盘行；none 模式原样返回。

        子类会覆盖本方法模拟写入失败，所以加解密必须经由这一层进入。
        """
        return self._cipher.encrypt_line(plain)

    def _decrypt_line(self, line: str) -> Optional[str]:
        """落盘行 → 明文；明文行原样返回；空行返回 None；校验失败抛 ValueError。"""
        return self._cipher.decrypt_line(line)

    def _parse_obj(self, line: str) -> Optional[Any]:
        """一行 → 解析后的对象；解密 / 解析失败返回 None（跳过该行）。"""
        try:
            plain = self._decrypt_line(line)
        except ValueError:
            # 坏密文 / 非本密钥：跳过该行，不中断整档回放
            return None
        if not plain:
            return None
        try:
            return json.loads(plain)
        except json.JSONDecodeError:
            return None
