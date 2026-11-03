# -*- coding: utf-8 -*-
"""AI角色扮演插件入口。

插件只做装配：读配置、建运行时、注册工具/端点/开屏脚本/事件订阅。
文本规范、合成、队列与播放器分别在 `text.py`、`provider.py`、`runtime.py`
与 `ui/` 中，互不越界。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, List

from agent.capabilities.plugin_paths import load_plugin_paths
from agent.core import event_name as ev
from agent.core.error_report import report_error

from .config import AICosplayConfig, config_path, load_config
from .provider import create_provider
from .runtime import AICosplayRuntime
from .runtime_worker import ACK_STATUSES, ERROR, PLAYED
from .tool import AICosplayTool

PATHS = load_plugin_paths(__file__)

PLUGIN_VERSION = "1.0"


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


def register(ctx: Any) -> List[Callable[[], None]]:
    """装配插件；任一注册失败时先释放运行时再抛出。"""
    config = load_config()
    _log_warnings(config)
    runtime = AICosplayRuntime(config, create_provider(config.engine))
    disposers: List[Callable[[], None]] = [runtime.dispose]
    try:
        disposers.append(ctx.register_tool(AICosplayTool(runtime)))
        disposers.append(ctx.set_subagent_tools([]))
        disposers.append(ctx.add_ui_item(
            PATHS["panel"], kind="panel",
            props={"action": "ai_cosplay.toggle",
                   "binding": {"existing": ["#aiCosplaySlot"]},
                   "scripts": ["ui/player.js", "ui/tool-view.js"],
                   "styles": ["ui/player.css"]}, order=10))
        disposers.append(ctx.add_route(
            "GET", "config", lambda _query: _config_payload(runtime),
            slot_path="app/backend/http/routes/ai_cosplay-config"))
        disposers.append(ctx.add_route(
            "GET", "status", lambda _query: _status_payload(runtime),
            slot_path="app/backend/http/routes/ai_cosplay-status"))
        disposers.append(ctx.add_route(
            "POST", "played", _played_handler(runtime),
            slot_path="app/backend/http/routes/ai_cosplay-played"))
        disposers.append(ctx.subscribe(
            ev.TURN_ENDED, _turn_handler(runtime),
            path="app/backend/events/subscriptions/turn_ended/ai_cosplay-turn-ended"))
        disposers.append(ctx.subscribe(
            ev.ERROR, _error_handler(runtime),
            path="app/backend/events/subscriptions/error/ai_cosplay-error"))
        def _mode_tail(cid: str) -> str:
            return _voice_directive(
                runtime.config.user_salutation,
                runtime.config.assistant_salutation,
                runtime.config.tone,
            ) if runtime.provider_ready() else ""

        # ai_cosplay 只服务主智能体：子智能体不注入语音指令，避免子会话被播报语义污染。
        disposers.append(ctx.add_mode_tail(
            _mode_tail,
            path="app/backend/prompt/mode-tails/ai_cosplay-voice",
            subagent_visible=False))
        ctx.set_runtime(runtime)
    except Exception:
        runtime.dispose()
        raise
    return disposers
