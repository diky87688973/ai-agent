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
from agent.core.image_embed import (
    describe_image,
    shrink_image,
)
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
        "读取本地图片文件并把图片本身交给模型查看（不是 OCR，不需要任何引擎）。"
        "适用于：描述图片内容、判断界面/图表/截图里的情况、核对颜色与布局与坐标、"
        "读取图中文字。"
        "支持 PNG / JPEG / GIF / WebP。"
        "默认不缩放，返回值含原图尺寸、实发尺寸与 `scale`（原图宽 / 实发宽）。"
    )
    parameters = {
        "path": {"type": "string", "description": "图片文件路径（绝对路径或相对工作目录）"},
        "label": {"type": "string", "description": "这张图的来源说明（可选，例如“用户桌面截图”）"},
        "max_side": {
            "type": "integer",
            "description": "把长边缩到不超过该像素后再发送；0（默认）= 保留原始尺寸。",
        },
    }

    def execute(self, arguments: Dict[str, Any]) -> Any:
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise ValueError("path 不能为空")
        label = str(arguments.get("label") or "").strip()
        max_side = arguments.get("max_side")
        try:
            max_side = READ_MAX_SIDE_DEFAULT if max_side is None or max_side == "" else int(max_side)
        except (TypeError, ValueError):
            max_side = READ_MAX_SIDE_DEFAULT

        path = Path(raw_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"图片不存在或不是文件：{path}")
        try:
            shown_path = str(path.resolve())
        except OSError:
            shown_path = str(path)

        raw = path.read_bytes()
        if not raw:
            raise ValueError(f"图片是空文件：{path}")
        if MAX_READ_BYTES and len(raw) > MAX_READ_BYTES:
            raise ValueError(
                f"图片过大：{len(raw)} 字节，上限 {MAX_READ_BYTES} 字节。"
            )

        mime, width, height = describe_image(raw, "")
        if mime not in IMAGE_MIMES:
            raise ValueError(
                f"不是支持的图片格式：{path}（按内容判定为 {mime}；"
                f"支持 {'、'.join(IMAGE_MIMES)}）"
            )

        sent, sent_mime = shrink_image(raw, max_side=max_side, declared_mime=mime)
        sent_w, sent_h = describe_image(sent, sent_mime)[1:]
        if not sent_w or not sent_h:
            # 缩过之后读不出尺寸时退回原图尺寸，避免上报 0。
            sent_w, sent_h = width, height
        scale = (width / sent_w) if sent_w else 1.0
        summary: Dict[str, Any] = {
            "path": shown_path,
            "format": sent_mime,
            # 原图尺寸：坐标以它为基准
            "width": width,
            "height": height,
            # 实发尺寸：模型看到的是这一份
            "sent_width": sent_w,
            "sent_height": sent_h,
            "scale": round(scale, 4),
            "raw_bytes": len(raw),
            "sent_bytes": len(sent),
            "shrunk": sent_w != width or sent_h != height,
        }
        if label:
            summary["label"] = label
        if not width or not height:
            # 尺寸解析失败不报错：图仍可发出，只是没有确切尺寸。
            summary["note"] = "未能解析像素尺寸"
        if summary["shrunk"]:
            # 缩放会改变图内坐标的含义，随结果一并给出换算关系。
            summary["note"] = (
                f"图片已从 {width}x{height} 缩到 {sent_w}x{sent_h}"
                f"（坐标需乘 {scale:.4g} 还原为原图坐标）"
            )

        return ToolResult.attach(summary, [{
            "mime": sent_mime,
            "data_base64": base64.b64encode(sent).decode("ascii"),
        }])


def build_plugins() -> List[ToolPlugin]:
    """构造本组工具（read_image）。"""
    return [ImageReadTool()]
