# -*- coding: utf-8 -*-
"""命令执行工具组：run_command / python_inline。

- run_command 执行顺序：① Plan 模式拒绝 → ② 命令黑名单
  → ③ 脚本内容检查→ ④ safe_mode 字符检查→ 执行；
- 执行侧：shell 选择、进程登记与超时强杀、输出解码与净化；
- python_inline：exec 执行源码（不经 shell），stdout/stderr 捕获复用同一净化；
  名义 timeout（exec 无法硬中断，仅登记参数）。
"""
from __future__ import annotations

import io
import os
import re
import subprocess
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Dict, List

from agent.capabilities.registry import ToolPlugin
from agent.core.session_scope import (
    current_context,
    current_progress_reporter,
    current_session_id,
    emit_progress,
)
from agent.mechanisms.command_safety import (
    STREAM_OUTPUT_MAX_CHARS,
    STREAM_OUTPUT_STDERR_MAX_CHARS,
    CommandBlacklisted,
    check_command_blacklist,
    check_script_content,
    decode_output,
    kill_shell_process_tree,
    register_shell_process,
    resolve_shell,
    sanitize_output_for_display,
    unregister_shell_process,
    validate_safe_command,
)
from agent.mechanisms.live_state import (
    ModeConflict,
    register_command_input_target,
    unregister_command_input_target,
)

#: 交互提示检测。
_INTERACTIVE_PROMPT_RE = re.compile(
    r"(?:\[Y\]\s*是\s*\[N\]\s*否|是否同意所有源协议|\(Y/N\)|Continue\?\s*\[y/n\]|需要确认"
    # 英文提示同样常见（winget / npm / git 都会问），只认中文的话
    # 用户根本没机会看到输入条，只能干等到超时。
    r"|\[y/n\]|\[Y/n\]|\[y/N\]|\(y/n\)|Are you sure|Proceed\?|Do you want to"
    r"|Press any key|Enter password|Enter passphrase|Overwrite\?)",
    re.I,
)

#: 等输入的最长时间（秒）：超时就不再提示，命令继续按原样等/结束。
_INPUT_WAIT_SEC = 180.0

#: stdin 优雅期（秒）：命令启动后这么久还没有任何输出，就认为它不会问人，
#: 直接把 stdin 关掉（给到 EOF）。
#:
#: 为什么必须有这一条：stdin 一旦是管道，`sort` / `cat` / 无参 `findstr` /
#: `python -c "sys.stdin.read()"` 这类"读到 EOF 才干活"的命令就会一直等，
#: 从"瞬间完成"变成"干等到 timeout 并被误报超时强杀"。会问人的命令一定
#: 先打印提示，所以"迟迟没有输出"就是"不需要人回答"的判据。
_STDIN_EOF_GRACE_SEC = 1.5



def _detect_awaiting_input(text_tail: str) -> Dict[str, Any]:
    """从输出尾部识别"命令在问人"；没有则返回空 dict。"""
    tail = (text_tail or "")[-1500:]
    if not _INTERACTIVE_PROMPT_RE.search(tail):
        return {}
    lines = [ln.strip() for ln in tail.splitlines() if ln.strip()][-10:]
    title = "\n".join(lines) if lines else "命令正在等待确认"
    return {"title": title[:800], "options": ["Y", "N"]}


def _resolve_cwd(arguments: Dict[str, Any]) -> str:
    """cwd 参数校验；缺省返回空串（继承进程当前目录）。"""
    raw = str(arguments.get("cwd") or "").strip()
    if not raw:
        return ""
    target = Path(raw)
    if not target.is_dir():
        raise NotADirectoryError(f"工作目录不存在或不是目录：{target}")
    return str(target)


def _reject_in_plan_mode(live_state: Any, action: str) -> None:
    """Plan 模式首道拦截：无状态或无会话作用域时放行（默认 auto）。"""
    if live_state is None:
        return
    cid = current_session_id()
    if cid and live_state.get_mode(cid) == "plan":
        raise ModeConflict(f"Plan 模式下禁止{action}（可先 run_type 切回 auto / execute）")


