# -*- coding: utf-8 -*-
"""更新 helper：在应用退出后切换版本并做健康检查。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from agent.core.error_report import report_error
from agent.update.install import apply_staged, health_check, install_root, rollback_pointer
from agent.update.state import read_state, write_state


def main() -> int:
    root = install_root()
    state_path = root / "updates" / "apply.json"
    if not state_path.is_file():
        return 0
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        version = str(state.get("version") or "")
        staging = Path(str(state.get("staging") or ""))
        if not version or not staging:
            raise ValueError("apply state 缺少 version/staging")
        target = apply_staged(root, staging, version)
        if not health_check(target):
            previous = read_state(root).get("from_version", "")
            rollback_pointer(root)
            write_state(root, "rolled_back", previous, version, "health_check_failed")
            return 2
        write_state(root, "healthy", read_state(root).get("from_version", ""), version)
        return 0
    except Exception as exc:
        report_error("agent.update.apply", exc)
        print(f"[update] 应用失败：{exc}", file=sys.stderr)
        try:
            rollback_pointer(root)
        except Exception as rollback:
            print(f"[update] 回滚失败：{rollback}", file=sys.stderr)
        return 1
    finally:
        try:
            state_path.unlink()
        except OSError as exc:
            report_error("agent.update.apply.cleanup", exc)


if __name__ == "__main__":
    raise SystemExit(main())
