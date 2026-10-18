# -*- coding: utf-8 -*-
"""写前检查：WriteContext、路径命中、大 diff 边界与 check_write 判定。"""
from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from agent.core.tool_call import GateDecision
from agent.mechanisms.quality.path_keys import _norm_path, resolve_write_path

if TYPE_CHECKING:
    from agent.mechanisms.quality.gate import QualityGate

MAX_DIFF_LINES = 80
# 预览卡片：diff 展示上限（超出只给统计，避免把整文件塞进事件流）
PREVIEW_DIFF_MAX_LINES = 600
PREVIEW_TEXT_MAX_CHARS = 20000


@dataclass
class WriteContext:
    """一次提交请求的上下文（写前检查的输入；写参数由 confirm_id 快照恢复）。"""

    confirm_id: str = ""  # 预览登记的确认 ID（提交唯一凭据）


def _in_paths(path: str, paths: List[str]) -> bool:
    """path 是否命中 paths 之一（全等或路径后缀匹配）。"""
    norm = _norm_path(path)
    if not norm:
        return False
    for p in paths:
        q = _norm_path(p)
        if q and (norm == q or norm.endswith("/" + q) or q.endswith("/" + norm)):
            return True
    return False


def _join_unified_diff(lines: Any) -> str:
    """拼 unified diff：keepends 行自带 \\n；无结尾换行的行补 \\n，并标 GNU 提示。

    否则 `"a"` vs `"a\\n"` 会变成 `-a+a\\n`（两行粘在一起）。
    """
    out: list[str] = []
    for line in lines:
        text = str(line)
        if text.endswith("\n"):
            out.append(text)
            continue
        out.append(text + "\n")
        if text[:1] in "-+ ":
            out.append("\\ No newline at end of file\n")
    return "".join(out)


def diff_text(old: str, new: str, path: str = "") -> str:
    """旧→新 unified diff 文本（供大删除检测、备份留档与 file_undo 展示）；无差异返回空串。

    `path` 会写进 `---` / `+++` 头：不传的话那两行没有文件名，
    事后翻备份时分不清这一版改的是哪个文件。

    用 `splitlines(keepends=True)`：仅差结尾换行时（`"a"` vs `"a\\n"`）
    普通 `splitlines()` 会得出空 diff，预览看不见却仍要 review。
    """
    if old == new:
        return ""
    name = str(path or "")
    return _join_unified_diff(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=name,
            tofile=name,
            n=0,
        )
    )


def change_payload(old_text: str, new_text: str, path: str = "") -> Dict[str, Any]:
    """构造"变更预览"载荷（供 Web 壳的文件编辑 / diff 卡片）。

    字段：path / new_file（原文件不存在）/ added / deleted / diff（unified，带上下文）/
    old_text / new_text / truncated。文本超限时截断并置 truncated=True——
    卡片仍可渲染，只是不展示全文（完整内容走右栏文件查看器）。
    """
    old = str(old_text or "")
    new = str(new_text or "")
    diff_lines = list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="a/" + (path or ""),
            tofile="b/" + (path or ""),
            n=3,
        )
    )
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    deleted = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    truncated = False
    if len(diff_lines) > PREVIEW_DIFF_MAX_LINES:
        diff_lines = diff_lines[:PREVIEW_DIFF_MAX_LINES]
        truncated = True
    if len(old) > PREVIEW_TEXT_MAX_CHARS:
        old = old[:PREVIEW_TEXT_MAX_CHARS]
        truncated = True
    if len(new) > PREVIEW_TEXT_MAX_CHARS:
        new = new[:PREVIEW_TEXT_MAX_CHARS]
        truncated = True
    return {
        "path": str(path or ""),
        "new_file": not old,
        "added": added,
        "deleted": deleted,
        "diff": _join_unified_diff(diff_lines),
        "old_text": old,
        "new_text": new,
        "truncated": truncated,
    }


