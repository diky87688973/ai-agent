# -*- coding: utf-8 -*-
"""只读工具测试：read_file / grep_files / glob_files + 注册制链路。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.builtin import glob_files, grep_files, read_file  # noqa: E402
from agent.capabilities.builtin.locate_tools import FileSearchTool  # noqa: E402
from agent.capabilities.registry import ToolRegistry  # noqa: E402
from agent.core.tool_call import ToolCallRequest, ToolPipeline  # noqa: E402


class ReadFileToolTest(unittest.TestCase):
    """read_file：行区间 / 边界 / 截断 / 错误。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.tool = read_file.build()

    def test_read_full_text(self) -> None:
        """全文读取。"""
        f = self.root / "a.txt"
        f.write_text("line1\nline2\nline3", encoding="utf-8")
        data = self.tool.execute({"path": str(f)})
        self.assertEqual(data["content"], "line1\nline2\nline3")
        self.assertEqual(data["total_lines"], 3)

    def test_read_line_range(self) -> None:
        """行区间切片（1-based 闭区间）。"""
        f = self.root / "b.txt"
        f.write_text("l1\nl2\nl3\nl4\nl5", encoding="utf-8")
        data = self.tool.execute({"path": str(f), "line_start": 2, "line_end": 4})
        self.assertEqual(data["content"], "l2\nl3\nl4")
        self.assertEqual((data["line_start"], data["line_end"]), (2, 4))

    def test_range_clamped_to_end(self) -> None:
        """line_end 超界时 clamp 到文件尾。"""
        f = self.root / "c.txt"
        f.write_text("a\nb", encoding="utf-8")
        data = self.tool.execute({"path": str(f), "line_start": 2, "line_end": 99})
        self.assertEqual(data["content"], "b")
        self.assertEqual(data["line_end"], 2)

    def test_invalid_range_raises(self) -> None:
        """start 超出总行数时抛 ValueError。"""
        f = self.root / "d.txt"
        f.write_text("a\nb", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.tool.execute({"path": str(f), "line_start": 5})

    def test_max_chars_truncation(self) -> None:
        """max_chars 截断并标记。"""
        f = self.root / "e.txt"
        f.write_text("x" * 100, encoding="utf-8")
        data = self.tool.execute({"path": str(f), "max_chars": 10})
        self.assertEqual(data["content"], "x" * 10)
        self.assertTrue(data["truncated"])

    def test_missing_file_raises(self) -> None:
        """文件不存在抛 FileNotFoundError（管道回灌）。"""
        with self.assertRaises(FileNotFoundError):
            self.tool.execute({"path": str(self.root / "nope.txt")})

    def test_missing_path_raises(self) -> None:
        """缺少 path 抛 ValueError。"""
        with self.assertRaises(ValueError):
            self.tool.execute({})

    def test_empty_file(self) -> None:
        """空文件：返回空内容与 0 行，不报错。"""
        f = self.root / "empty.txt"
        f.write_text("", encoding="utf-8")
        data = self.tool.execute({"path": str(f)})
        self.assertEqual(data["content"], "")
        self.assertEqual(data["total_lines"], 0)
        self.assertFalse(data["truncated"])


class GrepFilesToolTest(unittest.TestCase):
    """grep_files：字面 / OR / 正则 / 大小写 / limit。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.tool = grep_files.build()
        (self.root / "a.txt").write_text("alpha\nbeta\ngamma", encoding="utf-8")
        (self.root / "b.txt").write_text("Alpha\nBETA", encoding="utf-8")
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "c.txt").write_text("alpha deep", encoding="utf-8")

    def test_literal_hits(self) -> None:
        """字面命中（含子目录；相对路径输出）。"""
        data = self.tool.execute({"pattern": "alpha", "path": str(self.root)})
        self.assertEqual(data["count"], 2)
        self.assertEqual(sorted(m["file"] for m in data["matches"]), ["a.txt", "sub/c.txt"])

    def test_or_separator(self) -> None:
        """字面模式 | 为 OR 分隔。"""
        data = self.tool.execute({"pattern": "beta|gamma", "path": str(self.root)})
        self.assertEqual(data["count"], 2)

    def test_regex_and_ignore_case(self) -> None:
        """正则 + 忽略大小写（三个文件行首均命中：alpha / Alpha / alpha deep）。"""
        data = self.tool.execute(
            {"pattern": "^ALPHA", "path": str(self.root), "regex": True, "ignore_case": True}
        )
        self.assertEqual(data["count"], 3)
        self.assertEqual(sorted(m["file"] for m in data["matches"]), ["a.txt", "b.txt", "sub/c.txt"])

    def test_limit_truncation(self) -> None:
        """limit 截断并标记。"""
        data = self.tool.execute({"pattern": "alpha", "path": str(self.root), "limit": 1})
        self.assertEqual(data["count"], 1)
        self.assertTrue(data["truncated"])

    def test_no_match(self) -> None:
        """无命中：空结果不截断。"""
        data = self.tool.execute({"pattern": "zzz_not_there", "path": str(self.root)})
        self.assertEqual(data["count"], 0)
        self.assertFalse(data["truncated"])

    def test_missing_pattern_raises(self) -> None:
        """缺少 pattern 抛 ValueError。"""
        with self.assertRaises(ValueError):
            self.tool.execute({"path": str(self.root)})

    def test_blank_pattern_says_what_to_fix(self) -> None:
        """字面模式 | 分隔后无有效段：只说 pattern 与 regex 两个真正相关的处置。"""
        with self.assertRaises(ValueError) as ctx:
            self.tool.execute({"pattern": " | ", "path": str(self.root)})
        message = str(ctx.exception)
        self.assertIn("pattern", message)
        self.assertIn("regex=true", message)
        # 错在 pattern，不在工具：罗列换工具只会误导，也白花 token。
        for unrelated in ("glob_files", "read_file", "find_in_file"):
            self.assertNotIn(unrelated, message)

    def test_binary_file_skipped(self) -> None:
        """含 NUL 字节的文件被跳过（二进制嗅探）。"""
        blob = self.root / "blob.bin"
        blob.write_bytes(b"\x00\x01secret_marker")
        data = self.tool.execute({"pattern": "secret_marker", "path": str(self.root)})
        self.assertEqual(data["count"], 0)

    def test_path_not_dir_raises(self) -> None:
        """path 指向文件：说清本工具只搜目录，并给出真能吃下单文件的工具。"""
        with self.assertRaises(ValueError) as ctx:
            self.tool.execute({"pattern": "alpha", "path": str(self.root / "a.txt")})
        message = str(ctx.exception)
        self.assertIn("只搜目录", message)
        self.assertIn("find_in_file", message)

    def test_missing_path_is_not_reported_as_wrong_type(self) -> None:
        """路径不存在与类型不对必须分开说：两者处置完全不同。"""
        with self.assertRaises(ValueError) as ctx:
            self.tool.execute({"pattern": "alpha", "path": str(self.root / "nope")})
        message = str(ctx.exception)
        self.assertIn("不存在", message)
        # 换工具找不到不存在的东西，不得在这里罗列工具名。
        for tool_name in ("find_in_file", "regex_locate", "glob_files"):
            self.assertNotIn(tool_name, message)


class ScopeTest(unittest.TestCase):
    """搜索范围：只默认剪通用产物目录；要排别的目录须由调用方点名。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for name in ("data", ".git", "__pycache__", "build", "src"):
            d = self.root / name
            d.mkdir()
            (d / "n.txt").write_text("needle in " + name, encoding="utf-8")

    def _grep(self, **extra) -> dict:
        args = {"pattern": "needle", "path": str(self.root)}
        args.update(extra)
        return grep_files.build().execute(args)

    def _search(self, **extra) -> dict:
        args = {"pattern": "needle", "path": str(self.root)}
        args.update(extra)
        return FileSearchTool().execute(args)

    def _grep_tops(self, **extra) -> list:
        return sorted({m["file"].split("/")[0] for m in self._grep(**extra)["matches"]})

    def _search_tops(self, **extra) -> list:
        return sorted({Path(m["file"]).relative_to(self.root).parts[0]
                       for m in self._search(**extra)["matches"]})

    def test_data_is_searched_by_default(self) -> None:
        """data 不是通用产物目录名，默认就该被搜到。

        它只是某些项目自己的临时目录，换了项目可能正是源码 ——
        工具不该替调用方猜。
        """

        self.assertIn("data", self._grep_tops())
        self.assertIn("data", self._search_tops())

    def test_default_only_prunes_git_and_bytecode(self) -> None:
        """默认名单只含 .git 与 __pycache__，跳过数如实报出。"""

        data = self._grep()
        self.assertEqual(data["skipped_derived_dirs"], 2)
        self.assertEqual(self._grep_tops(), ["build", "data", "src"])

    def test_exclude_names_are_honoured(self) -> None:
        """点名排除的目录两个工具都不再搜。"""

        self.assertEqual(self._grep_tops(exclude=["data"]), ["build", "src"])
        self.assertEqual(self._search_tops(exclude=["data"]), ["build", "src"])
        self.assertEqual(self._grep(exclude=["data"])["skipped_derived_dirs"], 3)

    def test_include_derived_does_not_undo_exclude(self) -> None:
        """include_derived 只放开默认名单，点名排除的仍排除。"""

        tops = self._grep_tops(include_derived=True, exclude=["build"])
        self.assertIn(".git", tops)
        self.assertIn("__pycache__", tops)
        self.assertNotIn("build", tops)

    def test_exclude_echoes_what_was_asked(self) -> None:
        """回执原样回显调用方传的排除名单，便于自查是否漏传。"""

        data = self._grep(exclude=["data", "build"])
        self.assertEqual(data["exclude"], ["data", "build"])
        self.assertEqual(self._grep_tops(exclude=["data", "build"]), ["src"])
        self.assertEqual(self._search(exclude=["data", "build"])["exclude"], ["data", "build"])
        self.assertEqual(self._search_tops(exclude=["data", "build"]), ["src"])


class GlobFilesToolTest(unittest.TestCase):
    """glob_files：递归 / 非递归 / 类型过滤 / limit。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.tool = glob_files.build()
        (self.root / "x.py").write_text("x", encoding="utf-8")
        sub = self.root / "sub"
        sub.mkdir()
        (sub / "y.py").write_text("y", encoding="utf-8")
        (sub / "data.txt").write_text("t", encoding="utf-8")

    def test_recursive_default(self) -> None:
        """默认递归；**/ 前缀剥除。"""
        data = self.tool.execute({"path": str(self.root), "glob_pattern": "**/*.py"})
        self.assertEqual(data["entries"], ["sub/y.py", "x.py"])

    def test_non_recursive(self) -> None:
        """非递归仅当前层。"""
        data = self.tool.execute(
            {"path": str(self.root), "glob_pattern": "*.py", "recursive": False}
        )
        self.assertEqual(data["entries"], ["x.py"])

    def test_entry_type_dir(self) -> None:
        """目录过滤。"""
        data = self.tool.execute(
            {"path": str(self.root), "glob_pattern": "**/*", "entry_type": "dir"}
        )
        self.assertEqual(data["entries"], ["sub"])

    def test_limit_truncation(self) -> None:
        """limit 截断并标记。"""
        data = self.tool.execute(
            {"path": str(self.root), "glob_pattern": "**/*", "entry_type": "all", "limit": 1}
        )
        self.assertEqual(data["count"], 1)
        self.assertTrue(data["truncated"])

    def test_invalid_entry_type_raises(self) -> None:
        """非法 entry_type 抛 ValueError。"""
        with self.assertRaises(ValueError):
            self.tool.execute({"path": str(self.root), "entry_type": "what"})

    def test_derived_dirs_skipped_and_reported(self) -> None:
        """默认剪 .git / __pycache__；回执报数；include_derived 可显式放开。"""
        (self.root / ".git").mkdir()
        (self.root / ".git" / "secret.txt").write_text("git", encoding="utf-8")
        (self.root / "__pycache__").mkdir()
        (self.root / "__pycache__" / "x.pyc").write_text("pyc", encoding="utf-8")
        data = self.tool.execute(
            {"path": str(self.root), "glob_pattern": "**/*", "entry_type": "all"}
        )
        self.assertNotIn(".git", data["entries"])
        self.assertNotIn("__pycache__", data["entries"])
        self.assertEqual(data["skipped_derived_dirs"], 2)
        opened = self.tool.execute(
            {
                "path": str(self.root),
                "glob_pattern": "**/*",
                "entry_type": "all",
                "include_derived": True,
            }
        )
        self.assertIn(".git", opened["entries"])
        self.assertIn("__pycache__", opened["entries"])
        self.assertEqual(opened["skipped_derived_dirs"], 0)

    def test_path_not_dir_raises(self) -> None:
        """path 指向文件而非目录时抛 ValueError。"""
        with self.assertRaises(ValueError):
            self.tool.execute({"path": str(self.root / "x.py")})


class RegistryPipelineIntegrationTest(unittest.TestCase):
    """注册制链路：注册 → 声明导出 → 管道唯一入口执行。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_register_and_execute_via_pipeline(self) -> None:
        """三工具注册进 ToolRegistry；经 ToolPipeline.execute 驱动 read_file。"""
        f = self.root / "hello.txt"
        f.write_text("hello pipeline", encoding="utf-8")
        registry = ToolRegistry()
        registry.register(read_file.build())
        registry.register(grep_files.build())
        registry.register(glob_files.build())
        names = [s["name"] for s in registry.schemas()]
        self.assertEqual(names, ["glob_files", "grep_files", "read_file"])
        pipeline = ToolPipeline()
        result = pipeline.execute(
            registry,
            ToolCallRequest(call_id="c1", name="read_file", arguments={"path": str(f)}),
            None,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.data["content"], "hello pipeline")

    def test_unknown_tool_via_pipeline(self) -> None:
        """未注册工具名：管道结构化回灌（不抛异常）。"""
        registry = ToolRegistry()
        registry.register(read_file.build())
        pipeline = ToolPipeline()
        result = pipeline.execute(
            registry,
            ToolCallRequest(call_id="c2", name="nope_tool", arguments={}),
            None,
        )
        self.assertFalse(result.ok)
        self.assertIn("未知工具", result.error)

    def test_tool_error_structured(self) -> None:
        """工具异常：管道捕获为 ok=False 回灌。"""
        registry = ToolRegistry()
        registry.register(read_file.build())
        pipeline = ToolPipeline()
        result = pipeline.execute(
            registry,
            ToolCallRequest(
                call_id="c3", name="read_file", arguments={"path": str(self.root / "missing.txt")}
            ),
            None,
        )
        self.assertFalse(result.ok)
        self.assertIn("FileNotFoundError", result.error)


if __name__ == "__main__":
    unittest.main()
