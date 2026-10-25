# -*- coding: utf-8 -*-
"""命令工具测试：run_command / python_inline + command_safety 机制。

- 机制层单测：黑名单 / 内容级拦截 / safe_mode / 输出解码与净化 / shell 选择 / 进程登记强杀；
- 工具层（经管道唯一入口）：真实命令执行、拦截拒绝、脚本内容检查、超时强杀、exit_code。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.capabilities.builtin.command_tools import PythonInlineTool  # noqa: E402
from agent.core.session_scope import reset_progress_reporter, set_progress_reporter  # noqa: E402
from agent.core.tool_call import ToolCallRequest  # noqa: E402
from agent.mechanisms import command_safety as cs  # noqa: E402


def _norm(path_text: str) -> str:
    """路径归一（大小写 / 真实路径），用于 Windows 路径比较。"""
    return os.path.normcase(os.path.realpath(path_text))

class CommandSafetyUnitTest(unittest.TestCase):
    """机制层单测。"""

    def test_blacklist_del_with_advice(self) -> None:

        msg = cs.check_command_blacklist("del x.txt")
        self.assertIsNotNone(msg)
        self.assertIn("delete_file", str(msg))

    def test_blacklist_path_and_exe(self) -> None:

        self.assertIsNotNone(cs.check_command_blacklist("C:\\Windows\\System32\\del.exe x"))

    def test_blacklist_multiword(self) -> None:

        self.assertIsNotNone(cs.check_command_blacklist("powershell set-acl .\\a.txt"))

    def test_blacklist_disk_and_acl(self) -> None:
        self.assertIsNotNone(cs.check_command_blacklist("format D:"))
        self.assertIsNotNone(cs.check_command_blacklist("icacls .\\data /grant everyone:F"))

    def test_content_base64(self) -> None:

        self.assertIsNotNone(cs.check_command_blacklist("python -c \"import base64\""))

    def test_content_redirect_source(self) -> None:

        self.assertIsNotNone(cs.check_command_blacklist("echo x > a.py"))
        self.assertIsNone(cs.check_command_blacklist("echo hello"))

    def test_content_sed_i(self) -> None:

        self.assertIsNotNone(cs.check_command_blacklist("sed -i s/a/b/ x.py"))

    def test_safe_mode_chars(self) -> None:

        with self.assertRaises(ValueError) as ctx:
            cs.validate_safe_command("echo a && echo b")
        self.assertIn("safe_mode", str(ctx.exception))
        cs.validate_safe_command("echo hello")  # 无禁止字符：放行不抛

    def test_decode_output_gbk(self) -> None:

        self.assertEqual(cs.decode_output("中文输出".encode("gbk")), "中文输出")
        self.assertEqual(cs.decode_output(b""), "")

    def test_sanitize_ansi_and_cr(self) -> None:

        text = "\x1b[31mred\x1b[0m\n50%\r100%"
        self.assertEqual(cs.sanitize_output_for_display(text), "red\n100%")
        self.assertEqual(cs.sanitize_output_for_display("hello\r\n"), "hello")

    def test_sanitize_blank_collapse_and_truncate(self) -> None:

        self.assertEqual(cs.sanitize_output_for_display("a\n\n\n\n\nb"), "a\n\n\nb")
        truncated = cs.sanitize_output_for_display("x" * 50, max_chars=10)
        self.assertTrue(truncated.startswith("x" * 10))
        self.assertTrue(truncated.endswith("…(输出已截断)"))

    def test_resolve_shell(self) -> None:

        name, _ = cs.resolve_shell("auto", "powershell -c x")
        self.assertEqual(name, "powershell")
        name, _ = cs.resolve_shell("auto", "echo hi")
        self.assertEqual(name, "cmd")
        name, _ = cs.resolve_shell("powershell", "echo hi")
        self.assertEqual(name, "powershell")
        with self.assertRaises(ValueError):
            cs.resolve_shell("bash", "x")

    def test_process_registry_and_kill(self) -> None:
        import os

        # 子进程要自成进程组：`force_kill_active_shell_process` 在 POSIX 上走
        # `killpg(getpgid(pid))`，同组时那正是测试进程自己的组，一杀连TestRunner 一起没。
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=(os.name != "nt"),
        )
        try:
            cs.register_shell_process(proc.pid, "unit-test")
            count = cs.force_kill_active_shell_process("unit-test")
            self.assertGreaterEqual(count, 1)
            proc.wait(timeout=15)
            self.assertIsNotNone(proc.returncode)
            self.assertEqual(cs.force_kill_active_shell_process("unit-test"), 0)
        finally:
            if proc.poll() is None:
                proc.kill()

class CommandToolsTest(unittest.TestCase):
    """工具层：run_command（经管道唯一入口）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.app = build_app()
        self._seq = 0

    def _call(self, name: str, arguments: dict):
        self._seq += 1
        call = ToolCallRequest(call_id=f"c{self._seq}", name=name, arguments=arguments)
        return self.app.pipeline.execute(self.app.registry, call, None)

    def test_run_echo(self) -> None:
        r = self._call("run_command", {"command": "echo hello"})
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(r.data["exit_code"], 0)
        self.assertIn("hello", r.data["stdout"])
        self.assertEqual(r.data["shell"], "cmd")

    def test_run_blacklisted(self) -> None:

        r = self._call("run_command", {"command": "del x.txt"})
        self.assertFalse(r.ok)
        self.assertIn("CommandBlacklisted", str(r.error))
        self.assertIn("delete_file", str(r.error))

    def test_run_blacklisted_even_safe_mode_off(self) -> None:

        r = self._call("run_command", {"command": "rm -rf build", "safe_mode": False})
        self.assertFalse(r.ok)
        self.assertIn("CommandBlacklisted", str(r.error))

    def test_run_safe_mode_blocks_chars(self) -> None:

        r = self._call("run_command", {"command": "echo a && echo b"})
        self.assertFalse(r.ok)
        self.assertIn("safe_mode", str(r.error))

    def test_run_safe_mode_off_allows_chain(self) -> None:
        r = self._call("run_command", {"command": "echo a && echo b", "safe_mode": False})
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(r.data["exit_code"], 0)
        self.assertIn("a", r.data["stdout"])
        self.assertIn("b", r.data["stdout"])

    def test_run_script_content_check(self) -> None:

        script = self.root / "sc.py"
        script.write_text("import base64\n", encoding="utf-8")
        r = self._call("run_command", {"command": "python sc.py", "cwd": str(self.root)})
        self.assertFalse(r.ok)
        self.assertIn("CommandBlacklisted", str(r.error))
        self.assertIn("sc.py", str(r.error))

    def test_run_exit_code(self) -> None:
        r = self._call(
            "run_command",
            {"command": "python -c \"import sys; sys.exit(3)\"", "safe_mode": False},
        )
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(r.data["exit_code"], 3)

    def test_run_timeout_kills(self) -> None:

        r = self._call(
            "run_command",
            {"command": "python -c \"import time; time.sleep(30)\"", "timeout_sec": 1, "safe_mode": False},
        )
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertTrue(r.data["timed_out"])
        self.assertIn("超时", r.data["stderr"])

    def test_run_cwd(self) -> None:
        # 打印当前目录：Windows 用 `%CD%`，POSIX 用 `pwd`。
        command = "echo %CD%" if os.name == "nt" else "pwd"
        r = self._call("run_command", {"command": command, "cwd": str(self.root)})
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(_norm(r.data["stdout"].strip()), _norm(str(self.root)))

