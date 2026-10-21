# -*- coding: utf-8 -*-
"""文本编辑工具组：replace_in_file / apply_patch / read_write——预览 + 统一提交执行器。

- 预览入口（各 ToolPlugin.execute）：校验参数与目标文件状态、计算将产生的变更（不落盘）；
  由门控在结果中注入 confirm_id，确认后经 commit_write（统一提交入口）分派执行；
- 提交执行器（build_executors）：执行实际写盘；覆盖既有文件前留版本化备份（file_undo 依据），
  并随 "_diff" 返回旧→新 diff（供大删除检测用）。

预览入口只支持字面替换与行区间替换，不支持 region 字符区间与 rules 多条替换模式；
apply_patch 仅用于 path 根下已有文件（不支持新增 / 删除文件）。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.capabilities.registry import ToolPlugin
from agent.mechanisms.file_safety import FileBackups
from agent.mechanisms.quality import change_payload, diff_text

# ── 公共辅助 ────────────────────────────────────────────


def _read_text(target: Path) -> str:
    """读取文本文件（utf-8，容错替换）。"""
    return target.read_text(encoding="utf-8", errors="replace")


def _required_file(arguments: Dict[str, Any], key: str = "path") -> Path:
    """取必填文件路径参数并校验为既有文件。"""
    raw = str(arguments.get(key) or "").strip()
    if not raw:
        raise ValueError(f"缺少 {key}")
    target = Path(raw)
    if not target.is_file():
        raise FileNotFoundError(f"文件不存在或不是文件：{target}")
    return target


def _required_dir(arguments: Dict[str, Any], key: str) -> Path:
    """取必填目录路径参数并校验为既有目录。"""
    raw = str(arguments.get(key) or "").strip()
    if not raw:
        raise ValueError(f"缺少 {key}")
    target = Path(raw)
    if not target.is_dir():
        raise NotADirectoryError(f"目录不存在或不是目录：{target}")
    return target


# ── replace_in_file ────────────────────────────────────


def _apply_one_literal(text: str, old_text: str, new_text: str,
                       replace_all: bool, expected: Any = None,
                       index: int = 0) -> Dict[str, Any]:
    """单条字面替换；未命中或命中数不符抛带 data 的 ValueError。

    `index` 是批量里的序号（0-based），用于指明是哪一条出的问题。
    """
    label = f"第 {index + 1} 条：" if index else ""
    count = text.count(old_text)
    if count == 0:
        # 锁死：old 字面未命中一律 old_text_not_found。
        # 不得用「new 已在文件中」或删除语义反推 already_applied——
        # 那是全局属性猜局部操作，会掩盖找错串/找错文件；也不做大小写折叠。
        exc = ValueError(label + "old_text 未找到")
        exc.data = {
            "status": "old_text_not_found",
            "needs_commit": False,
            "matches": 0,
            "edit_index": index,
            "message": label + "old_text 未找到，未生成预览",
        }
        raise exc
    if expected is not None and int(expected) != count:
        exc = ValueError(
            f"{label}命中数不符：old_text 出现 {count} 次，expected_replacements={int(expected)}"
        )
        exc.data = {
            "status": "replacement_count_mismatch",
            "needs_commit": False,
            "matches": count,
            "expected_replacements": int(expected),
            "edit_index": index,
            "message": str(exc),
        }
        raise exc
    replaced = count if replace_all else 1
    new_content = text.replace(old_text, new_text) if replace_all else text.replace(old_text, new_text, 1)
    return {"text": new_content, "matches": count, "replaced": replaced}


def _apply_edits(text: str, edits: Any) -> Dict[str, Any]:
    """批量字面替换：按顺序逐条应用，任一条不命中即整批失败。

    顺序敏感是刻意的：后一条看到的是前一条替换后的文本，与逐次手工调用一致，
    这样「先改 A 再改 B」的既有工作方式原样成立；出错时指明是第几条。
    """
    if not isinstance(edits, list) or not edits:
        raise ValueError("edits 必须是非空数组")
    current = text
    total_matches = 0
    total_replaced = 0
    for index, item in enumerate(edits):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index + 1} 条：edits 的每项须是对象")
        old_text = str(item.get("old_text") or "")
        if not old_text:
            raise ValueError(f"第 {index + 1} 条：缺少 old_text")
        outcome = _apply_one_literal(
            current,
            old_text,
            str(item.get("new_text") or ""),
            bool(item.get("replace_all", True)),
            item.get("expected_replacements"),
            index,
        )
        current = outcome["text"]
        total_matches += int(outcome["matches"])
        total_replaced += int(outcome["replaced"])
    if current == text:
        return {
            "text": text,
            "mode": "edits",
            "matches": total_matches,
            "replaced": 0,
            "status": "already_applied",
            "reason": "noop_replace",
        }
    return {
        "text": current,
        "mode": "edits",
        "matches": total_matches,
        "replaced": total_replaced,
    }


def _reject_conflicting_edits_keys(arguments: Dict[str, Any]) -> None:
    """edits 模式下的参数互斥检查；不合规直接抛，绝不静默忽略。

    顶层 `replace_all` / `expected_replacements` 在批量模式下不生效（每条自己带）。
    放着不管就是静默忽略：用户写 `replace_all: false` 会以为只改第一处，
    实际每条都按默认把全部命中替换掉 —— 多改内容且没人报警。
    """
    if (arguments.get("old_text") or arguments.get("line_start") is not None
            or arguments.get("line_end") is not None):
        raise ValueError("edits 不能与 old_text / line_start / line_end 同时使用")
    for key in ("replace_all", "expected_replacements"):
        if arguments.get(key) is not None:
            raise ValueError(f"edits 模式下 {key} 须写进每一条 edit 里，不接受顶层设置")


def _apply_replace(text: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """在 text 上执行替换（不落盘）；返回 {text, mode, matches, replaced}；失败抛 ValueError。"""
    edits = arguments.get("edits")
    if edits is not None:
        _reject_conflicting_edits_keys(arguments)
        return _apply_edits(text, edits)
    line_start = arguments.get("line_start")
    line_end = arguments.get("line_end")
    if line_start is not None or line_end is not None:
        lines = text.split("\n")
        start = int(line_start) if line_start is not None else 1
        end = int(line_end) if line_end is not None else len(lines)
        if not (1 <= start <= end <= len(lines)):
            raise ValueError(f"行区间无效：line_start={start} / line_end={end}（共 {len(lines)} 行）")
        new_text = str(arguments.get("new_text") or "")
        merged = lines[: start - 1] + new_text.split("\n") + lines[end:]
        return {
            "text": "\n".join(merged),
            "mode": "lines",
            "matches": end - start + 1,
            "replaced": end - start + 1,
        }
    old_text = str(arguments.get("old_text") or "")
    if not old_text:
        raise ValueError("缺少 old_text（或 line_start / line_end）")
    new_text = str(arguments.get("new_text") or "")
    count = text.count(old_text)
    if count == 0:
        # 锁死：old 字面未命中一律 old_text_not_found。
        # 不得用「new 已在文件中」或删除语义反推 already_applied——
        # 那是全局属性猜局部操作，会掩盖找错串/找错文件；也不做大小写折叠。
        exc = ValueError("old_text 未找到")
        exc.data = {
            "status": "old_text_not_found",
            "needs_commit": False,
            "matches": 0,
            "message": "old_text 未找到，未生成预览",
        }
        raise exc
    expected = arguments.get("expected_replacements")
    if expected is not None and int(expected) != count:
        exc = ValueError(
            f"命中数不符：old_text 出现 {count} 次，expected_replacements={int(expected)}"
        )
        exc.data = {
            "status": "replacement_count_mismatch",
            "needs_commit": False,
            "matches": count,
            "expected_replacements": int(expected),
            "message": str(exc),
        }
        raise exc
    if bool(arguments.get("replace_all", True)):
        new_content = text.replace(old_text, new_text)
        replaced = count
    else:
        new_content = text.replace(old_text, new_text, 1)
        replaced = 1
    # 同值替换（old==new）或替换后无变化：勿发空 diff 的 confirm_id
    if new_content == text:
        return {
            "text": text,
            "mode": "literal",
            "matches": count,
            "replaced": 0,
            "status": "already_applied",
            "reason": "noop_replace",
        }
    return {
        "text": new_content,
        "mode": "literal",
        "matches": count,
        "replaced": replaced,
    }


class ReplaceInFileTool(ToolPlugin):
    """预览：文本替换（字面 / 行区间），不落盘。"""

    name = "replace_in_file"
    label = "替换文件内容"
    icon = "✏️"
    description = (
        "预览文本替换（不落盘）：字面替换（old_text→new_text，默认全部替换，可 expected_replacements 校验）"
        "或行区间替换（line_start/line_end）；返回 confirm_id，凭 commit_write 提交。"
        "多处字面替换可改用 edits 数组一次提交（按顺序应用，任一条未命中则整批拒绝并指明第几条）。"
        "old_text 字面未命中时一律 ok=false 且 data.status=old_text_not_found"
        "（不因 new_text 已在文件中、也不做大小写折叠而改判 already_applied）。"
        "old 命中但替换后内容不变（如同值替换）时 status=already_applied（needs_commit=false）。"
    )
    needs_preview = True
    needs_reread = True
    write_path_keys = ("path",)
    parameters = {
        "path": {"type": "string", "description": "目标文件路径"},
        "old_text": {"type": "string", "description": "字面替换：待替换文本"},
        "new_text": {"type": "string", "description": "替换为的文本（字面 / 行区间均用）"},
        "edits": {
            "type": "array",
            "description": (
                "批量字面替换：每项 {old_text, new_text, replace_all?, expected_replacements?}，"
                "按顺序应用；不能与 old_text / line_start / line_end 同时使用"
            ),
        },
        "replace_all": {"type": "boolean", "description": "字面替换：是否替换全部命中，默认 true"},
        "expected_replacements": {"type": "integer", "description": "字面替换：可选，命中数不符则拒绝"},
        "line_start": {"type": "integer", "description": "行区间替换：起始行（1-based 含）"},
        "line_end": {"type": "integer", "description": "行区间替换：结束行（1-based 含）"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        target = _required_file(arguments)
        text = _read_text(target)
        try:
            outcome = _apply_replace(text, arguments)
        except ValueError as exc:
            data = getattr(exc, "data", None)
            if isinstance(data, dict):
                data = dict(data)
                data.setdefault("path", str(target))
                exc.data = data
            raise
        if outcome.get("status") == "already_applied":
            return {
                "path": str(target),
                "status": "already_applied",
                "applied": False,
                "needs_commit": False,
                "mode": outcome["mode"],
                "matches": int(outcome.get("matches") or 0),
                "replaced": 0,
                "message": "替换结果与当前内容相同，无需写入",
                "_change": change_payload(text, text, str(target)),
            }
        return {
            "path": str(target),
            "preview": True,
            "mode": outcome["mode"],
            "matches": outcome["matches"],
            "replaced": outcome["replaced"],
            "bytes_before": len(text.encode("utf-8")),
            "bytes_after": len(outcome["text"].encode("utf-8")),
            "_change": change_payload(text, outcome["text"], str(target)),
        }


# ── apply_patch ────────────────────────────────────────


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_HUNK_PREFIXES = ("+", "-", " ")


def _hunk_usage(hunk: Dict[str, Any]) -> Tuple[int, int]:
    """返回 hunk 已消费的 (旧行数, 新行数)。"""
    ctx = sum(1 for t, _ in hunk["lines"] if t == " ")
    removed = sum(1 for t, _ in hunk["lines"] if t == "-")
    added = sum(1 for t, _ in hunk["lines"] if t == "+")
    return ctx + removed, ctx + added


def _parse_patch(patch_text: str) -> List[Dict[str, Any]]:
    """解析 unified diff；→ [{"path": str, "hunks": [...]}]；失败抛 ValueError。"""
    sections: List[Dict[str, Any]] = []
    section: Optional[Dict[str, Any]] = None
    hunk: Optional[Dict[str, Any]] = None
    for raw in str(patch_text or "").rstrip("\n").split("\n"):
        if hunk is not None:
            old_used, new_used = _hunk_usage(hunk)
            pending = old_used < hunk["old_count"] or new_used < hunk["new_count"]
            if pending and (raw[:1] in _HUNK_PREFIXES or raw == ""):
                hunk["lines"].append((" " if raw == "" else raw[0], raw[1:]))
                continue
            if not pending:
                hunk = None
        if raw.startswith("diff ") or raw.startswith("index "):
            continue
        if raw.startswith("--- "):
            section = {"old_path": raw[4:].strip(), "path": "", "hunks": []}
            sections.append(section)
            hunk = None
            continue
        if raw.startswith("+++ "):
            if section is None or section["path"]:
                raise ValueError("补丁结构错误：+++ 缺少对应 --- 头")
            section["path"] = raw[4:].strip()
            continue
        if raw.startswith("@@"):
            if section is None or not section["path"]:
                raise ValueError("补丁结构错误：hunk 缺少文件头（--- / +++）")
            match = _HUNK_RE.match(raw)
            if not match:
                raise ValueError(f"无法解析 hunk 头：{raw[:80]}")
            hunk = {
                "old_start": int(match.group(1)),
                "old_count": int(match.group(2) or 1),
                "new_count": int(match.group(4) or 1),
                "lines": [],
            }
            section["hunks"].append(hunk)
            continue
        if raw.startswith("\\"):
            continue
        if raw.strip() == "":
            continue
        if raw[:1] in _HUNK_PREFIXES:
            raise ValueError("补丁行数超出 hunk 头部声明（补丁可能损坏）")
        raise ValueError(f"无法解析补丁行：{raw[:80]!r}")
    if not sections:
        raise ValueError("补丁为空或缺少 --- / +++ 文件头")
    for sec in sections:
        if not sec["path"]:
            raise ValueError(f"补丁结构错误：{sec['old_path'] or '（未知）'} 缺少 +++ 行")
        if not sec["hunks"]:
            raise ValueError(f"文件段缺少 hunk：{sec['path']}")
        for h in sec["hunks"]:
            old_used, new_used = _hunk_usage(h)
            if old_used != h["old_count"] or new_used != h["new_count"]:
                raise ValueError(
                    f"hunk 声明行数与实际不符（-{h['old_count']},+{h['new_count']} vs 实际 {old_used}/{new_used}）：{sec['path']}"
                )
    return sections


def _resolve_patch_target(root: Path, patch_path: str) -> Path:
    """补丁文件路径 → 根下绝对路径（去 a//b/ 前缀；须在根内且为已有文件）。"""
    raw = str(patch_path or "").strip()
    if raw == "/dev/null":
        raise ValueError("不支持新增 / 删除文件的补丁（仅用于已有文件）")
    if raw.startswith("a/") or raw.startswith("b/"):
        raw = raw[2:]
    candidate = Path(raw)
    target = candidate if candidate.is_absolute() else root / candidate
    resolved = target.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"补丁目标越出根目录：{raw}")
    if not resolved.is_file():
        raise FileNotFoundError(f"补丁目标不存在（仅用于已有文件）：{raw}")
    return resolved


