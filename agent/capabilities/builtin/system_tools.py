# -*- coding: utf-8 -*-
"""系统与环境工具：env_probe / unified_diagnose / git_workspace。

- env_probe：探测 shell/python 可执行文件并给出使用建议；
- unified_diagnose：AST 语法检查 + 可选 ruff（PATH 中存在时）；发现 error 级问题时 ok=false 且 data 带全量诊断；
- git_workspace：只读四模式（worktree / log / blame / show）；结构化错误随 data 透传。
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from agent.capabilities.registry import ToolPlugin

BUILTIN_GLOB = "**/*.py"
BUILTIN_LIMIT_FILES = 500
BUILTIN_TIMEOUT_SEC = 120
BUILTIN_TRY_RUFF = True

GIT_MAX_DIFF_CHARS = 200_000
GIT_LOG_MAX = 20
GIT_BLAME_MAX_BYTES = 2_000_000


class DiagnosticsFailed(RuntimeError):
    """诊断发现 error 级问题：ok=false 但携带完整诊断数据。"""

    def __init__(self, message: str, data: Dict[str, Any]) -> None:
        super().__init__(message)
        self.data = data


class GitWorkspaceError(RuntimeError):
    """git 查询失败：结构化错误载荷随 data 透传。"""

    def __init__(self, message: str, *, hint: str = "", exit_code: Optional[int] = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.data = {
            "code": "E_GIT_WORKSPACE",
            "type": "GitWorkspaceError",
            "message": message,
            "exit_code": exit_code,
            "hint": hint or "检查 path 是否为 Git 仓库根目录，并确认 git 在 PATH 中",
            "retryable": retryable,
        }


def _read_text_any(path: Path, encoding: str) -> str:
    """源码读取：显式编码 errors=replace；auto 按 utf-8→gb18030→gbk 尝试。"""
    if encoding != "auto":
        return path.read_text(encoding=encoding, errors="replace")
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


class EnvProbeTool(ToolPlugin):
    """命令行环境探测。"""

    name = "env_probe"
    label = "探测运行环境"
    icon = "🧪"
    description = "探测本机可用命令行环境（cmd / powershell / pwsh / bash / python / py）并给出使用建议。"
    parameters: Dict[str, Dict[str, Any]] = {}

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # 只给命令名，不给 `.exe` 后缀：Windows 上 `shutil.which` 会按 PATHEXT 自行补全，
        # 写死 `.exe` 会让 POSIX 上一个也找不到（`bash.exe` 不存在）。
        candidates = [
            ("cmd", "cmd"),
            ("powershell", "powershell"),
            ("pwsh", "pwsh"),
            ("bash", "bash"),
            ("python", "python"),
            ("py", "py"),
        ]
        available: List[Dict[str, str]] = []
        for key, exe in candidates:
            path = shutil.which(exe) or ""
            if path:
                available.append({"mode": key, "executable": exe, "path": path})
        recommendations = [
            "文件读写优先使用工作区内工具：read_file、write_file、grep_files 等（进程内调用）。",
            "复杂引号/多行内容优先 write_file 落盘或使用 run_command（低优先级，注意安全策略）。",
        ]
        if any(x["mode"] == "cmd" for x in available):
            recommendations.append("Windows 下简单命令拼接可优先 cmd。")
        if any(x["mode"] == "powershell" for x in available):
            recommendations.append("PowerShell 可用；深层嵌套转义成本较高，复杂场景优先专用工具。")
        if any(x["mode"] == "bash" for x in available):
            recommendations.append("bash 可用；复杂引号场景用它比 cmd 少一层转义。")
        return {
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "cwd": str(Path.cwd()),
            "available": available,
            "pycharm_terminal_note": "IDE 终端调用系统 shell，常规命令均可使用。",
            "recommendations": recommendations,
        }


class UnifiedDiagnoseTool(ToolPlugin):
    """Python 统一诊断：AST 语法检查 + 可选 ruff。"""

    name = "unified_diagnose"
    label = "统一诊断"
    icon = "🛠️"
    description = "对目录下 Python 文件做 AST 语法诊断，并尽力调用 ruff（PATH 中存在时）；发现 error 级问题返回 ok=false。"
    parameters = {
        "path": {"type": "string", "description": "项目根目录"},
        "glob_pattern": {"type": "string", "description": "待扫描 Python 文件 glob（默认 **/*.py）"},
        "limit": {"type": "integer", "description": "最多扫描文件数（默认 500）"},
        "encoding": {"type": "string", "description": "读源文件编码（默认 utf-8；auto 尝试链）"},
        "timeout_sec": {"type": "integer", "description": "ruff 子进程超时秒数（默认 120）"},
        "no_ruff": {"type": "boolean", "description": "true 跳过 ruff，仅做 AST 语法检查"},
    }

    @staticmethod
    def _collect_py_files(root: Path, glob_pattern: str, limit: int) -> List[Path]:
        out: List[Path] = []
        for p in sorted(root.glob(glob_pattern)):
            if not p.is_file() or p.suffix.lower() != ".py":
                continue
            rp = p.resolve()
            try:
                rp.relative_to(root)
            except ValueError:
                continue
            out.append(rp)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _severity_for_ruff(code: str, message: str) -> str:
        if code.startswith("E9"):
            return "error"
        if code.startswith("F82"):
            return "error"
        if "invalid syntax" in message.lower():
            return "error"
        return "warning"

    def _syntax_diagnostics(self, files: List[Path], encoding: str) -> List[Dict[str, Any]]:
        diag: List[Dict[str, Any]] = []
        for path in files:
            try:
                src = _read_text_any(path, encoding)
            except OSError as e:
                diag.append(
                    {
                        "file": str(path),
                        "source": "syntax",
                        "rule": "io_error",
                        "severity": "error",
                        "line": None,
                        "column": None,
                        "end_line": None,
                        "end_column": None,
                        "message": str(e),
                    }
                )
                continue
            try:
                ast.parse(src, filename=str(path))
            except SyntaxError as e:
                lineno = e.lineno or 1
                diag.append(
                    {
                        "file": str(path),
                        "source": "syntax",
                        "rule": "syntax",
                        "severity": "error",
                        "line": lineno,
                        "column": e.offset or None,
                        "end_line": getattr(e, "end_lineno", None) or lineno,
                        "end_column": getattr(e, "end_offset", None),
                        "message": e.msg or str(e),
                    }
                )
        return diag

    def _run_ruff_json(self, root: Path, timeout: int) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        exe = shutil.which("ruff")
        if not exe:
            return None, "ruff 不在 PATH 中，已跳过"
        try:
            cp = subprocess.run(
                [exe, "check", ".", "--output-format=json"],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return None, f"ruff 超时（>{timeout}s），已跳过"
        except OSError as e:
            return None, f"ruff 无法执行: {e}"
        if cp.returncode not in (0, 1):
            err = (cp.stderr or cp.stdout or "").strip() or f"exit {cp.returncode}"
            return None, err
        raw = (cp.stdout or "").strip()
        if not raw:
            return [], None
        try:
            arr = json.loads(raw)
        except json.JSONDecodeError as e:
            return None, f"ruff JSON 解析失败: {e}"
        if not isinstance(arr, list):
            return None, "ruff 输出不是 JSON 数组"
        out: List[Dict[str, Any]] = []
        root_s = str(root.resolve())
        for item in arr:
            if not isinstance(item, dict):
                continue
            fn = item.get("filename")
            if not isinstance(fn, str):
                continue
            try:
                Path(fn).resolve().relative_to(Path(root_s))
            except ValueError:
                continue
            loc = item.get("location") or {}
            end_loc = item.get("end_location") or {}
            code = str(item.get("code") or "unknown")
            msg = str(item.get("message") or "")
            row, col = loc.get("row"), loc.get("column")
            erow, ecol = end_loc.get("row"), end_loc.get("column")
            out.append(
                {
                    "file": str(Path(fn).resolve()),
                    "source": "ruff",
                    "rule": code,
                    "severity": self._severity_for_ruff(code, msg),
                    "line": int(row) if isinstance(row, int) else None,
                    "column": int(col) if isinstance(col, int) else None,
                    "end_line": int(erow) if isinstance(erow, int) else None,
                    "end_column": int(ecol) if isinstance(ecol, int) else None,
                    "message": msg,
                }
            )
        return out, None

    @staticmethod
    def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: Set[Tuple[Any, ...]] = set()
        out: List[Dict[str, Any]] = []
        for d in sorted(
            items,
            key=lambda x: (x.get("file") or "", x.get("line") or 0, x.get("column") or 0, x.get("rule") or ""),
        ):
            key = (d.get("file"), d.get("line"), d.get("column"), d.get("rule"), d.get("source"), d.get("message"))
            if key in seen:
                continue
            seen.add(key)
            out.append(d)
        return out

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise ValueError("缺少 path")
        r = Path(raw_path).resolve()
        if not r.is_dir():
            raise NotADirectoryError(f"path 不是目录: {r}")
        glob_pattern = str(arguments.get("glob_pattern") or BUILTIN_GLOB)
        raw_limit = arguments.get("limit")
        raw_timeout = arguments.get("timeout_sec")
        try:
            limit = int(raw_limit) if raw_limit is not None and str(raw_limit).strip() != "" else BUILTIN_LIMIT_FILES
            timeout_sec = int(raw_timeout) if raw_timeout is not None and str(raw_timeout).strip() != "" else BUILTIN_TIMEOUT_SEC
        except (TypeError, ValueError):
            raise ValueError("limit / timeout_sec 须为整数")
        if limit <= 0:
            raise ValueError("limit 必须 > 0")
        if timeout_sec <= 0:
            raise ValueError("timeout_sec 必须 > 0")
        encoding = str(arguments.get("encoding") or "utf-8")
        no_ruff = bool(arguments.get("no_ruff", False))

        files = self._collect_py_files(r, glob_pattern, limit)
        diagnostics = self._syntax_diagnostics(files, encoding)
        ruff_notes: List[str] = []
        ruff_diag: Optional[List[Dict[str, Any]]] = None
        try_ruff = BUILTIN_TRY_RUFF and not no_ruff
        if try_ruff:
            ruff_diag, ruff_err = self._run_ruff_json(r, timeout_sec)
            if ruff_err:
                ruff_notes.append(ruff_err)
            if ruff_diag is not None:
                diagnostics.extend(ruff_diag)
        diagnostics = self._dedupe(diagnostics)
        error_count = sum(1 for d in diagnostics if d.get("severity") == "error")
        warn_count = sum(1 for d in diagnostics if d.get("severity") == "warning")
        payload = {
            "path": str(r),
            "glob_pattern": glob_pattern,
            "files_scanned": len(files),
            "diagnostics": diagnostics,
            "summary": {"errors": error_count, "warnings": warn_count, "total": len(diagnostics)},
            "ruff_attempted": try_ruff,
            "ruff_included": ruff_diag is not None,
            "notes": ruff_notes,
        }
        if error_count > 0:
            raise DiagnosticsFailed(f"诊断发现 {error_count} 个 error 级问题", payload)
        return payload


_HEADER_RE = re.compile(r"^([0-9a-f]{7,40}) (\d+) (\d+) (\d+)$")


class GitWorkspaceTool(ToolPlugin):
    """Git 工作区只读查询。"""

    name = "git_workspace"
    label = "查看 Git 工作区"
    icon = "🌿"
    description = "Git 工作区只读查询：worktree（状态+diff）/ log / blame / show；不执行写入型 git 命令。"
    parameters = {
        "path": {"type": "string", "description": "Git 仓库根目录（含 .git）"},
        "mode": {"type": "string", "description": "worktree / log / blame / show（默认 worktree）"},
        "max_diff_chars": {"type": "integer", "description": "diff/补丁输出截断上限（默认 200000）"},
        "log_max": {"type": "integer", "description": "log 模式提交条数（默认 20）"},
        "blame_path": {"type": "string", "description": "blame 模式：相对仓库根的文件路径"},
        "start_line": {"type": "integer", "description": "blame 起始行（与 end_line 成对）"},
        "end_line": {"type": "integer", "description": "blame 结束行（闭区间）"},
        "show_ref": {"type": "string", "description": "show 模式：提交 hash / 分支等（默认 HEAD）"},
    }

    @staticmethod
    def _run_git(cwd: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except FileNotFoundError as e:
            raise GitWorkspaceError(f"git 不在 PATH 中或无法执行: {e}")
        except subprocess.TimeoutExpired:
            raise GitWorkspaceError(f"git 命令超时（>{timeout}s）: {' '.join(args)}", retryable=True)

    @staticmethod
    def _truncate(s: str, max_chars: int) -> Tuple[str, bool]:
        if len(s) <= max_chars:
            return s, False
        return s[:max_chars], True

    @staticmethod
    def _ensure_repo(root: Path) -> None:
        if not root.is_dir():
            raise GitWorkspaceError(f"root 不是目录: {root}")
        if not (root / ".git").exists():
            raise GitWorkspaceError(f"不是 Git 仓库根目录（缺少 .git）: {root}")

    @staticmethod
    def _resolve_under_root(root: Path, rel: str) -> Path:
        root_r = root.resolve()
        p = (root_r / rel).resolve()
        try:
            p.relative_to(root_r)
        except ValueError:
            raise GitWorkspaceError(f"path 越出 root: {rel}")
        return p

    def _mode_worktree(self, root: Path, max_chars: int) -> Dict[str, Any]:
        st = self._run_git(root, "status", "--porcelain=v1", "-b")
        if st.returncode != 0:
            raise GitWorkspaceError(f"git status 失败: {st.stderr.strip() or st.stdout.strip()}")
        du = self._run_git(root, "diff", "--no-color")
        if du.returncode != 0:
            raise GitWorkspaceError(f"git diff 失败: {du.stderr.strip() or du.stdout.strip()}")
        ds = self._run_git(root, "diff", "--no-color", "--cached")
        if ds.returncode != 0:
            raise GitWorkspaceError(f"git diff --cached 失败: {ds.stderr.strip() or ds.stdout.strip()}")
        diff_worktree, tw = self._truncate(du.stdout or "", max_chars)
        diff_staged, ts = self._truncate(ds.stdout or "", max_chars)
        lines = [ln for ln in (st.stdout or "").splitlines() if ln.strip()]
        branch_line = ""
        porcelain: List[Dict[str, str]] = []
        for ln in lines:
            if ln.startswith("## "):
                branch_line = ln[3:].strip()
            else:
                porcelain.append({"raw": ln})
        return {
            "mode": "worktree",
            "path": str(root),
            "branch_line": branch_line,
            "porcelain": porcelain,
            "porcelain_count": len(porcelain),
            "diff_worktree": diff_worktree,
            "diff_staged": diff_staged,
            "diff_truncated": tw or ts,
            "raw_diff_worktree_chars": len(du.stdout or ""),
            "raw_diff_staged_chars": len(ds.stdout or ""),
            "effective_max_diff_chars": max_chars,
        }

    def _mode_log(self, root: Path, max_n: int) -> Dict[str, Any]:
        if max_n <= 0:
            raise GitWorkspaceError("log_max 必须 > 0")
        fmt = "%H%x1f%s%x1f%aN%x1f%ai%x1e"
        cp = self._run_git(root, "log", f"-n{max_n}", f"--pretty=format:{fmt}", "--no-color")
        if cp.returncode != 0:
            raise GitWorkspaceError(cp.stderr.strip() or cp.stdout.strip() or "git log 失败")
        entries: List[Dict[str, str]] = []
        raw = (cp.stdout or "").strip()
        if raw:
            for rec in raw.split("\x1e"):
                rec = rec.strip()
                if not rec:
                    continue
                parts = rec.split("\x1f")
                if len(parts) < 4:
                    continue
                entries.append({"commit": parts[0], "subject": parts[1], "author": parts[2], "date": parts[3]})
        return {"mode": "log", "path": str(root), "log_max": max_n, "entries": entries}

    def _mode_blame(self, root: Path, rel_path: str, start_line: Optional[int], end_line: Optional[int]) -> Dict[str, Any]:
        target = self._resolve_under_root(root, rel_path)
        if not target.is_file():
            raise GitWorkspaceError(f"blame 目标不是文件: {target}")
        raw_size = target.stat().st_size
        if raw_size > GIT_BLAME_MAX_BYTES and (start_line is None or end_line is None):
            raise GitWorkspaceError(f"文件过大（>{GIT_BLAME_MAX_BYTES} 字节），请指定 start_line / end_line（blame）")
        rel_git = target.resolve().relative_to(root.resolve()).as_posix()
        # porcelain 输出本身无色；新版 git 下 --no-color 与 --color-by-age 存在前缀歧义
        cmd: List[str] = ["blame", "--line-porcelain"]
        if start_line is not None and end_line is not None:
            if start_line < 1 or end_line < 1 or start_line > end_line:
                raise GitWorkspaceError("blame 下行范围非法：start_line / end_line 须为 >=1 且 start_line<=end_line")
            cmd += ["-L", f"{start_line},{end_line}"]
        cmd += ["--", rel_git]
        cp = self._run_git(root, *cmd)
        if cp.returncode != 0:
            raise GitWorkspaceError(cp.stderr.strip() or cp.stdout.strip() or "git blame 失败")
        lines_out: List[Dict[str, Any]] = []
        cur: Optional[Dict[str, Any]] = None
        meta: Dict[str, str] = {}
        for line in (cp.stdout or "").splitlines():
            m = _HEADER_RE.match(line)
            if m:
                cur = {"commit": m.group(1), "orig_line": int(m.group(2)), "final_line": int(m.group(3))}
                meta = {}
                continue
            if cur is None:
                continue
            if line.startswith("\t"):
                lines_out.append(
                    {
                        "commit": str(cur["commit"]),
                        "orig_line": int(cur["orig_line"]),
                        "final_line": int(cur["final_line"]),
                        "text": line[1:],
                        "author": meta.get("author", ""),
                        "summary": meta.get("summary", ""),
                    }
                )
                cur = None
                meta = {}
                continue
            if " " in line:
                k, _, rest = line.partition(" ")
                meta[k] = rest.strip()
        return {"mode": "blame", "path": str(root), "relative_path": rel_git, "lines": lines_out}

    def _mode_show(self, root: Path, ref: str, max_chars: int) -> Dict[str, Any]:
        ref = (ref or "").strip()
        if not ref:
            raise GitWorkspaceError("show_ref 不能为空")
        meta_cp = self._run_git(root, "show", "--no-color", "--no-patch", "--format=medium", ref)
        if meta_cp.returncode != 0:
            raise GitWorkspaceError(meta_cp.stderr.strip() or meta_cp.stdout.strip() or "git show 失败")
        stat_cp = self._run_git(root, "show", "--no-color", "--no-patch", "--stat", ref)
        stat_text = (stat_cp.stdout or "").strip() if stat_cp.returncode == 0 else ""
        # --root：根提交（无父）时 diff-tree 才会输出文件清单（否则为空）
        ns_cp = self._run_git(root, "diff-tree", "--root", "--no-color", "--no-commit-id", "--name-status", "-r", ref)
        if ns_cp.returncode != 0:
            raise GitWorkspaceError(ns_cp.stderr.strip() or ns_cp.stdout.strip() or "git diff-tree 失败")
        files: List[Dict[str, str]] = []
        for ln in (ns_cp.stdout or "").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            parts = ln.split("\t", maxsplit=1)
            if len(parts) == 2:
                files.append({"status": parts[0], "path": parts[1]})
            else:
                files.append({"status": "?", "path": ln})
        patch_cp = self._run_git(root, "show", "--no-color", "--pretty=format:", "-p", ref)
        patch_raw = patch_cp.stdout or ""
        if patch_cp.returncode != 0:
            patch_raw = ""
        patch, trunc = self._truncate(patch_raw, max_chars)
        return {
            "mode": "show",
            "path": str(root),
            "ref": ref,
            "commit_message": (meta_cp.stdout or "").strip(),
            "stat_summary": stat_text,
            "changed_files": files,
            "patch": patch,
            "patch_truncated": trunc,
            "raw_patch_chars": len(patch_raw),
            "effective_max_diff_chars": max_chars,
        }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise GitWorkspaceError("缺少 path")
        try:
            max_diff_chars = int(arguments.get("max_diff_chars") or GIT_MAX_DIFF_CHARS)
        except (TypeError, ValueError):
            raise GitWorkspaceError("max_diff_chars 须为整数")
        max_chars = max_diff_chars if max_diff_chars and max_diff_chars > 0 else GIT_MAX_DIFF_CHARS
        try:
            log_n = int(arguments.get("log_max") or GIT_LOG_MAX)
        except (TypeError, ValueError):
            raise GitWorkspaceError("log_max 须为整数")
        mode = str(arguments.get("mode") or "worktree").strip().lower()
        bp = str(arguments.get("blame_path") or "").strip()
        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")
        try:
            if start_line is not None:
                start_line = int(start_line)
            if end_line is not None:
                end_line = int(end_line)
        except (TypeError, ValueError):
            raise GitWorkspaceError("start_line / end_line 须为整数")
        show_ref = str(arguments.get("show_ref") or "HEAD")

        r = Path(raw_path).resolve()
        try:
            self._ensure_repo(r)
            if mode == "worktree":
                return self._mode_worktree(r, max_chars)
            if mode == "log":
                return self._mode_log(r, log_n)
            if mode == "blame":
                if not bp:
                    raise GitWorkspaceError("blame 模式需要 blame_path（相对仓库根 path 的文件路径）")
                if (start_line is None) != (end_line is None):
                    raise GitWorkspaceError("blame 模式下 start_line 与 end_line 必须同时给出或同时省略")
                return self._mode_blame(r, bp, start_line, end_line)
            if mode == "show":
                return self._mode_show(r, show_ref, max_chars)
            raise GitWorkspaceError(f"未知 mode: {mode!r}（须为 worktree|log|blame|show）")
        except GitWorkspaceError:
            raise
        except Exception as e:
            raise GitWorkspaceError(str(e))


def build_plugins() -> List[ToolPlugin]:
    """构造本组工具（env_probe / unified_diagnose / git_workspace）。"""
    return [EnvProbeTool(), UnifiedDiagnoseTool(), GitWorkspaceTool()]