def _close_streams(proc: "subprocess.Popen[bytes]") -> None:
    """关掉子进程的 stdout/stderr 管道句柄（逐块读不会像 communicate 那样自动收）。"""
    for stream in (getattr(proc, "stdout", None), getattr(proc, "stderr", None),
                   getattr(proc, "stdin", None)):
        if stream is None:
            continue
        try:
            stream.close()
        except Exception:
            pass


def _read_available(stream: Any, chunk: int = 4096) -> bytes:
    """从管道读「当前已到达」的数据（阻塞到至少有 1 字节或 EOF）。

    直接 `stream.read(4096)` 不行：Windows 上对管道的定长读会一直等到读满 4096
    字节或 EOF 才返回，一段小输出要等命令结束才一次性吐出来。这里先 `read(1)`
    （只等"有数据"，一旦有就立刻返回），再把已到达的其余部分读出来，
    兼顾及时性与吞吐。
    """
    try:
        first = stream.read(1)
    except OSError:
        # 管道已断开/关闭：等同 EOF，结束读线程
        return b""
    if not first:
        return b""                      # EOF
    rest = b""
    buffer = getattr(stream, "peek", None)
    if callable(buffer):
        try:
            pending = len(stream.peek(0))     # 不消费，只看缓冲区里有多少
            if pending:
                rest = stream.read(min(pending, chunk - 1))
        except OSError:
            # peek/续读失败：只交还已读到的首字节
            pass
    return first + rest


