# -*- coding: utf-8 -*-
"""任务工具共享异常与参数校验。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class UserConfirmRequired(Exception):
    """待确认信封：结构化 data（title / confirms 等）随 ToolResult.data 透传。

    `await_user=True` 告诉回合循环："这一回合到此为止，等用户在宿主界面上作答"。
    没有这个标记，模型会把 `ok=False` 读成工具失败并反复重试，直到步数上限。
    """

    await_user = True

    def __init__(
        self,
        title: str,
        confirms: List[str],
        multi: bool = False,
        custom_option_index: Optional[int] = None,
    ) -> None:
        super().__init__("需由宿主展示选项并由用户确认；确认结果由宿主写成工具结果")
        self.data: Dict[str, Any] = {"title": title, "confirms": list(confirms)}
        if multi:
            self.data["multi"] = True
        if custom_option_index is not None:
            self.data["custom_option_index"] = int(custom_option_index)


class ApprovalRequired(Exception):
    """待审批信封。`option_id` 与 `option_desc` 在 ToolResult.data 里。

    `await_user=True`，回合在此停下，等宿主界面上的同意或驳回。
    """

    await_user = True

    def __init__(self, option_id: str, option_desc: str) -> None:
        super().__init__("需由宿主展示审批并由用户同意或驳回")
        self.data: Dict[str, Any] = {
            "kind": "approval",
            "title": "审批",
            "option_id": option_id,
            "option_desc": option_desc,
        }


def approval_text(raw: Any, name: str, limit: int) -> str:
    """审批入参：非空字符串。超过上限时拒绝。"""
    if not isinstance(raw, str):
        raise ValueError(f"{name} 须为非空字符串")
    text = raw.strip()
    if not text:
        raise ValueError(f"{name} 须为非空字符串")
    if len(text) > limit:
        raise ValueError(f"{name} 最长 {limit} 字符")
    return text


def normalize_confirms(raw: Any) -> List[str]:
    """confirms 校验：非空字符串数组、逐项非空白。"""
    if not isinstance(raw, list) or len(raw) < 1:
        raise ValueError("confirms 须为非空字符串数组")
    out: List[str] = []
    for i, x in enumerate(raw):
        if not isinstance(x, str) or not x.strip():
            raise ValueError(f"confirms[{i}] 须为非空字符串")
        out.append(x)
    return out
