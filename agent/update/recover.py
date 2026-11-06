# -*- coding: utf-8 -*-
"""启动恢复：未完成切换时校验并回滚。"""
from __future__ import annotations

from agent.common.status import UPDATE_HEALTHY, UPDATE_ROLLED_BACK, UPDATE_SWITCHING
from agent.core.error_report import report_error
from agent.update.install import (
    cleanup_after_success,
    health_check,
    install_root,
    restore_backup,
)
from agent.update.logs import log_event
from agent.update.processes import cleanup_launcher_archives
from agent.update.state import clear_state, read_state, write_state


def main() -> int:
    root = install_root()
    try:
        state = read_state(root)
        phase = state.get("phase", "")
        log_event(root, "recover_start", phase=phase)
        if phase == UPDATE_SWITCHING:
            previous = state.get("from_version", "")
            installed = (root / "VERSION").read_text(encoding="utf-8").strip()
            if installed == state.get("to_version", "") and health_check(root):
                write_state(root, UPDATE_HEALTHY, previous,
                            state.get("to_version", ""), "recovered")
            else:
                if not restore_backup(root, previous):
                    raise RuntimeError(f"无法恢复更新备份：{previous}")
                write_state(root, UPDATE_ROLLED_BACK, previous,
                            state.get("to_version", ""), "recovery_failed")
                cleanup_after_success(root, state.get("to_version", ""))
                log_event(root, "recover_rolled_back", level="warn")
        elif phase in (UPDATE_HEALTHY, UPDATE_ROLLED_BACK):
            clear_state(root)
        removed = cleanup_launcher_archives(root, attempts=1)
        if removed:
            log_event(root, "launcher_archives_cleaned",
                      source="recover", count=len(removed))
        return 0
    except Exception as exc:
        log_event(root, "recover_failed", level="error",
                  error=f"{type(exc).__name__}: {exc}")
        report_error("agent.update.recover", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
