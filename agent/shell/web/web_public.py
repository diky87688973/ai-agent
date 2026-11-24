"""认证后的公共插件挂载与工作区文件响应。"""
from __future__ import annotations

import mimetypes
from contextlib import nullcontext
from urllib.parse import unquote

from agent.capabilities.http_mounts import build_http_mounts
from agent.common.http_contract import FileAccessError, FileResponse, HttpRequest, JsonResponse
from agent.core.error_report import report_error
from agent.shell.fspaths import default_fs_roots
from agent.shell.web.file_access import LocalFileAccess


class PublicRoutes:
    def _file_access(self):
        roots = ([self.shell.media_root] if self.shell.media_root
                 else (self.shell.fs_roots or default_fs_roots()))
        return LocalFileAccess(roots, self.shell.workspace_root)

    def _public_http(self, method, path=None, query=None, files=None):
        lifecycle = getattr(getattr(getattr(self.shell, "app", None), "context", None), "slot_lifecycle", None)
        with lifecycle.turn() if lifecycle is not None else nullcontext(None) as snapshot:
            if snapshot is None:
                return False
            with self.shell._lock:
                cached = getattr(self.shell, "_http_mount_cache", None)
                if cached is None or cached[0] is not snapshot:
                    cached = (snapshot, build_http_mounts(snapshot.config, snapshot.built))
                    self.shell._http_mount_cache = cached
            mount = cached[1].get(path or self._path())
            if mount is None:
                return False
            if method not in mount.methods:
                result = JsonResponse({"error": "method_not_allowed"}, 405,
                                      {"Allow": ", ".join(sorted(mount.methods))})
            elif method not in mount.handlers:
                result = JsonResponse({"error": "handler_unavailable"}, 503)
            else:
                request = HttpRequest(method, path or self._path(),
                                      self._query() if query is None else query,
                                      {key.lower(): value for key, value in self.headers.items()},
                                      files or self._file_access())
                try:
                    result = mount.handlers[method](request)
                except FileAccessError as exc:
                    result = JsonResponse({"error": exc.code}, exc.status)
                except Exception as exc:
                    report_error("http.public_handler", exc, path=request.path)
                    result = JsonResponse({"error": "file_handler_failed"}, 500)
            self.shell.file_transfers.send(self, result)
            return True

    def _workspace_file(self, path):
        root = self.shell.workspace_root
        if root is None:
            self._json(404, {"error": "workspace 未配置"})
            return
        files = LocalFileAccess([root], root)
        try:
            file = files.open(unquote(path[len("/workspace/"):]))
        except FileAccessError as exc:
            self._json(exc.status, {"error": exc.code})
            return
        mime = mimetypes.guess_type(str(file.path))[0] or "application/octet-stream"
        if mime.startswith(("image/", "audio/", "video/")) and mime != "image/svg+xml":
            file.close()
            if not self._public_http(self.command, "/api/media", {"path": str(file.path)}, files):
                self._json(503, {"error": "media_unavailable"})
            return
        if mime.startswith("text/") or mime in {"image/svg+xml", "application/xhtml+xml",
                                               "application/xml", "application/javascript",
                                               "application/ecmascript"}:
            mime = "text/plain; charset=utf-8"
        self.shell.file_transfers.send(self, FileResponse(file, mime))
