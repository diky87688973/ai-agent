# -*- coding: utf-8 -*-
"""壳层服务登记名（装配点 register / 使用方 get）。

`runner` / `classic_adapter` 仅由壳层与装配根引用；core 的服务词汇表不含这两项。
"""
from __future__ import annotations

SERVICE_RUNNER = "runner"                        # 后台会话运行器
SERVICE_CLASSIC_ADAPTER = "classic_adapter"      # 经典界面适配层（双向翻译）
