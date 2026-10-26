# -*- coding: utf-8 -*-
"""授权判断：只接收 Principal、路径和方法，不解析 HTTP。"""
from __future__ import annotations

from typing import Optional

from agent.shell.web.auth import policy
from agent.shell.web.auth.models import AuthDecision, AuthIdentity, Principal


class Authorizer:
    def decide(self, identity: Optional[AuthIdentity], method: str,
               path: str) -> AuthDecision:
        scope = policy.required_scope(method.upper(), path)
        if scope is None:
            return AuthDecision(True)
        if identity is None:
            return AuthDecision(False, 401, "unauthorized")
        if policy.allows(identity.principal.scopes, scope):
            return AuthDecision(True)
        return AuthDecision(False, 403, "forbidden")

    def scope_for(self, method: str, path: str) -> Optional[str]:
        return policy.required_scope(method.upper(), path)

    def allows(self, principal: Principal, scope: Optional[str]) -> bool:
        return policy.allows(principal.scopes, scope)
