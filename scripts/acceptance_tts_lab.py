# -*- coding: utf-8 -*-
"""音色工作台的面板验收：脚本是否执行、界面是否渲染、按钮是否真的能用。

这个场景必须走真实浏览器与真实端点：面板脚本要经过插件的任务路由加载、
接口要用真的 voice-options，任何一环断了都会停在骨架文字上。
"""
from __future__ import annotations

import sys
from typing import Any


def run(acc: Any) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [SKIP] 音色工作台场景因 Playwright 缺失跳过")
        return 2

    pw = None
    browser = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch()
    except Exception as exc:                                   # 环境缺 Chromium 属于跳过，不是失败
        print(f"  [SKIP] 音色工作台场景因 Chromium 不可用跳过（{type(exc).__name__}）",
              file=sys.stderr)
        return 2

    errors: list = []
    try:
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(acc.base + "/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1200)
        _open_panel(acc, page)
        if not _lab_available(page):
            print("  [SKIP] 音色工作台需要本地引擎，当前引擎没有音色库")
            return 2
        _check_render(acc, page)
        _check_presets(acc, page)
        _check_voice_rows(acc, page)
        _check_guards(acc, page)
        _check_preview(acc, page)
        acc.check("面板无未捕获脚本异常", not errors, f"{errors[:2]}")
    finally:
        _shutdown(browser, pw)
    return 0


def _open_panel(acc: Any, page: Any) -> None:
    """走设置页按钮同一条通路打开面板。"""
    page.evaluate("""() => document.dispatchEvent(new CustomEvent(
        'ai-agent:open-panel',
        {detail: {panel: 'app/shell/web-ui/right-panel/tts_voice'}}))""")
    acc.check("面板容器已插入", _wait(page, "() => !!document.getElementById('ttsLab')", 8000),
              "找不到 #ttsLab")


def _lab_available(page: Any) -> bool:
    """当前引擎能否开音色库：edge 引擎没有参考音色，工作台必然打不开。"""
    text = page.evaluate(
        "() => (document.getElementById('ttsLab') || {}).textContent || ''")
    return "当前引擎没有音色库" not in text


def _check_render(acc: Any, page: Any) -> None:
    acc.check("面板脚本已执行", _wait(page, "() => !!window.__ttsLabBooted", 8000),
              "lab.js 未执行（脚本没加载成功）")
    rendered = _wait(page, "() => document.querySelectorAll('#ttsLab .tts-lab-chip').length > 0",
                     8000)
    text = page.evaluate("() => (document.getElementById('ttsLab')||{}).innerText || ''")
    acc.check("维度卡片已渲染", rendered, f"文本={text[:80]!r}")
    chips = page.evaluate("() => document.querySelectorAll('#ttsLab .tts-lab-chip').length")
    acc.check("卡片数量符合维度与预设", chips >= 27, f"{chips} 个")
    acc.check("试听按钮存在",
              page.evaluate("""() => !!document.querySelector('#ttsLab [data-act="preview"]')"""), "")
    acc.check("保存按钮存在",
              page.evaluate("""() => !!document.querySelector('#ttsLab [data-act="save"]')"""), "")


def _check_presets(acc: Any, page: Any) -> None:
    page.evaluate("""() => {
        const chip = document.querySelector('#ttsLab .tts-lab-chip[data-preset]');
        if (chip) chip.click();
    }""")
    page.wait_for_timeout(300)
    sentence = page.evaluate(
        "() => (document.querySelector('#ttsLab .tts-lab-sentence')||{}).textContent || ''")
    acc.check("点预设后描述联动", bool(sentence.strip()), f"{sentence!r}")
    active = page.evaluate(
        "() => document.querySelectorAll('#ttsLab .tts-lab-chip.is-active').length")
    acc.check("选中态有高亮", active >= 5, f"{active} 个高亮")


def _check_voice_rows(acc: Any, page: Any) -> None:
    ok = _wait(page, "() => document.querySelectorAll('#ttsLab .tts-lab-voice').length > 0", 15000)
    rows = page.evaluate("() => document.querySelectorAll('#ttsLab .tts-lab-voice').length")
    acc.check("已有音色列表已加载", ok, f"{rows} 行")


def _check_guards(acc: Any, page: Any) -> None:
    """删当前音色要被拦住；同名保存要先确认。两条都不真的落盘。"""
    before = page.evaluate("() => document.querySelectorAll('#ttsLab .tts-lab-voice').length")
    page.evaluate("""() => {
        const cur = document.querySelector('#ttsLab .tts-lab-tag');
        const row = cur && cur.closest('.tts-lab-voice');
        const btn = row && row.querySelector('[data-act="delete"]');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(400)
    after = page.evaluate("() => document.querySelectorAll('#ttsLab .tts-lab-voice').length")
    guard = page.evaluate(
        "() => (document.querySelector('#ttsLab .tts-lab-status')||{}).textContent || ''")
    acc.check("删当前音色被拦住", "当前使用" in guard and before == after,
              f"状态={guard[:40]!r} 行数 {before}->{after}")

    dialogs: list = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    page.evaluate("""() => {
        const input = document.querySelector('#ttsLab [data-role="voice-id"]');
        if (input) input.value = 'ruanmeng';
        document.querySelector('#ttsLab [data-act="save"]').click();
    }""")
    page.wait_for_timeout(600)
    cancel = page.evaluate(
        "() => (document.querySelector('#ttsLab .tts-lab-status')||{}).textContent || ''")
    acc.check("同名保存先确认再覆盖", bool(dialogs) and "取消" in cancel,
              f"弹窗={dialogs[:1]} 状态={cancel[:40]!r}")


def _check_preview(acc: Any, page: Any) -> None:
    page.evaluate("""() => document.querySelector('#ttsLab [data-act="preview"]').click()""")
    ok = _wait(page, """() => {
        const el = document.querySelector('#ttsLab .tts-lab-status');
        return (el && el.textContent || '').indexOf('已生成') >= 0;
    }""", 90000)
    status = page.evaluate(
        "() => (document.querySelector('#ttsLab .tts-lab-status')||{}).textContent || ''")
    acc.check("点试听能拿到音频回执", ok, f"状态={status!r}")


def _shutdown(browser: Any, pw: Any) -> None:
    """关闭资源；关不掉只warn，不影响验收结论。"""
    if browser is not None:
        try:
            browser.close()
        except Exception as exc:                               # 关闭失败不该掩盖断言结果
            print(f"  [WARN] 关闭浏览器失败：{type(exc).__name__}", file=sys.stderr)
    if pw is not None:
        try:
            pw.stop()
        except Exception as exc:
            print(f"  [WARN] 停止 Playwright 失败：{type(exc).__name__}", file=sys.stderr)


def _wait(page: Any, expression: str, timeout_ms: int) -> bool:
    waited = 0
    step = 250
    while waited < timeout_ms:
        try:
            if page.evaluate(expression):
                return True
        except Exception as exc:                               # 页面切换瞬间会失败，下一轮重试
            _LAST_WAIT_ERROR.append(str(exc))
            print(f"  [WARN] 等待中页面异常：{type(exc).__name__}", file=sys.stderr)
        page.wait_for_timeout(step)
        waited += step
    return False


#: 轮询期间的临时错误，只用于诊断，不参与断言。
_LAST_WAIT_ERROR: list = []


def main() -> int:
    import tempfile
    from pathlib import Path

    try:
        from scripts.acceptance_web import Acceptance
    except ImportError:
        # 直接 `python scripts/acceptance_tts_lab.py` 跑时没有包前缀
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from scripts.acceptance_web import Acceptance

    with tempfile.TemporaryDirectory(prefix="accept-tts-lab-") as tmp:
        acc = Acceptance(Path(tmp))
        acc.start()
        try:
            code = run(acc)
        finally:
            acc.close()
        if code == 2:
            return 0
        if acc.failures:
            print(f"音色工作台验收未通过：{len(acc.failures)} 项失败")
            for item in acc.failures:
                print(f"  - {item}")
            return 1
        print("音色工作台验收：全部检查项 PASS。")
        return 0


if __name__ == "__main__":
    sys.exit(main())
