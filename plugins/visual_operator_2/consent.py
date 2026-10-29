# -*- coding: utf-8 -*-
"""视觉授权异常与固定文案。"""
from __future__ import annotations

from typing import Any, Dict, List

CONSENT_TITLE = "申请视觉操作授权,视觉操作过程中会持续录屏"
CONSENT_OPTIONS = ["同意", "拒绝"]


class VisionConsentRequired(Exception):
    """让宿主显示固定授权卡片，并挂起当前回合。"""

    await_user = True

    def __init__(self, request_id: str, conversation_id: str) -> None:
        super().__init__("视觉操作需要用户授权")
        self.data: Dict[str, Any] = {
            "kind": "vision_consent",
            "title": CONSENT_TITLE,
            "confirms": list(CONSENT_OPTIONS),
            "request_id": str(request_id or ""),
            "conversation_id": str(conversation_id or ""),
            "confirm_path": "/api/plugin/visual_operator_2/eye-consent/confirm",
            "confirm_method": "POST",
        }


def options() -> List[str]:
    return list(CONSENT_OPTIONS)

__all__ = ["CONSENT_OPTIONS", "CONSENT_TITLE", "VisionConsentRequired", "options"]
