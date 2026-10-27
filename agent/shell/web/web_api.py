# -*- coding: utf-8 -*-
"""Web JSON API：SSE 连接表、运行态与模型可用性（WebShell）。

WebShell 的业务动作按能力分布在同目录的 mixin：`web_chat` 输入与队列、
`web_sessions` 历史与标题、`web_files` 文件与媒体、`web_contributions`
插件贡献、`web_state` 会话设置与 UI 状态。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from agent.core import event_name as ev
from agent.core.error_report import report_error
from agent.core.input_attachments import MAX_IMAGES
from agent.mechanisms.session_title import TitleStore
from agent.shell.fspaths import normalize_roots
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER
from agent.shell.sse import Channel, sse_payload
from agent.shell.web.web_chat import ChatActions
from agent.shell.web.web_contributions import ContributionActions
from agent.shell.web.web_files import FileViewerActions
from agent.shell.web.web_sessions import SessionActions
from agent.shell.web.web_state import UiStateActions
from agent.shell.web.web_subagents import SubagentActions

if TYPE_CHECKING:  # 只为注解：壳层不得在运行期依赖装配根（A2）
    from agent.app import App


class WebShell(
    ChatActions,
    SessionActions,
    SubagentActions,
    FileViewerActions,
    ContributionActions,
    UiStateActions,
):
    """Web 壳：持有一张 SSE 连接表 + 一张会话运行表，服务于共享的 App。"""

    def __init__(
        self,
        app: App,
        media_root: Optional[Path] = None,
        *,
        fs_roots: Any = None,
        titles_dir: Optional[Path] = None,
        title_generator: Any = None,
        workspace_root: Optional[Path] = None,
    ) -> None:
        self.app = app
        self.media_root = Path(media_root).resolve() if media_root else None
        # `/workspace/<相对路径>` 静态路由的根 —— 经典 UI 的 Markdown 渲染会把
        # 工作区绝对路径的图片/视频重写成这个路由（`agent-ui.js` 的
        # `markedImageHref`）。命名沿用，缺省 `<data_root>/workspace`。
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        # 可见根：单个 Path / Path 列表 / None（None = 不限根，仅供测试与显式放开）
        self.fs_roots: List[Path] = normalize_roots(fs_roots)
        self.titles = TitleStore(Path(titles_dir) if titles_dir else None)
        self.title_generator = title_generator
        self._channels: List[Channel] = []
        self._lock = threading.Lock()
        self._runs: Dict[str, str] = {}  # cid → run_id（当前活跃回合）
        # 把壳自己交给适配层：它会复用本壳的 `_derive_title` 派生会话标题，
        # 避免适配层另写一套截断口径导致两侧标题不一致。
        classic = self._classic_adapter()
        if classic is not None:
            classic.adopt_shell(self)

    def _classic_adapter(self) -> Any:
        """当前上下文里的经典界面适配层；未装配时为 None。"""
        ctx = getattr(self.app, "context", None)
        if ctx is None or not ctx.has(SERVICE_CLASSIC_ADAPTER):
            return None
        return ctx.get(SERVICE_CLASSIC_ADAPTER)

    def attach(self) -> Channel:
        channel = Channel()
        with self._lock:
            self._channels.append(channel)
        return channel

    def detach(self, channel: Channel) -> None:
        channel.close()
        with self._lock:
            if channel in self._channels:
                self._channels.remove(channel)

    def broadcast(self, event: ev.Event) -> None:
        """把内核事件广播到全部 SSE 连接（EventBus 通配订阅者）。"""
        frame = sse_payload(event)
        if event.type == ev.TURN_STARTED:
            cid = str((event.data or {}).get("conversation_id") or "")
            rid = str((event.data or {}).get("run_id") or "")
            if cid and rid:
                with self._lock:
                    self._runs[cid] = rid
        elif event.type == ev.TURN_ENDED:
            cid = str((event.data or {}).get("conversation_id") or "")
            with self._lock:
                self._runs.pop(cid, None)
        with self._lock:
            channels = list(self._channels)
        for channel in channels:
            channel.push(frame)

    def _announce_model(self, cid: str, model: str) -> None:
        """把模型变化广播给同会话的其它标签页（与 announce_plugins 同构）。

        只有发起方写服务端；接收方只更新页头与本地 tab 字段，不再回写，
        否则两个标签页会互相触发写服务端，形成重复写与竞态。
        """
        classic = self._classic_adapter()
        announce = getattr(classic, "announce_model", None) if classic is not None else None
        if callable(announce):
            announce(cid, model)

    def _remember_run(self, cid: str, run_id: str) -> None:
        """记录空闲直接启动的 run_id，供 stop 回执关联；已结束的回合不登记。"""
        key = str(cid or "").strip()
        rid = str(run_id or "").strip()
        if not key or not rid:
            return
        mesh = getattr(self.app, "mesh", None)
        if mesh is None or not mesh.is_running(key):
            return
        with self._lock:
            self._runs[key] = rid

    def active_run(self, cid: str) -> str:
        with self._lock:
            return str(self._runs.get(str(cid or "").strip()) or "")

    @property
    def channel_count(self) -> int:
        with self._lock:
            return len(self._channels)

    def available_models(self) -> List[str]:
        """可选的模型 id 列表（只给 id，绝不给 key / url）。

        凭据不下发：浏览器能拿到的东西，任何能打开页面的人都能抄走。
        会话选模型选的是"服务端已配置的哪一个 id"，凭据始终留在服务端。
        """
        models = getattr(self.app, "available_models", None)
        if callable(models):
            return [str(m) for m in (models() or [])]
        return []

    def model_labels(self) -> Dict[str, str]:
        catalog = getattr(self.app, "model_catalog", None)
        if catalog is None:
            return {}
        try:
            snapshot = catalog.snapshot()
        except Exception as exc:
            report_error("agent.shell.web.web_api.model_labels", exc)
            return {}
        return {item.id: (item.label or item.id) for item in snapshot.entries}

    def health(self) -> Tuple[int, Dict[str, Any]]:
        """服务健康 + 顶栏所需的模型信息。"""
        provider = self.app.provider
        model = str(getattr(provider, "model", "") or "")
        # 可选模型清单以多模型插件目录为准；provider 可能不持有 `allowed_models`，
        # 只回一个模型会让前端模型下拉只剩一项，用户选其它模型还会被当非法拒掉。
        source = str(getattr(self.app, "model_config_state", "") or "")
        allowed = self.available_models()
        if source != "none":
            if not allowed:
                allowed = list(getattr(provider, "allowed_models", ()) or ())
                if not allowed:
                    allowed = [model] if model else []
            # 无白名单清单时把当前模型作为唯一候选下发（前端据此渲染模型菜单）；
            # 真正的多模型名单由多模型插件目录提供。
            if not allowed and model:
                allowed = [model]
        elif not allowed:
            # 降级态保持空清单：不能报出一个实际选不了的 id（顶栏也不会假装有模型）。
            model = ""
        settings = getattr(self.app, "model_config", None)
        model_config = settings() if callable(settings) else {}
        return 200, {
            "ok": True,
            "service": "agent.web",
            "conversation_buckets": (
                self.app.session_contexts.active_count()
                if self.app.session_contexts is not None
                else 0
            ),
            "sse_channels": self.channel_count,
            "tools": len(self.app.registry.names()),
            "model": model,
            "allowed_models": allowed,
            "model_labels": self.model_labels(),
            # 全局默认档位：会话还没回填前，顶栏先按它显示（会话值以 ui-state 为准）。
            "reasoning_effort": (self.app.live_state.default_effort
                                 if self.app.live_state is not None else "high"),
            "max_images": MAX_IMAGES,
            "model_config": model_config,
        }
