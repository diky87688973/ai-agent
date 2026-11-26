# -*- coding: utf-8 -*-
"""Breeze TTS 2 实现：通过本地 HTTP 服务合成，音频只在内存里流转。

引擎不吃数值语速与独立音色参数，只能靠自然语言指令表达；本 provider 负责
把诉求翻译成指令，并把裸 PCM 包成 WAV 供播放器直接使用。
"""
from __future__ import annotations

import io
import threading
import urllib.error
import urllib.parse
import urllib.request
import wave
from typing import Any

from agent.common.tts_contract import (
    MAX_AUDIO_BYTES,
    MIME_WAV,
    TTSCapabilities,
    TTSEngineUnavailable,
    TTSProvider,
    TTSRequest,
    TTSResult,
    TTSSynthesisError,
)

DEFAULT_SAMPLE_RATE = 24000
#: 单段文本上限；超过说明上游切段没做好，直接失败比静默截断安全。
MAX_TEXT_CHARS = 800

_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    """裸 PCM 包成 WAV，播放器才认。"""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(int(sample_rate))
        writer.writeframes(pcm)
    return buffer.getvalue()


class BreezeProvider(TTSProvider):
    """本地 Breeze TTS 2 服务适配。"""

    name = "breeze"

    def __init__(self, *, supervisor: Any, voice_desc: str,
                 emotion: str = "", cfg_scale: float = 2.0,
                 voice_id: str = "", temperature: float = 0.3,
                 top_k: int = 20) -> None:
        self._supervisor = supervisor
        self._voice_desc = str(voice_desc or "").strip()
        self._emotion = str(emotion or "").strip()
        self._cfg_scale = float(cfg_scale)
        self._voice_id = str(voice_id or "").strip()
        self._temperature = float(temperature)
        self._top_k = int(top_k)
        self._lock = threading.Lock()

    @property
    def supervisor(self) -> Any:
        """音色工作台要复用同一个进程管理，不能再建一个。"""
        return self._supervisor

    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities(
            supports_instruction=True,
            # 引擎本身不认语速，speed 改由播放侧执行，见 TTSResult.speed_applied。
            supports_speed=False,
            supports_cfg=True,
            needs_pinyin_hints=False,
        )

    def available(self) -> bool:
        return self._supervisor.missing_reason() == ""

    def _effective_voice_id(self, request: TTSRequest) -> str:
        """请求指定的音色优先，其次配置里的默认音色。

        `design=True` 时一律返回空，走「按指令设计音色」而不是克隆，
        否则工作台里任何组合都会锁死在同一段参考音色上。
        """
        if request.design:
            return ""
        return str(request.voice_id or "").strip() or self._voice_id

    def build_instruction(self, request: TTSRequest) -> str:
        """只描述音色与情感，不描述语速。

        实测该引擎对语速描述不响应（要求「快」反而慢 17%），
        语速改由播放侧按 speed 变速，见 TTSResult.speed_applied。
        已有参考音色时也不再拼音色描述：说话人由 voice_id 定死。
        """
        explicit = str(request.instruction or "").strip()
        if explicit:
            return explicit
        parts = []
        if not self._effective_voice_id(request):
            parts.append(str(request.voice or "").strip() or self._voice_desc)
        if self._emotion:
            parts.append(self._emotion)
        return "，".join(part for part in parts if part)

    def synthesize(self, request: TTSRequest) -> TTSResult:
        body = str(request.text or "").strip()
        if not body:
            raise TTSSynthesisError("合成文本为空")
        if len(body) > MAX_TEXT_CHARS:
            raise TTSSynthesisError(
                f"单段文本超过 {MAX_TEXT_CHARS} 字（实际 {len(body)}），应由调用方切段")

        # 服务按 --parallel 1 运行，并发请求会拿到 409 busy；串行化是这里的正确语义。
        with self._lock:
            return self._synthesize_locked(request, body)

    def _synthesize_locked(self, request: TTSRequest, body: str) -> TTSResult:
        base = self._supervisor.ensure_ready()
        cfg = float(request.cfg_scale) if request.cfg_scale > 0 else self._cfg_scale
        fields = {
            "text": body,
            "instruction": self.build_instruction(request),
            "cfg_scale": f"{cfg:g}",
            "seed": str(int(request.seed) if request.seed > 0 else 42),
        }
        voice_id = self._effective_voice_id(request)
        if voice_id:
            # 给定参考音色就锁住说话人；否则音色会跟着 instruction 与文本重新采样。
            fields["voice_id"] = voice_id
        # 采样随机性越小，同一说话人的音高越稳；0 表示沿用模型自带值。
        temp = float(request.temperature) if request.temperature > 0 else self._temperature
        if temp > 0:
            fields["temperature"] = f"{temp:g}"
        top_k = int(request.top_k) if request.top_k > 0 else self._top_k
        if top_k > 0:
            fields["top_k"] = str(top_k)
        payload = urllib.parse.urlencode(fields).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/v1/audio/speech", data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"})

        try:
            timeout = max(30.0, float(request.timeout_s))
            with _NO_PROXY.open(req, timeout=timeout) as resp:
                pcm = resp.read()
                sample_rate = int(resp.headers.get("X-Sample-Rate") or DEFAULT_SAMPLE_RATE)
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except OSError:
                detail = ""
            suffix = f"：{detail}" if detail else ""
            # 409 是服务端并发限制、503 是暂时不可用：都算引擎层不可用，
            # 不该归为「这段文本合成失败」，否则配置了兜底也不会生效。
            if exc.code in (409, 429, 503):
                raise TTSEngineUnavailable(
                    f"本地合成服务暂时不可用（HTTP {exc.code}{suffix}）") from exc
            raise TTSSynthesisError(
                f"合成请求被拒绝（HTTP {exc.code}{suffix}）") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise TTSEngineUnavailable(f"无法连接本地合成服务：{exc}") from exc

        if not pcm:
            raise TTSSynthesisError("合成没有返回音频")
        audio = _pcm_to_wav(pcm, sample_rate)
        if len(audio) > MAX_AUDIO_BYTES:
            raise TTSSynthesisError(
                f"单段音频超过 {MAX_AUDIO_BYTES} 字节（实际 {len(audio)}）")
        return TTSResult(audio=audio, sample_rate=sample_rate,
                         mime=MIME_WAV, engine=self.name, speed_applied=False)

    def release_idle(self) -> bool:
        """空闲则停掉常驻服务，释放显存。"""
        return bool(self._supervisor.release_idle())

    def dispose(self) -> None:
        """停掉常驻服务，释放显存。"""
        self._supervisor.stop()
