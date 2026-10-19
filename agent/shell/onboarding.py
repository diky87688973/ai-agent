# -*- coding: utf-8 -*-
"""首次启动的设置向导：读取/保存模型配置，并让当前进程立即生效。

Web 入口在没有任何可用模型时也启动服务；`/setup` 页只负责收集网关与密钥。
保存走设置页同一条 `save_host` 链路，因此 `app.reload_model_config()` 会立即
重建 provider，不需要重启进程。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from agent.config import get_model_reasoning, is_placeholder_api_key
from agent.shell.settings_panel import save_host


def status(app: Any, *, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """给向导页的公开状态；密钥只返回是否已填，不回明文。"""
    cfg = get_model_reasoning(config_path)
    key = str(cfg.get("api_key") or "")
    return {
        "ok": True,
        "configured": getattr(app, "model_config_state", "none") != "none",
        "source": str(getattr(app, "model_config_state", "none") or "none"),
        "api_base_url": str(cfg.get("api_base_url") or ""),
        "model": str(cfg.get("model") or ""),
        "context_window": int(cfg.get("context_window") or 0),
        "has_key": bool(key and not is_placeholder_api_key(key)),
    }


def save(
    app: Any,
    body: Any,
    *,
    config_path: Optional[Path] = None,
) -> Tuple[int, Dict[str, Any]]:
    """保存向导字段并热加载模型；失败时返回可读原因。"""
    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "缺少配置内容"}
    current = get_model_reasoning(config_path)
    base_url = str(body.get("api_base_url") or "").strip()
    api_key = str(body.get("api_key") or "").strip()
    model = str(body.get("model") or "").strip() or str(current.get("model") or "")
    if not base_url.startswith(("http://", "https://")):
        return 400, {"ok": False, "error": "网关地址必须以 http:// 或 https:// 开头"}
    if api_key and is_placeholder_api_key(api_key):
        return 400, {"ok": False, "error": "API Key 仍是占位值，请填写真实密钥"}
    if not api_key and not status(app, config_path=config_path)["has_key"]:
        return 400, {"ok": False, "error": "请填写 API Key"}

    updates: Dict[str, Any] = {"api_base_url": base_url, "model": model}
    if api_key:
        updates["api_key"] = api_key
    window = body.get("context_window")
    if window not in (None, ""):
        try:
            context_window = int(window)
        except (TypeError, ValueError):
            return 400, {"ok": False, "error": "上下文窗口必须是正整数"}
        if context_window < 1:
            return 400, {"ok": False, "error": "上下文窗口必须是正整数"}
        updates["context_window"] = context_window

    saved = save_host({"model_reasoning": updates}, app, config_path=config_path)
    if not saved.get("ok"):
        return 400, {"ok": False, "error": str(saved.get("error") or "保存失败")}
    if saved.get("reload_error"):
        return 400, {"ok": False, "error": str(saved["reload_error"])}
    if getattr(app, "model_config_state", "none") == "none":
        return 400, {"ok": False, "error": "保存后仍没有可用模型，请检查网关、密钥和模型名"}
    return 200, {"ok": True, **status(app, config_path=config_path)}