class PythonInlineTest(unittest.TestCase):
    """工具层：python_inline（经管道唯一入口）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.app = build_app()
        self._seq = 0

    def _call(self, name: str, arguments: dict):
        self._seq += 1
        call = ToolCallRequest(call_id=f"c{self._seq}", name=name, arguments=arguments)
        return self.app.pipeline.execute(self.app.registry, call, None)

    def test_inline_prints(self) -> None:
        r = self._call("python_inline", {"code": "print('hi-inline')"})
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(r.data["exit_code"], 0)
        self.assertIn("hi-inline", r.data["stdout"])

    def test_inline_prints_push_progress(self) -> None:
        seen: list[dict] = []
        token = set_progress_reporter(seen.append)
        try:
            data = PythonInlineTool().execute({"code": "print('hi-inline')"})
        finally:
            reset_progress_reporter(token)
        self.assertIn("hi-inline", data["stdout"])
        streamed = "".join(str(item.get("text") or "") for item in seen if item.get("stream") == "stdout")
        self.assertIn("hi-inline", streamed)

    def test_inline_exception_captured(self) -> None:
        r = self._call("python_inline", {"code": "raise ValueError('boom')"})
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(r.data["exit_code"], 1)
        self.assertIn("ValueError", r.data["stderr"])

    def test_inline_system_exit(self) -> None:
        r = self._call("python_inline", {"code": "import sys\nsys.exit(2)"})
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(r.data["exit_code"], 2)

    def test_inline_cwd_and_restore(self) -> None:
        before = str(Path.cwd())
        r = self._call(
            "python_inline",
            {"code": "from pathlib import Path\nprint(Path.cwd())", "cwd": str(self.root)},
        )
        self.assertTrue(r.ok, msg=str(r.error))
        self.assertEqual(_norm(r.data["stdout"].strip()), _norm(str(self.root)))
        self.assertEqual(_norm(str(Path.cwd())), _norm(before))

if __name__ == "__main__":
    unittest.main()

class CancelKillsProcessTest(unittest.TestCase):
    """停止要真的停子进程：只退出内核循环不够。

    `request_cancel` 记下「已请求停止」后，宿主退出自己的循环、界面显示"已停止"；
    `run_command` 不在读取循环里看这个状态时，子进程会继续跑到自然结束
    （编译 / 安装这种长命令尤其明显，用户以为停了、其实还在跑）。
    """

    def test_cancel_kills_the_child_process_and_returns_quickly(self) -> None:
        import os
        import subprocess
        import threading
        import time

        from agent.capabilities.builtin.command_tools import RunCommandTool
        from agent.core.context import ToolTurnContext
        from agent.core.session_scope import (
            reset_tool_turn_context,
            set_tool_turn_context,
        )

        state = {"canceled": False}
        threading.Timer(2.0, lambda: state.__setitem__("canceled", True)).start()

        # 用真实载体：管道执行期工具看到的是 `_ToolCallScope`，
        # 停止检查由 `_ToolPort.execute(..., canceled=...)` 带进来；
        # 自造替身的形状与真实载体不一致，测不出真问题。
        from agent.core.ports import _ToolCallScope

        scope = _ToolCallScope(conversation_id="cancel-probe",
                               canceled=lambda: state["canceled"])
        # 上下文是 contextvar：必须还原，否则会漏给同一进程里的后续用例
        token = set_tool_turn_context(ToolTurnContext(turn=scope, session=None))
        try:
            # 自然结束要 60 秒；取消在 2 秒时置位 —— 及时返回即证明取消生效。
            # ping 按计数阻塞，两个平台上都有，只是参数不同。
            command = "ping -n 60 127.0.0.1" if os.name == "nt" else "ping -c 60 127.0.0.1"
            started = time.time()
            result = RunCommandTool().execute(
                {"command": command, "timeout_sec": 120}
            )
            elapsed = time.time() - started
        finally:
            reset_tool_turn_context(token)

        self.assertLess(elapsed, 15.0,
                        msg=f"取消后应尽快返回，实际 {elapsed:.1f}s（命令自然要 60s）")
        self.assertTrue(result.get("canceled"), msg="结果应标明 canceled")
        self.assertFalse(result.get("timed_out"), msg="这不是超时路径")
        self.assertIn("已停止", str(result.get("stderr") or ""),
                      msg="stderr 应说明是被停止的")

        # 子进程必须真的死掉，而不是只让工具提前返回：ping 还挂在进程表里就是没杀掉。
        needle = "ping.exe" if os.name == "nt" else "ping -c 60"
        if os.name == "nt":
            listing = subprocess.run(
                ["wmic", "process", "get", "commandline"],
                capture_output=True, text=True, errors="replace",
            ).stdout
        else:
            listing = subprocess.run(
                ["ps", "-eo", "args"],
                capture_output=True, text=True, errors="replace",
            ).stdout
        survivors = [ln.strip() for ln in listing.splitlines() if needle in ln]
        self.assertEqual(survivors, [], msg=f"子进程必须被真的杀掉；残留：{survivors}")

class CancelWiringTest(unittest.TestCase):
    """停止检查必须从模块一路带到工具（装配层，不是工具自己猜）。

    工具的取消分支只有在装配层把检查函数一路传到底时才拿得到真值；只在工具内部
    检查取消位、装配层不接线，取消永远不生效。这条用例钉住那条接线。
    """

    def test_tool_port_passes_the_cancel_check_into_the_scope(self) -> None:
        from agent.core.ports import ToolPort

        seen = {}

        class _Probe:
            name = "probe"

            def execute(self, args):
                from agent.core.session_scope import current_context

                ctx = current_context()                 # ToolTurnContext
                scope = getattr(ctx, "turn", None)      # 管道带的载体
                seen["ctx"] = type(ctx).__name__
                seen["turn"] = type(scope).__name__
                seen["canceled"] = scope.canceled() if scope is not None else None
                return {"ok": True}

        class _Registry:
            def get(self, name):
                return _Probe()

        # 用真实管道：上下文 contextvar 由它设置，假管道会让工具看不到 scope
        from agent.core.tool_call import ToolPipeline

        port = ToolPort(registry=_Registry(), pipeline=ToolPipeline())
        call = type("C", (), {"name": "probe", "call_id": "c1", "arguments": {}})()
        state = {"v": False}
        port.execute(call, conversation_id="wiring", canceled=lambda: state["v"])
        self.assertEqual(seen.get("turn"), "_ToolCallScope",
                         msg="工具经 current_context().turn 拿载体")
        self.assertFalse(seen.get("canceled"), msg="未请求停止时不该为真")

        state["v"] = True
        port.execute(call, conversation_id="wiring", canceled=lambda: state["v"])
        self.assertTrue(seen.get("canceled"),
                        msg="请求停止后工具必须看得到（否则停止只停了个循环）")

    def test_scope_without_cancel_check_is_safe(self) -> None:
        """没传入检查函数时 `canceled()` 必须是 False；检查函数自己出错必须把异常抛出去。"""
        from agent.core.ports import _ToolCallScope

        self.assertFalse(_ToolCallScope().canceled())
        with self.assertRaises(ZeroDivisionError):
            _ToolCallScope(canceled=lambda: 1 / 0).canceled()
