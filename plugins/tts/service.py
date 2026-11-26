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

#: 本地方案不就绪时的简短提示；给状态页与诊断看，不写成动作指令。
INSTALL_HINT = (
    "请加载 tts 技能的 tts-setup 子技能，按其中步骤安装本地模型并填好模型目录"
    "（也可在 tts 插件设置里打开「本地方案不可用时用 Edge 兜底」）"
)

#: 本地方案不就绪时给模型的强指令。只提一句会被当成背景信息丢掉，必须写明
#: 先调哪个工具征得同意、同意后再加载哪个技能。
MODEL_DIRECTIVE = (
    "你必须先调用 user_confirm 工具问用户选哪条路，选项至少包含"
    "「现在安装本地模型」「改用 Edge 在线合成」「暂不处理」三项，不得只口头提一句就继续。"
    "选「现在安装本地模型」：你立即加载 tts 技能的 tts-setup 子技能，按其中步骤带用户装模型，"
    "装完把 model_dir 写进 tts 插件配置并重启宿主，重启后重试播报。"
    "选「改用 Edge 在线合成」：告诉用户在 tts 插件设置页打开"
    "「本地方案不可用时用 Edge 兜底」开关并保存，然后重启宿主才生效；"
    "这个开关只能由用户在界面上改，你不要伪称自己能代改，重启完再重试播报。"
    "选「暂不处理」：本轮不播报，改用文字回答，不再反复问。"
)


class TTSService:
    """合成服务的组合根；构造后即可直接调用。"""

    def __init__(self, config: TTSConfig, primary: TTSProvider,
                 fallback: Optional[TTSProvider] = None,
                 lab: Optional["VoiceLab"] = None,
                 degraded_reason: str = "") -> None:
        self._config = config
        self._primary = primary
        self._fallback = fallback
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
            return f"语音合成不可用。{MODEL_DIRECTIVE}"
        return f"{reason}。{MODEL_DIRECTIVE}"

    def status(self) -> Dict[str, object]:
        """状态快照。

        `engine` 是配置里写的引擎，`active_engine` 是实际在用的；两者不同即退化，
        原因记在 `degraded_reason`。当前 provider 可用不等于本地引擎就绪：
        退化成 edge 后前者仍为真，会把缺模型这件事掩盖掉。
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
