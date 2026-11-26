# -*- coding: utf-8 -*-
"""语音合成插件入口。

插件只做装配：读配置、构造服务、给设置页与状态页提供只读端点。
引擎实现在 `edge_provider.py` 与 `breeze_provider.py`，进程管理在
`supervisor.py`，对外门面在 `service.py`。
"""
from __future__ import annotations

import base64
import dataclasses
from typing import Any, Callable, Dict, Optional

from agent.common.tts_contract import (
    TTSCapabilities,
    TTSEngineUnavailable,
    TTSProvider,
    TTSRequest,
    TTSResult,
    TTSUnavailable,
)
from agent.core.error_report import report_error

from . import schema
from .config import TTSConfig, config_path, load_config
from .provider import create_provider, create_voice_lab
from .service import INSTALL_HINT, TTSService


def _log_warnings(config: TTSConfig) -> None:
    for warning in config.warnings:
        report_error("plugin.tts.config", ValueError(warning), plugin="tts")


def _edge_provider(config: TTSConfig) -> TTSProvider:
    return create_provider(dataclasses.replace(config, engine="edge"))


def _fallback_provider(config: TTSConfig) -> Optional[TTSProvider]:
    """按配置决定是否装配兜底：engine 为 edge 或开关关闭时返回 None。

    装配期拿到的 fallback 不是 None 就说明开启，下游不重读开关。
    """
    if config.engine == "edge" or not config.fallback_to_edge:
        return None
    return _edge_provider(config)


class _UnavailableProvider:
    """本地引擎装不起来、且用户关掉了兜底时用它。

    插件照常装载（不连带上游一起挂），但任何一次合成都会如实报错并附带安装指引；
    不复用 edge 顶上 —— 那会让“没装模型”变成“默默用网给”。
    """

    name = "breeze"

    def __init__(self, reason: str) -> None:
        self._reason = str(reason or "本地引擎不可用")

    def available(self) -> bool:
        return False

    def capabilities(self) -> TTSCapabilities:
        return TTSCapabilities(supports_instruction=False, supports_speed=False,
                               supports_cfg=False, needs_pinyin_hints=False)

    def synthesize(self, request: TTSRequest) -> TTSResult:
        raise TTSUnavailable(f"{self._reason}；{INSTALL_HINT}")

    def release_idle(self) -> bool:
        return False

    def dispose(self) -> None:
        return None


def make_service(ctx: Any) -> TTSService:
    """装配期构造合成服务。

    本地引擎装配失败不能让插件装载失败，否则上游连话都说不出。但退化必须可见：
    有兜底就拿它顶上并把原因写进 service，`GET status` 才能报出 `degraded_reason`
    与 `install_hint`；用户关掉兜底时则干脆不换引擎，合成时如实报错。
    """
    config = load_config()
    _log_warnings(config)
    fallback = _fallback_provider(config)

    try:
        primary = create_provider(config)
    except TTSEngineUnavailable as exc:
        report_error("plugin.tts.service", exc, plugin="tts")
        reason = f"本地引擎不可用：{exc}"
        substitute = fallback if fallback is not None else _UnavailableProvider(reason)
        return TTSService(config, substitute, None, None, reason)

    return TTSService(config, primary, fallback, create_voice_lab(config, primary))


def make_route_config(ctx: Any, service: TTSService) -> Callable[..., Any]:
    """`GET config`：当前合成配置快照。"""
    def handler(_query: Any) -> Any:
        config = service.config
        return 200, {
            "ok": True,
            "engine": config.engine,
            "default_model": config.default_model,
            "model_dir": config.model_dir,
            "server_port": config.server_port,
            "idle_timeout": config.idle_timeout,
            "cfg_scale": config.cfg_scale,
            "voice_desc": config.voice_desc,
            "voice_id": config.voice_id,
            "emotion": config.emotion,
            "edge_voice": config.edge_voice,
            "fallback_to_edge": config.fallback_to_edge,
            "config_path": str(config_path()),
        }
    return handler


