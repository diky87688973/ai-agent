# -*- coding: utf-8 -*-
"""配置 schema：内核配置文件里允许出现的节与键（唯一事实源）。

用途有两个，缺一不可：

1. `check_config_drift.py` 用它校验真实文件：未登记的节/键失败；
2. `get_*` 的默认值可以在这里对照，避免"模板写 700000、代码默认 600000"。

这里不替调用方决定"缺键怎么办"：缺键一律回落到调用方默认值（配置是增强项），
但多出来的键必须在门禁里被拦住 —— 打错一个键名却静默无效，比报错难查得多。
"""
from __future__ import annotations

from typing import Dict

#: 鉴权配置默认值：auth/config.py 与配置门禁共用的唯一来源。
AUTH_DEFAULTS: Dict[str, str] = {
    "mode": "auto",
    "session_hours": "12",
    "max_failures": "5",
    "lock_seconds": "300",
    "trusted_proxies": "",
    "allowed_hosts": "127.0.0.1,localhost,::1",
    "cookie_secure": "auto",
    "provider_module": "",
    "desktop_auto_login": "1",
}

#: `config.ini` 的节 → 键 → 默认值（值只用于文档对照与模板一致性，读取仍由 `config.py` 负责）。
SCHEMA: Dict[str, Dict[str, str]] = {
    "agent": {
        "reasoning_effort": "max",
        "backup_retention_days": "7",
        "max_passes": "64",
        "plugin_tree_only": "0",
    },
    "update": {
        "check_interval_minutes": "30",
    },
    "context": {
        "summary_token_fallback": "64000",
        "full_user_rounds": "5",
        "summary_output_max_chars": "5000",
        "image_turns": "1",
        "image_max": "8",
        "reasoning_replay_tokens": "8000",
    },
    "auth": dict(AUTH_DEFAULTS),

}

#: `web-ui-config.ini` 的节 → 键 → 默认值。
WEB_UI_SCHEMA: Dict[str, Dict[str, str]] = {
    "web-ui": {
        "display_tool_items": "1",
        "display_tool_steps": "0",
    },
}

#: 多模型插件的真实配置节与键。
#: `model` 这一组的节名是动态的（`[model:<id>]`），键集合对所有条目一致；
#: 单个条目可以省略不适用于自己的键（例如 openai 条目不写 `thinking`）。
MULTI_MODEL_SCHEMA: Dict[str, Dict[str, str]] = {
    "model": {
        "provider": "openai",
        "base_url": "",
        "api_key": "",
        "model": "",
        "label": "",
        "context_window": "",
        "compression_percent": "",
        "default": "",
        "max_tokens": "",
        "thinking": "",
        "thinking_budget_tokens": "",
    },
}


def schema_keys(section: str, schema: Dict[str, Dict[str, str]] | None = None) -> set[str]:
    """该节允许的键集合（节不存在返回空集）。"""
    table = SCHEMA if schema is None else schema
    return set(table.get(section, {}))
