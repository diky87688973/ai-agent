# -*- coding: utf-8 -*-
"""QualityGate：组合预览仓库、写前检查与写后诊断。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

import agent.mechanisms.quality.checks as _checks
import agent.mechanisms.quality.diagnose as _diagnose
from agent.core.tool_call import GateDecision
from agent.mechanisms.quality.checks import WriteContext
from agent.mechanisms.quality.path_keys import _norm_path
from agent.mechanisms.quality.pending import PendingStore

PathKeysFor = Callable[[str], Sequence[str]]


@dataclass
class QualityGate:
    """写盘门控与质量管线（id 制四步 + 三段检查）。"""

    # ── 四步协议状态（id 制）──
    _store: PendingStore = field(default_factory=PendingStore, repr=False)
    #: 按工具名取 `write_path_keys`（装配时闭包注册表；未装配则解析不到路径）
    path_keys_for: Optional[PathKeysFor] = field(default=None, repr=False)
    needs_reread: Set[str] = field(default_factory=set)
    pending_review: List[str] = field(default_factory=list)
    reviewed_ok: bool = True
    # 真写次数。预览解锁时记下当时的值，用来区分「写之前已解锁」和「写之后才解锁」。
    _write_generation: int = 0

    # ── 检查状态──
    intent: str = ""  # "" | "debug" | "troubleshoot"
    evidence_ok: bool = False
    fixable_paths: List[str] = field(default_factory=list)
    apply_patch_pending: bool = False
    pending_diagnose_red: bool = False
    large_delete_flag: bool = False
    diag_fail_flag: bool = False
    last_diagnose_summary: str = ""
    claim_fixed_blocked: bool = False

    @property
    def _pending(self) -> Dict[str, Dict[str, Any]]:
        """未提交预览字典（测试与兼容层读取长度 / 键）。"""
        return self._store.records

    def path_keys(self, tool: str) -> Tuple[str, ...]:
        """工具声明的写路径参数键序；无查找器或未声明时为空元组。"""
        if self.path_keys_for is None:
            return ()
        return tuple(
            str(k).strip()
            for k in (self.path_keys_for(str(tool or "")) or ())
            if str(k).strip()
        )

    # ── ① 预览登记（id 制）──────────────────────────────────
    def register_preview(self, tool: str, arguments: Dict[str, Any]) -> str:
        """登记一次预览快照（写参数入库），返回 confirm_id（提交唯一凭据）。"""
        return self._store.register_preview(
            tool, arguments, path_keys=self.path_keys(tool)
        )

    def peek(self, confirm_id: str) -> Optional[Dict[str, Any]]:
        """查看确认 ID 关联的预览快照（不消费）；无效返回 None。"""
        return self._store.peek(confirm_id)

    def take_record(self, confirm_id: str) -> Optional[Dict[str, Any]]:
        """取出并消费预览快照（完整记录：tool + arguments，一次性）；无效/已使用返回 None。"""
        return self._store.take_record(confirm_id)

    def take(self, confirm_id: str) -> Optional[Dict[str, Any]]:
        """取出并消费预览快照的写参数（一次性）；无效/已使用返回 None。"""
        return self._store.take(confirm_id)

    def discard(self, confirm_id: str) -> bool:
        """丢弃一个未提交的预览快照（释放，不执行）；返回是否命中。"""
        return self._store.discard(confirm_id)

    # ── ② 确认 ──────────────────────────────────────────────
    def confirm(self, confirm_id: str) -> bool:
        """确认（review 通过）某次预览可提交；返回是否找到该快照。"""
        return self._store.confirm(confirm_id, write_generation=self._write_generation)

    # ── ③ 提交前检查（四步协议核心）──────────────────────────
    def check_write(self, wc: WriteContext) -> GateDecision:
        """写前组合门控（id 制）。"""
        return _checks.check_write(self, wc)

    # ── ④ 记账与重读 / 复核 ─────────────────────────
    def note_committed(
        self,
        path: str,
        *,
        diff_text: str = "",
        tool: str = "",
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
        if diff_text:
            _diagnose.maybe_flag_large_delete(self, norm, diff_text)

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
        """写后本地检查：.py / .json。"""
        return _diagnose.run_post_write_checks(self, path)

    def build_quality_report(self, path: str) -> Dict[str, Any]:
        """写后质量报告：overall / checks / required_next_actions。"""
        return _diagnose.build_quality_report(self, path)

    def _flag_diag_fail(self, summary: str) -> None:
        _diagnose.flag_diag_fail(self, summary)

    def _maybe_flag_large_delete(self, path: str, diff_text: str) -> None:
        _diagnose.maybe_flag_large_delete(self, path, diff_text)