def make_route_status(ctx: Any, service: TTSService) -> Callable[..., Any]:
    """`GET status`：引擎就绪情况与能力矩阵。"""
    def handler(_query: Any) -> Any:
        return 200, {"ok": True, **service.status()}
    return handler


_NO_LAB = (400, {"ok": False,
                 "error": "当前引擎没有音色库；音色工作台只在本地引擎下可用"})


def _body(args: Any) -> Dict[str, Any]:
    if isinstance(args, dict):
        body = args.get("body")
        if isinstance(body, dict):
            return body
    return {}


def _dims(body: Dict[str, Any]) -> Dict[str, str]:
    """接受带 dim_ 前缀与不带两种键名：设置页用前缀避免与配置键撞名。"""
    out: Dict[str, str] = {}
    for key in schema.DIMENSION_ORDER:
        value = body.get(f"dim_{key}")
        if value is None or str(value) == "":
            value = body.get(key)
        out[key] = str(value or "")
    return out


def make_route_voice_options(ctx: Any, service: TTSService) -> Callable[..., Any]:
    """`GET voice/options`：维度、预设与样板句。界面据此渲染，不写死措辞。"""
    def handler(_query: Any) -> Any:
        if service.lab is None:
            return _NO_LAB
        return 200, {"ok": True, **schema.options_payload()}
    return handler


def make_route_voice_preview(ctx: Any, service: TTSService) -> Callable[..., Any]:
    """`POST voice/preview`：按维度组合合成样板，不入库。"""
    def handler(args: Any) -> Any:
        lab = service.lab
        if lab is None:
            return _NO_LAB
        dims = _dims(_body(args))
        try:
            result = lab.preview(dims)
        except ValueError as exc:
            # VoiceLabError 与 normalize 的 ValueError 都算调用方参数错
            return 400, {"ok": False, "error": str(exc)}
        except TTSEngineUnavailable as exc:
            return 503, {"ok": False, "error": str(exc)}
        return 200, {
            "ok": True,
            "instruction": schema.describe(dims),
            "mime": result.mime,
            "sample_rate": result.sample_rate,
            "audio": base64.b64encode(result.audio).decode("ascii"),
        }
    return handler


def make_route_voice_save(ctx: Any, service: TTSService) -> Callable[..., Any]:
    """`POST voice/save`：把当前组合固化成命名音色。"""
    def handler(args: Any) -> Any:
        lab = service.lab
        if lab is None:
            return _NO_LAB
        body = _body(args)
        try:
            saved = lab.save(_dims(body), str(body.get("id") or ""))
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}
        except TTSEngineUnavailable as exc:
            return 503, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, **saved}
    return handler


def make_route_voice_list(ctx: Any, service: TTSService) -> Callable[..., Any]:
    """`GET voice/list`：已注册音色与各自的维度组合。"""
    def handler(_query: Any) -> Any:
        lab = service.lab
        if lab is None:
            return _NO_LAB
        try:
            voices = lab.list_voices()
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}
        except TTSEngineUnavailable as exc:
            return 503, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, "voices": voices, "current": service.config.voice_id}
    return handler


def make_route_voice_delete(ctx: Any, service: TTSService) -> Callable[..., Any]:
    """`POST voice/delete`：删内存与磁盘两处。"""
    def handler(args: Any) -> Any:
        lab = service.lab
        if lab is None:
            return _NO_LAB
        try:
            removed = lab.delete_voice(str(_body(args).get("id") or ""))
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}
        except TTSEngineUnavailable as exc:
            return 503, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, **removed}
    return handler


def make_route_voice_current(ctx: Any, service: TTSService) -> Callable[..., Any]:
    """`POST voice/current`：把配置里的 voice_id 换成指定音色。"""
    def handler(args: Any) -> Any:
        lab = service.lab
        if lab is None:
            return _NO_LAB
        try:
            changed = lab.set_current(str(_body(args).get("id") or ""))
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}
        except TTSEngineUnavailable as exc:
            return 503, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, **changed}
    return handler