def check_write(gate: "QualityGate", wc: WriteContext) -> GateDecision:
    """写前组合门控（id 制）：ID 有效 → 已确认 → 路径 → 意图/证据 → 红灯限面 →
    跨文件 review → apply_patch 通道 → 连改重读 → 大 diff。"""
    rec = gate.peek(wc.confirm_id)
    if rec is None:
        return GateDecision(
            allow=False,
            reason="confirm_id 无效或已使用：请先 write_file 预览拿到确认 ID",
        )
    if not rec.get("confirmed"):
        # 这段 reason 给出下一步操作（review 本次改动 + 用哪个工具提交 + 带哪个 ID）：
        # 含糊的文案会让模型误发起 `user_confirm`（白跑一轮），所以要点名工具；
        # 但不能写成"带 confirm_id 调一下就能解锁" —— 那是在教模型走过场，
        # review 基于本次改动的实际审阅并给出验证证据。
        # 四步协议的状态转移由 `register_preview` / `confirm` / `take_record` 承载。
        return GateDecision(
            allow=False,
            reason=(
                "预览未解锁：请先 review 本次改动，"
                "用 review_conclusion 提交结论与验证证据，"
                "再用同一 confirm_id 调 commit_write 提交。"
            ),
        )
    args = dict(rec.get("arguments") or {})
    tool = str(rec.get("tool") or "")
    path = str(rec.get("path") or "") or resolve_write_path(
        args, gate.path_keys(tool)
    )
    if not path:
        return GateDecision(
            allow=False,
            reason=(
                "无法从预览快照解析目标路径：工具须声明 write_path_keys，"
                "请重新预览"
            ),
        )
    if gate.intent in ("debug", "troubleshoot") and not gate.evidence_ok:
        return GateDecision(
            allow=False,
            reason="当前为排查/调试意图：请先用只读工具收集证据，再写盘",
        )
    if gate.pending_diagnose_red:
        allowed = gate.fixable_paths or list(gate.pending_review)
        if not _in_paths(path, allowed):
            return GateDecision(
                allow=False,
                reason="写后诊断仍有问题未处理：先修复已改文件上的 fail 项，再改其他文件",
            )
    if gate.pending_review and not gate.reviewed_ok:
        if (not _in_paths(path, gate.pending_review)
                and not gate._unlocked_before_latest_write(rec)):
            return GateDecision(
                allow=False,
                reason="上一次真写的 review 尚未完成：请先提交 review 结论，再跨文件继续写",
            )
    if (tool == "apply_patch" and gate.apply_patch_pending
            and not gate._unlocked_before_latest_write(rec)):
        return GateDecision(
            allow=False,
            reason="apply_patch 上一次真写尚未 review：请先提交 review 结论",
        )
    if path in gate.needs_reread:
        return GateDecision(
            allow=False,
            reason=(
                f"该路径刚落盘过：请先 read_file 复核当前内容与行号（{path}）。"
                "复核不使已解锁的 confirm_id 失效；确认无误后用原 confirm_id 继续 "
                "commit_write，不必重新预览。"
            ),
        )
    if tool == "replace_in_file":
        new_text = str(args.get("new_text") or "")
        new_lines = new_text.count("\n") + 1
        if new_lines > MAX_DIFF_LINES:
            span: Optional[int] = None
            line_start = args.get("line_start")
            line_end = args.get("line_end")
            if line_start is not None and line_end is not None:
                try:
                    span = int(line_end) - int(line_start) + 1
                except (TypeError, ValueError):
                    span = None
            if span is None or span <= 0:
                return GateDecision(
                    allow=False,
                    reason=(
                        f"单次替换内容过大（>{MAX_DIFF_LINES} 行）："
                        "请提供目标行区间（line_start/line_end）或拆成更小的局部替换"
                    ),
                )
            if span > MAX_DIFF_LINES:
                return GateDecision(
                    allow=False,
                    reason=(
                        f"目标区间跨度过大（{span} 行 > {MAX_DIFF_LINES} 行）："
                        "请拆成更小的局部替换"
                    ),
                )
            if new_lines > max(40, span * 3):
                return GateDecision(
                    allow=False,
                    reason="替换内容相对目标区间过大：请拆成更小的局部替换",
                )
    return GateDecision(allow=True)
