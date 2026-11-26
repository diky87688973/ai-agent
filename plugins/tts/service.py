# -*- coding: utf-8 -*-
"""插件对外的唯一门面：选引擎、按需回落、给出状态快照。

回落只发生在「引擎不可用」时；单段合成失败不换引擎，否则会把真实故障
伪装成一次成功，调用方也拿不到可归因的错误。
"""
from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Dict, Optional

from agent.common.tts_contract import (
    TTSCapabilities,
    TTSProvider,
    TTSRequest,
    TTSResult,
    TTSUnavailable,
)

from .config import TTSConfig

if TYPE_CHECKING:  # 避免运行时循环导入，仅用于注解
    from .voice_lab import VoiceLab

#: 本地方案不就绪时的完整引导。文案归 tts：只有它知道模型装哪、装什么、
#: 装不好还有哪条退路；上游只管原样透传，不自造措辞。
INSTALL_HINT = (
    "请加载 tts 技能的 tts-setup 子技能，按其中步骤安装本地模型并填好模型目录"
    "（也可在 tts 插件设置里打开「本地方案不可用时用 Edge 兜底」）"
)


class TTSService:
    """合成服务的组合根；构造后即可直接调用。"""

    def __init__(self, config: TTSConfig, primary: TTSProvider,
                 fallback: Optional[TTSProvider] = None,
                 lab: Optional["VoiceLab"] = None,
                 degraded_reason: str = "") -> None:
        self._config = config
        self._primary = primary
        self._fallback = fallback if config.fallback_to_edge else None
        self._lab = lab
        self._degraded_reason = str(degraded_reason or "")
        self._last_fallback_reason = ""

    @property
    def config(self) -> TTSConfig:
        return self._config

    @property
    def engine(self) -> str:
        return self._primary.name

    @property
    def lab(self) -> Optional["VoiceLab"]:
        """音色工作台；网络引擎下为 None，调用方据此给可读提示。"""
        return self._lab

    def capabilities(self) -> TTSCapabilities:
        return self._primary.capabilities()

    def ready(self) -> bool:
        """主引擎或兜底引擎可用，就意味着能出声。"""
        if self._primary.available():
            return True
        return self._fallback is not None and self._fallback.available()

    def synthesize(self, request: TTSRequest) -> TTSResult:
        try:
            return self._primary.synthesize(request)
        except TTSUnavailable as exc:
            self._last_fallback_reason = f"{self._primary.name}: {exc}"
            if self._fallback is None:
                raise
            return self._fallback.synthesize(request)

    def unavailable_hint(self) -> str:
        """本地方案不就绪时的完整提示；就绪或本就不是本地引擎时返回空串。"""
        status = self.status()
        if str(self._config.engine or "").strip() != "breeze" or status["engine_ready"]:
            return ""
        reason = str(status.get("degraded_reason") or "").strip()
        if not reason:
            return INSTALL_HINT
        return f"{reason}。{INSTALL_HINT}"

    def status(self) -> Dict[str, object]:
        """状态快照。

        `engine` 是配置里写的引擎，`active_engine` 是实际在用的；两者不同就说明
        退化了，原因在 `degraded_reason`。不要把“当前 provider 可用”当成
        “本地引擎就绪”——退化成 edge 后前者仍为真，会把缺模型这件事掩盖掉。
        """
        configured = str(self._config.engine or "").strip()
        active = self._primary.name
        engine_ready = active == configured and self._primary.available()
        if configured == "breeze" and not engine_ready:
            hint = INSTALL_HINT
        else:
            hint = ""
        return {
            "engine": configured,
            "active_engine": active,
            "engine_ready": engine_ready,
            "primary_ready": engine_ready,
            "degraded": bool(self._degraded_reason) or active != configured,
            "degraded_reason": self._degraded_reason,
            "install_hint": hint,
            "fallback_engine": self._fallback.name if self._fallback else "",
            "fallback_ready": self._fallback.available() if self._fallback else False,
            "last_fallback_reason": self._last_fallback_reason,
            "model_dir": self._config.model_dir,
            "default_model": self._config.default_model,
            "capabilities": dataclasses.asdict(self._primary.capabilities()),
            "voice_id": self._config.voice_id,
            "voice_lab": self._lab is not None,
            "warnings": list(self._config.warnings),
        }

    def release_idle(self) -> bool:
        """把空闲的本地服务停掉，释放显存。"""
        return self._primary.release_idle()

    def dispose(self) -> None:
        self._primary.dispose()
        if self._fallback is not None:
            self._fallback.dispose()
