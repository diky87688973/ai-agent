# -*- coding: utf-8 -*-
"""运行态登记（可替换实现）：回答"某个会话的回合是不是正在跑"。

## 需要它做什么

SSE 没有游标就不回放：中途打开、或在跟跑中刷新的页面收不到 `run_started`，
于是它既显示不出「停止」、又判不出"忙"，用户在那个页面上既发不出消息
（点了必 409）也停不掉任务。所以页面首次打开时必须能从服务端问出
"这条会话在不在跑"。

## 独立成模块的理由

进程内存做权威判断，在多实例部署下必然错：实例 A 跑的回合，实例 B 看不见，
于是 B 会对用户说"没在跑"。所以运行态必须收敛到一个可替换的接口后面：
换共享存储（Redis / DB）只换实现，调用方一行不改。

## 两个实现

| 实现 | 用途 | 崩溃残留 |
|---|---|---|
| `InMemoryRunRegistry` | 单实例、测试 | 进程退出即消失（不会残留） |
| `FileRunRegistry` | 默认（`<data_root>/runs/`） | 心跳 + TTL 自愈（见下） |

### `FileRunRegistry` 的"在跑"判定

```
文件存在 且 now - 心跳时间 <= 存活期 且 那个进程还活着  →  在跑
```

心跳是主判据，进程存活是补强：

① 心跳 + TTL 跨平台、跨机器、共享盘可用 —— 换成分布式存储时语义不变；
② 崩溃自愈：进程死了心跳就停，超期后条目自动被判过期并清掉；
③ 补强那一层（`_pid_alive`）解决的是 TTL 窗口内的误判：进程被强杀后
   心跳会冻结在死前那一刻，而 TTL 还有十几分钟 —— 这期间文件看起来完全"新鲜"，
   于是同会话并发保护（`/api/chat/send` 的 409）与界面停止键同时失效。
   判一下 pid 就能立刻识破，不必干等 TTL。

> ⚠️ 判活实现见 `_pid_alive` 的 docstring：Windows 用 `ctypes` `OpenProcess`，
> 因为 `os.kill(pid, 0)` 在无控制台进程里对活进程也抛 `WinError 87`。
> 该函数只做判活，不杀进程。

⚠️ 心跳不只写在占位/释放时：占位期间读取也会刷新（`running()` 读取时续期）。
`run_command` 的长任务（`ping -n 120` ≈ 120 秒）会让一次回合长时间不与登记表交互 ——
只写两次的话，长任务中途就会被误判成"已结束"。
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Protocol, runtime_checkable

#: 一个回合的存活期（秒）。超过这么久没有心跳 → 判定为过期（进程多半已死）。
#: 取 15 分钟：远大于任何单次工具调用，又能在崩溃后自动恢复。
DEFAULT_TTL_SECONDS = 900.0

#: 两次心跳之间的最小间隔（秒）：避免高频读取把磁盘写爆。
_HEARTBEAT_MIN_INTERVAL = 30.0


@runtime_checkable
class RunRegistry(Protocol):
    """运行态登记的接口（调用方只依赖它，不依赖任何具体实现）。

    实现必须是幂等的：`release` 一个没登记过的 cid 不算错。
    """

    def claim(self, cid: str, run_id: str) -> bool:
        """尝试占位。已有人在跑 → False（调用方据此判"忙"）。"""
        ...

    def release(self, cid: str) -> None:
        """释放占位（回合结束 / 异常兜底）。幂等。"""
        ...

    def renew(self, cid: str, run_id: str) -> bool:
        """换一个 run_id 但不释放占位（队列抽干时用）。

        `renew` 在保持占位的前提下换 run_id：抽干下一条消息时要"始终占着位"——
        若先 `release` 再 `claim`，中间会出现"空闲窗口"，此时另一个投递
        看到空闲就会再激活一趟（同一个回合被执行两遍）。
        已登记 → 换 id 返回 True；未登记 → 不凭空占位，返回 False。
        """
        ...

    def touch(self, cid: str) -> None:
        """续心跳（占位期间调用）。幂等；未登记则忽略。"""
        ...

    def running(self, cid: str) -> bool:
        """该会话是否正在跑（读取时续心跳，见模块 docstring）。"""
        ...

    def running_cids(self) -> List[str]:
        """全部正在跑的会话 id（快照）。"""
        ...

    def active_run_id(self, cid: str) -> str:
        """该会话当前的 run_id；未在跑返回空串。"""
        ...


class InMemoryRunRegistry:
    """纯内存实现：单实例 / 测试用。进程退出即消失，不会留下残留。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._runs: Dict[str, str] = {}

    def claim(self, cid: str, run_id: str) -> bool:
        key = str(cid or "").strip()
        if not key:
            return False
        with self._lock:
            if key in self._runs:
                return False
            self._runs[key] = str(run_id or "")
            return True

    def release(self, cid: str) -> None:
        with self._lock:
            self._runs.pop(str(cid or "").strip(), None)

    def renew(self, cid: str, run_id: str) -> bool:
        key = str(cid or "").strip()
        with self._lock:
            if key not in self._runs:
                return False
            self._runs[key] = str(run_id or "")
            return True

    def touch(self, cid: str) -> None:
        return None

    def running(self, cid: str) -> bool:
        with self._lock:
            return str(cid or "").strip() in self._runs

    def running_cids(self) -> List[str]:
        with self._lock:
            return sorted(self._runs.keys())

    def active_run_id(self, cid: str) -> str:
        with self._lock:
            return self._runs.get(str(cid or "").strip(), "")


