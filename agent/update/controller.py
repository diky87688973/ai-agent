# -*- coding: utf-8 -*-
"""更新检查、下载暂存与重启请求。"""
from __future__ import annotations

import json
import os
import signal
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from agent.core.error_report import report_error
from agent.update.checker import check, manifest_url
from agent.update.install import install_root, payload_root
from agent.update.stage import stage_package
from agent.update.version import is_dev_checkout


class UpdateController:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root is not None else install_root()
        self.updates = self.root / "updates"
        self._lock = threading.Lock()
        self._manifest = None
        self._status: Dict[str, Any] = {
            "available": False,
            "current": "",
            "remote": "",
            "channel": "",
            "detail": "idle",
            "staged": False,
            "version": "",
        }

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def check(self) -> Dict[str, Any]:
        with self._lock:
            if is_dev_checkout(self.root):
                self._manifest = None
                self._status.update({"available": False, "detail": "dev_checkout"})
                return dict(self._status)
            result = check(payload_root(self.root), manifest_url())
            self._manifest = result.manifest if result.available else None
            staged = bool(result.manifest and (self.updates / "staging" / str(result.manifest.version) / ".ready").is_file())
            self._status = {
                "available": result.available,
                "current": result.current,
                "remote": result.remote,
                "channel": result.channel,
                "detail": result.detail,
                "staged": staged,
                "version": result.remote if result.available else "",
            }
            return dict(self._status)

    def download(self) -> Dict[str, Any]:
        with self._lock:
            if self._manifest is None:
                raise ValueError("没有可下载的更新")
            path = stage_package(
                self._manifest,
                manifest_url=manifest_url(),
                updates_dir=self.updates,
            )
            self._status.update({"staged": True, "detail": "staged", "staging": str(path)})
            return dict(self._status)

    def apply(self) -> Dict[str, Any]:
        with self._lock:
            if not self._status.get("staged") or self._manifest is None:
                raise ValueError("更新尚未下载完成")
            version = str(self._manifest.version)
            staging = self.updates / "staging" / version
            self.updates.mkdir(parents=True, exist_ok=True)
            (self.updates / "apply.json").write_text(
                json.dumps({"version": version, "staging": str(staging)},
                           ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            self._status.update({"detail": "restarting"})
        def _finish() -> None:
            if os.environ.get("AI_AGENT_GUI") == "1":
                parent = os.getppid()
                try:
                    if parent > 0 and parent != os.getpid():
                        os.kill(parent, signal.SIGTERM)
                except OSError as exc:
                    report_error("agent.update.controller.stop_gui", exc)
            os._exit(0)

        threading.Timer(0.6, _finish).start()
        return {"ok": True, "version": version}
