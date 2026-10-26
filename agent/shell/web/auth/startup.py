# -*- coding: utf-8 -*-
"""鉴权启动策略：判断当前配置是否允许对外启动。"""
from __future__ import annotations

from typing import Any


def can_start_public(auth: Any) -> bool:
    """非回环启动前必须有密码或可用外部 provider。"""
    if auth.config.mode == "local":
        return auth.local_bypass
    if auth.config.mode == "auto" and auth.local_bypass:
        return True
    if auth.provider_error:
        return False
    return auth.credentials.exists() or auth.provider is not None
