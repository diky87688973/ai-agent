"""真实页面的 Web UI 插件关闭、恢复与刷新回归。"""
from __future__ import annotations

import sys
from typing import Any


def run(acc: Any) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return 2
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except Exception as exc:
            print(f"[acceptance_web_hotplug] {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        try:
            page = browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(acc.base, wait_until="domcontentloaded")
            page.locator(".hdr-settings-btn").click()
            page.get_by_role("button", name="插件", exact=True).click()
            for enabled in (False, True):
                card = page.locator(".st-card").filter(has_text="图形操作界面")
                with page.expect_response(
                    lambda response: response.url.endswith("/api/settings/plugins")
                    and response.request.method == "POST"
                ) as received:
                    card.locator(".st-switch").click()
                result = received.value.json()
                acc.check(f"Web UI 开关请求 {enabled} 成功", result.get("ok"), str(result))
                page.wait_for_timeout(700)
                checkbox = page.locator(".st-card").filter(
                    has_text="图形操作界面").locator("input[type=checkbox]")
                acc.check(f"Web UI 开关显示 {enabled}", checkbox.is_checked() == enabled)
                loaded = page.request.get(acc.base + "/api/plugins/loaded").json()["loaded"]
                acc.check(f"Web UI 装载状态 {enabled}", ("web_ui" in loaded) == enabled)
            page.reload(wait_until="domcontentloaded")
            page.locator(".hdr-settings-btn").wait_for()
            acc.check("Web UI 恢复后刷新仍有设置入口", True)
            acc.check("Web UI 热插拔无未捕获脚本异常", not errors, str(errors))
            from scripts.web_confirm_checks import check_confirm_matrix
            check_confirm_matrix(page, acc)
            acc.check("确认卡矩阵无未捕获脚本异常", not errors, str(errors))
            return 0
        finally:
            browser.close()
