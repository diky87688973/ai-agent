# -*- coding: utf-8 -*-
"""AI角色扮演插件入口。

插件只提供装配工厂：读配置、建运行时、造工具/端点/事件订阅/模式尾部。
文本规范、合成、队列与播放器分别在 `text.py`、`provider.py`、`runtime.py`
与 `ui/` 中，互不越界。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from agent.core.error_report import report_error

from .config import AICosplayConfig, config_path, load_config
from .provider import create_provider
from .runtime import AICosplayRuntime
from .runtime_worker import ACK_STATUSES, ERROR, PLAYED
from .tool import AICosplayTool


def _voice_directive(user_salutation: str, assistant_salutation: str,
                     tone: str) -> str:
    return (
        "## AI说话\n"
        "必须主动使用 ai_speek 工具与用户沟通!!!\n"
        "这是让AI开口说话的工具，是除正文以外的另一条输出通道，内容会经过语音播放，"
        "关键内容必须在 ai_speek 工具播报出来，以照顾视觉障碍者。\n"
        f"对用户称「{user_salutation}」，自称「{assistant_salutation}」。语气保持{tone}。\n"
        "说话要自然、代入当前角色身份和个性，更重要的是模仿人类口语说话。"
    )


def _config_path() -> Path:
    """本插件配置文件路径；配置归属测试用同一入口。"""
    return config_path()


def _log_warnings(config: AICosplayConfig) -> None:
    for warning in config.warnings:
        report_error("plugin.ai_cosplay.config", ValueError(warning), plugin="ai_cosplay")


def _turn_handler(runtime: AICosplayRuntime) -> Callable[[Any], None]:
    def _handler(event: Any) -> None:
        data = getattr(event, "data", None) or {}
        cid = str(data.get("conversation_id") or "")
        if not cid:
            return
        if bool(data.get("stopped")) or bool(data.get("halted")):
            runtime.stop_cid(cid, "turn_stopped")

    return _handler


def _error_handler(runtime: AICosplayRuntime) -> Callable[[Any], None]:
    def _handler(event: Any) -> None:
        data = getattr(event, "data", None) or {}
        cid = str(data.get("conversation_id") or "")
        if cid:
            runtime.stop_cid(cid, ERROR)

    return _handler


def _config_payload(runtime: AICosplayRuntime) -> Any:
    config = runtime.config
    return 200, {
        "ok": True,
        "engine": config.engine,
        "voice": config.voice,
        "user_salutation": config.user_salutation,
        "assistant_salutation": config.assistant_salutation,
        "tone": config.tone,
        "max_segment_chars": config.max_segment_chars,
        "play_interval_ms": config.play_interval_ms,
        "sync_playback": config.sync_playback,
        "speed": config.speed,
    }


def _status_payload(runtime: AICosplayRuntime) -> Any:
    return 200, {"ok": True, **runtime.status()}


def _played_handler(runtime: AICosplayRuntime) -> Callable[[dict], Any]:
    def _handler(args: dict) -> Any:
        body = args.get("body") if isinstance(args, dict) else None
        payload = body if isinstance(body, dict) else {}
        cid = str(payload.get("conversation_id")
                  or args.get("conversation_id") or "")
        call_id = str(payload.get("call_id") or "").strip()
        status = str(payload.get("status") or PLAYED).strip().lower()
        detail = str(payload.get("detail") or "").strip()[:300]
        if not call_id:
            return 400, {"ok": False, "error": "缺少 call_id"}
        if status not in ACK_STATUSES:
            return 400, {"ok": False, "error": "未知播放状态"}
        matched = runtime.ack_playback(cid, call_id, status, detail)
        return 200, {"ok": True, "matched": matched}

    return _handler


def make_runtime(ctx: Any) -> AICosplayRuntime:
    """装配期构造运行时：读配置、留警告、建合成提供者。"""
    config = load_config()
    _log_warnings(config)
    return AICosplayRuntime(config, create_provider(config.engine))


def make_tool(ctx: Any, runtime: AICosplayRuntime) -> AICosplayTool:
    """`ai_speek` 工具：把模型要说的话交给运行时播报。"""
    return AICosplayTool(runtime)


def make_route_config(ctx: Any, runtime: AICosplayRuntime) -> Callable[..., Any]:
    """`GET config`：当前语音配置快照。"""
    def handler(_query: Any) -> Any:
        return _config_payload(runtime)
    return handler


def make_route_status(ctx: Any, runtime: AICosplayRuntime) -> Callable[..., Any]:
    """`GET status`：当前播放队列状态。"""
    def handler(_query: Any) -> Any:
        return _status_payload(runtime)
    return handler


def make_route_played(ctx: Any, runtime: AICosplayRuntime) -> Callable[..., Any]:
    """`POST played`：前端回报播放结果。"""
    return _played_handler(runtime)


def make_event_turn_ended(ctx: Any, runtime: AICosplayRuntime) -> Callable[[Any], None]:
    """回合结束订阅；事件名取 `agent.core.event_name.TURN_ENDED`。"""
    return _turn_handler(runtime)


def make_event_error(ctx: Any, runtime: AICosplayRuntime) -> Callable[[Any], None]:
    """错误订阅；事件名取 `agent.core.event_name.ERROR`。"""
    return _error_handler(runtime)


def make_mode_tail(ctx: Any, runtime: AICosplayRuntime) -> Callable[[str], str]:
    """模式尾部指令：提供者就绪时才注入，否则返回空串。"""
    def tail(cid: str) -> str:
        if not runtime.provider_ready():
            return ""
        return _voice_directive(
            runtime.config.user_salutation,
            runtime.config.assistant_salutation,
            runtime.config.tone,
        )
    return tail
