# -*- coding: utf-8 -*-
"""上下文 token 粗略估算（纯函数，无装配副作用）。

CJK 每字约 1 token；其余按 4 字符 1 token。用途是压缩触发与预算统计，
宁可略高也不要低估（低估会让窗口悄悄溢出）。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Tuple

#: CJK 区段的字符每字约 1 token（本工程正文以中文为主，实测 prompt_tokens 与
#: 字符数同量级）；其余按 4 字符 1 token。见 `approx_tokens_text`。
#: 每张图片计入的 token 上限（官方口径每图最多 1024）。
IMAGE_TOKENS_PER_IMAGE = 384

_CJK_RANGES: Tuple[Tuple[int, int], ...] = (
    (0x3000, 0x303F),    # 中文标点
    (0x3400, 0x4DBF),    # 扩展 A
    (0x4E00, 0x9FFF),    # 基本区
    (0xF900, 0xFAFF),    # 兼容表意
    (0xFF00, 0xFFEF),    # 全角
    (0x20000, 0x3FFFF),  # 扩展 B 及以上
)


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def approx_tokens_text(text: str) -> int:
    """粗略 token 估算：CJK 每字 1 token，其余每 4 字符 1 token。

    **不能整体按 `len // 4` 算**：中文正文一个字约一个 token，除 4 会低估约四倍 ——
    实测一条会话的估算 173,219 对上真实 prompt 1,000,563（差 5.8 倍，主要是中文工具输出），
    于是 `summary_token_threshold` 形同虚设，压缩永远晚触发，请求一路顶到上限。

    这里只做分区计数，不引入分词器依赖：它是**估算**，用途是"什么时候该压缩"，
    宁可略高也不要低（低估会让窗口悄悄溢出）。
    """
    s = str(text or "")
    if not s:
        return 0
    cjk = 0
    for ch in s:
        if _is_cjk(ch):
            cjk += 1
    rest = len(s) - cjk
    return cjk + rest // 4 + 4


def default_message_tokens(msg: Dict[str, Any]) -> int:
    """缺省消息 token 估算（接入时可替换为更精确实现）。

    口径 = **将要发出去的那一条**：
    - `content`：文本按字符估算；多模态里的图片块按每图固定上限计（base64 是编码
      而非文本，按字符算会把一张截图算成两千多 token，官方口径每图最多 1024）。
    - `tool_calls`：`arguments` 是请求体的一部分（`python_inline` 的 `code`、
      `write_file` 的正文都在里面，一段几 KB），漏掉它估算会系统性偏小。
    - `reasoning_content`：按当前回传预算裁过之后**还剩多少就计多少**
      （`set_dialogue` 已经裁好；不裁全量回传的那份也确实要计费）。
    """
    if not isinstance(msg, dict):
        return 0
    content = msg.get("content")
    if isinstance(content, str):
        n = approx_tokens_text(content)
    elif content is None:
        n = 0
    elif isinstance(content, list):
        imgs = sum(1 for p in content
                   if isinstance(p, dict) and p.get("type") == "image_url")
        texts = "".join(str(p.get("text") or "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text")
        n = approx_tokens_text(texts) + imgs * IMAGE_TOKENS_PER_IMAGE
    else:
        try:
            n = approx_tokens_text(json.dumps(content, ensure_ascii=False))
        except (TypeError, ValueError):
            n = approx_tokens_text(str(content))
    calls = msg.get("tool_calls")
    if isinstance(calls, list) and calls:
        try:
            n += approx_tokens_text(json.dumps(calls, ensure_ascii=False))
        except (TypeError, ValueError):
            n += 16
    reasoning = msg.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        n += approx_tokens_text(reasoning)
    return n
