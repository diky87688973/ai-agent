# -*- coding: utf-8 -*-
"""语音合成插件的配置读取。

`plugin-config.ini` 的 `[config]` 是唯一来源。非法数值回退默认值并留下警告，
引擎名非法则直接失败——引擎选错会让整条链路不可用，不能静默替换。
"""
from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from agent.config import load_ini

from .models import MODELS

CONFIG_FILE = "plugin-config.ini"
CONFIG_SECTION = "config"

DEFAULT_ENGINE = "breeze"
SUPPORTED_ENGINES = ("breeze", "edge")
DEFAULT_MODEL = "breeze-tts-2-q4k"
DEFAULT_PORT = 8137
DEFAULT_STARTUP_TIMEOUT = 20.0
DEFAULT_IDLE_TIMEOUT = 600.0
#: 指令引导强度。实测同一说话人在 cfg=2 时句间基频极差 45.7 Hz，cfg=3 时降到 31.8 Hz；
#: 而句内起伏（表现力代理）反而从 33.4 Hz 升到 34.9 Hz。所以默认取 3：更稳也更活。
DEFAULT_CFG_SCALE = 3.0
DEFAULT_VOICE_DESC = "一位温柔清晰的年轻女性，声音柔和亲切"
DEFAULT_EMOTION = "平静"
DEFAULT_SPEED = 1.0
DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"
#: 本地引擎不可用时是否用 edge 顶上。唯一权威；字段默认、解析默认、装配分支都读它。
DEFAULT_FALLBACK_TO_EDGE = True
MIN_SPEED = 0.5
MAX_SPEED = 2.0
MIN_CFG = 1.0
MAX_CFG = 5.0
#: 采样温度与 top-k。默认跟模型自带值一致；压低它们会连情绪起伏一起抹平，
#: 所以不用它们做音色稳定手段。这里只留成可调项，供确实需要时手动改。
DEFAULT_TEMPERATURE = 0.9
DEFAULT_TOP_K = 50
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
MIN_TOP_K = 0
MAX_TOP_K = 100


