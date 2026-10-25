# -*- coding: utf-8 -*-
"""会话日志的行级加密与密钥管理。

- 模式：none / local；local 为纯标准库 encrypt-then-MAC（HMAC-SHA256 密钥流 XOR）；
- 密钥文件 `<data_root>/cache/session_encryption.key`：32 字节主密钥，
  存在则复用、缺失则生成（0600）；
- 实际加密键 = HMAC(app_entropy, 主密钥)；app_entropy 与应用根路径绑定。

落盘行是 JSON envelope：`MAGIC` 键标版本，`alg` 标算法，`nonce` / `data` / `tag`
均为 base64。明文行（没有 `MAGIC` 键）原样透传，混存日志能同时读回。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
from pathlib import Path
from typing import Optional

from agent.core.error_report import report_error

MAGIC = "__fan_agent_session_encrypted__"
ALG_LOCAL = "local-hmac-sha256-stream-v1"
APP_ENTROPY_SALT = "|fan-agent-session-v1"
#: 密钥文件读或建的互斥锁（模块级，跨实例共享）
_KEY_LOCK = threading.Lock()


def _xor_stream(data: bytes, key: bytes, nonce: bytes) -> bytes:
    """HMAC-SHA256 密钥流 XOR；纯标准库实现。"""
    out = bytearray()
    counter = 0
    while len(out) < len(data):
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(a ^ b for a, b in zip(data, out[: len(data)]))


class SessionCipher:
    """行加解密器：实际加密键惰性加载并按实例缓存。"""

    def __init__(self, data_root: Path, mode: str = "none") -> None:
        self.data_root = Path(data_root)
        self.mode = mode if mode in ("none", "local") else "none"
        self._key_cache: Optional[bytes] = None

    def encrypt_line(self, plain: str) -> str:
        """明文行 → 落盘行；none 模式原样返回。"""
        if self.mode == "none":
            return plain
        key = self._session_key()
        nonce = os.urandom(16)
        cipher = _xor_stream(plain.encode("utf-8"), key, nonce)
        tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
        envelope = {
            MAGIC: 1,
            "alg": ALG_LOCAL,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "data": base64.b64encode(cipher).decode("ascii"),
            "tag": base64.b64encode(tag).decode("ascii"),
        }
        return json.dumps(envelope, ensure_ascii=True, separators=(",", ":"))

    def decrypt_line(self, line: str) -> Optional[str]:
        """落盘行 → 明文；明文行原样返回；空行返回 None；校验失败抛 ValueError。"""
        text = line.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text
        if not isinstance(parsed, dict) or parsed.get(MAGIC) != 1:
            return text
        if str(parsed.get("alg") or "") != ALG_LOCAL:
            raise ValueError(f"不支持的会话加密算法：{parsed.get('alg')!r}")
        key = self._session_key()
        try:
            nonce = base64.b64decode(str(parsed.get("nonce") or "").encode("ascii"))
            cipher = base64.b64decode(str(parsed.get("data") or "").encode("ascii"))
            tag = base64.b64decode(str(parsed.get("tag") or "").encode("ascii"))
        except Exception as exc:
            report_error("agent.mechanisms.session_crypto.SessionCipher.decrypt_line", exc)
            raise ValueError(f"会话密文 envelope 损坏：{exc}") from exc
        expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise ValueError("会话加密 tag 校验失败（内容被篡改或密钥不符）")
        try:
            return _xor_stream(cipher, key, nonce).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"会话密文解码失败：{exc}") from exc

    def _session_key(self) -> bytes:
        """实际加密键：HMAC(app_entropy, 主密钥材料)；惰性加载并缓存。"""
        if self._key_cache is None:
            material = self._load_or_create_key_material()
            self._key_cache = hmac.new(
                self._app_entropy(), material, hashlib.sha256
            ).digest()
        return self._key_cache

    def _load_or_create_key_material(self) -> bytes:
        """32 字节主密钥：文件存在则复用，缺失则生成（0600）；锁防并发双建。"""
        key_file = self.data_root / "cache" / "session_encryption.key"
        with _KEY_LOCK:
            if key_file.is_file():
                return base64.urlsafe_b64decode(
                    key_file.read_text(encoding="ascii").strip().encode("ascii")
                )
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key = os.urandom(32)
            key_file.write_text(base64.urlsafe_b64encode(key).decode("ascii"), encoding="ascii")
            try:
                os.chmod(str(key_file), 0o600)
            except OSError as exc:
                report_error(
                    "agent.mechanisms.session_crypto.SessionCipher._load_or_create_key_material", exc
                )
            return key

    @staticmethod
    def _app_entropy() -> bytes:
        """应用熵：sha256(项目根路径 + 固定串)——密钥与安装位置绑定。"""
        app_root = Path(__file__).resolve().parents[2]
        return hashlib.sha256((str(app_root) + APP_ENTROPY_SALT).encode("utf-8")).digest()
