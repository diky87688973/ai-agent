# -*- coding: utf-8 -*-
"""`App` 的模型策略面：可用清单、会话模型收敛、窗口与压缩阈值。

模型目录是唯一权威来源；目录未接入或快照失败时按非权威处理。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from agent.config import (
    DEFAULT_COMPRESSION_PERCENT,
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_SUMMARY_TOKEN_FALLBACK,
    compression_threshold,
    get_context,
)
from agent.core.context import SERVICE_MODEL_CATALOG
from agent.core.error_report import report_error
from agent.mechanisms.providers.missing import MissingProvider


class AppModelPolicy:
    """`App` 的模型选择与阈值解析。"""

    def available_models(self) -> list:
        """可选的模型 id 列表（会话选模型只能从中挑）。

        目录权威时每次现读快照：插件配置是热读的，缓存名单会让下拉、
        白名单与配置各说各话。非权威态才用装配注入的 `_available_models`。
        """
        snapshot = self._catalog_snapshot()
        if snapshot is not None and snapshot.authoritative:
            return [item.id for item in snapshot.entries]
        return list(self._available_models)

    def _catalog_snapshot(self) -> Any:
        """当前目录快照；未接入目录或快照失败时返回 None（调用方按非权威处理）。"""
        catalog = self.model_catalog
        snapshot = getattr(catalog, "snapshot", None)
        if not callable(snapshot):
            return None
        try:
            return snapshot()
        except Exception as exc:
            # 快照失败不能把整条请求链路带崩：按无模型处理，下一回合重读。
            report_error("app.model_catalog", exc)
            return None

    @property
    def model_catalog(self) -> Any:
        """模型目录（唯一权威来源）；未接入时返回 None。"""
        return (self.context.get(SERVICE_MODEL_CATALOG)
                if self.context.has(SERVICE_MODEL_CATALOG) else None)

    def model_config(self) -> Dict[str, Any]:
        """`/health` 的模型配置态：来源 / 权威 / 降级，三者都可机读。"""
        snapshot = self._catalog_snapshot()
        return {
            "source": self.model_config_state,
            "authoritative": bool(snapshot is not None and snapshot.authoritative),
            "degraded": self.model_config_state == "none",
        }

    def model_for(self, conversation_id: str) -> str:
        """解析会话模型，并把已被删掉的 id 收敛回默认值（读取点收敛）。

        插件改配置后，旧标签页可能还拿着一个已经不存在的 id。这里写回默认值，
        而不是让它一路撞到 `未配置的模型` 错误 —— 显示同步与状态写入必须分开。
        """
        state = self.live_state
        current = str(state.get_model(conversation_id) or "").strip()
        allowed = self.available_models()
        if not allowed or not current or current in allowed:
            return current
        snapshot = self._catalog_snapshot()
        fallback = (str(snapshot.default_id or "") if snapshot is not None
                    and snapshot.authoritative else str(state.default_model or "")).strip() or allowed[0]
        state.set_model(conversation_id, fallback)
        report_error(
            "app.model",
            f"会话模型 {current!r} 不在可用清单，已回落 {fallback!r}",
            conversation_id=str(conversation_id or ""),
        )
        return fallback

    def context_window_for(self, conversation_id: str) -> int:
        """会话当前所用模型的上下文窗口（token）。

        窗口是模型的物理上限；压缩阈值按它计算，换模型后下一回合重算。
        目录取条目自带的 `context_window`；拿不到时给 0。
        """
        snapshot = self._catalog_snapshot()
        if snapshot is not None and snapshot.authoritative:
            entry = snapshot.entry(self.model_for(conversation_id))
            if entry is not None:
                return entry.context_window or DEFAULT_CONTEXT_WINDOW
        return 0

    def compression_percent_for(self, conversation_id: str) -> int:
        """会话当前模型的压缩百分比；模型缺失时用默认 70。"""
        snapshot = self._catalog_snapshot()
        if snapshot is not None and snapshot.authoritative:
            entry = snapshot.entry(self.model_for(conversation_id))
            if entry is not None:
                return entry.compression_percent
        return DEFAULT_COMPRESSION_PERCENT

    def compression_threshold_for(self, conversation_id: str) -> int:
        """会话当前模型的压缩触发阈值；窗口缺失时用配置回退值。"""
        fallback = int(get_context().get("summary_token_fallback")
                       or DEFAULT_SUMMARY_TOKEN_FALLBACK)
        return compression_threshold(
            self.context_window_for(conversation_id),
            self.compression_percent_for(conversation_id),
            fallback,
        )

    def reload_model_config(self, config_path: Optional[Path] = None) -> str:
        """返回模型配置来源说明；模型由多模型插件维护。"""
        if self.model_config_state == "catalog":
            return "模型目录权威，配置由多模型插件维护"
        return "模型由多模型插件维护"

    def refresh_model_config(self, config_path: Optional[Path] = None) -> str:
        """插件装卸后重算权威来源：目录接管则刷新路由，否则清空模型。"""
        snapshot = self._catalog_snapshot()
        if snapshot is not None and snapshot.authoritative:
            self.model_config_state = "catalog"
            self._available_models = [item.id for item in snapshot.entries]
            self.live_state.default_model = snapshot.default_id
            self._reload_policy(self._available_models, snapshot.default_id, False)
            return ""
        return self._mark_model_config_none()

    def _reload_policy(self, allowed_ids: Any, default_id: str, fallback: bool) -> None:
        policy = getattr(self.provider, "reload_policy", None)
        if callable(policy):
            policy(allowed_ids=list(allowed_ids),
                   default_id=default_id, fallback_to_default=fallback)

    def _mark_model_config_none(self) -> str:
        self.model_config_state = "none"
        self._available_models = []
        self.live_state.default_model = ""
        reloader = getattr(self.provider, "reload_default", None)
        if callable(reloader):
            reloader(MissingProvider())
        self._reload_policy((), "", False)
        return "未配置可用模型：请在 multi_model 插件中配置至少一个模型"
