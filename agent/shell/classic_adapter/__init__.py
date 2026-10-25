# -*- coding: utf-8 -*-
"""经典界面适配层（内核 ↔ 浏览器界面之间的双向翻译）。

 ┌──────────┐ HTTP/SSE（经典契约） ┌──────────┐ 内核 API ┌────────┐
 │ 经典界面 │ ←──────────────────→ │  适配层  │ ←──────→ │  内核  │
 └──────────┘                      └──────────┘          └────────┘
                        inbound / outbound

方向一：前端 → 服务端（`inbound.py`）
 界面的入参与返回体形状 → 调用内核既有面 → 组回界面形状。

方向二：服务端 → 前端（`outbound.py`）
 内核事件（`tool_call` / `tool_result` / `step_started` / …）
 → 界面认的事件（`tool_start` / `tool_end` / `llm_round` / …）。

纪律
 - 只使用 `App` 已有的公开面（runner / store / live_state / mesh / …），内核无改动。
 - 界面素材沿用 `web_assets/classic/` 下的原文件。
 - 新的交互方式由新的 adapter 承担，本层只做经典界面翻译。

契约常量定义在 `contract.py`。
"""
from __future__ import annotations

from agent.shell.classic_adapter.adapter import ClassicAdapter

__all__ = ["ClassicAdapter"]
