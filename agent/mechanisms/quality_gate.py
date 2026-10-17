# -*- coding: utf-8 -*-
"""写盘门控与质量管线 — id 制四步协议（预览 → 确认 → 凭 ID 提交 → 重读）+ 三段检查。

四步协议（id 制，所有提交统一走 confirm_id）：
- 预览（write_file / replace_in_file / apply_patch / read_write / delete_file / file_ops / file_undo）：
  写参数快照登记入库，返回 confirm_id（不落盘）；
  同路径只留最新快照；未提交条数上限 `MAX_PENDING_PREVIEWS`，满则按登记顺序挤掉最旧的；
- 确认（宿主）：confirm(confirm_id)；
- 提交（commit_write）：仅凭 confirm_id —— content 等写参数由本模块从快照恢复，
  模型不重传（省 token、防重写漂移）；预览与提交是两个独立工具入口，不共用函数入口。

- 写前 gate：预览强制 / 意图·证据 / 路径解析 /
  红灯限面 / 跨文件 review / apply_patch 通道 / 连改重读 /
  ID 绑定（提交凭 confirm_id；参数从预览快照恢复）/
  大 diff（防盲覆盖：未预览即拒）；
- 写中 inspect：记账 / 大删除检测；
- 写后 feedback：review 语义 / 空口已修复 / 报告 /
  本地检查（py/json；javac、引用扫描等按需扩展）。

设计：每会话一个 QualityGate 实例；本模块不做文件写入 ——
"执行"由工具层完成，gate 负责流程、状态与检查。
"""
from __future__ import annotations

import ast
import difflib
import json
import py_compile
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
from uuid import uuid4

from agent.core.session_scope import current_session_id
from agent.core.tool_call import (
    GateDecision,
    PostObserver,
    PreGate,
    ToolCallRequest,
    ToolResult,
)

MAX_DIFF_LINES = 80
LARGE_DELETE_MIN_LINES = 30
LARGE_DELETE_ADD_RATIO = 0.35
# 未提交预览快照上限：同路径只留最新；满额时按登记顺序挤掉最旧的。
MAX_PENDING_PREVIEWS = 100


def _norm_path(p: str) -> str:
    """路径规范化：统一斜杠、去首尾空白。"""
    return str(p or "").replace("\\", "/").strip()


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


# 写类工具的目标路径参数键序（按工具取首个非空值）
_TOOL_PATH_KEYS: Dict[str, Tuple[str, ...]] = {
    "write_file": ("path",),
    "replace_in_file": ("path",),
    "apply_patch": ("path",),
    "read_write": ("dest_path",),
    "delete_file": ("path",),
    "file_ops": ("dest", "source"),
    "file_undo": ("path",),
    "archive": ("dest", "source"),
    "skill_manage": ("source", "name"),
}


def resolve_write_path(tool: str, args: Dict[str, Any]) -> str:
    """解析写目标路径（按工具参数键序取首个非空值）。"""
    for key in _TOOL_PATH_KEYS.get(str(tool or ""), ("path",)):
        value = str(args.get(key) or "").strip()
        if value:
            return _norm_path(value)
    return ""


def diff_text(old: str, new: str, path: str = "") -> str:
    """旧→新 unified diff 文本（供大删除检测、备份留档与 file_undo 展示）；无差异返回空串。

    `path` 会写进 `---` / `+++` 头：不传的话那两行没有文件名，
    事后翻备份时分不清这一版改的是哪个文件。
    """
    if old == new:
        return ""
    name = str(path or "")
    lines = difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile=name, tofile=name, lineterm="", n=0,
    )
    return "\n".join(lines)


# 预览卡片：diff 展示上限（超出只给统计，避免把整文件塞进事件流）
PREVIEW_DIFF_MAX_LINES = 600
PREVIEW_TEXT_MAX_CHARS = 20000


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
            old.splitlines(), new.splitlines(), fromfile="a/" + (path or ""), tofile="b/" + (path or ""), lineterm="", n=3
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
        "diff": "\n".join(diff_lines),
        "old_text": old,
        "new_text": new,
        "truncated": truncated,
    }


@dataclass
class WriteContext:
    """一次提交请求的上下文（写前检查的输入；写参数由 confirm_id 快照恢复）。"""

    confirm_id: str = ""           # 预览登记的确认 ID（提交唯一凭据）