class FileRunRegistry:
    """落盘实现：每条在跑的会话一个文件，心跳 + TTL 判定存活。

    文件：`<dir>/<cid>.json` → `{"run_id", "pid", "started_at", "heartbeat"}`

    目录里出现残留（进程被 kill）时，条目会在 TTL 后被判定为过期并清理 ——
    所以不需要额外的启动清理，也不会把过期条目当成"在跑"。
    """

    def __init__(
        self,
        directory: Optional[Path] = None,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._lock = threading.RLock()
        self._dir = Path(directory) if directory else None
        self._ttl = float(ttl_seconds)
        self._last_touch: Dict[str, float] = {}

    # ── 内部 ────────────────────────────────────────────

    def _file(self, cid: str) -> Optional[Path]:
        if self._dir is None or not cid:
            return None
        return self._dir / f"{cid}.json"

    def _read(self, fp: Path) -> Optional[Dict[str, object]]:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _pid_alive(pid: object) -> bool:
        """记录里那个进程还在吗？只在"确知它死了"时返回 False。

        判活不用 `os.kill(pid, 0)`：

        那条路在 Windows 上不可靠：在没有控制台的进程里
        （Windows 服务 / 计划任务 / `pythonw` / 分离启动 / `Start-Process -WindowStyle Hidden`），
        `os.kill(pid, 0)` 对活着的进程也抛 `OSError [WinError 87] 参数错误`
        —— 连"自己探自己"都失败。把它当成"已死"会引出完整的失效链：

        `_pid_alive` 恒 False → `FileRunRegistry.running()` 在 `claim()` 成功之后
        立刻返回 False → `running_cids()` 恒空 → `/api/chat/send` 永不返回 409
        （同会话并发保护失效）、界面永远不出现停止键、`mesh.end_run` 的 `renew`
        恒失败而走"理论上到不了"的兜底分支。

        ## 判据（Windows 优先，非 Windows 回落）

        Windows 用 `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`（不需要控制台）：

        * 拿到有效 handle → 进程存在 → 活着；
        * `last_error == 87`（`ERROR_INVALID_PARAMETER`）→ 确知该 pid 不存在 → 已死；
        * 其它错误 → 说不准，按活着处理（保守）。

        非 Windows 回落 `os.kill(pid, 0)`：只有 `ProcessLookupError` 才算"确知已死"。

        "说不准就当活着"是刻意的：误判"死了"会让正在跑的任务失去并发保护与停止入口，
        而误判"活着"最多让一条过期记录多留一会儿 —— 它由 `_fresh()` 的心跳 TTL 兜底回收
        （死进程不再续期，过期即不再算在跑）。
        """
        try:
            value = int(pid)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        if value <= 0:
            return False

        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, value)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            # 87 = ERROR_INVALID_PARAMETER：该 pid 根本不存在
            if ctypes.get_last_error() == 87:
                return False
            return True          # 其它错误：说不准 → 保守当活着

        try:
            os.kill(value, 0)
        except ProcessLookupError:
            return False             # 唯一"确知已死"的信号
        except PermissionError:
            return True              # 存在但不属于我
        except OSError:
            return True              # 探活失败 ≠ 已死
        return True

    def _fresh(self, rec: Dict[str, object]) -> bool:
        """心跳是否新鲜（未过期）且那个进程还活着。

        除心跳 TTL 外还比对 `pid`：心跳只证明"文件最后一次被写过"，而进程被强杀时
        心跳会冻结在死前那一刻，看起来一直是新鲜的 —— 于是残留条目要等满 TTL
        （15 分钟）才被判过期。这 15 分钟里界面对那个会话一直显示"停止"、
        `/api/chat/send` 一直 409，用户被卡在一个根本不存在的“在跑”任务上。
        文件里记了 `pid`，读它来做这层判断是零成本的。
        """
        try:
            beat = float(rec.get("heartbeat") or 0.0)
        except (TypeError, ValueError):
            return False
        if (time.time() - beat) > self._ttl:
            return False
        # pid 缺失或不是本机可判定的形态时不额外否决。
        if "pid" in rec and not self._pid_alive(rec.get("pid")):
            return False
        return True

    def _write(self, fp: Path, rec: Dict[str, object]) -> bool:
        try:
            fp.parent.mkdir(parents=True, exist_ok=True)
            # 原子落地：先写临时文件再替换，避免读到半截 JSON。
            tmp = fp.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, fp)
            return True
        except OSError:
            return False

    def _drop(self, fp: Path) -> None:
        try:
            # `missing_ok`：并发下别的请求可能已经清掉了这条残留，
            # 那不是错误（删一个不存在的东西 = 它已经不在跑了）。
            fp.unlink(missing_ok=True)
        except OSError:
            pass

    # ── 接口 ────────────────────────────────────────────

    def claim(self, cid: str, run_id: str) -> bool:
        key = str(cid or "").strip()
        fp = self._file(key)
        if fp is None:
            return False
        now = time.time()
        rec: Dict[str, object] = {
            "run_id": str(run_id or ""),
            "pid": os.getpid(),
            "started_at": now,
            "heartbeat": now,
        }
        with self._lock:
            old = self._read(fp) if fp.is_file() else None
            if old is not None and self._fresh(old):
                return False          # 有人在跑（心跳未过期）
            if old is not None:
                self._drop(fp)        # 过期残留：清掉再占
            if not self._write(fp, rec):
                return False
            self._last_touch[key] = now
            return True

    def release(self, cid: str) -> None:
        key = str(cid or "").strip()
        fp = self._file(key)
        if fp is None:
            return
        with self._lock:
            self._drop(fp)
            self._last_touch.pop(key, None)

    def renew(self, cid: str, run_id: str) -> bool:
        key = str(cid or "").strip()
        fp = self._file(key)
        if fp is None:
            return False
        now = time.time()
        with self._lock:
            rec = self._read(fp) if fp.is_file() else None
            if rec is None or not self._fresh(rec):
                return False          # 没有有效占位：不凭空占
            rec["run_id"] = str(run_id or "")
            rec["heartbeat"] = now
            if not self._write(fp, rec):
                return False
            self._last_touch[key] = now
            return True

    def touch(self, cid: str) -> None:
        key = str(cid or "").strip()
        fp = self._file(key)
        if fp is None:
            return
        now = time.time()
        with self._lock:
            last = self._last_touch.get(key, 0.0)
            # 限流的上界必须跟着 TTL 走：写死 30 秒的话，一旦 TTL 配得比它短
            # （短租约场景会如此），强制续心跳会被限流掉、条目照样过期。
            # 取 TTL 的一半，保证"至少能在过期前写进去一次"。
            floor = max(0.0, min(_HEARTBEAT_MIN_INTERVAL, self._ttl / 2.0))
            if now - last < floor and fp.is_file():
                return                # 限流：避免把磁盘写爆
            rec = self._read(fp) if fp.is_file() else None
            if rec is None:
                return
            rec["heartbeat"] = now
            if self._write(fp, rec):
                self._last_touch[key] = now

    def running(self, cid: str) -> bool:
        key = str(cid or "").strip()
        fp = self._file(key)
        if fp is None or not fp.is_file():
            return False
        with self._lock:
            rec = self._read(fp)
            if rec is None:
                self._drop(fp)        # 坏文件：当作没在跑，一并清掉
                return False
            if not self._fresh(rec):
                self._drop(fp)        # 过期残留：自愈
                return False
            self.touch(key)           # 读取时续心跳（长任务不被误判为结束）
            return True

    def running_cids(self) -> List[str]:
        if self._dir is None or not self._dir.is_dir():
            return []
        out: List[str] = []
        for fp in self._dir.glob("*.json"):
            cid = fp.stem
            if self.running(cid):
                out.append(cid)
        return sorted(out)

    def active_run_id(self, cid: str) -> str:
        key = str(cid or "").strip()
        fp = self._file(key)
        if fp is None or not fp.is_file():
            return ""
        with self._lock:
            rec = self._read(fp)
            if rec is None or not self._fresh(rec):
                return ""
            return str(rec.get("run_id") or "")


def build_run_registry(
    directory: Optional[Path] = None,
    *,
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
) -> RunRegistry:
    """按目录可用性选择实现：有目录 → 落盘；没有 → 纯内存。

    调用方（装配层）只拿 `RunRegistry`，不知道也不需要知道是哪个实现 ——
    更换后端只改这一处。
    """
    if directory is None:
        return InMemoryRunRegistry()
    return FileRunRegistry(directory, ttl_seconds=ttl_seconds)
