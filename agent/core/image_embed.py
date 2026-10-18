# -*- coding: utf-8 -*-
"""视觉嵌图：附件 → OpenAI `image_url` 块（本地缩放 + base64 + 预算）。

图片原样内联进请求体，以下两个量由本模块负责：

1. 尺寸：官方推理前会再缩放（总像素约 1300×1300 封顶，单图 token 上限 1024）。
   本地先缩到长边 800 可减小请求体，不影响最终效果。
2. 预算：内联 base64 计入请求体 48 MiB 上限。多张截图叠加会顶爆该上限，
   症状是整轮请求被拒。超预算的附件记入 `skipped`，由调用方转成文本占位。

嵌图参数由调用方以关键字参数传入（`build_embed_parts` 的 `max_side` / `max_bytes`，
`shrink_image` / `shrink_path` 的 `max_side`）；缺省取下方两个常量，本模块不读配置文件。

所属层：内核：消息派生的一部分 —— 把事实折叠成请求的一方负责把图片摆成
模型要的样子。放进 `mechanisms` 会让内核反向依赖机制层。
Pillow 是可选依赖：缺了走"不缩放"分支，功能仍可用。
"""
from __future__ import annotations

import base64
import io
import struct
from pathlib import Path
from typing import Any, Dict, List, Tuple

#: 嵌图前本地缩放的最大边长（像素）。0 = 不缩放。
EMBED_MAX_SIDE = 800
#: 内联 base64 的总预算（字符）。0 = 不限。
#: 默认 24 MiB —— 官方请求体上限是 48 MiB，留出文本与工具的余量。
EMBED_MAX_BYTES = 24 * 1024 * 1024


def _load_pillow() -> Any:
    """按需导入 Pillow；缺库返回 None，调用方退化为不缩放。

    缩放是优化而非正确性前提：缺库时仍发原图。
    """
    import importlib.util

    if importlib.util.find_spec("PIL") is None:
        return None
    from PIL import Image  # type: ignore

    return Image


def _sniff_mime(data: bytes) -> str:
    """按内容判格式；不是已知图片格式时返回空串。

    与 `_mime_of` 的差别：本函数只认真实内容，`_mime_of` 在认不出时回落到声明的 MIME。
    """
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _mime_of(data: bytes, declared: str) -> str:
    """按内容判格式；认不出时回落到声明的 MIME（官方即以文件内容判断）。"""
    return _sniff_mime(data) or str(declared or "image/png")


def shrink_image(
    data: bytes,
    *,
    max_side: int = EMBED_MAX_SIDE,
    declared_mime: str = "",
) -> Tuple[bytes, str]:
    """把图片缩到长边 ≤ `max_side`；返回 `(字节, mime)`。

    下列情形原样返回不抛：`max_side<=0`、无 Pillow、GIF（可能丢帧）、解码失败。
    """
    mime = _mime_of(data, declared_mime)
    if max_side <= 0 or not data:
        return data, mime
    Image = _load_pillow()
    if Image is None:
        return data, mime
    if mime not in ("image/png", "image/jpeg", "image/webp"):
        # GIF 可能是动图，缩放会丢帧，故不缩。
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
        # 缩放失败时原图照常发出。
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

    预算按累计 base64 字符数算；超预算的附件进 `skipped`，
    由调用方转成文本占位（模型据此知道有图未随请求发送）。
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
            # 超预算不静默丢弃：记入 skipped，由调用方给占位文字。
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


def build_tool_parts(
    attachments: Any,
    *,
    max_side: int = 0,
    max_bytes: int = EMBED_MAX_BYTES,
) -> Tuple[List[Dict[str, Any]], str]:
    """工具附件 → `(content 数组里的块, 超限说明)`。

    与 `build_embed_parts` 的差别：

    1. 缺省不缩放。实发尺寸由工具决定，本函数只负责编成 `image_url` 块；
    2. 超限说明作为第二个返回值单独给出，由调用方按需附到正文；
    3. 体积预算仍在：超出 `max_bytes` 的附件不进块，改由说明交代。

    图片经本函数产出而不是并入 `tool_done.data`：后者的数据会落到事件流并
    `json.dumps`，base64 会按字符计入每次事件序列化的体积。
    """
    parts, skipped = build_embed_parts(attachments, max_side=max_side, max_bytes=max_bytes)
    if not skipped:
        return parts, ""
    return parts, f"（{len(skipped)} 张图片因体积超限未随本次结果发送）"