@dataclass
class QualityGate:
    """写盘门控与质量管线（id 制四步 + 三段检查）。"""

    # ── 四步协议状态（id 制）──
    # confirm_id → {"tool": str, "arguments": dict, "confirmed": bool}
    _pending: Dict[str, Dict[str, Any]] = field(default_factory=dict, repr=False)
    needs_reread: Set[str] = field(default_factory=set)
    pending_review: List[str] = field(default_factory=list)
    reviewed_ok: bool = True
    # 真写次数。预览解锁时记下当时的值，用来区分「写之前已解锁」和「写之后才解锁」。
    _write_generation: int = 0

    # ── 检查状态──
    intent: str = ""               # "" | "debug" | "troubleshoot"
    evidence_ok: bool = False
    fixable_paths: List[str] = field(default_factory=list)
    apply_patch_pending: bool = False
    pending_diagnose_red: bool = False
    large_delete_flag: bool = False
    diag_fail_flag: bool = False
    last_diagnose_summary: str = ""
    claim_fixed_blocked: bool = False
    changeset_mod_ids: List[Tuple[str, str]] = field(default_factory=list)

    # ── ① 预览登记（id 制）──────────────────────────────────
    def register_preview(self, tool: str, arguments: Dict[str, Any]) -> str:
        """登记一次预览快照（写参数入库），返回 confirm_id（提交唯一凭据）。

        同一写目标路径只保留最新一条；条数达到 `MAX_PENDING_PREVIEWS` 时，
        按登记顺序挤掉最旧的未提交快照后再写入。
        """
        tool_name = str(tool or "")
        args = dict(arguments or {})
        path = resolve_write_path(tool_name, args)
        if path:
            stale = [
                key
                for key, rec in self._pending.items()
                if resolve_write_path(
                    str(rec.get("tool") or ""),
                    dict(rec.get("arguments") or {}),
                )
                == path
            ]
            for key in stale:
                del self._pending[key]
        while len(self._pending) >= MAX_PENDING_PREVIEWS:
            oldest = next(iter(self._pending))
            del self._pending[oldest]
        cid = uuid4().hex
        self._pending[cid] = {
            "tool": tool_name,
            "arguments": args,
            "confirmed": False,
        }
        return cid

    def peek(self, confirm_id: str) -> Optional[Dict[str, Any]]:
        """查看确认 ID 关联的预览快照（不消费）；无效返回 None。"""
        return self._pending.get(str(confirm_id or "").strip())

    def take_record(self, confirm_id: str) -> Optional[Dict[str, Any]]:
        """取出并消费预览快照（完整记录：tool + arguments，一次性）；无效/已使用返回 None。"""
        rec = self._pending.pop(str(confirm_id or "").strip(), None)
        if rec is None:
            return None
        return {"tool": str(rec.get("tool") or ""), "arguments": dict(rec.get("arguments") or {})}

    def take(self, confirm_id: str) -> Optional[Dict[str, Any]]:
        """取出并消费预览快照的写参数（一次性）；无效/已使用返回 None。"""
        record = self.take_record(confirm_id)
        return None if record is None else record["arguments"]

    def discard(self, confirm_id: str) -> bool:
        """丢弃一个未提交的预览快照（释放，不执行）；返回是否命中。"""
        key = str(confirm_id or "").strip()
        if key not in self._pending:
            return False
        del self._pending[key]
        return True

    # ── ② 确认 ──────────────────────────────────────────────
    def confirm(self, confirm_id: str) -> bool:
        """确认（review 通过）某次预览可提交；返回是否找到该快照。"""
        rec = self.peek(confirm_id)
        if rec is None:
            return False
        rec["confirmed"] = True
        rec["confirmed_generation"] = self._write_generation
        return True

    # ── ③ 提交前检查（四步协议核心）──────────────────────────
    def check_write(self, wc: WriteContext) -> GateDecision:
        """写前组合门控（id 制）：ID 有效 → 已确认 → 路径 → 意图/证据 → 红灯限面 →
        跨文件 review → apply_patch 通道 → 连改重读 → 大 diff。"""
        rec = self.peek(wc.confirm_id)
        if rec is None:
            return GateDecision(
                allow=False,
                reason="confirm_id 无效或已使用：请先 write_file 预览拿到确认 ID",
            )
        if not rec.get("confirmed"):
            # 这段 reason 给出**下一步操作**（review 本次改动 + 用哪个工具提交 + 带哪个 ID）：
            # 含糊的文案会让模型误发起 `user_confirm`（白跑一轮），所以要**点名工具**；
            # 但不能写成"带 confirm_id 调一下就能解锁" —— 那是在教模型走过场，
            # review 基于**本次改动的实际审阅**并给出验证证据。
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
        path = resolve_write_path(tool, args)
        if not path:
            return GateDecision(allow=False, reason="无法从预览快照解析目标路径：请重新预览")
        if self.intent in ("debug", "troubleshoot") and not self.evidence_ok:
            return GateDecision(
                allow=False,
                reason="当前为排查/调试意图：请先用只读工具收集证据，再写盘",
            )
        if self.pending_diagnose_red:
            allowed = self.fixable_paths or list(self.pending_review)
            if not _in_paths(path, allowed):
                return GateDecision(
                    allow=False,
                    reason="写后诊断仍有问题未处理：先修复已改文件上的 fail 项，再改其他文件",
                )
        if self.pending_review and not self.reviewed_ok:
            if (not _in_paths(path, self.pending_review)
                    and not self._unlocked_before_latest_write(rec)):
                return GateDecision(
                    allow=False,
                    reason="上一次真写的 review 尚未完成：请先提交 review 结论，再跨文件继续写",
                )
        if (tool == "apply_patch" and self.apply_patch_pending
                and not self._unlocked_before_latest_write(rec)):
            return GateDecision(
                allow=False,
                reason="apply_patch 上一次真写尚未 review：请先提交 review 结论",
            )
        if path in self.needs_reread:
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
                        reason=f"单次替换内容过大（>{MAX_DIFF_LINES} 行）：请提供目标行区间（line_start/line_end）或拆成更小的局部替换",
                    )
                if span > MAX_DIFF_LINES:
                    return GateDecision(
                        allow=False,
                        reason=f"目标区间跨度过大（{span} 行 > {MAX_DIFF_LINES} 行）：请拆成更小的局部替换",
                    )
                if new_lines > max(40, span * 3):
                    return GateDecision(
                        allow=False,
                        reason="替换内容相对目标区间过大：请拆成更小的局部替换",
                    )
        return GateDecision(allow=True)

    # ── ④ 记账与重读 / 复核 ─────────────────────────
    def note_committed(
        self,
        path: str,
        *,
        diff_text: str = "",
        tool: str = "",
        mod_id: str = "",
        reread: bool = True,
    ) -> None:
        """真写成功后的记账 + 大删除检测；reread=False 用于结构性操作（删除/移动/重命名）。"""
        self._write_generation += 1
        norm = _norm_path(path)
        if reread:
            self.needs_reread.add(norm)
        if norm not in self.pending_review:
            self.pending_review.append(norm)
        self.reviewed_ok = False
        self.claim_fixed_blocked = True
        if norm not in self.fixable_paths:
            self.fixable_paths.append(norm)
        if tool == "apply_patch":
            self.apply_patch_pending = True
        if mod_id:
            self.changeset_mod_ids.append((norm, str(mod_id)))
        if diff_text:
            self._maybe_flag_large_delete(norm, diff_text)

    def _unlocked_before_latest_write(self, rec: Dict[str, Any]) -> bool:
        """这份预览在最近一次真写之前就已经解锁。

        同一批里连续提交多份已审预览时，第一份落盘会把 `reviewed_ok` 打回未完成。
        写之前就解锁的后续提交仍然有效；写之后才解锁的新文件继续要先 review。
        """
        stamped = rec.get("confirmed_generation")
        return isinstance(stamped, int) and stamped < self._write_generation

    def note_read(self, path: str) -> None:
        """read 复核后清除该路径的"需重读"标记。"""
        self.needs_reread.discard(_norm_path(path))

    def review_done(self) -> None:
        """写后复核完成：大删除红灯因 review 解除（视为有意确认）；
        诊断红灯（diag_fail_flag）不因 review 解除，须真正修复。"""
        self.pending_review.clear()
        self.reviewed_ok = True
        self.apply_patch_pending = False
        if self.large_delete_flag:
            self.large_delete_flag = False
            self.last_diagnose_summary = ""
        self.pending_diagnose_red = self.large_delete_flag or self.diag_fail_flag
        if not self.pending_diagnose_red:
            self.fixable_paths.clear()
            self.claim_fixed_blocked = False

    # ── 意图 / 证据 ──────────────────────
    def set_intent(self, intent: str) -> None:
        """设置会话意图（"" | "debug" | "troubleshoot"）；切换时重置证据状态。"""
        self.intent = intent if intent in ("debug", "troubleshoot") else ""
        self.evidence_ok = False

    def note_evidence(self) -> None:
        """记录一次成功的只读证据采集。"""
        self.evidence_ok = True

    def note_assistant_text(self, text: str) -> None:
        """存在未验证写入时，"已修复"类表述置催办标记。"""
        if not (self.pending_diagnose_red or (self.pending_review and not self.reviewed_ok)):
            self.claim_fixed_blocked = False
            return
        if re.search(r"(已修复|已解决|修复完成|搞定了)", str(text or "")):
            self.claim_fixed_blocked = True

    # ── 写后 feedback（本地可跑的检查）────
    def run_post_write_checks(self, path: str) -> List[Dict[str, Any]]:
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
                self._flag_diag_fail(f"{path}: {exc}")
                return checks
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    py_compile.compile(str(fp), cfile=str(Path(tmp) / "out.pyc"), doraise=True)
                checks.append({"id": "py_compile", "status": "pass", "summary": "py_compile 通过"})
            except Exception as exc:
                checks.append({"id": "py_compile", "status": "fail", "summary": f"py_compile 失败：{exc}"})
                self._flag_diag_fail(f"{path}: {exc}")
        elif suffix == ".json":
            try:
                json.loads(fp.read_text(encoding="utf-8", errors="replace"))
                checks.append({"id": "json_valid", "status": "pass", "summary": "JSON 解析通过"})
            except Exception as exc:
                checks.append({"id": "json_valid", "status": "fail", "summary": f"JSON 解析失败：{exc}"})
                self._flag_diag_fail(f"{path}: {exc}")
        if checks and all(c.get("status") == "pass" for c in checks) and not self.large_delete_flag:
            self.diag_fail_flag = False
            self.pending_diagnose_red = False
        return checks

    def build_quality_report(self, path: str) -> Dict[str, Any]:
        """写后质量报告：overall / checks / required_next_actions。"""
        norm = _norm_path(path)
        checks = self.run_post_write_checks(path)
        actions: List[str] = []
        if self.large_delete_flag:
            checks.append({
                "id": "large_delete",
                "status": "fail",
                "summary": self.last_diagnose_summary or "检测到异常大删除，请确认并非误删",
            })
            actions.append("确认大删除是否为有意改动（review 提交后解除）")
        if self.diag_fail_flag:
            actions.append("先修复诊断 fail 项，再扩大改动")
        if self.pending_review:
            actions.append("请提交 review 结论（review_done）")
        overall = "red" if (self.diag_fail_flag or self.large_delete_flag) else "green"
        return {
            "overall": overall,
            "path": norm,
            "checks": checks,
            "required_next_actions": actions,
        }

    # ── 内部辅助 ────────────────────────────────────────────
    def _flag_diag_fail(self, summary: str) -> None:
        self.diag_fail_flag = True
        self.pending_diagnose_red = True
        self.last_diagnose_summary = summary[:1500]

    def _maybe_flag_large_delete(self, path: str, diff_text: str) -> None:
        """删除 ≥30 行且（无新增或新增 < 删除×35%）→ 大删除红灯。"""
        dels = sum(1 for ln in diff_text.splitlines() if ln.startswith("-") and not ln.startswith("---"))
        adds = sum(1 for ln in diff_text.splitlines() if ln.startswith("+") and not ln.startswith("+++"))
        if dels >= LARGE_DELETE_MIN_LINES and (adds == 0 or adds < dels * LARGE_DELETE_ADD_RATIO):
            self.large_delete_flag = True
            self.pending_diagnose_red = True
            self.last_diagnose_summary = (
                f"{path}: diff 显示大量删除（-{dels}/+{adds}），请确认并非误删。"
            )


