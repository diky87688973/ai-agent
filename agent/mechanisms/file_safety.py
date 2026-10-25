# -*- coding: utf-8 -*-
"""文件安全设施（写路径配套）：版本化备份 + 回收目录。

- `FileBackups`：真写覆盖前把原内容留档。按被测文件分组——

      <root>/<路径哈希>/<版本名>/original         原文件字节
      <root>/<路径哈希>/<版本名>/metadata.json    mod_id / path / time / …

  `<路径哈希>` = 文件绝对路径的 MD5 前 16 位。同一个文件的所有版本都在它下面，
  所以"某文件有哪些可回滚版本"就是读一个目录，不必遍历全部备份。
  用哈希而不是文件名：文件名里的中文、空格、超长都会被净化成一串 `_`，
  既没法区分不同文件，也读不出是什么。

  `<版本名>` 是 `YYYYMMDD_HHMMSS_mmm_NNNN_随机短段`（见 `_version_dir_name`）：
  日期在最前，按年龄清理只需解析它，不需要任何外部记账；也不用中心索引 ——
  索引是一处必须与备份保持一致的状态，坏了会让全部备份不可用，
  而每个版本自带的 `metadata.json` 不会。

- `Recycle`：删除类操作不真删 —— 移入 `<root>/<YYYYMMDD>/<原名>_时间戳_随机短段`，
  文件与目录均可移入，可人工取回。

纪律：本模块只做"保全动作"，不做门控决策；写盘流程由工具层 + QualityGate 承载。
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from agent.core.error_report import report_error

_LOCK = threading.Lock()

#: 版本目录名：`YYYYMMDD_HHMMSS_mmm_NNNN_随机短段`。日期必须在最前，供按年龄清理解析。
#: 定序靠时间戳 + 同毫秒序号：时间戳只到毫秒，同一毫秒内的多次改动只看时间戳分不出
#: 先后，而随机段与先后无关 —— 拿它定序会让 `file_undo list` 顺序错乱、
#: `undo` 挑错版本。目录名按字典序倒序即新→旧，所以序号必须零填充等宽。
_VERSION_DIR_RE = re.compile(r"^(\d{8})_(\d{6})_(\d{3})_\d{4}_[0-9a-z]{4}$")

#: 备份目录内的固定文件名
ORIGINAL_NAME = "original"
METADATA_NAME = "metadata.json"

#: `prune()` 的缺省保留天数。配置项 `[agent] backup_retention_days` 覆盖它
#: （见 `agent.config.get_backup_retention_days`）。
DEFAULT_RETENTION_DAYS = 7

#: 路径哈希取 MD5 十六进制的长度。16 位足够区分（冲突概率可忽略），目录名也短。
PATH_HASH_LEN = 16

#: metadata 里 `diff_text` 的字符上限。备份目录不该被一个巨 diff 撑大。
DIFF_TEXT_MAX_CHARS = 2000


def _clip_diff(text: Any) -> str:
    """截断 diff 并标记它被截断了 —— 静默截断会被读成"改动就这么点"。
    """
    s = str(text or "")
    if len(s) <= DIFF_TEXT_MAX_CHARS:
        return s
    return s[:DIFF_TEXT_MAX_CHARS] + "…（已截断）"


def path_hash(path: Any) -> str:
    """文件绝对路径的 MD5 短码，用作该文件全部备份的目录名。

    用路径哈希而不是文件名：文件名可能含中文、空格、`.`、超长，净化后互相分不开。
    """
    raw = str(Path(str(path)).resolve()).replace("\\", "/")
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:PATH_HASH_LEN]


def _stamp() -> str:
    """`YYYYMMDD_HHMMSS_mmm` —— 毫秒级时间戳。

    `time.strftime` 没有毫秒指令，用 `time.time()` 的小数部分取三位。
    """
    now = time.time()
    return f"{time.strftime('%Y%m%d_%H%M%S', time.localtime(now))}_{int(now % 1 * 1000):03d}"


#: 同一毫秒内的自增序号，避免同毫秒的版本排序不确定。
_seq_lock = threading.Lock()
_seq_stamp = ""
_seq_value = 0


def _next_seq(stamp: str) -> int:
    """同一毫秒内递增的序号；毫秒一变就归零。

    版本目录按名字倒序排出新→旧，所以名字里必须有能定序的字段。
    时间戳只到毫秒，同一毫秒内发生的多次改动就分不出先后 ——
    随机短段与先后无关，拿它定序会让 `list` 顺序错乱、`undo` 挑错版本。
    """
    global _seq_stamp, _seq_value
    with _seq_lock:
        if stamp != _seq_stamp:
            _seq_stamp = stamp
            _seq_value = 0
        else:
            _seq_value += 1
        return _seq_value


def _version_dir_name() -> str:
    """新版本目录名：`YYYYMMDD_HHMMSS_mmm_NNNN_随机短段`。

    `NNNN` 是同毫秒内的序号（定序用），随机短段只用来避免极端情况下撞名。
    """
    stamp = _stamp()
    return f"{stamp}_{_next_seq(stamp):04d}_{uuid4().hex[:4]}"


def _version_time_text(name: str) -> str:
    """从版本目录名反解可读时间（`YYYY-MM-DD HH:MM:SS`）；格式不符返回空串。"""
    m = _VERSION_DIR_RE.match(str(name or ""))
    if not m:
        return ""
    d, t = m.group(1), m.group(2)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}:{t[4:6]}"

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FileBackups:
    """版本化备份库：按文件路径哈希分组，每个版本自描述，无中心索引。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    # ── 路径 ──────────────────────────────────────────────

    def group_dir(self, path: Any) -> Path:
        """某文件的全部备份所在目录（不创建）。"""
        return self.root / path_hash(path)

    def _version_dirs(self, path: Any) -> List[Path]:
        """某文件的版本目录（名称倒序 = 新→旧）。"""
        group = self.group_dir(path)
        if not group.is_dir():
            return []
        entries = list(group.iterdir())
        return sorted((d for d in entries if d.is_dir()), key=lambda d: d.name, reverse=True)

    def _meta_of(self, version_dir: Path) -> Optional[Dict[str, Any]]:
        """读某个版本目录的 metadata.json；缺失或损坏返回 None。"""
        fp = version_dir / METADATA_NAME
        if not fp.is_file():
            return None
        try:
            obj = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return obj if isinstance(obj, dict) else None

    # ── 写 ────────────────────────────────────────────────

    def create(
        self,
        path: Path,
        *,
        mode: str = "",
        encoding: str = "utf-8",
        diff_text: str = "",
    ) -> Optional[str]:
        """把 `path` 当前内容留档；文件不存在返回 None，成功返回 mod_id。

        `mod_id` 形如 `<路径哈希>:<版本目录名>`。`mode` / `diff_text` 供 `file_undo` 展示。
        """
        target = Path(path)
        if not target.is_file():
            return None
        data = target.read_bytes()

        group = self.group_dir(target)
        ver = _version_dir_name()
        ver_dir = group / ver
        try:
            ver_dir.mkdir(parents=True, exist_ok=True)
            (ver_dir / ORIGINAL_NAME).write_bytes(data)
            metadata = {
                "mod_id": f"{group.name}:{ver}",
                "path": str(target.resolve()),
                # 键名是 `time`（`file_undo` 列历史时按这个名字读）
                "time": _version_time_text(ver) or time.strftime("%Y-%m-%d %H:%M:%S"),
                "bytes": len(data),
                "encoding": encoding,
                "original_sha256": _sha256(data),
                "mode": str(mode or ""),
                "diff_text": _clip_diff(diff_text),
            }
            with _LOCK:
                (ver_dir / METADATA_NAME).write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            return None
        return str(metadata["mod_id"])

    # ── 读 ────────────────────────────────────────────────

    def list_for(self, path: Path) -> List[Dict[str, Any]]:
        """某文件的历史备份（新→旧）。

        直接读该文件的哈希目录，逐个版本读 `metadata.json` —— 不遍历全部备份，
        也不按文件名推前缀（文件名净化后会互相分不开）。
        """
        out: List[Dict[str, Any]] = []
        for ver_dir in self._version_dirs(path):
            meta = self._meta_of(ver_dir)
            if meta is not None:
                out.append(meta)
        return out

    def meta(self, mod_id: str) -> Optional[Dict[str, Any]]:
        """按 `mod_id` 查版本记录；格式不符或不存在返回 None。"""
        parts = str(mod_id or "").split(":")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return None
        return self._meta_of(self.root / parts[0] / parts[1])

    def read(self, mod_id: str) -> Optional[bytes]:
        """读回某版本的原内容；目录或文件缺失返回 None。"""
        parts = str(mod_id or "").split(":")
        if len(parts) != 2:
            return None
        fp = self.root / parts[0] / parts[1] / ORIGINAL_NAME
        if not fp.is_file():
            return None
        return fp.read_bytes()

    # ── 维护 ──────────────────────────────────────────────

    def prune(self, retention_days: int = DEFAULT_RETENTION_DAYS) -> Tuple[int, int]:
        """删除 `retention_days` 天前的版本；返回 (删除版本数, 保留版本数)。

        年龄取自版本目录名最前面的日期段，不依赖任何外部记账。
        名字不含合法日期的目录一律不动（可能是人工放进来的东西）。
        某文件的版本全部删光后，它的哈希目录一并移除。
        """
        if not self.root.is_dir():
            return 0, 0
        try:
            cutoff = time.strftime(
                "%Y%m%d", time.localtime(time.time() - max(0, int(retention_days)) * 86400))
        except (OSError, ValueError):
            return 0, 0
        removed = kept = 0
        try:
            groups = list(self.root.iterdir())
        except OSError:
            return 0, 0
        for group in groups:
            if not group.is_dir():
                continue
            # 读不到的组跳过：清理是尽力而为的维护动作，不该因一个坏组让启动失败
            try:
                versions = list(group.iterdir())
            except OSError as exc:
                report_error("agent.mechanisms.file_safety.FileBackups.prune", exc)
                continue
            for ver in versions:
                if not ver.is_dir():
                    continue
                m = _VERSION_DIR_RE.match(ver.name)
                if m is None:
                    kept += 1
                    continue
                if m.group(1) < cutoff:
                    try:
                        shutil.rmtree(ver)
                    except OSError:
                        kept += 1
                        continue
                    removed += 1
                else:
                    kept += 1
            # 空目录（版本被删光）一并清理，不留空壳
            try:
                if not any(group.iterdir()):
                    group.rmdir()
            # 删不掉就算了：留个空目录无害，不值得让清理报错
            except OSError as exc:
                report_error("agent.mechanisms.file_safety.FileBackups.prune", exc)
        return removed, kept


class Recycle:
    """回收目录：target_for（计算回收目标）/ move（移入）。"""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def target_for(self, path: Path) -> Path:
        """回收目标路径（时间戳 + 随机短段；不执行移动）。"""
        src = Path(path)
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", src.name)[:30] or "file"
        return self.root / time.strftime("%Y%m%d") / f"{safe}_{_version_dir_name()}"

    def move(self, path: Path) -> Path:
        """把文件 / 目录移入回收目录；返回新路径。"""
        src = Path(path)
        dest = self.target_for(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        return dest
