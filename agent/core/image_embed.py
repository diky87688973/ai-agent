# -*- coding: utf-8 -*-
"""视觉嵌图：附件 → OpenAI `image_url` 块（本地缩放 + base64 + 预算）。

**用途**：图片是原样内联进请求体的，所以两件事必须自己管 ——

1. **尺寸**：官方在推理前会把图片自动缩放（总像素约 1300×1300 封顶，单图 token
   上限 1024）。先本地缩到长边 800，请求体小一大截而**效果无损** ——
   反正下游还会再缩一次，先缩只赚不赔。
2. **预算**：内联 base64 计入请求体 48 MiB 上限。不设预算时，
   多张截图叠加会把请求体顶爆，而症状是**整轮请求被拒**（不是"这张图看不到"）。
   超预算的附件转文本占位，让模型知道"有图但没带上"，而不是让它以为用户没发。

嵌图参数由调用方以关键字参数传入（`build_embed_parts` 的 `max_side` / `max_bytes`，
`shrink_image` / `shrink_path` 的 `max_side`）；缺省取下方两个常量，本模块不读配置文件。

**所属层：内核**：这是"消息派生"的一部分 —— 谁把事实折叠成请求，谁就要负责
把图片摆成模型要的样子。放进 `mechanisms` 会让内核反向依赖机制层（分层检查直接拦下）。
Pillow 是**可选**依赖：缺了就走"不缩放"分支，功能仍然可用。
"""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Dict, List, Tuple

#: 嵌图前本地缩放的最大边长（像素）。0 = 不缩放。
EMBED_MAX_SIDE = 800
#: 内联 base64 的总预算（字符）。0 = 不限。
#: 默认 24 MiB —— 官方请求体上限是 48 MiB，留出文本与工具的余量。
EMBED_MAX_BYTES = 24 * 1024 * 1024


def _load_pillow() -> Any:
    """按需导入 Pillow；没有就退化为"不缩放"。

    做成可选依赖：缩放是**优化**而不是正确性前提。
    缺库时仍然发图（只是体积大一些），不能因为少一个优化库就让整个视觉功能不可用。
    """
    try:
        from PIL import Image  # type: ignore

        return Image
    except Exception:
        return None


def _mime_of(data: bytes, declared: str) -> str:
    """按**内容**判格式（官方即以文件实际内容判断，而非声明的 MIME）。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return str(declared or "image/png")


def shrink_image(
    data: bytes,
    *,
    max_side: int = EMBED_MAX_SIDE,
    declared_mime: str = "",
) -> Tuple[bytes, str]:
    """把图片缩到长边 ≤ `max_side`；返回 `(字节, mime)`。

    缩不动就原样返回（`max_side<=0`、无 Pillow、动图、解码失败都不会抛）。
    """
    mime = _mime_of(data, declared_mime)
    if max_side <= 0 or not data:
        return data, mime
    Image = _load_pillow()
    if Image is None:
        return data, mime
    if mime not in ("image/png", "image/jpeg", "image/webp"):
        # GIF 可能是动图：缩放会丢帧，宁可不缩。
        return data, mime
    img = None
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
        if max(img.size) <= max_side:
            return data, mime
        img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        fmt = {"image/png": "PNG", "image/webp": "WEBP", "image/jpeg": "JPEG"}[mime]
        if fmt == "JPEG" and img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(buf, format=fmt)
        return buf.getvalue(), mime
    except Exception:
        # 判据：缩放失败**不该让图片发不出去** —— 原图照常发出。
        return data, mime
    finally:
        if img is not None:
            try:
                img.close()
            except Exception:
                pass


def build_embed_parts(
    attachments: Any,
    *,
    max_side: int = EMBED_MAX_SIDE,
    max_bytes: int = EMBED_MAX_BYTES,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """附件 → `(content 数组里的块, 被跳过的附件序号)`。

    预算按**累计 base64 字符数**算；超预算的附件进 `skipped`，
    由调用方转成文本占位（"有图但没带上"必须让模型知道）。
    """
    parts: List[Dict[str, Any]] = []
    skipped: List[str] = []
    used = 0
    items = attachments if isinstance(attachments, list) else []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        declared = str(item.get("mime") or "").strip()
        data = item.get("data_base64")
        if not isinstance(data, str) or not data:
            continue
        try:
            raw = base64.b64decode(data, validate=False)
        except Exception:
            skipped.append(str(index))
            continue
        if not raw:
            skipped.append(str(index))
            continue
        shrunk, mime = shrink_image(raw, max_side=max_side, declared_mime=declared)
        b64 = base64.b64encode(shrunk).decode("ascii")
        if max_bytes > 0 and used + len(b64) > max_bytes:
            # 判据：超预算**不静默丢** —— 记进 skipped，由调用方给占位文字。
            skipped.append(str(index))
            continue
        used += len(b64)
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    return parts, skipped


def placeholder_text(indexes: List[str]) -> str:
    """被跳过的附件 → 一句说明（模型据此知道"有图，但这轮没带上"）。"""
    if not indexes:
        return ""
    return f"（另有 {len(indexes)} 张图片因体积超限未随本轮请求发送）"


def shrink_path(path: Path, *, max_side: int = EMBED_MAX_SIDE) -> bytes:
    """从文件读图并缩放（工具类用途；读不到返回空字节）。"""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return b""
    out, _mime = shrink_image(raw, max_side=max_side)
    return out


#: 只给**最近这么多张**图内联嵌图；更早的图转文本占位。
#:
#: 依据：
#: 每次请求都把历史上的每一张图重新内联一遍，会让请求体随会话线性膨胀
#: （一个 43 条消息的会话累计 11 张图 ≈ 238KB 图片字节），
#: 而且该形态下模型会稳定地读不出图（同一张图单独发则正常）。
#: 老图对当前这一轮几乎没有价值 —— 问的是"这张图"时，指的是刚发的那张。
MAX_INLINE_IMAGES = 3


def strip_old_images(
    messages: Any,
    *,
    keep_last: int = MAX_INLINE_IMAGES,
) -> Tuple[List[Dict[str, Any]], int]:
    """把**较早**消息里的图片块换成文本占位，只保留最近 `keep_last` 张。

    返回 `(处理后的消息, 被剥离的张数)`。事实与字节仍在 —— 事实仍在
    `.raw` 里，图片字节仍在附件缓存里；这里只是不把老图重复塞进请求体。
    """
    msgs = list(messages or [])
    positions: List[int] = []
    for i, m in enumerate(msgs):
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if isinstance(content, list) and any(
            isinstance(p, dict) and p.get("type") == "image_url" for p in content
        ):
            positions.append(i)
    if keep_last < 0 or len(positions) <= keep_last:
        return msgs, 0
    drop = set(positions[:-keep_last]) if keep_last else set(positions)
    out: List[Dict[str, Any]] = []
    stripped = 0
    for i, m in enumerate(msgs):
        if i not in drop or not isinstance(m, dict):
            out.append(m)
            continue
        content = m.get("content")
        texts = [str(p.get("text") or "") for p in content
                 if isinstance(p, dict) and p.get("type") == "text"]
        n_imgs = sum(1 for p in content
                     if isinstance(p, dict) and p.get("type") == "image_url")
        stripped += n_imgs
        note = f"（历史消息：此处原有 {n_imgs} 张图片，已不在本轮请求中）"
        joined = "\n".join(t for t in texts if t).strip()
        out.append({**m, "content": f"{joined}\n{note}" if joined else note})
    return out, stripped