def _pump(
    proc: "subprocess.Popen[bytes]",
    out_chunks: List[bytes],
    err_chunks: List[bytes],
    timeout: float,
    progress: Any = None,
) -> str:
    """边读边上报 stdout/stderr；返回 "ok" / "timeout" / "canceled"。

    两个流各用一条后台线程读，主线程只做截止轮询——这一步是必须的：
    管道上的 `read()` 是阻塞的，若在主线程里读，一条长时间不输出的命令
    （如 `sleep 30`）就永远回不到截止检查——截止检查不执行，timeout 设多少都拦不住。
    Windows 上 `select` 不能用于管道，所以只能靠线程。
    两个流都必须被读，否则其中一个缓冲区写满会把子进程卡死。

    上报器显式传进线程：`contextvars` 不会自动跨线程，线程里直接调
    `emit_progress` 会拿到默认的 None 而静默丢弃（正常结束只剩 done 帧）。

    取消（"停止"）必须在这里生效：宿主收到停止请求后只会退出自己的循环，
    子进程仍在跑 —— 不在这里杀，用户点了停止却看到命令继续跑（编译/安装尤其明显），
    而界面早已显示"已停止"。取消状态经 `current_context().turn.canceled()` 读，
    它就是内核给模块的停止检查（`Ports.canceled`）。
    """
    import threading

    start_ts = time.time()
    deadline = start_ts + max(0.0, float(timeout))
    readers: List[threading.Thread] = []
    reporter = current_progress_reporter()
    #: 最近的输出尾部：只拿来判定"命令是不是在问人"，不参与结果拼接。
    tail = {"text": ""}
    tail_lock = threading.Lock()

    def _report(name: str, chunk: bytes) -> None:
        if reporter is None:
            return
        text = decode_output(chunk)
        payload = {"stream": name, "text": text, "done": False}
        # 同时识别"命令在问人"：判定结果挂到进度上，UI 据此弹输入条。
        if isinstance(progress, dict) and not progress.get("awaiting_input"):
            with tail_lock:
                tail["text"] = (tail["text"] + text)[-3000:]
                joined = tail["text"]
            hit = _detect_awaiting_input(joined)
            if hit:
                progress["awaiting_input"] = hit
                payload["awaiting_input"] = hit
        try:
            reporter(payload)
        except Exception:
            pass

    def _reader(stream: Any, chunks: List[bytes], name: str) -> None:
        if stream is None:
            return
        while True:
            chunk = _read_available(stream)
            if not chunk:
                break
            chunks.append(chunk)
            _report(name, chunk)

    for stream, chunks, name in ((proc.stdout, out_chunks, "stdout"),
                                 (proc.stderr, err_chunks, "stderr")):
        thread = threading.Thread(target=_reader, args=(stream, chunks, name),
                                  name=f"fa-tool-{name}", daemon=True)
        thread.start()
        readers.append(thread)

    turn = getattr(current_context(), "turn", None)
    awaiting_since: float = 0.0
    #: 优雅期是否已过（过了就关 stdin，见 `_STDIN_EOF_GRACE_SEC`）。
    stdin_eof_done = False
    while True:
        try:
            proc.wait(timeout=0.05)
            break
        except subprocess.TimeoutExpired:
            if time.time() > deadline:
                return "timeout"
            if turn is not None and turn.canceled():
                return "canceled"
            # ── 交互式命令的 stdin 通道──────────────
            # 命令可能停下来问话（winget / npm init）。人回答了就把文本写进去；
            # 没人回答则超过 `_INPUT_WAIT_SEC` 后不再提示，让命令自己走完。
            # 优雅期内没有任何输出 ⇒ 这条命令不会问人 ⇒ 关掉 stdin 让它拿到 EOF。
            # 一旦有了输出（说明可能正在等回答），就不再关，交给输入条。
            if not stdin_eof_done and (time.time() - start_ts) > _STDIN_EOF_GRACE_SEC:
                stdin_eof_done = True
                with tail_lock:
                    produced = bool(tail["text"].strip())
                if not produced and getattr(proc, "stdin", None) is not None:
                    try:
                        proc.stdin.close()
                    except OSError:
                        pass
                    except ValueError:
                        pass
            if isinstance(progress, dict):
                if progress.get("_user_input") is not None:
                    raw_in = str(progress.pop("_user_input", "") or "").strip()
                    progress.pop("awaiting_input", None)
                    if raw_in and getattr(proc, "stdin", None) is not None:
                        try:
                            proc.stdin.write((raw_in + "\n").encode("utf-8", errors="replace"))
                            proc.stdin.flush()
                        except OSError:
                            # 判据：子进程可能已经退出（管道关闭），此时写入必然抛
                            # OSError；人的回答晚了一步，不是错误，吞掉继续收尾。
                            pass
                    awaiting_since = 0.0
                elif progress.get("awaiting_input"):
                    if not awaiting_since:
                        awaiting_since = time.time()
                    elif time.time() - awaiting_since > _INPUT_WAIT_SEC:
                        progress.pop("awaiting_input", None)
                        awaiting_since = 0.0
    # 正常结束：给读线程一点时间把缓冲里剩下的吐完（管道到 EOF 就会退）
    for thread in readers:
        thread.join(timeout=1.0)
    return "ok"


