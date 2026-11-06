# -*- coding: utf-8 -*-
"""更新 helper：在应用退出后切换版本并做健康检查。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from agent.common.status import UPDATE_HEALTHY, UPDATE_ROLLED_BACK
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


def _rollback(root: Path, version: str, detail: str) -> None:
    previous = read_state(root).get("from_version", "")
    if not previous or not restore_backup(root, previous):
        raise RuntimeError(f"无法恢复更新备份：{previous or '缺少原版本'}")
    write_state(root, UPDATE_ROLLED_BACK, previous, version, detail)


def _cleanup_request(root: Path, state_path: Path, version: str) -> None:
    try:
        state_path.unlink(missing_ok=True)
    except OSError as exc:
        log_event(root, "apply_state_cleanup_failed", level="error", error=str(exc))
        report_error("agent.update.apply.cleanup", exc)
    try:
        cleanup_after_success(root, version)
    except Exception as exc:
        log_event(root, "apply_staging_cleanup_failed", level="error", error=str(exc))
        report_error("agent.update.apply.cleanup_staging", exc)


def _finish_launcher(root: Path) -> None:
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


def main() -> int:
    parser_root = install_root()
    state_path = None
    for index, arg in enumerate(sys.argv):
        if arg == "--root" and index + 1 < len(sys.argv):
            parser_root = Path(sys.argv[index + 1])
        if arg == "--state" and index + 1 < len(sys.argv):
            state_path = Path(sys.argv[index + 1])
    root = parser_root
    if state_path is None:
        state_path = root / "updates" / "apply.json"
    if not state_path.is_file():
        return 0
    state = {}
    owns_update = False
    cleanup_ready = False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        version = str(state.get("version") or "")
        staging_text = str(state.get("staging") or "").strip()
        if not version or not staging_text:
            raise ValueError("apply state 缺少 version/staging")
        staging = Path(staging_text)
        helper = staging / "payload" / "agent" / "update" / "apply.py"
        if Path(__file__).resolve() != helper.resolve():
            log_event(root, "bootstrap_start", version=version, staging=str(staging))
            new_code = _run_new_updater(root, state_path, staging)
            if new_code >= 0:
                return new_code
        owns_update = True
        log_event(root, "apply_start", version=version, staging=str(staging))
        target = apply_staged(root, staging, version)
        previous = read_state(root).get("from_version", "")
        if not health_check(target):
            log_event(root, "apply_health_failed", level="error", version=version)
            _rollback(root, version, "health_check_failed")
            cleanup_ready = True
            return 2
        _finish_launcher(root)
        write_state(root, UPDATE_HEALTHY, previous, version)
        cleanup_ready = True
        log_event(root, "apply_success", version=version)
        return 0
    except Exception as exc:
        log_event(root, "apply_failed", level="error", error=str(exc))
        report_error("agent.update.apply", exc)
        print(f"[update] 应用失败：{exc}", file=sys.stderr)
        if owns_update:
            try:
                _rollback(root, str(state.get("version") or ""), "apply_failed")
                cleanup_ready = True
            except Exception as rollback:
                log_event(root, "apply_rollback_failed", level="error", error=str(rollback))
                report_error("agent.update.apply.rollback", rollback)
                print(f"[update] 回滚失败：{rollback}", file=sys.stderr)
        return 1
    finally:
        if owns_update and cleanup_ready:
            _cleanup_request(root, state_path, str(state.get("version") or ""))


if __name__ == "__main__":
    raise SystemExit(main())
