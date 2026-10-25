# -*- coding: utf-8 -*-
"""命令执行安全机制：黑名单 / 内容级拦截 / safe_mode / 进程生命周期 / 输出净化 / shell 选择。

- 组 A 黑名单：真删除 / 毁灭性命令一律拦截（无论 safe_mode 开关）；
- 组 B 内容级拦截：base64 内联 / 重定向写源码 / sed -i / 脚本内容扫描；
- 组 C safe_mode：禁止字符 [;&|`$><]；
- 组 D 生命周期：进程登记 / 注销、进程树强杀、超时 / 取消强杀、退出清账；
- 组 E 输出：解码顺序、展示净化与截断、shell 选择。

设计：本模块只做检查与基础设施，不做门控决策；调用方（工具层）按组顺序组合调用。
边界：Plan 模式拒绝由 run_type 的状态接入；scope 参数预留（当前工具以全局 scope 登记）。
"""
from __future__ import annotations

import atexit
import os
import re
import signal
import subprocess
import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from agent.core.error_report import report_error

STREAM_OUTPUT_MAX_CHARS = 12000
STREAM_OUTPUT_STDERR_MAX_CHARS = 4000

_SAFE_BLOCK_RE = re.compile(r"[;&|`$><]")
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_SOURCE_EXT = r"(?:py|json|md|ts|js|html|css|java|txt|ini|cfg|toml|yaml|xml|bat|sh|ps1)"
_REDIRECT_SOURCE_RE = re.compile(r"(?:>>?|\|)\s*[^\s<>|]*\." + _SOURCE_EXT + r"\b", re.IGNORECASE)
_SED_INPLACE_RE = re.compile(r"\bsed\s+-i", re.IGNORECASE)
_SOURCE_EXT_RE = re.compile(r"\." + _SOURCE_EXT + r"\b", re.IGNORECASE)


class CommandBlacklisted(Exception):
    """命令或脚本内容命中安全黑名单。"""


# ── 组 A：命令黑名单─────────────────────────

_DELETE_ADVICE = "请使用 delete_file（移入回收站，可恢复）"
_DISK_ADVICE = "请使用系统磁盘管理工具"
_SYSTEM_ADVICE = "请通过系统安全策略 / 属性设置调整"

# 单词语义条目：提取首个词后匹配
_CMD_BLACKLIST: Dict[str, str] = {
    # Windows CMD
    "del": _DELETE_ADVICE,
    "erase": _DELETE_ADVICE,
    "rmdir": _DELETE_ADVICE,
    "rd": _DELETE_ADVICE,
    "deltree": _DELETE_ADVICE,
    # PowerShell
    "remove-item": _DELETE_ADVICE,
    "ri": _DELETE_ADVICE,
    "remove-itemproperty": _DELETE_ADVICE,
    "rp": _DELETE_ADVICE,
    "clear-item": _DELETE_ADVICE,
    "cli": _DELETE_ADVICE,
    # Unix
    "rm": _DELETE_ADVICE,
    "unlink": _DELETE_ADVICE,
    "shred": _DELETE_ADVICE,
    "wipe": _DELETE_ADVICE,
    "srm": _DELETE_ADVICE,
    # 格式化 / 分区 / 磁盘
    "format": _DISK_ADVICE,
    "mkfs": _DISK_ADVICE,
    "fdisk": _DISK_ADVICE,
    "mkswap": _DISK_ADVICE,
    "dd": _DISK_ADVICE,
    "diskpart": _DISK_ADVICE,
    # 注册表
    "reg": _SYSTEM_ADVICE,
    "regdelete": _SYSTEM_ADVICE,
    # ACL 与权限（防绕过只读锁）
    "icacls": _SYSTEM_ADVICE,
    "cacls": _SYSTEM_ADVICE,
    "xcacls": _SYSTEM_ADVICE,
    "takeown": _SYSTEM_ADVICE,
    "attrib": _SYSTEM_ADVICE,
    "subinacl": _SYSTEM_ADVICE,
    "setacl": _SYSTEM_ADVICE,
}

