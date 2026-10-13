# -*- coding: utf-8 -*-
"""会话标题生成。

- 一次模型调用（无工具），输入 = 会话首条用户输入 + 首条模型回复（截断）；
- 输出清洗：去引号 / 去换行 / 去"标题："前缀；上限 18 字；
- 失败（无 provider / 异常 / 空文本 / 退化占位）→ 回落 **首条用户输入前缀**，仍无 → 空串（调用方按短 id 展示）；
- 结果落盘 `<titles_dir>/<cid>.title`，
  重启后仍可读——标题是派生缓存，不是事实源的一部分。

纪律：标题生成属**旁路增强**，任何异常都不得影响回合与接口可用性。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.core.ports import LogicalRequest

MAX_TITLE_CHARS = 18
MAX_INPUT_CHARS = 600  # 送模型的素材上限（省 token）

_TITLE_PROMPT = """你是会话标题生成器。根据下面这段对话开头，生成一个**简短中文标题**。

要求：
1. 只输出标题本身，不要引号、不要句号、不要"标题："等前缀；
2. 不超过 {max_chars} 个字；
3. 概括用户要做什么（动词优先），不要复述原句；
4. 若内容不足以判断意图，只输出四个字：新会话
"""

# 占位 / 退化标题
_PLACEHOLDER_RE = re.compile(r"^(新会话|生成标题中…?|会话\s*[A-Za-z0-9_-]{8}|untitled|title)$", re.I)


def is_placeholder_title(title: str) -> bool:
    """是否为占位标题（需重新生成或以短 id 回退展示）。"""
    return not str(title or "").strip() or bool(_PLACEHOLDER_RE.match(str(title).strip()))


def clean_title(raw: str, *, max_chars: int = MAX_TITLE_CHARS) -> str:
    """清洗模型输出为可展示标题（去引号 / 换行 / 前缀 / 超长截断）。"""
    text = str(raw or "").strip()
    if not text:
        return ""
    # 只取第一行（模型有时会多写解释）
    text = text.splitlines()[0].strip()
    # 去包裹引号与常见前缀
    text = text.strip("\"'“”‘’《》【】[]() ")
    text = re.sub(r"^(标题|会话标题|title)\s*[:：]\s*", "", text, flags=re.I)
    text = text.strip("\"'“”‘’《》【】[]() ")
    # 去掉尾部标点
    text = text.rstrip("。.!！?？,，;；:：")
    if len(text) > max_chars:
        text = text[:max_chars]
    return text.strip()


def fallback_title(messages: List[Dict[str, Any]], *, max_chars: int = MAX_TITLE_CHARS) -> str:
    """从消息派生回落标题：取首条用户输入，无则空串。"""
    for message in messages:
        if not isinstance(message, dict):
            continue
        if str(message.get("role") or "") != "user":
            continue
        text = " ".join(str(message.get("content") or "").split())
        if text:
            return text[:max_chars] + ("…" if len(text) > max_chars else "")
    return ""


def make_provider_title_generator(
    provider: Any, *, max_chars: int = MAX_TITLE_CHARS
) -> Callable[[List[Dict[str, Any]]], str]:
    """构造基于模型 provider 的标题生成函数；provider 缺失或失败 → 空串。"""

    def _generate(messages: List[Dict[str, Any]]) -> str:
        if provider is None:
            return ""
        material = _material_from_messages(messages)
        if not material:
            return ""
        request = LogicalRequest(
            messages=[
                {"role": "system", "content": _TITLE_PROMPT.format(max_chars=max_chars)},
                {"role": "user", "content": material},
            ],
            tools=[],
        )
        parts: List[str] = []
        try:
            for delta in provider.stream(request):
                if getattr(delta, "kind", "") == "text":
                    parts.append(str(getattr(delta, "text", "") or ""))
        except Exception as exc:  # 旁路增强：失败不抛出
            print(f"[title] 生成失败（已回退）: {exc}", file=sys.stderr, flush=True)
            return ""
        return clean_title("".join(parts), max_chars=max_chars)

    return _generate


def _material_from_messages(messages: List[Dict[str, Any]]) -> str:
    """取会话开头的用户输入与首条模型回复（各自截断），拼成送模型的素材。"""
    user_text = ""
    assistant_text = ""
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "")
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        if role == "user" and not user_text:
            user_text = content[:MAX_INPUT_CHARS]
        elif role == "assistant" and user_text and not assistant_text:
            assistant_text = content[:MAX_INPUT_CHARS]
            break
    if not user_text:
        return ""
    if assistant_text:
        return f"【用户】\n{user_text}\n\n【助手】\n{assistant_text}"
    return f"【用户】\n{user_text}"


class TitleStore:
    """标题落盘与读取（`<titles_dir>/<cid>.title`，约定）。"""

    def __init__(self, titles_dir: Optional[Path] = None) -> None:
        self.titles_dir = Path(titles_dir) if titles_dir else None

    def _path(self, cid: str) -> Optional[Path]:
        key = str(cid or "").strip()
        if self.titles_dir is None or not key or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", key):
            return None
        return self.titles_dir / f"{key}.title"

    def load(self, cid: str) -> str:
        path = self._path(cid)
        if path is None or not path.is_file():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def save(self, cid: str, title: str) -> bool:
        text = str(title or "").strip()
        path = self._path(cid)
        if path is None or not text:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return True
        except OSError:
            return False
