# -*- coding: utf-8 -*-
"""catalog 生成与校验测试：渲染确定性 / 漂移检出 / 仓库零漂移锚点。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from check_catalog import check  # noqa: E402
from gen_catalog import (  # noqa: E402
    CATALOG_PATH,
    collect_display,
    collect_schemas,
    render_catalog,
    write_catalog,
)


class RenderCatalogTest(unittest.TestCase):
    """渲染契约：确定性、格式、写出往返。"""

    def test_render_deterministic(self) -> None:
        """同一装配集两次渲染逐字节一致；LF 换行、无 CRLF。"""
        first = render_catalog(collect_schemas())
        second = render_catalog(collect_schemas())
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertNotIn("\r", first)

    def test_render_sorted_and_complete(self) -> None:
        """JSON 可解析；工具按名称排序；四个字段齐全。"""
        payload = json.loads(render_catalog(collect_schemas()))
        tools = payload["tools"]
        names = [t["name"] for t in tools]
        self.assertEqual(names, sorted(names))
        self.assertIn("read_file", names)
        for tool in tools:
            for key in ("name", "description", "parameters", "parallel_safe"):
                self.assertIn(key, tool)

    def test_write_catalog_roundtrip(self) -> None:
        """写出文件与渲染文本逐字节一致（临时目录），无 CRLF。"""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "tools.json"
            count = write_catalog(target)
            raw = target.read_bytes()
        self.assertEqual(count, len(collect_schemas()))
        self.assertEqual(
            raw,
            render_catalog(collect_schemas(), collect_display()).encode("utf-8"))
        self.assertNotIn(b"\r", raw)


class CheckCatalogTest(unittest.TestCase):
    """校验器：零漂移锚点 + 缺失 / 损坏 / 漂移三式检出。"""

    def test_repo_catalog_zero_drift(self) -> None:
        """仓库 catalog/tools.json 与当前装配集零漂移。"""
        self.assertEqual(check(CATALOG_PATH), [])

    def test_missing_file_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            problems = check(Path(tmp) / "absent.json")
        self.assertTrue(problems)
        self.assertIn("不存在", problems[0])

    def test_corrupt_file_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "tools.json"
            target.write_bytes(b"{ not json")
            problems = check(target)
        self.assertTrue(problems)
        self.assertIn("损坏", problems[0])

    def test_drift_detected(self) -> None:
        """篡改三式（删 echo / 改 commit_write / 增 ghost）逐一被定位。"""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "tools.json"
            tools = json.loads(render_catalog(collect_schemas()))["tools"]
            tools = [t for t in tools if t["name"] != "echo"]
            for index, tool in enumerate(tools):
                if tool["name"] == "commit_write":
                    tools[index] = dict(tool, description="被篡改")
            tools.append({"name": "ghost", "description": "", "parameters": {}, "parallel_safe": False})
            target.write_text(
                json.dumps({"tools": tools}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            problems = check(target)
        text = "\n".join(problems)
        self.assertIn("缺少工具：echo", text)
        self.assertIn("多余工具：ghost", text)
        self.assertIn("工具声明不一致", text)
        self.assertIn("commit_write", text)


class CatalogDisplayTest(unittest.TestCase):
    """目录带 `display`（中文名 + 图标），来源是工具自己的声明。"""

    def test_every_tool_has_display(self) -> None:
        from gen_catalog import collect_display, collect_schemas
        schemas = collect_schemas()
        display = collect_display()
        names = [s["name"] for s in schemas]
        self.assertEqual(sorted(names), sorted(display.keys()))
        missing = [n for n, d in display.items() if not d.get("label") or not d.get("icon")]
        self.assertEqual(missing, [], msg=f"这些工具没声明 label/icon：{missing}")

    def test_render_includes_display(self) -> None:
        import json as _json

        from gen_catalog import collect_display, collect_schemas, render_catalog
        payload = _json.loads(render_catalog(collect_schemas(), collect_display()))
        row = [t for t in payload["tools"] if t["name"] == "skill_manage"][0]
        self.assertEqual(row["display"], {"icon": "🧩", "label": "技能管理"})

if __name__ == "__main__":
    unittest.main()
