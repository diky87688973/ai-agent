# -*- coding: utf-8 -*-
"""Provider 共用的工具 schema 规范化。"""
from __future__ import annotations

from typing import Any, Dict


def _object_schema(raw: Any) -> Dict[str, Any]:
    """补齐 `type` / `properties`，保证拿到的是合法 object schema。"""
    schema = dict(raw) if isinstance(raw, dict) else {}
    if not isinstance(schema.get("type"), str) or not schema["type"]:
        schema["type"] = "object"
    if schema["type"] == "object" and not isinstance(schema.get("properties"), dict):
        schema["properties"] = {}
    return schema


def tool_parameters(tool: Dict[str, Any]) -> Dict[str, Any]:
    """工具声明 → 完整的 JSON Schema 对象（供两家线格式共用）。

    三种声明形状，来源是同一份 `ToolRegistry.schemas()`：

    1. 逻辑形 `{"name", "description", "parameters": {参数名: 片段}}` —— `parameters`
       是属性映射，必须包装成 `{"type": "object", "properties": {...}}`；
    2. OpenAI 线形 `{"type": "function", "function": {...}}` —— `parameters` 已是完整 schema；
    3. Anthropic 形（自带 `input_schema`）—— 已是完整 schema。

    包装时必定补 `type: "object"`：把属性映射直接当 schema 下发，线上会得到
    `type: null`，Anthropic 一侧直接 400（OpenAI 兼容网关不校验，所以这个缺陷只在
    Anthropic 协议上暴露）。
    """
    fn = tool.get("function") if isinstance(tool.get("function"), dict) else tool
    raw = fn.get("input_schema")
    if not isinstance(raw, dict):
        raw = fn.get("parameters")
        if fn is tool and tool.get("type") != "function":
            # 逻辑形：`parameters` 是属性映射，不是 schema
            raw = {"type": "object", "properties": raw if isinstance(raw, dict) else {}}
    return _object_schema(raw)
