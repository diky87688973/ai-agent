# -*- coding: utf-8 -*-
"""读图工具：read_image —— 把本地图片作为图片附件回灌给模型。

输入侧的图片经 `image_embed.build_embed_parts` 进入请求；工具返回的图片此前进不去，
因为 `tool` 消息的 `content` 是字符串。本工具把图片挂到 `ToolResult.attachments`，
由 `SessionLogView` 翻成 `image_url` 块。

与 `image_ocr` 是两件独立的事：`image_ocr` 走 OCR 引擎产出文字，本工具把图交给
模型自己看。两者不互相替代，也不构成先后流程。

尺寸默认不缩放（`READ_MAX_SIDE_DEFAULT = 0`）：本工具用于按图定位坐标时，
缩放会使坐标静默失真。
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List

from agent.capabilities.registry import ToolPlugin
from agent.core.context import SERVICE_STORE, SERVICE_SUBAGENTS
from agent.core.event_name import TOOL_DONE, TURN_STARTED
from agent.core.image_embed import describe_image, shrink_image
from agent.core.input_attachments import attachment_id
from agent.core.session_scope import current_context, current_session_id
from agent.core.tool_call import ToolResult

#: 读图前的原始文件大小上限（字节）。0 = 不限。
#: 32 MiB 对应官方内联预算 48 MiB 的数量级，更可能是误指了非图片文件。
MAX_READ_BYTES = 32 * 1024 * 1024

#: 认得的图片格式（与官方一致：按文件内容判，不看扩展名）。
IMAGE_MIMES = ("image/png", "image/jpeg", "image/gif", "image/webp")

#: `read_image` 默认缩放上限。0 = 不缩放，保留原始尺寸。
#:
#: 用户附件走 `EMBED_MAX_SIDE`（800）以减小请求体；工具读图用于按图定位坐标时
#: 缩放会使坐标失真，且模型无法从图中得知自己看的是缩略图。
#: 返回值同时给出原图与实发尺寸供调用方换算。
#:
#: 显式传 `max_side` 时，用返回值里的 `width/height` 与
#: `sent_width/sent_height` 算比例。
READ_MAX_SIDE_DEFAULT = 0


class ImageReadTool(ToolPlugin):
    """读取本地图片并附给模型。"""

    name = "read_image"
    label = "看图"
    icon = "👁"
    description = (
        "读取本地图片或历史 attachment_id 并把图片本身交给模型查看（不是 OCR，不需要任何引擎）。"
        "适用于：描述图片内容、判断界面/图表/截图里的情况、核对颜色与布局与坐标、"
        "读取图中文字。"
        "支持 PNG / JPEG / GIF / WebP。"
        "默认不缩放，返回值含原图尺寸、实发尺寸与 `scale`（原图宽 / 实发宽）。"
    )
    parameters = {
        "path": {"type": "string", "description": "图片文件路径；attachment_id 二选一"},
        "attachment_id": {"type": "string", "description": "历史图片引用；从占位中的 attachment_id 取得"},
        "label": {"type": "string", "description": "这张图的来源说明（可选，例如“用户桌面截图”）"},
        "max_side": {
            "type": "integer",
            "description": "把长边缩到不超过该像素后再发送；0（默认）= 保留原始尺寸。",
        },
    }

    def _session_events(self) -> list:
        ctx = current_context()
        cid = current_session_id()
        app = getattr(ctx, "app", None) if ctx is not None else None
        if app is None or not cid or not callable(getattr(app, "has", None)):
            return []
        stores = []
        if app.has(SERVICE_STORE):
            stores.append(app.get(SERVICE_STORE))
        if app.has(SERVICE_SUBAGENTS):
            manager = app.get(SERVICE_SUBAGENTS)
            store_for = getattr(manager, "store_for", None)
            if callable(store_for):
                stores.append(store_for(cid))
        events = []
        for store in stores:
            events.extend(store.load(cid))
        return events

    def _already_read(self, ident: str) -> bool:
        events = self._session_events()
        start = 0
        for index, event in enumerate(events):
            if str(getattr(event, "type", "")) == TURN_STARTED:
                start = index
        for event in events[start:]:
            if str(getattr(event, "type", "")) != TOOL_DONE:
                continue
            data = getattr(event, "data", None) or {}
            if str(data.get("name") or "") != "read_image":
                continue
            payload = data.get("data")
            if isinstance(payload, dict) and str(payload.get("attachment_id") or "") == ident:
                return True
        return False

    def _bytes_from_attachment(self, ident: str) -> tuple[bytes, str]:
        events = self._session_events()
        if not events:
            raise ValueError("当前上下文没有会话存储，无法读取历史附件")
        if self._already_read(ident):
            raise ValueError(
                "本回合已读取过该附件，不能重复读取；"
                "若图片未随请求发送，请等下一回合或调整 image_max")
        for event in events:
            if str(getattr(event, "type", "")) != "input_claimed":
                continue
            rows = (getattr(event, "data", None) or {}).get("attachments") or []
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                data = row.get("data_base64")
                if not isinstance(data, str) or not data:
                    continue
                actual = str(row.get("attachment_id") or attachment_id(data, index))
                if actual == ident:
                    try:
                        return base64.b64decode(data, validate=True), str(row.get("mime") or "")
                    except Exception as exc:
                        raise ValueError(f"历史附件损坏：{ident}") from exc
        raise ValueError(f"历史附件不存在：{ident}")

    def _load_source(self, arguments: Dict[str, Any]) -> tuple[bytes, str, str]:
        ident = str(arguments.get("attachment_id") or "").strip()
        raw_path = str(arguments.get("path") or "").strip()
        if ident:
            raw, declared = self._bytes_from_attachment(ident)
            return raw, declared, f"attachment:{ident}"
        if not raw_path:
            raise ValueError("path 或 attachment_id 必须提供其一")
        path = Path(raw_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"图片不存在或不是文件：{path}")
        try:
            shown = str(path.resolve())
        except OSError:
            shown = str(path)
        return path.read_bytes(), "", shown

    def _payload(self, raw: bytes, declared_mime: str, shown_path: str,
                 label: str, max_side: int) -> Any:
        if not raw:
            raise ValueError(f"图片是空文件：{shown_path}")
        if MAX_READ_BYTES and len(raw) > MAX_READ_BYTES:
            raise ValueError(f"图片过大：{len(raw)} 字节，上限 {MAX_READ_BYTES} 字节")
        mime, width, height = describe_image(raw, declared_mime)
        if mime not in IMAGE_MIMES:
            raise ValueError(
                f"不是支持的图片格式：{shown_path}（按内容判定为 {mime}；"
                f"支持 {'、'.join(IMAGE_MIMES)}）")
        sent, sent_mime = shrink_image(raw, max_side=max_side, declared_mime=mime)
        sent_w, sent_h = describe_image(sent, sent_mime)[1:]
        if not sent_w or not sent_h:
            sent_w, sent_h = width, height
        scale = (width / sent_w) if sent_w else 1.0
        summary: Dict[str, Any] = {
            "path": shown_path, "format": sent_mime,
            "width": width, "height": height,
            "sent_width": sent_w, "sent_height": sent_h,
            "scale": round(scale, 4), "raw_bytes": len(raw),
            "sent_bytes": len(sent), "shrunk": sent_w != width or sent_h != height,
        }
        if shown_path.startswith("attachment:"):
            summary["attachment_id"] = shown_path.split(":", 1)[1]
        if label:
            summary["label"] = label
        if not width or not height:
            summary["note"] = "未能解析像素尺寸"
        if summary["shrunk"]:
            summary["note"] = (f"图片已从 {width}x{height} 缩到 {sent_w}x{sent_h}"
                               f"（坐标需乘 {scale:.4g} 还原为原图坐标）")
        return ToolResult.attach(summary, [{
            "mime": sent_mime,
            "data_base64": base64.b64encode(sent).decode("ascii"),
        }])

    def execute(self, arguments: Dict[str, Any]) -> Any:
        raw, declared, shown_path = self._load_source(arguments)
        label = str(arguments.get("label") or "").strip()
        max_side = arguments.get("max_side")
        try:
            max_side = READ_MAX_SIDE_DEFAULT if max_side is None or max_side == "" else int(max_side)
        except (TypeError, ValueError):
            max_side = READ_MAX_SIDE_DEFAULT
        return self._payload(raw, declared, shown_path, label, max_side)


def build_plugins() -> List[ToolPlugin]:
    """构造本组工具（read_image）。"""
    return [ImageReadTool()]
