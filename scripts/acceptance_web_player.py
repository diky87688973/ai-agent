# -*- coding: utf-8 -*-
"""AI说话播放器的浏览器验收：注入、插件事件送达、关闭后撤销。

被 `acceptance_web.py` 调用，不单独作为 CI 步骤。
"""
from __future__ import annotations

import sys
from typing import Any


def run(acc: Any) -> None:
    """在已启动的验收服务上跑播放器场景。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [SKIP] AI说话播放器（未安装 playwright：pip install -e \".[ui]\"）")
        return
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:
            print(f"[scripts.acceptance_web_player.run] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            print(f"  [SKIP] AI说话播放器（Chromium 不可用：{type(exc).__name__}）")
            return
        try:
            page = browser.new_page()
            errors: list = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(acc.base + "/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)
            acc.check(
                "AI说话播放条已注入",
                page.evaluate(
                    "() => !!window.aiAgentAISpeak && !!document.getElementById('aiSpeakPlayer')"
                ),
            )
            page.evaluate(
                """() => document.dispatchEvent(new CustomEvent("ai-agent:plugin-event", {
                    detail: {type: "plugin_event", plugin: "ai_speak", event: "stop",
                             conversation_id: "accept-web-ai"}
                }))"""
            )
            page.wait_for_timeout(100)
            acc.check("AI说话插件事件无异常", not errors, f"{errors[:2]}")
            page.evaluate(
                """() => document.dispatchEvent(new CustomEvent("ai-agent:plugins-changed", {
                    detail: {loaded: ["knowledge"]}
                }))"""
            )
            page.wait_for_timeout(100)
            acc.check(
                "关闭插件后播放条撤销",
                page.evaluate(
                    "() => !window.aiAgentAISpeak && !document.getElementById('aiSpeakPlayer')"
                ),
            )
            acc.check("关闭插件后无未捕获异常", not errors, f"{errors[:2]}")
        finally:
            browser.close()