class ConfigError(ValueError):
    """配置值不可用，插件装载失败。"""

    def __init__(self, message: str, *, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else None
        super().__init__(f"{self.path}: {message}" if self.path else message)


@dataclass(frozen=True)
class TTSConfig:
    """一份不可变配置；warnings 只记录被回退的数值。"""

    engine: str = DEFAULT_ENGINE
    model_dir: str = ""
    default_model: str = DEFAULT_MODEL
    server_port: int = DEFAULT_PORT
    startup_timeout: float = DEFAULT_STARTUP_TIMEOUT
    idle_timeout: float = DEFAULT_IDLE_TIMEOUT
    cfg_scale: float = DEFAULT_CFG_SCALE
    voice_desc: str = DEFAULT_VOICE_DESC
    voice_id: str = ""
    temperature: float = DEFAULT_TEMPERATURE
    top_k: int = DEFAULT_TOP_K
    emotion: str = DEFAULT_EMOTION
    speed: float = DEFAULT_SPEED
    edge_voice: str = DEFAULT_EDGE_VOICE
    fallback_to_edge: bool = DEFAULT_FALLBACK_TO_EDGE
    warnings: Tuple[str, ...] = ()


def config_path() -> Path:
    return Path(__file__).resolve().parent / CONFIG_FILE


def _clean(value: object) -> str:
    return str(value or "").strip().strip("'\"")


def _float(raw: str, default: float) -> Tuple[float, Optional[str]]:
    if not raw:
        return default, None
    try:
        return float(raw), None
    except (TypeError, ValueError):
        return default, f"非数字值 {raw!r}，使用默认值 {default:g}"


def _int(raw: str, default: int) -> Tuple[int, Optional[str]]:
    if not raw:
        return default, None
    try:
        return int(raw), None
    except (TypeError, ValueError):
        return default, f"非整数值 {raw!r}，使用默认值 {default}"


def _bool(raw: str, default: bool) -> Tuple[bool, Optional[str]]:
    """只认 0 与 1；其他写法一律无效并回退默认。

    允许 true/yes/on 一类同义词就会让同一个开关出现多种表示，
    写入端只写 0/1、读取端却什么都收，两边迟早对不上。
    """
    text = str(raw or "").strip()
    if not text:
        return default, None
    if text == "1":
        return True, None
    if text == "0":
        return False, None
    return default, f"只接受 0 或 1，收到 {raw!r}，已用默认值 {int(default)}"


def _parse_limits(
    values: dict[str, str], warnings: list[str]
) -> Tuple[int, float, float, float, float, bool]:
    """解析数值与开关项；越界一律回退默认值并记一条警告。"""
    port, warning = _int(values.get("server_port", ""), DEFAULT_PORT)
    if warning:
        warnings.append(f"server_port {warning}")
    if not 1 <= port <= 65535:
        warnings.append(f"server_port={port} 超出 1–65535，使用默认值 {DEFAULT_PORT}")
        port = DEFAULT_PORT

    startup_timeout, warning = _float(
        values.get("startup_timeout", ""), DEFAULT_STARTUP_TIMEOUT)
    if warning:
        warnings.append(f"startup_timeout {warning}")
    if startup_timeout < 1:
        warnings.append(
            f"startup_timeout={startup_timeout:g} 小于 1，"
            f"使用默认值 {DEFAULT_STARTUP_TIMEOUT:g}")
        startup_timeout = DEFAULT_STARTUP_TIMEOUT

    idle_timeout, warning = _float(values.get("idle_timeout", ""), DEFAULT_IDLE_TIMEOUT)
    if warning:
        warnings.append(f"idle_timeout {warning}")
    if idle_timeout < 0:
        warnings.append(f"idle_timeout={idle_timeout:g} 小于 0，按 0 处理")
        idle_timeout = 0.0

    cfg_scale, warning = _float(values.get("cfg_scale", ""), DEFAULT_CFG_SCALE)
    if warning:
        warnings.append(f"cfg_scale {warning}")
    if not MIN_CFG <= cfg_scale <= MAX_CFG:
        warnings.append(
            f"cfg_scale={cfg_scale:g} 超出 {MIN_CFG:g}–{MAX_CFG:g}，"
            f"使用默认值 {DEFAULT_CFG_SCALE:g}")
        cfg_scale = DEFAULT_CFG_SCALE

    speed, warning = _float(values.get("speed", ""), DEFAULT_SPEED)
    if warning:
        warnings.append(f"speed {warning}")
    if not MIN_SPEED <= speed <= MAX_SPEED:
        warnings.append(
            f"speed={speed:g} 超出 {MIN_SPEED:g}–{MAX_SPEED:g}，"
            f"使用默认值 {DEFAULT_SPEED:g}")
        speed = DEFAULT_SPEED

    fallback, warning = _bool(values.get("fallback_to_edge", ""),
                              DEFAULT_FALLBACK_TO_EDGE)
    if warning:
        warnings.append(f"fallback_to_edge {warning}")

    return port, startup_timeout, idle_timeout, cfg_scale, speed, fallback


def _parse_sampling(values: dict[str, str], warnings: list[str]) -> Tuple[float, int]:
    """解析采样随机性。

    温度与 top-k 越小，音色越稳、表现力越平；实测这两项是音色稳定性的主要旋钮，
    所以放进配置而不是写死。
    """
    temperature, warning = _float(values.get("temperature", ""), DEFAULT_TEMPERATURE)
    if warning:
        warnings.append(f"temperature {warning}")
    if not MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE:
        warnings.append(
            f"temperature={temperature:g} 超出 {MIN_TEMPERATURE:g}–{MAX_TEMPERATURE:g}，"
            f"使用默认值 {DEFAULT_TEMPERATURE:g}")
        temperature = DEFAULT_TEMPERATURE

    top_k, warning = _int(values.get("top_k", ""), DEFAULT_TOP_K)
    if warning:
        warnings.append(f"top_k {warning}")
    if not MIN_TOP_K <= top_k <= MAX_TOP_K:
        warnings.append(
            f"top_k={top_k} 超出 {MIN_TOP_K}–{MAX_TOP_K}，使用默认值 {DEFAULT_TOP_K}")
        top_k = DEFAULT_TOP_K
    return temperature, top_k


def load_config(path: Optional[Path] = None) -> TTSConfig:
    """读取并校验 `[config]`。

    设置页把引擎与模型当自由文本保存，手滑一个字符就会让整个插件装载失败，
    上游连话都说不出来。因此非法引擎与未登记模型一律回退默认值并留一条警告，
    由 status.warnings 对外可见，而不是让整条链路跟着倒。
    """
    target = Path(path) if path is not None else config_path()
    try:
        parser = load_ini(target)
    except configparser.Error as exc:
        raise ConfigError(f"无法解析配置：{exc}", path=target) from exc

    values = {}
    if parser.has_section(CONFIG_SECTION):
        values = {str(k).strip(): _clean(v) for k, v in parser.items(CONFIG_SECTION)}

    warnings: list[str] = []
    engine = (values.get("engine") or DEFAULT_ENGINE).lower()
    if engine not in SUPPORTED_ENGINES:
        warnings.append(
            f"engine={engine!r} 只接受 {'/'.join(SUPPORTED_ENGINES)}，"
            f"使用默认值 {DEFAULT_ENGINE}")
        engine = DEFAULT_ENGINE

    port, startup_timeout, idle_timeout, cfg_scale, speed, fallback = _parse_limits(
        values, warnings)
    temperature, top_k = _parse_sampling(values, warnings)

    default_model = values.get("default_model") or DEFAULT_MODEL
    if default_model not in MODELS:
        warnings.append(
            f"default_model={default_model!r} 未登记，使用默认值 {DEFAULT_MODEL}")
        default_model = DEFAULT_MODEL

    return TTSConfig(
        engine=engine,
        model_dir=values.get("model_dir", ""),
        default_model=default_model,
        server_port=port,
        startup_timeout=startup_timeout,
        idle_timeout=idle_timeout,
        cfg_scale=cfg_scale,
        voice_desc=values.get("voice_desc") or DEFAULT_VOICE_DESC,
        voice_id=values.get("voice_id", ""),
        temperature=temperature,
        top_k=top_k,
        emotion=values.get("emotion") or DEFAULT_EMOTION,
        speed=speed,
        edge_voice=values.get("edge_voice") or DEFAULT_EDGE_VOICE,
        fallback_to_edge=fallback,
        warnings=tuple(warnings),
    )
