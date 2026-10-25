# -*- coding: utf-8 -*-
"""错误日志：落盘、容错、工具管道挂钩。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.context import SERVICE_ERROR_LOG  # noqa: E402
from agent.core.error_report import bind_error_sink, report_error  # noqa: E402
from agent.core.tool_call import ToolCallRequest, ToolPipeline  # noqa: E402
from agent.mechanisms.error_log import ErrorLog  # noqa: E402


class ErrorLogWriteTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.log = ErrorLog(self.root)

    def test_report_writes_jsonl(self) -> None:
        self.log.report("core.tool", RuntimeError("boom"), conversation_id="c1", tool="echo")
        text = self.log.path.read_text(encoding="utf-8")
        self.assertEqual(text.count("\n"), 1)
        row = json.loads(text.strip())
        self.assertEqual(row["tag"], "core.tool")
        self.assertEqual(row["level"], "error")
        self.assertEqual(row["exc_type"], "RuntimeError")
        self.assertIn("boom", row["message"])
        self.assertEqual(row["conversation_id"], "c1")
        self.assertEqual(row["tool"], "echo")
        self.assertIn("traceback", row)

    def test_report_string_without_exc_type(self) -> None:
        self.log.report("plugin.load", "缺 plugin.py", plugin="x")
        row = json.loads(self.log.path.read_text(encoding="utf-8").strip())
        self.assertEqual(row["tag"], "plugin.load")
        self.assertNotIn("exc_type", row)
        self.assertEqual(row["plugin"], "x")

    def test_write_failure_does_not_raise(self) -> None:
        # 把 path 指到不可能创建的位置：父路径是普通文件
        blocker = self.root / "not_a_dir"
        blocker.write_text("x", encoding="utf-8")
        bad = ErrorLog(blocker)  # logs 会在 blocker/logs — blocker 是文件则 mkdir 失败
        # 改内部 path 为「文件下的子路径」以迫使写失败
        bad._path = blocker / "child.log"  # type: ignore[attr-defined]
        bad.report("t", "m")  # 不得抛


class ErrorReportFacadeTest(unittest.TestCase):
    def tearDown(self) -> None:
        bind_error_sink(None)

    def test_bound_sink_receives_call(self) -> None:
        seen: list = []

        def _sink(tag, exc, **kw):
            seen.append((tag, exc, kw))

        bind_error_sink(_sink)
        report_error("core.model", ValueError("x"), conversation_id="c")
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], "core.model")
        self.assertIsInstance(seen[0][1], ValueError)

    def test_sink_exception_does_not_raise(self) -> None:
        def _sink(*_a, **_k):
            raise RuntimeError("sink broken")

        bind_error_sink(_sink)
        report_error("t", "m")  # 不得抛


class ToolPipelineErrorLogTest(unittest.TestCase):
    def tearDown(self) -> None:
        bind_error_sink(None)

    def test_tool_exception_not_reported(self) -> None:
        # 工具异常已收成 ToolResult(ok=False)，不算进程故障，不得刷 errors.log。
        seen: list = []
        bind_error_sink(lambda tag, exc, **kw: seen.append((tag, kw.get("tool"))))

        class _Boom:
            def execute(self, _args):
                raise RuntimeError("tool boom")

        reg = MagicMock()
        reg.get.return_value = _Boom()
        pipe = ToolPipeline()
        result = pipe.execute(
            reg,
            ToolCallRequest(call_id="1", name="boom_tool", arguments={}),
            MagicMock(conversation_id="cid-9"),
        )
        self.assertFalse(result.ok)
        self.assertEqual(seen, [])

    def test_await_user_not_reported(self) -> None:
        seen: list = []
        bind_error_sink(lambda *a, **k: seen.append(1))

        class _NeedConfirm(Exception):
            await_user = True

        class _Tool:
            def execute(self, _args):
                raise _NeedConfirm("wait")

        reg = MagicMock()
        reg.get.return_value = _Tool()
        pipe = ToolPipeline()
        result = pipe.execute(
            reg,
            ToolCallRequest(call_id="1", name="confirm", arguments={}),
            MagicMock(conversation_id="c"),
        )
        self.assertTrue(result.await_user)
        self.assertEqual(seen, [])


class BuildAppErrorLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self._prev_data = os.environ.get("AI_AGENT_DATA_ROOT")
        os.environ["AI_AGENT_DATA_ROOT"] = str(self.root / "data")

    def tearDown(self) -> None:
        bind_error_sink(None)
        if self._prev_data is None:
            os.environ.pop("AI_AGENT_DATA_ROOT", None)
        else:
            os.environ["AI_AGENT_DATA_ROOT"] = self._prev_data

    def test_build_app_registers_and_binds(self) -> None:
        app = build_app(
            backup_root=self.root / "bk",
            recycle_root=self.root / "rc",
        )
        self.addCleanup(app.dispose)
        self.assertTrue(app.context.has(SERVICE_ERROR_LOG))
        elog = app.context.get(SERVICE_ERROR_LOG)
        self.assertIsInstance(elog, ErrorLog)
        self.assertEqual(elog.path, self.root / "data" / "logs" / "errors.log")
        report_error("probe", "from test")
        self.assertTrue(elog.path.is_file())
        body = elog.path.read_text(encoding="utf-8")
        self.assertIn("probe", body)


if __name__ == "__main__":
    unittest.main()
