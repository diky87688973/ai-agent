# -*- coding: utf-8 -*-
"""更新 helper：在应用退出后切换版本并做健康检查。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from agent.core.error_report import report_error
from agent.update.install import (
    apply_staged,
    cleanup_after_success,
    health_check,
    install_root,
    restore_backup,
)
from agent.update.logs import log_event
from agent.update.processes import (
    cleanup_launcher_archives,
    launch_after_update,
    stop_old_launcher,
)
from agent.update.state import read_state, write_state


def _run_new_updater(root: Path, state_path: Path, staging: Path) -> int:
    helper = staging / "payload" / "agent" / "update" / "apply.py"
    if not helper.is_file():
        helper = staging / "agent" / "update" / "apply.py"
    if not helper.is_file():
        return -1
    payload = helper.parents[2]
    env = dict(os.environ)
    env["AI_AGENT_INSTALL_ROOT"] = str(root)
    result = subprocess.run(
        [sys.executable, "-m", "agent.update.apply", "--root", str(root),
         "--state", str(state_path)],
        cwd=str(payload),
        env=env,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    return int(result.returncode)


def main() -> int:
    parser_root = install_root()
    for index, arg in enumerate(sys.argv):
        if arg == "--root" and index + 1 < len(sys.argv):
            parser_root = Path(sys.argv[index + 1])
        if arg == "--state" and index + 1 < len(sys.argv):
            state_path = Path(sys.argv[index + 1])
    root = parser_root
    if "state_path" not in locals():
        state_path = root / "updates" / "apply.json"
    if not state_path.is_file():
        return 0
    state = {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        version = str(state.get("version") or "")
        staging = Path(str(state.get("staging") or ""))
        if not version or not staging:
            raise ValueError("apply state 缺少 version/staging")
        helper = staging / "payload" / "agent" / "update" / "apply.py"
        if Path(__file__).resolve() != helper.resolve():
            log_event(root, "bootstrap_start", version=version, staging=str(staging))
            new_code = _run_new_updater(root, state_path, staging)
            if new_code >= 0:
                return new_code
        log_event(root, "apply_start", version=version, staging=str(staging))
        target = apply_staged(root, staging, version)
        previous = read_state(root).get("from_version", "")
        if not health_check(target):
            log_event(root, "apply_health_failed", level="error", version=version)
            restore_backup(root, previous)
            write_state(root, "rolled_back", previous, version, "health_check_failed")
            return 2
        cleanup_after_success(root, version)
        try:
            state_path.unlink()
        except OSError as exc:
            log_event(root, "apply_state_cleanup_failed", level="error", error=str(exc))
            write_state(root, "healthy", previous, version)
            return 0
        killed = stop_old_launcher(root)
        removed = cleanup_launcher_archives(root)
        if removed:
            log_event(root, "launcher_archives_cleaned", count=len(removed))
        remaining = list((root / "updates" / "launcher").glob("agent-gui.exe.old-*"))
        if remaining:
            log_event(root, "launcher_archives_remaining", level="error", count=len(remaining))
        if killed:
            log_event(root, "old_launcher_stopped", pids=killed)
            if not launch_after_update(root):
                log_event(root, "relaunch_failed", level="error")
        write_state(root, "healthy", previous, version)
        log_event(root, "apply_success", version=version)
        return 0
    except Exception as exc:
        log_event(root, "apply_failed", level="error", error=str(exc))
        report_error("agent.update.apply", exc)
        print(f"[update] 应用失败：{exc}", file=sys.stderr)
        try:
            restore_backup(root, read_state(root).get("from_version", ""))
        except Exception as rollback:
            log_event(root, "apply_rollback_failed", level="error", error=str(rollback))
            report_error("agent.update.apply.rollback", rollback)
            print(f"[update] 回滚失败：{rollback}", file=sys.stderr)
        return 1
    finally:
        try:
            state_path.unlink()
        except OSError as exc:
            log_event(root, "apply_state_cleanup_failed", level="error", error=str(exc))
            report_error("agent.update.apply.cleanup", exc)
        try:
            cleanup_after_success(root, str(state.get("version") or ""))
        except Exception as exc:
            log_event(root, "apply_staging_cleanup_failed", level="error", error=str(exc))
            report_error("agent.update.apply.cleanup_staging", exc)


if __name__ == "__main__":
    raise SystemExit(main())
