# -*- coding: utf-8 -*-
"""搜索范围判据：按目录名剪枝 + 按进程根 `data/` 的绝对路径剪枝。

两条约束同时成立：

- 进程根下的 `data/` 默认剪掉 —— 那里是会话事实流、备份与回收站，按字面命中
  几万条运行记录，真正要看的源码会被挤到看不见；
- 别处的 `data/` 一律不剪 —— `data` 是个普通词，别的项目里它可能就是源码目录，
  按名字排会把用户要看的东西一起藏掉。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.builtin import glob_files, grep_files  # noqa: E402
from agent.capabilities.builtin.scan_scope import (  # noqa: E402
    RUNTIME_DATA_DIR,
    ScanScope,
    relative_parts,
    scope,
)
from agent.config import PROJECT_ROOT  # noqa: E402


def _canonical(path: Path) -> str:
    """与 scan_scope 内部同一口径的路径比较形式。"""
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))


class RuntimeDataIsPrunedTest(unittest.TestCase):
    """进程根下的 data 按绝对路径剪掉，不看目录名。"""

    def test_project_root_prunes_its_own_data(self) -> None:
        scan = scope(PROJECT_ROOT)
        self.assertTrue(scan.skip_dir(PROJECT_ROOT, "data"))
        self.assertEqual(scan.runtime_data, _canonical(RUNTIME_DATA_DIR))

    def test_parent_traversal_still_prunes_it(self) -> None:
        """搜索根在父级时，遍历到 `<root>/data` 一样要剪。"""
        scan = scope(PROJECT_ROOT.parent)
        self.assertTrue(scan.skip_dir(PROJECT_ROOT, "data"))

    def test_files_under_runtime_data_are_skipped_by_path(self) -> None:
        """glob 带目录分隔符的场合按整路径判。"""
        scan = scope(PROJECT_ROOT)
        inside = PROJECT_ROOT / "data" / "session" / "raw" / "a.raw"
        self.assertTrue(scan.skip_path(inside, PROJECT_ROOT))

    def test_include_derived_reopens_it(self) -> None:
        scan = scope(PROJECT_ROOT, include_derived=True)
        self.assertFalse(scan.skip_dir(PROJECT_ROOT, "data"))
        self.assertFalse(scan.skip_path(PROJECT_ROOT / "data" / "a.raw", PROJECT_ROOT))


class OtherDataIsNotPrunedTest(unittest.TestCase):
    """不是进程根下的 data 一律不剪。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        for name in ("data", "src", "database"):
            (self.root / name).mkdir()
            (self.root / name / "n.md").write_text("needle", encoding="utf-8")
        (self.root / "src" / "data").mkdir()
        (self.root / "src" / "data" / "m.md").write_text("needle", encoding="utf-8")

    def test_same_named_data_elsewhere_is_searched(self) -> None:
        scan = scope(self.root)
        self.assertFalse(scan.skip_dir(self.root, "data"))
        self.assertFalse(scan.skip_dir(self.root / "src", "data"))

        entries = glob_files.build().execute(
            {"path": str(self.root), "glob_pattern": "**/*.md"}
        )["entries"]
        self.assertIn("data/n.md", entries)
        self.assertIn("src/data/m.md", entries)

    def test_database_is_not_mistaken_for_data(self) -> None:
        """按路径段全等匹配，不是字符串前缀。"""
        self.assertFalse(scope(self.root).skip_dir(self.root, "database"))
        tops = {m["file"].split("/")[0] for m in
                grep_files.build().execute(
                    {"pattern": "needle", "path": str(self.root)})["matches"]}
        self.assertIn("database", tops)

    def test_general_derived_names_still_pruned(self) -> None:
        """.git / __pycache__ 仍按名字剪，与 data 的绝对路径判据并存。"""
        for name in (".git", "__pycache__"):
            (self.root / name).mkdir()
            (self.root / name / "n.md").write_text("needle", encoding="utf-8")
        data = grep_files.build().execute({"pattern": "needle", "path": str(self.root)})
        tops = {m["file"].split("/")[0] for m in data["matches"]}
        self.assertNotIn(".git", tops)
        self.assertNotIn("__pycache__", tops)
        self.assertIn("data", tops)
        self.assertEqual(data["skipped_derived_dirs"], 2)


class ExplicitDataRootTest(unittest.TestCase):
    """显式把搜索根设在 data 里时不剪它：那时的 data 就是要看的内容。"""

    def test_root_inside_data_disables_the_path_rule(self) -> None:
        scan = scope(RUNTIME_DATA_DIR)
        self.assertEqual(scan.runtime_data, "")
        self.assertFalse(scan.skip_dir(RUNTIME_DATA_DIR, "session"))

    def test_deeper_root_inside_data_also_disables_it(self) -> None:
        self.assertEqual(scope(RUNTIME_DATA_DIR / "session").runtime_data, "")

    def test_name_rules_still_apply_inside_data(self) -> None:
        self.assertTrue(scope(RUNTIME_DATA_DIR).skip_dir(RUNTIME_DATA_DIR, "__pycache__"))


class ProjectRootEndToEndTest(unittest.TestCase):
    """端到端：在真实项目根搜索，结果里不该出现 data/ 下的东西。"""

    def test_glob_never_returns_paths_under_data(self) -> None:
        data = glob_files.build().execute(
            {"path": str(PROJECT_ROOT), "glob_pattern": "**/*.md", "limit": 5000}
        )
        self.assertFalse([e for e in data["entries"] if e.split("/")[0] == "data"])

    def test_include_derived_never_yields_fewer_entries(self) -> None:
        """放开默认名单后条目只会变多，且不再计入剪枝数。"""
        default = glob_files.build().execute(
            {"path": str(PROJECT_ROOT), "glob_pattern": "**/*.md", "limit": 5000}
        )
        opened = glob_files.build().execute(
            {"path": str(PROJECT_ROOT), "glob_pattern": "**/*.md", "limit": 5000,
             "include_derived": True}
        )
        self.assertGreaterEqual(opened["count"], default["count"])
        self.assertEqual(opened["skipped_derived_dirs"], 0)


class ScanScopeShapeTest(unittest.TestCase):
    """ScanScope 是冻结值对象：同一份输入给出同一份范围，可安全共享。"""

    def test_value_equal(self) -> None:
        self.assertEqual(scope(PROJECT_ROOT), scope(PROJECT_ROOT))

    def test_frozen(self) -> None:
        with self.assertRaises(AttributeError):
            scope(PROJECT_ROOT).names = frozenset()  # type: ignore[misc]

    def test_explicit_exclude_survives_include_derived(self) -> None:
        scan = scope(PROJECT_ROOT, include_derived=True, exclude=["build"])
        self.assertEqual(scan, ScanScope(frozenset({"build"})))
        self.assertTrue(scan.skip_dir(PROJECT_ROOT, "build"))

    def test_relative_parts_outside_root_is_empty(self) -> None:
        """路径不在 root 下时返回空段：调用方据此按「不排除」处理。"""
        outside = PROJECT_ROOT / "data" / "elsewhere" / "x.raw"
        self.assertEqual(relative_parts(outside, PROJECT_ROOT / "somewhere"), ())


if __name__ == "__main__":
    unittest.main()
