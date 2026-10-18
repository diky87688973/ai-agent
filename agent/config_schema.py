# -*- coding: utf-8 -*-
"""配置 schema：内核配置文件里**允许出现**的节与键（唯一事实源）。

用途有两个，缺一不可：

1. `check_config_drift.py` 用它做双向比对 —— `.example` 缺键 / 多键、真实文件多键都失败；
2. `get_*` 的默认值可以在这里对照，避免"模板写 700000、代码默认 600000"。

这里**不**替调用方决定"缺键怎么办"：缺键一律回落到调用方默认值（配置是增强项），
但**多出来的键**必须在门禁里被拦住 —— 打错一个键名却静默无效，比报错难查得多。
"""
from __future__ import annotations

from typing import Dict

#: `config.ini` 的节 → 键 → 默认值（值只用于文档对照与模板一致性，读取仍由 `config.py` 负责）。
SCHEMA: Dict[str, Dict[str, str]] = {
    "model_reasoning": {
        "api_base_url": "",
        "api_key": "",
        "model": "",
        "models": "",
    },
    "agent": {
        "reasoning_effort": "max",
        "backup_retention_days": "7",
        "max_passes": "64",
        "user_rules_file": "",
        "plugin_tree_only": "0",
    },
    "context": {
        "summary_token_threshold": "700000",
        "full_user_rounds": "1",
        "summary_output_max_chars": "5000",
        "image_turns": "999999",
        "image_max": "999999",
        "model_context_window": "1000000",
        "reasoning_replay_tokens": "8000",
    },
}

#: `web-ui-config.ini` 的节 → 键 → 默认值。
WEB_UI_SCHEMA: Dict[str, Dict[str, str]] = {
    "web-ui": {
        "display_tool_items": "1",
        "display_tool_steps": "0",
    },
}

#: `plugins/multi_model/plugin-config.ini.example` 的节与键。
#: `model` 这一组的节名是动态的（`[model:<id>]`），键集合对所有条目一致；
#: 单个条目可以省略不适用于自己的键（例如 openai 条目不写 `thinking`）。
MULTI_MODEL_SCHEMA: Dict[str, Dict[str, str]] = {
    "base": {
        "id": "multi_model",
        "enable": "1",
        "name": "",
        "icon": "",
        "version": "",
        "desc": "",
    },
    "model": {
        "provider": "openai",
        "base_url": "",
        "api_key": "",
        "model": "",
        "label": "",
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
