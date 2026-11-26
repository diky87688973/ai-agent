# -*- coding: utf-8 -*-
"""AI角色扮演插件的配置读取。

`plugin-config.ini` 的 `[config]` 是唯一配置来源。读取只做解析与校验，
不创建线程、不访问网络；调用方拿到 `AICosplayConfig` 后自行决定如何记录
`warnings`。
"""
from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from agent.config import load_ini

CONFIG_FILE = "plugin-config.ini"
CONFIG_SECTION = "config"
DEFAULT_VOICE = "一位温柔清晰的年轻女性，声音柔和亲切"
DEFAULT_USER_SALUTATION = "陛下"
DEFAULT_ASSISTANT_SALUTATION = "臣妾"
DEFAULT_TONE = "温婉"
DEFAULT_PERSONA = ""
DEFAULT_MAX_SEGMENT_CHARS = 128
DEFAULT_PLAY_INTERVAL_MS = 0
DEFAULT_SYNC_PLAYBACK = False
DEFAULT_SPEED = 1.0
MIN_SPEED = 0.5
MAX_SPEED = 2.0

#: 插件读取的 `[config]` 键；模板必须与它双向一致。



class ConfigError(ValueError):
    """配置值不可用，插件装载失败。"""

    def __init__(self, message: str, *, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else None
        super().__init__(f"{self.path}: {message}" if self.path else message)


@dataclass(frozen=True, slots=True)
class AICosplayConfig:
    """一份不可变配置；警告只描述被回退的数值，不阻断装载。"""

    voice: str = DEFAULT_VOICE
    user_salutation: str = DEFAULT_USER_SALUTATION
    assistant_salutation: str = DEFAULT_ASSISTANT_SALUTATION
    tone: str = DEFAULT_TONE
    persona: str = DEFAULT_PERSONA
    max_segment_chars: int = DEFAULT_MAX_SEGMENT_CHARS
    play_interval_ms: int = DEFAULT_PLAY_INTERVAL_MS
    sync_playback: bool = DEFAULT_SYNC_PLAYBACK
    speed: float = DEFAULT_SPEED
    warnings: Tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.voice)


def config_path() -> Path:
    """插件自己的配置文件；与插件同目录。"""
    return Path(__file__).resolve().parent / CONFIG_FILE


def _clean(value: object) -> str:
    return str(value or "").strip().strip("'\"")


def _int_value(raw: str, default: int) -> Tuple[int, Optional[str]]:
    """解析整数；非数字返回默认值并给出一条警告。"""
    if not raw:
        return default, None
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return default, f"非整数值 {raw!r}，使用默认值 {default}"


def _float_value(raw: str, default: float) -> Tuple[float, Optional[str]]:
    """解析浮点数；非数字返回默认值并给出一条警告。"""
    if not raw:
        return default, None
    try:
        return float(raw), None
    except (TypeError, ValueError):
        return default, f"非数字值 {raw!r}，使用默认值 {default}"


def _bool_value(raw: str, default: bool, key: str) -> bool:
    """ini 只能存文本，布尔在边界上用 0/1；其他写法是配置错误。

    不再接受 true/yes/on：多一种写法就多一套映射，
    写入端只写 0/1，读取端就只该认 0/1。
    """
    text = str(raw or "").strip()
    if not text:
        return default
    if text == "1":
        return True
    if text == "0":
        return False
    raise ConfigError(f"{key} 只接受 0 或 1，收到 {raw!r}")


def _parse_numeric(values: dict[str, str], warnings: list[str]) -> Tuple[int, int, bool, float]:
    """解析数值项并收集回退警告。"""
    max_segment_chars, warning = _int_value(
        values.get("max_segment_chars", ""), DEFAULT_MAX_SEGMENT_CHARS
    )
    if warning:
        warnings.append(f"max_segment_chars {warning}")
    if max_segment_chars < 1:
        warnings.append(
            f"max_segment_chars={max_segment_chars} 小于 1，使用默认值 "
            f"{DEFAULT_MAX_SEGMENT_CHARS}"
        )
        max_segment_chars = DEFAULT_MAX_SEGMENT_CHARS

    play_interval_ms, warning = _int_value(
        values.get("play_interval_ms", ""), DEFAULT_PLAY_INTERVAL_MS
    )
    if warning:
        warnings.append(f"play_interval_ms {warning}")
    if play_interval_ms < 0:
        warnings.append(f"play_interval_ms={play_interval_ms} 小于 0，按 0 处理")
        play_interval_ms = 0

    sync_playback = _bool_value(
        values.get("sync_playback", ""), DEFAULT_SYNC_PLAYBACK, "sync_playback"
    )

    speed, warning = _float_value(values.get("speed", ""), DEFAULT_SPEED)
    if warning:
        warnings.append(f"speed {warning}")
    if not MIN_SPEED <= speed <= MAX_SPEED:
        warnings.append(
            f"speed={speed} 超出 {MIN_SPEED:g}–{MAX_SPEED:g}，使用默认值 {DEFAULT_SPEED:g}"
        )
        speed = DEFAULT_SPEED
    return max_segment_chars, play_interval_ms, sync_playback, speed


def load_config(path: Optional[Path] = None) -> AICosplayConfig:
    """读取并校验 `[config]`。

    `voice` 必须非空：它是上游对音色的诉求，为空等于没有诉求，合成引擎
    无从参考。不可用时抛 `ConfigError`，让插件装载失败并在插件列表里可见。
    数值错误回退默认值，通过 `warnings` 交给调用方留痕。
    """
    target = Path(path) if path is not None else config_path()
    try:
        parser = load_ini(target)
    except configparser.Error as exc:
        raise ConfigError(f"无法解析配置：{exc}", path=target) from exc

    values = {}
    if parser.has_section(CONFIG_SECTION):
        values = {str(k).strip(): _clean(v) for k, v in parser.items(CONFIG_SECTION)}

    voice = values["voice"] if "voice" in values else DEFAULT_VOICE
    if not voice:
        raise ConfigError(f"[{CONFIG_SECTION}] voice 不能为空", path=target)

    user_salutation = values.get("user_salutation", DEFAULT_USER_SALUTATION)
    if not user_salutation:
        user_salutation = DEFAULT_USER_SALUTATION
    assistant_salutation = values.get(
        "assistant_salutation", DEFAULT_ASSISTANT_SALUTATION
    )
    if not assistant_salutation:
        assistant_salutation = DEFAULT_ASSISTANT_SALUTATION
    tone = values.get("tone", DEFAULT_TONE)
    if not tone:
        tone = DEFAULT_TONE
    persona = values.get("persona", DEFAULT_PERSONA)

    warnings: list[str] = []
    max_segment_chars, play_interval_ms, sync_playback, speed = _parse_numeric(values, warnings)

    return AICosplayConfig(
        voice=voice,
        user_salutation=user_salutation,
        assistant_salutation=assistant_salutation,
        tone=tone,
        persona=persona,
        max_segment_chars=max_segment_chars,
        play_interval_ms=play_interval_ms,
        sync_playback=sync_playback,
        speed=speed,
        warnings=tuple(warnings),
    )