def _png_size(data: bytes) -> Tuple[int, int]:
    if len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return int(w), int(h)
    return 0, 0


def _gif_size(data: bytes) -> Tuple[int, int]:
    if len(data) >= 10:
        w, h = struct.unpack("<HH", data[6:10])
        return int(w), int(h)
    return 0, 0


def _jpeg_size(data: bytes) -> Tuple[int, int]:
    """扫 JPEG 段头找 SOF，取真实像素尺寸。"""
    i, n = 2, len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if i + 4 > n:
            break
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        # SOF0..SOF15（除 DHT=C4 / JPG=C8 / DAC=CC）带尺寸
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return w, h
        i += 2 + max(seg_len, 2)
    return 0, 0


def _webp_size(data: bytes) -> Tuple[int, int]:
    """WebP 三种子格式：VP8X / VP8L / VP8（有损）。"""
    if len(data) < 30:
        return 0, 0
    fourcc = data[12:16]
    try:
        if fourcc == b"VP8X":
            w = 1 + int.from_bytes(data[24:27], "little")
            h = 1 + int.from_bytes(data[27:30], "little")
            return w, h
        if fourcc == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if fourcc == b"VP8 ":
            # 关键帧头之后 3 字节是 14 位宽 + 14 位高
            i = data.find(b"\x9d\x01\x2a", 20, 40)
            if i > 0 and i + 7 <= len(data):
                w = int.from_bytes(data[i + 3:i + 5], "little") & 0x3FFF
                h = int.from_bytes(data[i + 5:i + 7], "little") & 0x3FFF
                return w, h
    except (IndexError, ValueError):
        # 头部字段不足或越界：尺寸读不出，交由调用方按 0 处理。
        pass
    return 0, 0


def describe_image(data: bytes, declared_mime: str = "") -> Tuple[str, int, int]:
    """`(mime, 宽, 高)`；尺寸读不出时宽高为 0。

    自己解析文件头而不依赖 Pillow：Pillow 是可选依赖，而尺寸是工具要报给模型的
    基本信息。内容不是任何已知图片格式时返回空 mime，调用方据此拒绝。
    """
    sniffed = _sniff_mime(data)
    if not sniffed:
        # 声明值只是猜测，不能用来描述：内容不是图片就没有格式与尺寸可言。
        return "", 0, 0
    mime = sniffed
    try:
        if mime == "image/png":
            w, h = _png_size(data)
        elif mime == "image/gif":
            w, h = _gif_size(data)
        elif mime == "image/jpeg":
            w, h = _jpeg_size(data)
        elif mime == "image/webp":
            w, h = _webp_size(data)
        else:
            return mime, 0, 0
    except Exception:
        return mime, 0, 0
    return mime, w, h


def shrink_path(path: Path, *, max_side: int = EMBED_MAX_SIDE) -> bytes:
    """从文件读图并缩放（工具类用途；读失败让 OSError 冒泡）。"""
    raw = Path(path).read_bytes()
    out, _mime = shrink_image(raw, max_side=max_side)
    return out


#: 只给最近这么多轮用户发言里的图内联嵌图；更早的图转文本占位。
#: 0 = 一张都不带；负数 = 不限（全带）。
#:
#: 缺省 999999 = 不剥。剥图改写的是消息序列最老的那几条，KV 缓存前缀从第 0 条起
#: 作废；不剥则前缀恒定、缓存可复用，代价是内联 base64 随会话线性增长，
#: 最终受官方 48 MiB 请求体上限约束。
#:
#: 配 `[context] image_turns` 改小该值即按用户轮剥图，见 `strip_old_images`。
KEEP_IMAGE_TURNS = 999999

#: 进请求体的图片总数上限（在轮数之内再设一道闸）。
#: 0 = 一张都不带；负数 = 不限。缺省 999999 = 不设限。
#: 与 `KEEP_IMAGE_TURNS` 相互独立：轮数限制往前看多远，总量限制最多带几张。
MAX_EMBED_IMAGES = 999999