# 多词条目：整命令前缀匹配（长度倒序检查）
_MULTI_WORD_BLACKLIST: Tuple[Tuple[str, str], ...] = (
    ("powershell set-acl", _SYSTEM_ADVICE),
    ("reg delete", _SYSTEM_ADVICE),
)


def _extract_base_command(command: str) -> str:
    """提取基准命令名：首个词 → 去引号 / 去 .exe / 取 basename / 小写。"""
    text = str(command or "").strip()
    if not text:
        return ""
    token = text.split()[0].strip("\"'")
    token = token.replace("\\", "/")
    name = token.rsplit("/", 1)[-1]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name.lower()


def _advice_message(entry: str, advice: str) -> str:
    """拦截消息：含命中条目与替代建议。"""
    return f"命令被安全黑名单拦截（{entry}）：真删除 / 毁灭性操作一律禁止——{advice}"


def check_text_content(text: str) -> Optional[str]:
    """内容级拦截：base64 / 重定向写源码 / sed -i；命中返回消息。

    这些是内容级硬拦截，与 safe_mode 开关无关。
    """
    low = str(text or "").lower()
    if "import base64" in low or "from base64" in low:
        return (
            "命令含 base64 内联被拦截（base64 嵌图浪费 token 且易中断对话）："
            "文件内容请用专用工具（read_file / write_file / read_write / web_fetch）；图片用 ![图片](url) 预览"
        )
    if _REDIRECT_SOURCE_RE.search(str(text or "")):
        return "命令重定向 / 管道写入源码文件被拦截：代码编辑必须走 write_file / replace_in_file / apply_patch"
    if _SED_INPLACE_RE.search(str(text or "")) and _SOURCE_EXT_RE.search(str(text or "")):
        return "sed -i 就地修改源码文件被拦截：请使用 replace_in_file"
    return None


def check_command_blacklist(command: str) -> Optional[str]:
    """黑名单 + 内容级检查；命中返回拦截消息，未命中返回 None。"""
    text = str(command or "")
    lowered = text.strip().lower()
    for entry, advice in _MULTI_WORD_BLACKLIST:
        if lowered.startswith(entry):
            return _advice_message(entry, advice)
    base = _extract_base_command(text)
    if base in _CMD_BLACKLIST:
        return _advice_message(base, _CMD_BLACKLIST[base])
    return check_text_content(text)


def _extract_py_candidates(command: str) -> List[str]:
    """命令中的 .py 文件令牌（去引号；保序去重）。"""
    out: List[str] = []
    for raw in re.split(r"\s+", str(command or "")):
        token = raw.strip("\"'")
        if token.lower().endswith(".py") and token not in out:
            out.append(token)
    return out


def check_script_content(command: str, cwd: Optional[Path] = None) -> Optional[str]:
    """脚本内容检查：命令引用的 .py 文件读入后跑内容级检查；命中消息含文件名。

    绝对路径直接解析；相对路径按 cwd（缺省进程当前目录）解析。文件不存在则跳过。
    """
    base = Path(cwd) if cwd is not None else Path.cwd()
    for token in _extract_py_candidates(command):
        raw = Path(token)
        resolved = raw if raw.is_absolute() else (base / raw)
        try:
            if not resolved.is_file():
                continue
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            report_error("agent.mechanisms.command_safety.check_script_content", exc)
            continue
        hit = check_text_content(content)
        if hit:
            return f"脚本内容检查拦截（{token}）：{hit}"
    return None


def validate_safe_command(command: str) -> None:
    """safe_mode 字符检查：命中禁止字符 [;&|`$><] 抛 ValueError。"""
    match = _SAFE_BLOCK_RE.search(str(command or ""))
    if match:
        raise ValueError(f"safe_mode：命令包含禁止字符: {match.group()}")


# ── 组 D：进程生命周期───────────────────────

_ACTIVE_LOCK = threading.Lock()
_ACTIVE_SHELL_PIDS: Dict[str, Set[int]] = {}


