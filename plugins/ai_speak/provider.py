# -*- coding: utf-8 -*-
"""AI说话的语音合成端口与 edge-tts 适配。

端口只产出内存中的音频字节；插件不落盘。edge-tts 延迟导入，缺库时插件
仍可装载，工具执行时给出可安装的提示。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, List, Protocol

MAX_AUDIO_BYTES = 4 * 1024 * 1024
MIME_MPEG = "audio/mpeg"


class SpeechError(Exception):
    """语音能力的基类异常。"""


class SpeechEngineUnavailable(SpeechError):
    """引擎依赖不可用；调用方应给出安装或环境提示。"""


class SpeechSynthesisError(SpeechError):
    """单段合成失败；调用方按段隔离。"""


@dataclass(frozen=True, slots=True)
class SpeechAudio:
    """一段合成结果；`data` 只留在内存。"""

    data: bytes
    mime: str = MIME_MPEG
    voice: str = ""


class TTSProvider(Protocol):
    """合成端口。"""

    name: str

    def available(self) -> bool: ...

    def synthesize(self, text: str, *, voice: str, timeout_s: float) -> SpeechAudio: ...


def _import_edge_tts() -> Any:
    try:
        import edge_tts  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SpeechEngineUnavailable(
            "edge-tts 未安装。请执行: pip install edge-tts"
        ) from exc
    return edge_tts


class EdgeTTSProvider:
    """edge-tts 适配；每次合成在独立事件循环里跑，超时由外层等待。"""

    name = "edge"

    def available(self) -> bool:
        try:
            _import_edge_tts()
        except SpeechEngineUnavailable:
            return False
        return True

    def synthesize(self, text: str, *, voice: str, timeout_s: float) -> SpeechAudio:
        body = str(text or "").strip()
        if not body:
            raise SpeechSynthesisError("合成文本为空")
        selected = str(voice or "").strip()
        if not selected:
            raise SpeechSynthesisError("音色名为空")

        edge_tts = _import_edge_tts()

        async def _collect() -> bytes:
            communicate = edge_tts.Communicate(body, selected)
            chunks: List[bytes] = []
            async for chunk in communicate.stream():
                if not isinstance(chunk, dict):
                    continue
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunks.append(bytes(chunk["data"]))
            return b"".join(chunks)

        try:
            audio = asyncio.run(asyncio.wait_for(_collect(), timeout=max(0.1, float(timeout_s))))
        except asyncio.TimeoutError as exc:
            raise SpeechSynthesisError(
                f"合成超时（{timeout_s:.0f}s，音色 {selected}）"
            ) from exc
        except SpeechError:
            raise
        except Exception as exc:
            raise SpeechSynthesisError(
                f"合成失败（音色 {selected}）：{type(exc).__name__}: {exc}"
            ) from exc

        if not audio:
            raise SpeechSynthesisError(f"合成没有音频（音色 {selected}）")
        if len(audio) > MAX_AUDIO_BYTES:
            raise SpeechSynthesisError(
                f"单段音频超过 {MAX_AUDIO_BYTES} 字节（实际 {len(audio)}）"
            )
        return SpeechAudio(data=audio, mime=MIME_MPEG, voice=selected)


def create_provider(engine: str = "edge") -> TTSProvider:
    """按配置创建引擎；配置校验已在装载期完成。"""
    name = str(engine or "edge").strip().lower()
    if name != "edge":
        raise SpeechEngineUnavailable(f"不支持的合成引擎：{engine!r}")
    return EdgeTTSProvider()
