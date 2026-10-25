# -*- coding: utf-8 -*-
"""启动恢复：未完成切换时校验并回滚。"""
from __future__ import annotations

from agent.update.install import cleanup_after_success, health_check, install_root, restore_backup
from agent.update.logs import log_event
from agent.update.state import clear_state, read_state, write_state


def main() -> int:
    root = install_root()
    state = read_state(root)
    phase = state.get("phase", "")
    log_event(root, "recover_start", phase=phase)
    if phase == "switching":
        previous = state.get("from_version", "")
        if health_check(root):
            write_state(root, "healthy", previous,
                        state.get("to_version", ""), "recovered")
        else:
            restore_backup(root, previous)
            write_state(root, "rolled_back", previous,
                        state.get("to_version", ""), "recovery_failed")
            cleanup_after_success(root, state.get("to_version", ""))
            log_event(root, "recover_rolled_back", level="warn")
    elif phase in ("healthy", "rolled_back"):
        clear_state(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