def register_shell_process(pid: int, scope: str = "") -> None:
    """按 scope 登记活动 shell 子进程 PID。"""
    with _ACTIVE_LOCK:
        _ACTIVE_SHELL_PIDS.setdefault(str(scope or ""), set()).add(int(pid))


def unregister_shell_process(pid: int, scope: str = "") -> None:
    """注销已结束的 shell 子进程。"""
    with _ACTIVE_LOCK:
        pool = _ACTIVE_SHELL_PIDS.get(str(scope or ""))
        if pool is not None:
            pool.discard(int(pid))


def kill_shell_process_tree(pid: int) -> None:
    """强杀进程树：Windows taskkill /F /T；Unix killpg SIGKILL（兜底单进程）。"""
    pid = int(pid)
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=15,
                check=False,
            )
        except Exception as exc:
            report_error("agent.mechanisms.command_safety.kill_shell_process_tree", exc)
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception as exc:
            report_error("agent.mechanisms.command_safety.kill_shell_process_tree", exc)


def force_kill_active_shell_process(scope: str = "") -> int:
    """强杀活动 shell 进程（可按 scope 限定）；返回处理数量并清空对应登记。"""
    with _ACTIVE_LOCK:
        scopes = [str(scope or "")] if scope else list(_ACTIVE_SHELL_PIDS.keys())
        pids: List[int] = []
        for key in scopes:
            pids.extend(sorted(_ACTIVE_SHELL_PIDS.get(key) or ()))
    for pid in pids:
        kill_shell_process_tree(pid)
    with _ACTIVE_LOCK:
        for key in scopes:
            _ACTIVE_SHELL_PIDS.pop(key, None)
    return len(pids)


atexit.register(force_kill_active_shell_process)  # 退出清账，防孤儿进程


# ── 组 E：输出处理与 shell 选择───────────────


def decode_output(data: bytes) -> str:
    """bytes → utf-8 → gb18030 → gbk → cp936 依次尝试；最终 errors=replace 兜底。"""
    if not data:
        return ""
    payload = bytes(data)
    for enc in ("utf-8", "gb18030", "gbk", "cp936"):
        try:
            return payload.decode(enc)
        except (UnicodeDecodeError, LookupError) as exc:
            report_error("agent.mechanisms.command_safety.decode_output", exc)
            continue
    return payload.decode("utf-8", errors="replace")


def sanitize_output_for_display(text: str, *, max_chars: int = STREAM_OUTPUT_MAX_CHARS) -> str:
    """输出展示净化：去 ANSI 转义 / 回车覆盖行；连续空行压缩（≤2）；超长截断加提示。"""
    value = str(text or "")
    if not value:
        return ""
    value = _ANSI_RE.sub("", value)
    value = value.replace("\r\n", "\n")  # CRLF 行尾先归一（\r 仅在行内时才是覆盖语义）
    value = "\n".join(line.split("\r")[-1] for line in value.split("\n"))
    lines: List[str] = []
    blanks = 0
    for line in value.split("\n"):
        if line.strip() == "":
            blanks += 1
            if blanks > 2:
                continue
        else:
            blanks = 0
        lines.append(line)
    value = "\n".join(lines).strip("\n")
    if len(value) > max_chars:
        value = value[:max_chars] + "…(输出已截断)"
    return value


def resolve_shell(shell: str, command: str) -> Tuple[str, List[str]]:
    """解析 shell→ (shell 名, argv 前缀)；auto 下 powershell / pwsh 前缀 → powershell。"""
    mode = str(shell or "auto").strip().lower()
    if mode not in ("auto", "cmd", "powershell"):
        raise ValueError("shell 必须是 auto / cmd / powershell 之一")
    if mode == "auto":
        first = str(command or "").strip().lower()
        mode = "powershell" if first.startswith("powershell") or first.startswith("pwsh") else "cmd"
    if os.name == "nt":
        if mode == "powershell":
            return "powershell", ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
        return "cmd", ["cmd", "/c"]
    if mode == "powershell":
        return "powershell", ["pwsh", "-NoProfile", "-Command"]
    return "cmd", ["sh", "-c"]
