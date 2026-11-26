# -*- coding: utf-8 -*-
"""语音合成的公共契约：请求、结果、能力声明与失败分类。

契约放在 common 层，插件只依赖它，不依赖彼此的私有实现；同一份契约同时
服务本地模型与网络引擎，换实现时上游调用方无需改动。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

#: 单段音频上限；超出的多半是上游失控，按失败处理而不是继续传。
MAX_AUDIO_BYTES = 8 * 1024 * 1024
MIME_MPEG = "audio/mpeg"
MIME_WAV = "audio/wav"
MIME_PCM = "audio/pcm"


@dataclass(frozen=True)
class TTSRequest:
    """一次合成请求。

    `voice` 是音色诉求（自然语言）；`voice_id` 是已注册的具体音色标识。
    两者不是一回事：前者让引擎自己找声音，后者指定用哪个参考音色。
    """

    text: str
    voice: str = ""
    voice_id: str = ""
    instruction: str = ""
    speed: float = 1.0
    cfg_scale: float = 1.0
    #: 0 表示用 provider 配置里的值；这两个由音色参数表控制。
    temperature: float = 0.0
    top_k: int = 0
    #: 0 表示用 provider 默认种子；扫种子是同一句指令下改变音色的唯一旋钮。
    seed: int = 0
    timeout_s: float = 30.0
    #: True 表示忽略参考音色，完全按 instruction 设计音色。
    #: 音色工作台必须用它，否则会回退到配置里的 voice_id，
    #: 听什么都是同一个人的不同语气。
    design: bool = False


@dataclass(frozen=True)
class TTSResult:
    """一段合成结果；音频只留在内存，不落盘。

    `speed_applied` 表示语速是否已在合成侧生效：为假代表引擎不认语速参数，
    调用方必须在播放侧自行变速，否则配置的语速等于没配。
    """

    audio: bytes
    sample_rate: int
    mime: str
    engine: str
    speed_applied: bool = False


@dataclass(frozen=True)
class TTSCapabilities:
    """引擎能做与不能做的事，供调用方决定如何表达诉求而不必知道具体引擎。"""

    supports_instruction: bool
    supports_speed: bool
    supports_cfg: bool
    needs_pinyin_hints: bool


class TTSUnavailable(RuntimeError):
    """合成能力不可用的基类。"""


class TTSEngineUnavailable(TTSUnavailable):
    """依赖缺失、端口不通或引擎启动失败。"""


class TTSNotInstalled(TTSUnavailable):
    """模型未安装；错误信息里要带上可执行的安装引导。"""


class TTSSynthesisError(RuntimeError):
    """单段合成失败；调用方按段隔离，不影响其他段。"""


class TTSProvider(Protocol):
    """合成端口。实现方各自决定如何把诉求翻译成自家参数。"""

    name: str

    def capabilities(self) -> TTSCapabilities: ...

    def available(self) -> bool: ...

    def synthesize(self, request: TTSRequest) -> TTSResult: ...

    def release_idle(self) -> bool: ...

    def dispose(self) -> None: ...
