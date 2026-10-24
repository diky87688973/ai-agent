# -*- coding: utf-8 -*-
"""启动恢复：未完成切换时校验并回滚。"""
from __future__ import annotations

from agent.update.install import health_check, install_root, payload_root, rollback_pointer
from agent.update.state import clear_state, read_state, write_state


def main() -> int:
    root = install_root()
    state = read_state(root)
    phase = state.get("phase", "")
    if phase == "switching":
        target = payload_root(root)
        if health_check(target):
            write_state(root, "healthy", state.get("from_version", ""),
                        state.get("to_version", ""), "recovered")
        else:
            rollback_pointer(root)
            write_state(root, "rolled_back", state.get("from_version", ""),
                        state.get("to_version", ""), "recovery_failed")
    elif phase in ("healthy", "rolled_back"):
        clear_state(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