def strip_old_images(
    messages: Any,
    *,
    keep_turns: int = KEEP_IMAGE_TURNS,
    max_images: int = MAX_EMBED_IMAGES,
) -> Tuple[List[Dict[str, Any]], int]:
    """只保留最近 `keep_turns` 轮用户发言里的图片块，更早的转文本占位。

    两个上限都为 999999 时不产生任何改动：`keep_turns` 只会取到末尾这么多条，
    配额也用不完，缺省行为即历史图片全保留、前缀恒定。

    返回 `(处理后的消息, 被剥离的图片块数)`。只改发给模型的这一份：事实流里的
    base64 不变，历史回显与重新提问仍能取到原图。

    保留优先级：最近一轮用户图 > 本轮工具图 > 更老的用户图 > 更老的工具图。
    总量超过 `max_images` 时从优先级最低的开始砍；一轮之内仍不够时，
    再砍该轮靠后的那几张（一张都不留时整轮转占位）。

    按轮计数而不是按张：一轮里发三张图算一轮。

    工具结果里的图片（`role=tool`）不按轮次窗口剥：它由工具在这一轮刚读出来，
    不重复内联历史用户图，但受总量闸约束。
    """
    msgs = list(messages or [])
    if keep_turns < 0 and max_images < 0:
        return msgs, 0
    # 带图的 user 消息 = 一轮（同一轮的后续消息不会有图），按时间升序
    positions = [
        i for i, m in enumerate(msgs)
        if isinstance(m, dict)
        and str(m.get("role") or "") == "user"
        and _image_block_count(m) > 0
    ]
    # 带图的 tool 消息（工具返回的图），按时间升序
    tool_positions = [
        i for i, m in enumerate(msgs)
        if isinstance(m, dict)
        and str(m.get("role") or "") == "tool"
        and _image_block_count(m) > 0
    ]
    if not positions and not tool_positions:
        return msgs, 0

    # ── 挑出要保留的图片块：按优先级分配配额 ──
    # 分配次序即优先级：最近一轮用户图 > 当前这一轮的工具图 > 更老的用户图 >
    # 更老的工具图。"当前这一轮"指最后一条 tool 图片消息之后的那些用户轮。
    keep_ids: set = set()
    remaining = max_images
    window = positions if keep_turns < 0 else positions[-keep_turns:] if keep_turns else []
    newest_user = window[-1] if window else -1

    def grant(index: int) -> None:
        """给某条消息分配配额，保留其中靠后的若干张。"""
        nonlocal remaining
        if max_images >= 0 and remaining <= 0:
            return
        blocks = _image_block_indexes(msgs[index])
        take = len(blocks) if max_images < 0 else min(len(blocks), remaining)
        keep_ids.update((index, k) for k in blocks[len(blocks) - take:])
        if max_images >= 0:
            remaining -= take

    for i in reversed(window):                       # 最近一轮用户图先分
        if i == newest_user:
            grant(i)
            break
    for i in reversed(tool_positions):               # 本轮工具图紧随其后
        if i > newest_user:
            grant(i)
    for i in reversed(window):                       # 其余用户轮
        if i != newest_user:
            grant(i)
    for i in reversed(tool_positions):               # 更老的工具图
        if i <= newest_user:
            grant(i)

    # ── 把没选中的块换成占位 ──
    # 逐条按 `keep_ids` 判，而不是先看是否在轮次窗口内：工具消息不在窗口里，
    # 按窗口提前放行会让它绕过配额。
    out: List[Dict[str, Any]] = []
    stripped = 0
    for i, m in enumerate(msgs):
        if not isinstance(m, dict):
            out.append(m)
            continue
        blocks = _image_block_indexes(m)
        if not blocks:
            out.append(m)
            continue
        drop = [k for k in blocks if (i, k) not in keep_ids]
        if not drop:
            out.append(m)
            continue
        stripped += len(drop)
        out.append({**m, "content": _drop_selected_blocks(m.get("content"), drop)})
    return out, stripped


def _image_block_indexes(message: Any) -> List[int]:
    """该消息里图片块的下标（升序）。"""
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [k for k, p in enumerate(content)
            if isinstance(p, dict) and p.get("type") == "image_url"]


def _image_block_count(message: Dict[str, Any]) -> int:
    return len(_image_block_indexes(message))


def _drop_selected_blocks(content: Any, drop: List[int]) -> Any:
    """摘掉指定下标的图片块；其余块（含没被选中的图片）按原顺序保留，末尾补占位。"""
    if not isinstance(content, list):
        return content
    drop_set = set(drop)
    kept = [part for k, part in enumerate(content) if k not in drop_set]
    kept.append({"type": "text",
                 "text": f"（此处原有 {len(drop)} 张图片，已不在本轮请求中；需要时重新发送）"})
    return kept
