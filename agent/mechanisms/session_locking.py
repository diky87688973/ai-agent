# -*- coding: utf-8 -*-
"""跨进程排它锁：按目标文件加锁，争用超时就失败。

同一会话的"记偏移 → 追加 → 回滚"是读改写，进程内锁挡不住别的进程
（4 进程并发写会丢 39/100 行，且不报错）。
"""
from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from agent.core.error_report import report_error

try:                                     # Windows
    import msvcrt as _msvcrt
except ImportError:                      # POSIX
    _msvcrt = None
try:
    import fcntl as _fcntl
except ImportError:
    _fcntl = None

#: 区分「环境限制」与「争用超时」的哨兵文本（见 `cross_process_lock`）
_NO_LOCK_MECHANISM = "无法加跨进程锁"


@contextmanager
def cross_process_lock(path: Path):
    """按文件加跨进程排它锁；争用超时就抛错（不降级无锁写）。

    Windows 上 `LK_LOCK` 是「每秒重试、最多 10 次」，9 秒后抛 `Errno 36`；
    若把它当成「锁不可用」而打印警告后继续写，就在最需要锁的时候回到了
    会丢行的形态（16 行丢 1 行 + 1 坏行，且子进程退出码仍是 0）。

    语义：
      · 用 `LK_NBLCK`（非阻塞）自己轮询，不设那 10 次上限；
      · 超时（默认 30s，`AI_AGENT_LOCK_TIMEOUT` 可调）→ 抛错，让数据走待重试队列，
        「同一事实只写一次」的承诺才不会被「无锁写」破坏；
      · 只有「本平台没有任何锁机制」才留痕降级（环境限制，不是争用）。

    锁加在 `<文件>.lock` 上：这个文件故意不删 —— 删了会和别的进程的"已打开句柄"
    形成"锁的是已删除文件"的经典竞态。它是零字节的，代价可以忽略。

    ⚠️ 句柄必须每趟开关：句柄不关会让 Windows 下 `TemporaryDirectory.cleanup()`
    报 `PermissionError [WinError 32]`（文件仍被占用），而本项目大量测试依赖临时目录。
    每趟开关的开销约 +2.5ms/条、一个回合 ~+22ms —— 相对回合本身（秒级）可忽略。
    """
    lock_path = path.with_suffix(path.suffix + ".lock")
    fh = None
    locked = False
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock_path, "a+b")
        if _msvcrt is not None:
            deadline = time.monotonic() + _lock_timeout()
            while True:
                try:
                    _msvcrt.locking(fh.fileno(), _msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.05)
        elif _fcntl is not None:
            _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
            locked = True
        else:
            # 两个机制都没有时必须显式判失败，走 except 的留痕路径：
            # 两个分支都不进会让 `locked` 静默保持 False，
            # "跨进程保护已经没了"没人知道。降级可以，静默不行。
            raise RuntimeError(_NO_LOCK_MECHANISM)
    except Exception as exc:
        try:
            if fh is not None:
                fh.close()
        except Exception as exc:
            # 旁路，刻意吞掉：关不掉也不该顶掉原始异常。
            report_error("agent.mechanisms.session_locking.cross_process_lock", exc)
        fh = None
        if _NO_LOCK_MECHANISM in str(exc):
            # 环境限制（没有任何锁机制）→ 留痕降级。
            print(f"[store] 跨进程锁不可用（降级为进程内锁）：{type(exc).__name__}: {exc}",
                  file=sys.stderr, flush=True)
            locked = False
        else:
            # 争用超时 → 不许写。抛出去让数据进待重试队列。
            raise
    try:
        yield locked
    finally:
        if fh is not None:
            try:
                if locked and _msvcrt is not None:
                    fh.seek(0)
                    _msvcrt.locking(fh.fileno(), _msvcrt.LK_UNLCK, 1)
                elif locked and _fcntl is not None:
                    _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
            except Exception as exc:
                # 旁路，刻意吞掉：解锁失败由 close() 兜底（进程退出也会释放）。
                report_error("agent.mechanisms.session_locking.cross_process_lock", exc)
            try:
                fh.close()
            except Exception as exc:
                # 旁路，刻意吞掉：关闭失败不影响已完成的写入。
                report_error("agent.mechanisms.session_locking.cross_process_lock", exc)


def _lock_timeout() -> float:
    """跨进程锁的争用等待上限（秒）。默认 30s；可用 `AI_AGENT_LOCK_TIMEOUT` 覆盖。"""
    try:
        return max(1.0, float(os.environ.get("AI_AGENT_LOCK_TIMEOUT", "30")))
    except (TypeError, ValueError):
        return 30.0
