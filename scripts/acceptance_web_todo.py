# -*- coding: utf-8 -*-
"""Web 验收：Todo 清单 close 的浏览器 DOM 回归。"""
from __future__ import annotations

import sys


def run(acc) -> None:
    """Todo 清单 close 必须隐藏当前清单，而不是只更新数据。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [SKIP] Todo 清单关闭（未安装 playwright：pip install -e \".[ui]\"）")
        return
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as exc:
            print(f"[scripts.acceptance_web_todo.run] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            print(f"  [SKIP] Todo 清单关闭（Chromium 不可用：{type(exc).__name__}）")
            return
        try:
            page = browser.new_page()
            page.goto(acc.base + "/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)
            ready = page.evaluate("() => typeof renderTodoListFromEvent")
            acc.check("Todo 关闭测试：渲染函数已加载", ready == "function", f"typeof={ready}")
            if ready != "function":
                return
            visible = page.evaluate(
                """() => {
                  renderTodoListFromEvent({
                    items: [{text: '验收条目', done: false}],
                    collapsed: false,
                  }, activeConversationId);
                  const a = document.querySelector('.todo-list-area');
                  return {display: getComputedStyle(a).display,
                          hidden: a.classList.contains('hidden'),
                          items: document.querySelectorAll('.todo-item').length};
                }"""
            )
            acc.check("Todo 关闭测试：close 前可见",
                      visible["display"] != "none" and not visible["hidden"]
                      and visible["items"] == 1, str(visible))
            closed = page.evaluate(
                """() => {
                  renderTodoListFromEvent({items: [], close: true}, activeConversationId);
                  const a = document.querySelector('.todo-list-area');
                  return {display: getComputedStyle(a).display,
                          hidden: a.classList.contains('hidden')};
                }"""
            )
            acc.check("Todo 关闭测试：close 后隐藏",
                      closed["display"] == "none" and closed["hidden"], str(closed))
        finally:
            browser.close()
