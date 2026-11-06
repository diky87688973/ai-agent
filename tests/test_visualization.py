"""可视化文档边界、事实修订与声明式插件生命周期。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from agent.app import build_app
from agent.core.context import SERVICE_STORE, AppContext, ToolTurnContext
from agent.core.event_name import TOOL_DONE
from agent.core.events import Event
from agent.core.session_scope import reset_tool_turn_context, set_tool_turn_context
from agent.mechanisms.session_store import SessionStore
from agent.shell.plugin_settings import set_plugin_enabled, sync_plugins
from plugins.visualization.plugin import VisualizeTool
from plugins.visualization.validation import validate_document

ROOT = Path(__file__).resolve().parents[1]


def document(kind="proportion", data=None, revision=1):
    return {
        "panel_id": "context-layout",
        "revision": revision,
        "operation": "upsert",
        "kind": kind,
        "title": "上下文分配",
        "summary": "系统占 25%，历史占 75%。",
        "data": data
        if data is not None
        else {"items": [{"label": "系统", "value": 25}, {"label": "历史", "value": 75}]},
    }


class VisualizationValidationTest(unittest.TestCase):
    def test_all_components_accept_valid_data_and_return_independent_snapshots(self):
        cases = {
            "proportion": {"items": [{"label": "a", "value": 1}]},
            "donut": {"items": [{"label": "a", "value": 1}]},
            "bar": {"items": [{"label": "a", "value": -2}]},
            "progress": {"items": [{"label": "a", "value": 1, "total": 2}]},
            "flow": {
                "nodes": [{"id": "a", "label": "a"}],
                "edges": [{"source": "a", "target": "a"}],
            },
            "line": {"labels": ["a"], "series": [{"label": "s", "values": [0]}]},
            "table": {"columns": [{"key": "a", "label": "A"}], "rows": [{"a": None}, {"a": True}]},
        }
        for kind, data in cases.items():
            with self.subTest(kind=kind):
                source = document(kind, data)
                result = validate_document(source)
                result["data"].clear()
                self.assertEqual(source["data"], data)

    def test_invalid_numbers_fields_versions_and_payload_limits_fail(self):
        for bad in (-1, True, float("nan"), float("inf"), 10**500, "3"):
            source = document()
            source["data"]["items"][0]["value"] = bad
            with self.subTest(value=str(bad)[:20]), self.assertRaises(ValueError):
                validate_document(source)
        for key, value in (
            ("kind", "unknown"),
            ("revision", True),
            ("revision", 0),
            ("panel_id", "../bad"),
            ("title", "x" * 121),
            ("summary", ""),
        ):
            source = document()
            source[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_document(source)
        source = document()
        source["script"] = "alert(1)"
        with self.assertRaises(ValueError):
            validate_document(source)
        source = document(
            "table", {"columns": [{"key": "a", "label": "a"}], "rows": [{"a": "中" * 1000}] * 30}
        )
        with self.assertRaisesRegex(ValueError, "64 KiB"):
            validate_document(source)

    def test_proportions_empty_state_zero_total_and_progress_bounds(self):
        self.assertEqual(validate_document(document(data={"items": []}))["data"]["items"], [])
        with self.assertRaises(ValueError):
            validate_document(document(data={"items": [{"label": "a", "value": 0}]}))
        for value, total in ((2, 1), (-1, 1), (0, 0)):
            with self.subTest(value=value, total=total), self.assertRaises(ValueError):
                validate_document(
                    document(
                        "progress", {"items": [{"label": "a", "value": value, "total": total}]}
                    )
                )

    def test_references_dimensions_and_nested_cells_fail(self):
        cases = [
            document("flow", {"nodes": [{"id": "a", "label": "a"}] * 2, "edges": []}),
            document(
                "flow",
                {"nodes": [{"id": "a", "label": "a"}], "edges": [{"source": "a", "target": "b"}]},
            ),
            document("line", {"labels": ["a"], "series": [{"label": "s", "values": [1, 2]}]}),
            document(
                "table", {"columns": [{"key": "a", "label": "a"}], "rows": [{"a": {"html": "x"}}]}
            ),
        ]
        for source in cases:
            with self.subTest(kind=source["kind"]), self.assertRaises(ValueError):
                validate_document(source)


class VisualizationFactsTest(unittest.TestCase):
    def test_revision_idempotence_conflicts_removal_and_session_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            app = AppContext()
            app.register(SERVICE_STORE, store)
            turn = ToolTurnContext(
                app=app, session=SimpleNamespace(conversation_id="panel-session-01")
            )
            token = set_tool_turn_context(turn)
            try:
                tool = VisualizeTool()
                first = tool.execute(document())
                store.append(
                    turn.conversation_id, [Event(TOOL_DONE, {"name": "visualize", "data": first})]
                )
                self.assertEqual(tool.execute(document()), first)
                conflict = document()
                conflict["title"] = "different"
                with self.assertRaises(ValueError):
                    tool.execute(conflict)
                with self.assertRaises(ValueError):
                    tool.execute(document(revision=3))
                second = tool.execute(document(revision=2))
                store.append(
                    turn.conversation_id, [Event(TOOL_DONE, {"name": "visualize", "data": second})]
                )
                remove = document(revision=3)
                remove.update(operation="remove", data={})
                removed = tool.execute(remove)
                self.assertEqual(removed["display"]["operation"], "remove")
                turn.session.conversation_id = "panel-session-02"
                self.assertEqual(tool.execute(document())["display"]["revision"], 1)
                with self.assertRaises(ValueError):
                    tool.execute(remove)
            finally:
                reset_tool_turn_context(token)

    def test_tool_requires_fact_recording_context(self):
        with self.assertRaisesRegex(ValueError, "工具管道"):
            VisualizeTool().execute(document())

    def test_task_retry_uses_recorded_fact_after_source_disappears(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            app = AppContext()
            app.register(SERVICE_STORE, store)
            turn = ToolTurnContext(app=app, session=SimpleNamespace(conversation_id="task-retry-01"))
            source = document("tasks", {"batch": "b", "task_ids": ["t"]})
            recorded = {"display": {"version": 1, "id": source["panel_id"], "revision": 1,
                                   "operation": "upsert", "type": "visualization.tasks",
                                   "title": source["title"], "summary": source["summary"], "data": source["data"]}}
            store.append(turn.conversation_id, [Event(TOOL_DONE, {"name": "visualize", "data": recorded})])
            token = set_tool_turn_context(turn)
            try:
                self.assertEqual(VisualizeTool().execute(source), recorded)
                with self.assertRaisesRegex(ValueError, "服务不可用"):
                    VisualizeTool().execute({**source, "revision": 2})
            finally:
                reset_tool_turn_context(token)

    def test_real_plugin_unloads_and_reenables_without_host_replacement(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"AI_AGENT_DATA_ROOT": tmp}),
        ):
            root = Path(tmp)
            manifest = root / "plugins.ini"
            manifest.write_text(
                "[plugin:web_ui]\nenabled=1\n[plugin:visualization]\nenabled=1\n", encoding="utf-8"
            )
            app = build_app(data_root=root, plugins_path=manifest, plugins_dir=ROOT / "plugins")
            try:
                store = app.store
                self.assertIsNotNone(app.registry.get("visualize"))
                set_plugin_enabled("visualization", False, app=app)
                sync_plugins(app=app)
                self.assertIsNone(app.registry.get("visualize"))
                set_plugin_enabled("visualization", True, app=app)
                sync_plugins(app=app)
                self.assertIsNotNone(app.registry.get("visualize"))
                self.assertIs(app.store, store)
            finally:
                app.dispose()
