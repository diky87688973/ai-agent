# -*- coding: utf-8 -*-
"""写后诊断：大删除检测、本地 py/json 检查与质量报告。"""
from __future__ import annotations

import ast
import json
import py_compile
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

from agent.mechanisms.quality.path_keys import norm_path

if TYPE_CHECKING:
    from agent.mechanisms.quality.gate import QualityGate

LARGE_DELETE_MIN_LINES = 30
LARGE_DELETE_ADD_RATIO = 0.35


def flag_diag_fail(gate: "QualityGate", summary: str) -> None:
    """置诊断红灯（diag_fail_flag + pending_diagnose_red）。"""
    gate.diag_fail_flag = True
    gate.pending_diagnose_red = True
    gate.last_diagnose_summary = summary[:1500]


def maybe_flag_large_delete(gate: "QualityGate", path: str, diff_text: str) -> None:
    """删除 ≥30 行且（无新增或新增 < 删除×35%）→ 大删除红灯。"""
    dels = sum(
        1 for ln in diff_text.splitlines()
        if ln.startswith("-") and not ln.startswith("---")
    )
    adds = sum(
        1 for ln in diff_text.splitlines()
        if ln.startswith("+") and not ln.startswith("+++")
    )
    if dels >= LARGE_DELETE_MIN_LINES and (adds == 0 or adds < dels * LARGE_DELETE_ADD_RATIO):
        gate.large_delete_flag = True
        gate.pending_diagnose_red = True
        gate.last_diagnose_summary = (
            f"{path}: diff 显示大量删除（-{dels}/+{adds}），请确认并非误删。"
        )


def run_post_write_checks(gate: "QualityGate", path: str) -> List[Dict[str, Any]]:
    """写后本地检查：.py → ast.parse + py_compile；.json → json.loads。
    失败置诊断红灯（diag_fail_flag + pending_diagnose_red）；全通过清红灯。"""
    checks: List[Dict[str, Any]] = []
    fp = Path(str(path))
    if not fp.is_file():
        return checks
    suffix = fp.suffix.lower()
    if suffix == ".py":
        try:
            ast.parse(fp.read_text(encoding="utf-8", errors="replace"), filename=str(fp))
            checks.append({"id": "py_syntax", "status": "pass", "summary": "Python 语法通过"})
        except SyntaxError as exc:
            checks.append({"id": "py_syntax", "status": "fail", "summary": f"Python 语法错误：{exc}"})
            flag_diag_fail(gate, f"{path}: {exc}")
            return checks
        try:
            with tempfile.TemporaryDirectory() as tmp:
                py_compile.compile(str(fp), cfile=str(Path(tmp) / "out.pyc"), doraise=True)
            checks.append({"id": "py_compile", "status": "pass", "summary": "py_compile 通过"})
        except Exception as exc:
            checks.append({"id": "py_compile", "status": "fail", "summary": f"py_compile 失败：{exc}"})
            flag_diag_fail(gate, f"{path}: {exc}")
    elif suffix == ".json":
        try:
            json.loads(fp.read_text(encoding="utf-8", errors="replace"))
            checks.append({"id": "json_valid", "status": "pass", "summary": "JSON 解析通过"})
        except Exception as exc:
            checks.append({"id": "json_valid", "status": "fail", "summary": f"JSON 解析失败：{exc}"})
            flag_diag_fail(gate, f"{path}: {exc}")
    if checks and all(c.get("status") == "pass" for c in checks) and not gate.large_delete_flag:
        gate.diag_fail_flag = False
        gate.pending_diagnose_red = False
    return checks


def build_quality_report(gate: "QualityGate", path: str) -> Dict[str, Any]:
    """写后质量报告：overall / checks / required_next_actions。"""
    norm = norm_path(path)
    checks = run_post_write_checks(gate, path)
    actions: List[str] = []
    if gate.large_delete_flag:
        checks.append({
            "id": "large_delete",
            "status": "fail",
            "summary": gate.last_diagnose_summary or "检测到异常大删除，请确认并非误删",
        })
        actions.append("确认大删除是否为有意改动（review 提交后解除）")
    if gate.diag_fail_flag:
        actions.append("先修复诊断 fail 项，再扩大改动")
    if gate.pending_review:
        # 写后复核账：不是提醒「刚才的预览没 review」（那一步已在 commit 前做完），
        # 而是跨文件继续写之前要再清一次账。
        actions.append("若继续改其他文件，请先做写后复核（review_conclusion）")
    overall = "red" if (gate.diag_fail_flag or gate.large_delete_flag) else "green"
    return {
        "overall": overall,
        "path": norm,
        "checks": checks,
        "required_next_actions": actions,
    }