def _apply_hunks(text: str, hunks: List[Dict[str, Any]]) -> str:
    """把 hunks 应用到 text（按声明位置 + 累计偏移严格校验上下文）；失败抛 ValueError。"""
    lines = text.split("\n")
    offset = 0
    for hunk in hunks:
        start = hunk["old_start"] - 1 + offset
        old_block = [ln for t, ln in hunk["lines"] if t in (" ", "-")]
        new_block = [ln for t, ln in hunk["lines"] if t in (" ", "+")]
        if start < 0 or start + len(old_block) > len(lines):
            raise ValueError(f"hunk 越界（第 {hunk['old_start']} 行）")
        if lines[start : start + len(old_block)] != old_block:
            raise ValueError(f"hunk 无法应用（第 {hunk['old_start']} 行附近上下文不匹配）")
        lines[start : start + len(old_block)] = new_block
        offset += len(new_block) - len(old_block)
    return "\n".join(lines)


class ApplyPatchTool(ToolPlugin):
    """预览：unified diff 应用（校验 + 统计），不落盘。"""

    name = "apply_patch"
    label = "应用补丁"
    icon = "🔧"
    description = "预览补丁应用（不落盘）：把 unified diff（patch_text）应用到 path 根下已有文件（目标可带 a//b/ 前缀，须在根内）；返回各文件统计与 confirm_id，凭 commit_write 提交。"
    needs_preview = True
    needs_reread = True
    write_path_keys = ("path",)
    parameters = {
        "path": {"type": "string", "description": "补丁应用根目录（目标文件须位于其下）"},
        "patch_text": {"type": "string", "description": "unified diff 文本（可含多个文件段）"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        root = _required_dir(arguments, "path")
        sections = _parse_patch(str(arguments.get("patch_text") or ""))
        files: List[Dict[str, Any]] = []
        for section in sections:
            target = _resolve_patch_target(root, section["path"])
            text = _read_text(target)
            new_text = _apply_hunks(text, section["hunks"])
            files.append(
                {
                    "path": str(target),
                    "hunks": len(section["hunks"]),
                    "additions": sum(1 for h in section["hunks"] for t, _ in h["lines"] if t == "+"),
                    "deletions": sum(1 for h in section["hunks"] for t, _ in h["lines"] if t == "-"),
                    "bytes_before": len(text.encode("utf-8")),
                    "bytes_after": len(new_text.encode("utf-8")),
                    "_change": change_payload(text, new_text, str(target)),
                }
            )
        return {"path": str(root), "preview": True, "files": files}


# ── read_write ─────────────────────────────────────────


def _slice_lines(text: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """行区间切片 + max_chars 截断；返回 {text, truncated}。"""
    lines = text.split("\n")
    start = int(arguments.get("line_start") or 1)
    end_raw = arguments.get("line_end")
    end = int(end_raw) if end_raw is not None else len(lines)
    if not (1 <= start <= end <= len(lines)):
        raise ValueError(f"行区间无效：line_start={start} / line_end={end}（共 {len(lines)} 行）")
    piece = "\n".join(lines[start - 1 : end])
    max_chars = int(arguments.get("max_chars") or 0)
    truncated = False
    if max_chars > 0 and len(piece) > max_chars:
        piece = piece[:max_chars]
        truncated = True
    return {"text": piece, "truncated": truncated}


class ReadWriteTool(ToolPlugin):
    """预览：从 source_path 取片段写入 dest_path（校验 + 切片），不落盘。"""

    name = "read_write"
    label = "管道读写"
    icon = "🔀"
    description = "预览管道写（不落盘）：从 source_path 取片段（可选 line_start/line_end 行区间、max_chars 截断）写入 dest_path；返回 confirm_id，凭 commit_write 提交。"
    needs_preview = True
    needs_reread = True
    write_path_keys = ("dest_path",)
    parameters = {
        "source_path": {"type": "string", "description": "源文件路径"},
        "dest_path": {"type": "string", "description": "目标文件路径"},
        "line_start": {"type": "integer", "description": "起始行（1-based 含）"},
        "line_end": {"type": "integer", "description": "结束行（1-based 含）"},
        "max_chars": {"type": "integer", "description": "最大字符数截断（0=不截断，默认 0）"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        source = _required_file(arguments, "source_path")
        dest_raw = str(arguments.get("dest_path") or "").strip()
        if not dest_raw:
            raise ValueError("缺少 dest_path")
        piece = _slice_lines(_read_text(source), arguments)
        payload = piece["text"].encode("utf-8")
        dest = Path(dest_raw)
        old_dest = ""
        if dest.is_file():
            try:
                old_dest = dest.read_text(encoding="utf-8", errors="replace")
            except OSError:
                old_dest = ""
        return {
            "source_path": str(source),
            "dest_path": str(dest),
            "preview": True,
            "bytes": len(payload),
            "truncated": piece["truncated"],
            "dest_exists": dest.is_file(),
            "_change": change_payload(old_dest, piece["text"], str(dest)),
        }


# ── 提交执行器（由 commit_write 统一分派）──────────────


def _execute_replace(backups: FileBackups, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """提交：重新校验并执行替换（预览后文件变化会被拒绝）；覆盖前留备份。"""
    target = _required_file(arguments)
    text = _read_text(target)
    outcome = _apply_replace(text, arguments)
    payload = outcome["text"].encode("utf-8")
    changed = diff_text(text, outcome["text"], str(target))
    mod_id = backups.create(target, mode=str(outcome["mode"]), diff_text=changed) or ""
    target.write_bytes(payload)
    return {
        "path": str(target),
        "written": True,
        "bytes": len(payload),
        "mod_id": mod_id,
        "_diff": changed,
    }


def _execute_patch(backups: FileBackups, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """提交：重新解析并应用补丁；逐文件留备份；path 记为首个目标文件。"""
    root = _required_dir(arguments, "path")
    sections = _parse_patch(str(arguments.get("patch_text") or ""))
    written: List[Dict[str, Any]] = []
    primary_diff = ""
    for index, section in enumerate(sections):
        target = _resolve_patch_target(root, section["path"])
        text = _read_text(target)
        new_text = _apply_hunks(text, section["hunks"])
        payload = new_text.encode("utf-8")
        changed = diff_text(text, new_text, str(target))
        mod_id = backups.create(target, mode="patch", diff_text=changed) or ""
        target.write_bytes(payload)
        if index == 0:
            primary_diff = changed
        written.append({"path": str(target), "bytes": len(payload), "mod_id": mod_id})
    primary = written[0]["path"] if written else str(root)
    return {"path": primary, "written": True, "files": written, "_diff": primary_diff}


def _execute_read_write(backups: FileBackups, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """提交：重新切片并写入 dest（覆盖前留备份）。"""
    source = _required_file(arguments, "source_path")
    dest_raw = str(arguments.get("dest_path") or "").strip()
    if not dest_raw:
        raise ValueError("预览快照不完整：请重新预览（read_write）")
    piece = _slice_lines(_read_text(source), arguments)
    payload = piece["text"].encode("utf-8")
    dest = Path(dest_raw)
    old_text = _read_text(dest) if dest.is_file() else ""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 目标可能原本不存在（此时没有旧内容可算 diff），与备份留档的口径一致
    changed = diff_text(old_text, piece["text"], str(dest)) if dest.is_file() else ""
    mod_id = backups.create(dest, mode="read_write", diff_text=changed) or ""
    dest.write_bytes(payload)
    return {
        "path": str(dest),
        "written": True,
        "bytes": len(payload),
        "truncated": piece["truncated"],
        "mod_id": mod_id,
        "_diff": changed,
    }


def build_plugins() -> List[ToolPlugin]:
    """构造本组预览插件（replace_in_file / apply_patch / read_write）。"""
    return [ReplaceInFileTool(), ApplyPatchTool(), ReadWriteTool()]


def build_executors(backups: FileBackups) -> Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]]:
    """构造本组提交执行器表。"""
    return {
        "replace_in_file": lambda args: _execute_replace(backups, args),
        "apply_patch": lambda args: _execute_patch(backups, args),
        "read_write": lambda args: _execute_read_write(backups, args),
    }
