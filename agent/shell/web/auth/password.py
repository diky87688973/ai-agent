# -*- coding: utf-8 -*-
"""密码哈希与校验：仅使用标准库 scrypt。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Any, Dict

from agent.core.error_report import report_error

N = 16384
R = 8
P = 1
SALT_BYTES = 16
DKLEN = 32


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _raw(value: Any) -> bytes:
    return base64.b64decode(str(value or ""), validate=True)


def hash_password(password: str) -> Dict[str, Any]:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(
        str(password).encode("utf-8"), salt=salt, n=N, r=R, p=P, dklen=DKLEN,
    )
    return {
        "algo": "scrypt",
        "salt": _b64(salt),
        "hash": _b64(digest),
        "n": N,
        "r": R,
        "p": P,
    }


def verify_password(password: str, record: Any) -> bool:
    if not isinstance(record, dict) or record.get("algo") != "scrypt":
        return False
    try:
        digest = hashlib.scrypt(
            str(password).encode("utf-8"),
            salt=_raw(record.get("salt")),
            n=int(record.get("n", N)),
            r=int(record.get("r", R)),
            p=int(record.get("p", P)),
            dklen=len(_raw(record.get("hash"))),
        )
        return hmac.compare_digest(digest, _raw(record.get("hash")))
    except Exception as exc:
        report_error("agent.shell.web.auth.password.verify", exc)
        return False
