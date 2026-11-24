"""媒体 HTTP 处理器；以 MIME 类别限定内容，不依赖网页查看器。"""
from __future__ import annotations

import mimetypes
from datetime import datetime, timezone

from agent.common.http_contract import FileResponse, JsonResponse


def _media(file):
    mime = mimetypes.guess_type(str(file.path))[0] or "application/octet-stream"
    kind = mime.partition("/")[0]
    if mime == "image/svg+xml" or kind not in {"image", "audio", "video"}:
        return None
    return kind, mime


def make_content(ctx):
    def content(request):
        file = request.files.open(request.query.get("path", ""))
        try:
            media = _media(file)
            if media is None:
                file.close()
                return JsonResponse({"error": "unsupported_media_type"}, 415)
            return FileResponse(file, media[1])
        except Exception:
            file.close()
            raise
    return content


def make_info(ctx):
    def info(request):
        file = request.files.open(request.query.get("path", ""))
        try:
            media = _media(file)
            if media is None:
                return JsonResponse({"error": "unsupported_media_type"}, 415)
            return JsonResponse({"version": 1, "name": file.path.name, "path": str(file.path),
                                 "kind": media[0], "mime": media[1], "size_bytes": file.stat.st_size,
                                 "modified_at": datetime.fromtimestamp(
                                     file.stat.st_mtime, timezone.utc).isoformat()})
        finally:
            file.close()
    return info
