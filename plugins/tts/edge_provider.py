# -*- coding: utf-8 -*-
"""Edge TTS 实现：网络合成，作为默认与兜底引擎。

它不理解音色描述，只认音色名，因此音色名来自插件配置而不是上游诉求；
上游给的 `voice` 在这里被忽略，这一限制通过能力声明对外可见。
"""
from __future__ import annotations

import asyncio
from typing import Any, List

from agent.common.tts_contract import (
    MAX_AUDIO_BYTES,
    MIME_MPEG,
    TTSCapabilities,
    TTSEngineUnavailable,
    TTSProvider,
    TTSRequest,
    TTSResult,
    TTSSynthesisError,
)

SAMPLE_RATE_MPEG = 24000


def _import_edge_tts() -> Any:
    try:
        import edge_tts  # type: ignore[import-not-found]
    except ImportError as exc:
        raise TTSEngineUnavailable(
            "edge-tts 未安装。请执行: pip install edge-tts"
        ) from exc
    return edge_tts


class EdgeProvider(TTSProvider):
    """edge-tts 适配；每次合成在独立事件循环里跑，超时由本类等待。"""

    name = "edge"

    def __init__(self, *, voice: str, pinyin: Any = None) -> None:
        self._voice = str(voice or "").strip()
        self._pinyin = pinyin

    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities(
            supports_instruction=False,
            supports_speed=True,
            supports_cfg=False,
            needs_pinyin_hints=True,
        )

    def available(self) -> bool:
        try:
            _import_edge_tts()
        except TTSEngineUnavailable:
            return False
        return bool(self._voice)

    def synthesize(self, request: TTSRequest) -> TTSResult:
        body = str(request.text or "").strip()
        if not body:
            raise TTSSynthesisError("合成文本为空")
        if not self._voice:
            raise TTSEngineUnavailable("edge 音色未配置")

        # 多音字改写是 Edge 专属适配，本地模型不需要，故放在 provider 内部。
        if self._pinyin is not None:
            body = self._pinyin.apply(body)
        selected = self._voice
        timeout = max(0.1, float(request.timeout_s))

        edge_tts = _import_edge_tts()

        async def _collect() -> bytes:
            speed = float(request.speed)
            rate = f"{(speed - 1.0) * 100:+.0f}%" if abs(speed - 1.0) > 1e-9 else ""
            communicate = (edge_tts.Communicate(body, selected, rate=rate) if rate
                           else edge_tts.Communicate(body, selected))
            chunks: List[bytes] = []
            async for chunk in communicate.stream():
                if not isinstance(chunk, dict):
                    continue
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunks.append(bytes(chunk["data"]))
            return b"".join(chunks)

        try:
            audio = asyncio.run(asyncio.wait_for(_collect(), timeout=timeout))
        except asyncio.TimeoutError as exc:
            raise TTSSynthesisError(
                f"合成超时（{timeout:.0f}s，音色 {selected}）") from exc
        except TTSEngineUnavailable:
            raise
        except Exception as exc:
            raise TTSSynthesisError(
                f"合成失败（音色 {selected}）：{type(exc).__name__}: {exc}") from exc

        if not audio:
            raise TTSSynthesisError(f"合成没有音频（音色 {selected}）")
        if len(audio) > MAX_AUDIO_BYTES:
            raise TTSSynthesisError(
                f"单段音频超过 {MAX_AUDIO_BYTES} 字节（实际 {len(audio)}）")
        return TTSResult(audio=audio, sample_rate=SAMPLE_RATE_MPEG,
                         mime=MIME_MPEG, engine=self.name, speed_applied=True)

    def release_idle(self) -> bool:
        """网络引擎没有常驻进程，无需回收。"""
        return False

    def dispose(self) -> None:
        """无外部资源需要释放。"""
