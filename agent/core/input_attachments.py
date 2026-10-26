# -*- coding: utf-8 -*-
"""输入附件规则：图片 MIME、数量上限与归一化。"""
from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Any, Dict, List

MAX_IMAGES = 4
IMAGE_MIMES = ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif")



def attachment_id(data_base64: Any, index: int = 0) -> str:
    """附件的稳定引用：从图片内容派生，刷新前后一致。"""
    digest = hashlib.sha1(str(data_base64 or "").encode("utf-8")).hexdigest()[:16]
    return f"att-{digest}-{int(index)}"


def with_attachment_ids(attachments: Any) -> List[Dict[str, Any]]:
    """给输入附件补稳定 attachment_id；不丢未知字段。"""
    out: List[Dict[str, str]] = []
    for index, item in enumerate(attachments or []):
        if not isinstance(item, dict):
            continue
        row = dict(item)
        data = row.get("data_base64")
        if isinstance(data, str) and data.strip():
            row["attachment_id"] = str(row.get("attachment_id") or attachment_id(data, index))
        out.append(row)
    return out

def normalize_images(raw: Any) -> List[Dict[str, str]]:
    """校验并归一化图片附件；非法项丢弃，数量上限为 `MAX_IMAGES`。"""
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for item in raw:
        if len(out) >= MAX_IMAGES:
            break
        if not isinstance(item, dict):
            continue
        mime = str(item.get("mime") or "").strip().lower()
        data = item.get("data_base64")
        if not isinstance(data, str) or not data.strip():
            continue
        if mime not in IMAGE_MIMES:
            continue
        out.append({"mime": mime, "data_base64": data.strip()})
    return out


def decode_attachment(item: Dict[str, Any]) -> bytes:
    """把归一化附件解成原始字节；损坏的 base64 抛出 ValueError。"""
    raw = item.get("data_base64") if isinstance(item, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("附件缺少 data_base64")
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("附件 base64 不合法") from exc


def encode_attachment(data: bytes) -> str:
    return base64.b64encode(bytes(data)).decode("ascii")
