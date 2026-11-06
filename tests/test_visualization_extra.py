"""扩展组件的边界与语法限制。"""

from __future__ import annotations

import unittest

from plugins.visualization.validation import validate_document
from tests.test_visualization import document


class ExtraVisualizationTest(unittest.TestCase):
    def test_mermaid_accepts_flow_sequence_and_blocks_active_content(self):
        for code in ("flowchart LR\nA-->B", "sequenceDiagram\nA->>B: request\nB-->>A: reply"):
            self.assertEqual(
                validate_document(document("mermaid", {"code": code}))["data"]["code"], code
            )
        for code in (
            "pie\ntitle bad",
            'flowchart LR\nclick A href "https://example.com"',
            "%%{init:{}}%%\nflowchart LR\nA-->B",
            "flowchart LR\nA[<img src=x>]",
            "flowchart LR\nstyle A fill:red",
            "flowchart LR\nA-->B\n" * 151,
        ):
            with self.subTest(code=code[:40]), self.assertRaises(ValueError):
                validate_document(document("mermaid", {"code": code}))

    def test_periods_units_and_status_are_required(self):
        for kind, key in (("gantt", "tasks"), ("waterfall", "items")):
            valid = {
                "unit": "ms",
                key: [{"label": "请求", "start": 1, "end": 3, "status": "succeeded"}],
            }
            self.assertEqual(validate_document(document(kind, valid))["data"], valid)
            valid[key][0]["end"] = 0
            with self.assertRaises(ValueError):
                validate_document(document(kind, valid))
        self.assertEqual(
            validate_document(document("timeline", {"unit": "s", "events": []}))["data"]["events"],
            [],
        )

    def test_controls_reject_unknown_types_invalid_choices_and_duplicate_ids(self):
        control = {
            "id": "model",
            "label": "模型",
            "type": "select",
            "value": "a",
            "options": [{"value": "a", "label": "A"}],
        }
        self.assertEqual(
            validate_document(document("controls", {"fields": [control]}))["data"]["fields"][0],
            control,
        )
        for fields in (
            [control, control],
            [{**control, "value": "missing"}],
            [{"id": "x", "label": "X", "type": "html", "value": "<b>x</b>"}],
            [{"id": "x", "label": "X", "type": "toggle", "value": "false"}],
            [
                {
                    "id": "x",
                    "label": "X",
                    "type": "range",
                    "value": 11,
                    "min": 0,
                    "max": 10,
                    "step": 1,
                }
            ],
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate_document(document("controls", {"fields": fields}))

    def test_task_references_are_bounded_and_unique(self):
        for ids in ([], ["a", "a"], ["../bad"], [["nested"]]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                validate_document(document("tasks", {"batch": "batch-1", "task_ids": ids}))

    def test_range_values_align_with_step_and_bound_precision(self):
        field = {"id": "r", "label": "R", "type": "range", "min": 0, "max": 1, "step": 0.1, "value": 0.3}
        validate_document(document("controls", {"fields": [field]}))
        for patch in ({"value": 0.35}, {"step": 1e-200}, {"step": 2, "value": 1}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                validate_document(document("controls", {"fields": [{**field, **patch}]}))