class RunCommandTool(ToolPlugin):
    """执行单条 shell 命令：安全防线 + 超时强杀 + 输出净化。"""

    name = "run_command"
    label = "执行命令"
    icon = "⚡"
    description = "执行单条 shell 命令并收集 stdout/stderr/exit_code；先过安全防线（黑名单 / 脚本内容 / safe_mode），超时强杀进程树。"
    parameters = {
        "command": {"type": "string", "description": "单条命令（非多行脚本；多步请多次调用）"},
        "cwd": {"type": "string", "description": "工作目录（可选；默认继承进程当前目录）"},
        "timeout_sec": {"type": "integer", "description": "超时秒数（默认 300；超时强杀进程树）"},
        "shell": {"type": "string", "description": "auto / cmd / powershell（默认 auto）"},
        "safe_mode": {"type": "boolean", "description": "默认 true：禁止 [;&|`$><] 字符；确有必要时才置 false"},
    }

    def __init__(self, live_state: Any = None) -> None:
        self._live_state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # ① Plan 模式拒绝（首道）
        _reject_in_plan_mode(self._live_state, "命令执行")
        command = str(arguments.get("command") or "").strip()
        if not command:
            raise ValueError("缺少 command")
        # ② 命令黑名单
        violation = check_command_blacklist(command)
        if violation:
            raise CommandBlacklisted(violation)
        cwd = _resolve_cwd(arguments)
        # ③ 脚本内容检查
        script_hit = check_script_content(command, Path(cwd) if cwd else None)
        if script_hit:
            raise CommandBlacklisted(script_hit)
        # ④ safe_mode 字符检查
        if bool(arguments.get("safe_mode", True)):
            validate_safe_command(command)
        return self._run(command, cwd, arguments)

    def _run(self, command: str, cwd: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行并收集：登记 PID → 限时等待（边读边报进度）→ 超时强杀 → 输出净化。

        进度：把 stdout/stderr 逐块读出并经 `emit_progress` 上报，
        这样 UI 能在命令跑的时候就看到输出，而不是等它结束。
        结果字典给出整段 stdout/stderr；进度只是旁路观察，不影响返回内容。
        """
        shell_name, argv_prefix = resolve_shell(str(arguments.get("shell") or "auto"), command)
        timeout = float(arguments.get("timeout_sec") or 300)
        started = time.time()
        # Windows：以字符串形式传命令行（保留命令原文引号；list 形式会被 CRT 转义破坏 cmd/powershell 解析）
        spawn_args: Any = " ".join(argv_prefix + [command]) if os.name == "nt" else (argv_prefix + [command])
        ctx = current_context()
        scope = getattr(ctx, "tool_scope", None) or ctx
        cid = str(getattr(scope, "conversation_id", "") or current_session_id() or "")
        tid = str(getattr(scope, "tool_call_id", "") or "")
        #: 交互式命令的进度载体：`_pump` 轮询它的 `_user_input`，
        #: `/api/chat/command-input` 往它里面写（键 = cid:tool_call_id）。
        progress: Dict[str, Any] = {"phase": "run_command"}
        cmd_key = f"{cid}:{tid}" if tid else ""
        proc = subprocess.Popen(
            spawn_args,
            cwd=cwd or None,
            # stdin 给管道：winget / npm init 这类命令会停下来等人回答，
            # 给 DEVNULL 的话它们只会立刻 EOF 失败，人也没有入口把答案送进去。
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            # 子进程必须自成一个进程组：取消与超时走 `kill_shell_process_tree`，
            # 它在 Unix 上是 `os.killpg(os.getpgid(pid))`。子进程若与 agent 同组，
            # 那个组就是 agent 自己的组，一杀连宿主一起死（退出码 137）。
            # 它同时也是 Ctrl-C 与终端信号的隔离边界。
            start_new_session=True,
        )
        register_shell_process(proc.pid)
        if cmd_key:
            register_command_input_target(cmd_key, progress)
        outcome = "ok"
        out_chunks: list[bytes] = []
        err_chunks: list[bytes] = []
        try:
            outcome = _pump(proc, out_chunks, err_chunks, timeout, progress)
            if outcome in ("timeout", "canceled"):
                # 超时与"用户停止"都要真的杀掉进程树：只退出内核循环不够，
                # 子进程会继续跑到自然结束。
                kill_shell_process_tree(proc.pid)
                _pump(proc, out_chunks, err_chunks, 10.0, progress)
        finally:
            if cmd_key:
                unregister_command_input_target(cmd_key)
            unregister_shell_process(proc.pid)
            emit_progress(done=True)
            # 管道句柄必须显式关闭：`communicate()` 会自己收，逐块读不会
            # （不关会一直挂到 GC，长跑服务就是句柄泄漏）
            _close_streams(proc)
        exit_code = proc.returncode if proc.returncode is not None else -1
        stdout_text = decode_output(b"".join(out_chunks))
        stderr_text = decode_output(b"".join(err_chunks))
        if outcome == "timeout":
            stderr_text = f"{stderr_text}\n[超时强杀] 命令超过 {timeout:g}s，已终止进程树".lstrip()
        elif outcome == "canceled":
            stderr_text = f"{stderr_text}\n[已停止] 收到停止请求，已终止进程树".lstrip()
        return {
            "command": command,
            "shell": shell_name,
            "cwd": cwd or str(Path.cwd()),
            "exit_code": exit_code,
            "timed_out": outcome == "timeout",
            "canceled": outcome == "canceled",
            "duration_sec": round(time.time() - started, 3),
            "stdout": sanitize_output_for_display(stdout_text, max_chars=STREAM_OUTPUT_MAX_CHARS),
            "stderr": sanitize_output_for_display(stderr_text, max_chars=STREAM_OUTPUT_STDERR_MAX_CHARS),
        }


class _ProgressText(io.TextIOBase):
    """写入同时上报进度，stdout/stderr 由此推到界面。"""

    def __init__(self, sink: io.StringIO, stream: str) -> None:
        self._sink = sink
        self._stream = stream

    def write(self, s: str) -> int:
        text = "" if s is None else str(s)
        if not text:
            return 0
        self._sink.write(text)
        emit_progress(stream=self._stream, text=text)
        return len(text)

    def flush(self) -> None:
        self._sink.flush()


class PythonInlineTool(ToolPlugin):
    """exec 执行 Python 源码（不经 shell）：stdout/stderr 捕获 + 净化。"""

    name = "python_inline"
    label = "执行内联 Python"
    icon = "🐍"
    description = "exec 执行 Python 源码（不经 shell），stdout/stderr 捕获；名义 timeout（exec 无法硬中断）。复杂编排可用；勿代替 run_command 跑安装类命令。"
    parameters = {
        "code": {"type": "string", "description": "完整 Python 源码"},
        "cwd": {"type": "string", "description": "执行前 chdir（可选；默认不变）"},
        "timeout_sec": {"type": "integer", "description": "名义超时（exec 无法硬中断；仅登记）"},
    }

    def __init__(self, live_state: Any = None) -> None:
        self._live_state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # ① Plan 模式拒绝（首道）
        _reject_in_plan_mode(self._live_state, "代码执行")
        code = str(arguments.get("code") or "")
        if not code.strip():
            raise ValueError("缺少 code")
        raw_cwd = str(arguments.get("cwd") or "").strip()
        old_cwd = Path.cwd()
        if raw_cwd:
            target = Path(raw_cwd)
            if not target.is_dir():
                raise NotADirectoryError(f"工作目录不存在或不是目录：{target}")
            os.chdir(target)
        ran_in = Path.cwd()
        buffer_out = io.StringIO()
        buffer_err = io.StringIO()
        exit_code = 0
        try:
            with (
                redirect_stdout(_ProgressText(buffer_out, "stdout")),
                redirect_stderr(_ProgressText(buffer_err, "stderr")),
            ):
                try:
                    exec(compile(code, "<python_inline>", "exec"), {"__name__": "__main__"})
                except SystemExit as exc:
                    exit_code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
                except Exception:
                    traceback.print_exc()
                    exit_code = 1
        finally:
            if raw_cwd:
                os.chdir(old_cwd)
            emit_progress(done=True)
        return {
            "exit_code": int(exit_code),
            "cwd": str(ran_in),
            "stdout": sanitize_output_for_display(buffer_out.getvalue(), max_chars=STREAM_OUTPUT_MAX_CHARS),
            "stderr": sanitize_output_for_display(buffer_err.getvalue(), max_chars=STREAM_OUTPUT_STDERR_MAX_CHARS),
        }


def build_plugins(live_state: Any = None) -> List[ToolPlugin]:
    """构造本组工具（run_command / python_inline）；提供 live_state 时启用 Plan 门控。"""
    return [RunCommandTool(live_state), PythonInlineTool(live_state)]
