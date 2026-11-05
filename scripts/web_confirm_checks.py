"""确认卡跨配色、风格与屏宽的浏览器回归。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def check_confirm_matrix(page: Any, acc: Any) -> None:
    for width in (1200, 390):
        page.set_viewport_size({"width": width, "height": 850})
        for style in ("dsh", "minimal"):
            for multi in (False, True):
                sizes = {}
                for theme in ("light", "dark"):
                    page.evaluate("""({theme,style,multi}) => {
                        closeUserConfirmCardHost();
                        document.getElementById('confirm-test-style')?.remove();
                        document.documentElement.dataset.uiTheme=theme;
                        document.documentElement.dataset.uiStyle=style;
                        openUserConfirmModalFromToolEnd({user_confirm_required:true,
                            user_confirm_title:'请确认接下来的操作',user_confirm_multi:multi,
                            user_confirm_options:['继续执行，并在完成后汇总结果','先查看执行计划']},null);
                    }""", {"theme": theme, "style": style, "multi": multi})
                    if style == "minimal":
                        asset = ROOT / "plugins/theme_style/styles/minimal" / f"{theme}.css"
                        page.add_style_tag(path=str(asset)).evaluate("e=>e.id='confirm-test-style'")
                    page.locator(".uc-opt-row").first.click()
                    page.wait_for_timeout(300)
                    card = page.locator(".user-confirm-card")
                    sizes[theme] = card.evaluate("""e=>['', '.uc-opt-row','.uc-opt-input',
                        '.user-confirm-actions','.uc-ok','.user-confirm-badge'].map(s=>{
                            let r=(s?e.querySelector(s):e).getBoundingClientRect();
                            return [r.width,r.height];})""")
                    label = f"确认卡 {style}/{theme}/{width}/多选={multi}"
                    acc.check(label + " 无横向溢出", card.evaluate("e=>e.scrollWidth<=e.clientWidth+1"))
                    button = page.locator(".uc-ok")
                    for state in ("normal", "hover", "focus", "disabled"):
                        if state == "hover":
                            button.hover()
                        elif state == "focus":
                            button.focus()
                        elif state == "disabled":
                            button.evaluate("e=>e.disabled=true")
                        colors = button.evaluate("""e=>{
                            let c=getComputedStyle(e);return [c.color,c.backgroundColor];}""")
                        acc.check(label + f" {state} 主按钮可见",
                                  colors[0] == "rgb(255, 255, 255)"
                                  and colors[1] not in ("rgba(0, 0, 0, 0)", "rgb(255, 255, 255)"),
                                  str(colors))
                acc.check(f"确认卡 {style}/{width}/多选={multi} 日夜尺寸一致",
                          sizes["light"] == sizes["dark"], str(sizes))
    page.evaluate("""() => {closeUserConfirmCardHost();
        document.getElementById('confirm-test-style')?.remove();
        delete document.documentElement.dataset.uiStyle;}""")