# ── 工具管道桥接（id 制）：把 gate 挂到 ToolPipeline 的 pre / post 钩子 ──


def build_pipeline_gate(
    gate: QualityGate,
    *,
    preview_tools: Iterable[str] = (
        "write_file",
        "replace_in_file",
        "apply_patch",
        "read_write",
        "delete_file",
        "file_ops",
        "file_undo",
        "archive",
        "skill_manage",
    ),
    commit_tools: Iterable[str] = ("commit_write",),
    read_tools: Iterable[str] = ("read_file",),
    live_state: Any = None,
    gate_resolver: Optional[Callable[[], QualityGate]] = None,
) -> Tuple[PreGate, PostObserver]:
    """构建挂 ToolPipeline 的门控钩子（id 制四步：预览 → 确认 → 凭 ID 提交 → 重读）。

    会话级门控：`gate` 参数为默认桶门控，`gate_resolver`
    给出"按当前会话解析门控"的通路——每会话独占一个 QualityGate 实例（预览快照 /
    待重读 / 待 review / 红灯 / 意图证据均不得跨会话）。解析器缺省时退化为单门控
    （无会话装配的直调场景）。

    - pre：提交入口（commit_write）真写前先走模式门控（Plan 拒绝 / Execute
      须非空清单），再走 gate.check_write（凭 confirm_id 快照解析路径与写参数）；
      预览入口无落盘副作用，放行。
    - post：成功的预览（结果未标 needs_commit=False）→ gate.register_preview（写参数
      快照入库），并把 confirm_id 注入 result.data（供宿主确认与模型提交引用）；
      成功的提交 → gate.note_committed 记账（diff 由执行器随 "_diff" 返回）+
      写后诊断，报告附到 result.data["host_quality"]（写后回灌）；
      read_file 成功 → gate.note_read（清除"连改重读"标记，四步协议第 4 步）。
    """
    preview_names = tuple(preview_tools)
    commit_names = tuple(commit_tools)
    read_names = tuple(read_tools)
    content_tools = ("write_file", "replace_in_file", "apply_patch", "read_write", "file_undo")
    pending_commits: Dict[str, Dict[str, str]] = {}  # call_id → {tool}

    def _gate() -> QualityGate:
        """本次调用的会话门控：管道执行期内已注入会话作用域，可安全解析。"""
        return gate_resolver() if gate_resolver is not None else gate

    def pre(call: ToolCallRequest, ctx: Any) -> Optional[GateDecision]:
        if call.name not in commit_names:
            return None
        if live_state is not None:
            conv = current_session_id()
            mode = live_state.get_mode(conv) if conv else "auto"
            if mode == "plan":
                return GateDecision(
                    allow=False,
                    reason="ModeConflict：Plan 模式下禁止写盘（可先 run_type 切回 auto / execute）",
                )
            if mode == "execute" and not live_state.has_active_todo(conv):
                return GateDecision(
                    allow=False,
                    reason="ModeConflict：Execute 模式写盘前须先创建非空执行清单（todo_list create）",
                )
        cid = str(call.arguments.get("confirm_id") or "")
        session_gate = _gate()
        decision = session_gate.check_write(WriteContext(confirm_id=cid))
        if not decision.allow:
            return decision
        record = session_gate.peek(cid) or {}
        pending_commits[call.call_id] = {"tool": str(record.get("tool") or "")}
        return None

    def post(call: ToolCallRequest, result: ToolResult, ctx: Any) -> None:
        info = pending_commits.pop(call.call_id, None)
        if not result.ok:
            return
        session_gate = _gate()
        if call.name in preview_names:
            if isinstance(result.data, dict) and result.data.get("needs_commit", True):
                cid = session_gate.register_preview(call.name, dict(call.arguments))
                result.data["confirm_id"] = cid
            return
        if call.name in commit_names:
            if not isinstance(result.data, dict):
                return
            path = str(result.data.get("path") or "")
            if not path:
                return
            tool = str((info or {}).get("tool") or "")
            session_gate.note_committed(
                path,
                diff_text=str(result.data.pop("_diff", "") or ""),
                tool=tool,
                mod_id=str(result.data.get("mod_id") or ""),
                reread=tool in content_tools,
            )
            report = session_gate.build_quality_report(path)
            result.data["host_quality"] = report
            return
        if call.name in read_names:
            path = str(call.arguments.get("path") or "")
            if path:
                session_gate.note_read(path)

    return pre, post
