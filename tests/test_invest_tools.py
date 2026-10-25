# -*- coding: utf-8 -*-
"""调查与工具测试：定位族 / 文本数据 / 系统 / OCR / 网络 / 打包。

覆盖：find_in_file / regex_locate / file_search / text_diff / env_probe /
unified_diagnose / git_workspace / data_table / image_ocr / web_fetch /
web_fetch_render / archive；可选依赖缺失路径随环境自动跳过实跑分支。
"""
from __future__ import annotations

import http.server
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.builtin import (  # noqa: E402
    archive_tool,
    locate_tools,
    ocr_tool,
    system_tools,
    text_data_tools,
    web_tools,
)
from agent.capabilities.registry import ToolRegistry  # noqa: E402


class FindInFileTest(unittest.TestCase):
    """单文件定位。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.fp = Path(self._tmp.name) / "a.txt"
        self.fp.write_text("alpha beta\ngamma alpha\n", encoding="utf-8")
        self.tool = locate_tools.FindInFileTool()

    def test_literal_or_and_occurrence(self) -> None:
        r = self.tool.execute({"path": str(self.fp), "pattern": "beta|gamma"})
        self.assertTrue(r["found"])
        self.assertEqual(r["total_matches"], 2)
        second = self.tool.execute({"path": str(self.fp), "pattern": "beta|gamma", "occurrence": 1})
        self.assertEqual(second["matched_text"], "gamma")
        self.assertEqual(second["start_line"], 2)

    def test_region_and_rowcols(self) -> None:
        r = self.tool.execute({"path": str(self.fp), "pattern": "beta"})
        self.assertEqual(r["matched_text"], "beta")
        self.assertEqual(r["start_line"], 1)
        self.assertEqual(r["start_column"], 7)
        self.assertEqual(r["end_column"], 11)

    def test_not_found_and_out_of_range(self) -> None:
        r = self.tool.execute({"path": str(self.fp), "pattern": "zzz"})
        self.assertFalse(r["found"])
        with self.assertRaises(ValueError):
            self.tool.execute({"path": str(self.fp), "pattern": "alpha", "occurrence": 9})

    def test_blank_pattern_says_what_to_fix(self) -> None:
        """字面模式 pattern 为空：只说 pattern 本身该怎么改。"""
        with self.assertRaises(ValueError) as ctx:
            self.tool.execute({"path": str(self.fp), "pattern": ""})
        message = str(ctx.exception)
        self.assertIn("pattern", message)
        # 错在 pattern，不在工具：罗列换工具只会误导。
        for unrelated in ("glob_files", "read_file"):
            self.assertNotIn(unrelated, message)

    def test_path_is_dir_points_to_directory_tools(self) -> None:
        """path 传了目录：说清本工具只处理单文件，并指向能搜目录的工具。"""
        root = Path(self._tmp.name)
        with self.assertRaises(ValueError) as ctx:
            self.tool.execute({"path": str(root), "pattern": "alpha"})
        message = str(ctx.exception)
        self.assertIn("目录", message)
        self.assertIn("grep_files", message)

    def test_missing_file_is_not_reported_as_dir(self) -> None:
        """文件不存在与传了目录必须分开说 —— 旧版两者都报「不是已存在文件」。"""
        root = Path(self._tmp.name)
        with self.assertRaises(FileNotFoundError) as ctx:
            self.tool.execute({"path": str(root / "nope.md"), "pattern": "x"})
        message = str(ctx.exception)
        self.assertIn("不存在", message)
        self.assertNotIn("目录", message)

    def test_regex_invalid(self) -> None:
        with self.assertRaises(ValueError):
            self.tool.execute({"path": str(self.fp), "pattern": "([", "regex": True})

class RegexLocateTest(unittest.TestCase):
    """单文件/目录正则定位。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "one.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
        (self.root / "sub").mkdir()
        (self.root / "sub" / "two.py").write_text("x = 3\n", encoding="utf-8")
        (self.root / "skip.txt").write_text("x = 4\n", encoding="utf-8")
        self.tool = locate_tools.RegexLocateTool()

    def test_directory_recursive_and_glob(self) -> None:
        r = self.tool.execute({"path": str(self.root), "pattern": r"x = \d", "glob_pattern": "*.py"})
        self.assertEqual(r["count"], 2)
        files = {Path(i["file"]).name for i in r["items"]}
        self.assertEqual(files, {"one.py", "two.py"})

    def test_limit_truncation(self) -> None:
        r = self.tool.execute({"path": str(self.root), "pattern": "=", "limit": 2})
        self.assertEqual(r["count"], 2)
        self.assertTrue(r["truncated"])

    def test_blank_pattern_raises(self) -> None:
        """空 pattern 报错：空正则会命中每个位置。"""
        with self.assertRaises(ValueError) as ctx:
            self.tool.execute({"path": str(self.root), "pattern": ""})
        message = str(ctx.exception)
        self.assertIn("pattern 不能为空", message)
        self.assertIn("非空正则", message)

    def test_invalid_regex_and_limit(self) -> None:
        with self.assertRaises(ValueError):
            self.tool.execute({"path": str(self.root), "pattern": "(["})
        with self.assertRaises(ValueError):
            self.tool.execute({"path": str(self.root), "pattern": "x", "limit": 0})

class FileSearchTest(unittest.TestCase):
    """大目录内容搜索。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (self.root / "keep.txt").write_text("line1\nneedle here\nline3\n", encoding="utf-8")
        (self.root / "ignored.log").write_text("needle too\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("*.log\n", encoding="utf-8")
        self.tool = locate_tools.FileSearchTool()

    def test_context_and_gitignore(self) -> None:
        r = self.tool.execute({"path": str(self.root), "pattern": "needle", "context_lines": 1})
        self.assertEqual(r["total_matches"], 1)
        hit = r["matches"][0]
        self.assertEqual(hit["line"], 2)
        self.assertEqual([x["text"] for x in hit["context_before"]], ["line1"])
        self.assertEqual([x["text"] for x in hit["context_after"]], ["line3"])
        r2 = self.tool.execute({"path": str(self.root), "pattern": "needle", "no_gitignore": True})
        self.assertEqual(r2["total_matches"], 2)

    def test_blank_pattern_raises(self) -> None:
        """空 pattern 报错，不要静默把每个位置都当成命中。"""
        with self.assertRaises(ValueError) as ctx:
            self.tool.execute({"path": str(self.root), "pattern": ""})
        message = str(ctx.exception)
        self.assertIn("pattern 不能为空", message)
        self.assertIn("非空 pattern", message)

    def test_limit(self) -> None:
        r = self.tool.execute({"path": str(self.root), "pattern": "needle", "no_gitignore": True, "limit": 1})
        self.assertEqual(r["total_matches"], 1)

class TextDataToolsTest(unittest.TestCase):
    """text_diff / data_table。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_text_diff_file_vs_text(self) -> None:
        fp = self.root / "old.txt"
        fp.write_text("a\nb\nc\n", encoding="utf-8")
        tool = text_data_tools.TextDiffTool()
        r = tool.execute({"left_file": str(fp), "right_text": "a\nB\nc\nd\n"})
        self.assertFalse(r["summary"]["same"])
        self.assertGreaterEqual(r["summary"]["added_lines"], 2)
        self.assertGreaterEqual(r["summary"]["deleted_lines"], 1)
        self.assertIn("```diff", r["diff_markdown"])
        same = tool.execute({"left_text": "x", "right_text": "x"})
        self.assertTrue(same["summary"]["same"])
        with self.assertRaises(ValueError):
            tool.execute({"left_text": "x"})

    def test_data_table_csv_actions(self) -> None:
        fp = self.root / "t.csv"
        fp.write_text("name,score\nAlice,90\nbob,70\nCara,80\n", encoding="utf-8")
        tool = text_data_tools.DataTableTool()
        pv = tool.execute({"action": "preview", "path": str(fp)})
        self.assertEqual(pv["total_rows"], 3)
        self.assertEqual(pv["columns"], ["name", "score"])
        flt = tool.execute({"action": "filter", "path": str(fp), "filter_col": "name", "filter_val": "BOB"})
        self.assertEqual(flt["filtered_rows"], 1)
        rx = tool.execute({"action": "filter", "path": str(fp), "filter_col": "name", "filter_val": "^[AC]", "regex": True})
        self.assertEqual(rx["filtered_rows"], 2)
        st = tool.execute({"action": "stats", "path": str(fp), "col": "score"})
        self.assertEqual(st["sum"], 240.0)
        self.assertEqual(st["min"], 70.0)
        srt = tool.execute({"action": "sort", "path": str(fp), "sort_col": "score", "sort_desc": True})
        self.assertEqual(srt["preview"][0]["score"], "90")
        md = tool.execute({"action": "to_md", "path": str(fp)})
        self.assertIn("|name|score|", md["content"])
        with self.assertRaises(ValueError):
            tool.execute({"action": "nope", "path": str(fp)})

    def test_data_table_xlsx_dependency_path(self) -> None:
        fp = self.root / "t.xlsx"
        fp.write_bytes(b"PK dummy")
        tool = text_data_tools.DataTableTool()
        has_openpyxl = ocr_tool._available("openpyxl")
        if has_openpyxl:
            self.skipTest("环境已装 openpyxl，缺依赖分支不适用")
        with self.assertRaises(ImportError) as ctx:
            tool.execute({"action": "preview", "path": str(fp)})
        self.assertIn("openpyxl", str(ctx.exception))

class SystemToolsTest(unittest.TestCase):
    """env_probe / unified_diagnose / git_workspace。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_env_probe_shape(self) -> None:
        r = system_tools.EnvProbeTool().execute({})
        self.assertIn("platform", r)
        self.assertIn("python", r)
        self.assertIsInstance(r["available"], list)
        self.assertTrue(r["recommendations"])

    def test_unified_diagnose_red_green(self) -> None:
        good = self.root / "good"
        good.mkdir()
        (good / "ok.py").write_text("x = 1\n", encoding="utf-8")
        tool = system_tools.UnifiedDiagnoseTool()
        green = tool.execute({"path": str(good), "no_ruff": True})
        self.assertEqual(green["summary"]["errors"], 0)
        self.assertFalse(green["ruff_attempted"])
        bad = self.root / "bad"
        bad.mkdir()
        (bad / "broken.py").write_text("def f(:\n    pass\n", encoding="utf-8")
        with self.assertRaises(system_tools.DiagnosticsFailed) as ctx:
            tool.execute({"path": str(bad), "no_ruff": True})
        payload = ctx.exception.data
        self.assertGreaterEqual(payload["summary"]["errors"], 1)

    def test_git_workspace_modes(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("环境无 git，跳过 git_workspace 实跑")
        repo = self.root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
        (repo / "a.txt").write_text("hello\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "-c", "user.name=T", "-c", "user.email=t@t", "commit", "-q", "-m", "init"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        tool = system_tools.GitWorkspaceTool()
        wt = tool.execute({"path": str(repo), "mode": "worktree"})
        self.assertEqual(wt["mode"], "worktree")
        log = tool.execute({"path": str(repo), "mode": "log"})
        self.assertEqual(len(log["entries"]), 1)
        self.assertEqual(log["entries"][0]["subject"], "init")
        bl = tool.execute({"path": str(repo), "mode": "blame", "blame_path": "a.txt"})
        self.assertEqual(bl["lines"][0]["text"], "hello")
        show = tool.execute({"path": str(repo), "mode": "show"})
        self.assertIn("a.txt", [f["path"] for f in show["changed_files"]])
        nope = self.root / "norepo"
        nope.mkdir()
        with self.assertRaises(system_tools.GitWorkspaceError) as ctx:
            tool.execute({"path": str(nope)})
        self.assertEqual(ctx.exception.data["code"], "E_GIT_WORKSPACE")

class _HtmlHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # HTTP 动词命名（stdlib 约定）
        body = (
            b"<html><head><title>Test Page</title></head>"
            b"<body><h1>Hello World</h1><p>some longer body text content</p></body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return

class WebToolsTest(unittest.TestCase):
    """web_fetch / web_fetch_render。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _HtmlHandler)
        cls._thread = threading.Thread(target=cls._srv.serve_forever, daemon=True)
        cls._thread.start()
        cls.url = f"http://127.0.0.1:{cls._srv.server_address[1]}/"

    @classmethod
    def tearDownClass(cls) -> None:
        cls._srv.shutdown()

    def test_fetch_ok_and_checks(self) -> None:
        tool = web_tools.WebFetchTool()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "page.txt"
            r = tool.execute({"url": self.url, "min_chars": 10, "require_keywords": "Hello,不存在", "out_file": str(out)})
            self.assertEqual(r["title"], "Test Page")
            self.assertIn("Hello World", r["text"])
            self.assertTrue(r["written"])
            self.assertEqual(out.read_text(encoding="utf-8"), r["text"])
            self.assertEqual(r["checks"]["hit_keywords"], ["Hello"])

    def test_fetch_acceptance_failure_keeps_data(self) -> None:
        tool = web_tools.WebFetchTool()
        with self.assertRaises(web_tools.WebFetchError) as ctx:
            tool.execute({"url": self.url, "min_chars": 100000})
        exc = ctx.exception
        self.assertEqual(exc.data["code"], "E_ACCEPTANCE")
        self.assertEqual(exc.data["checks"]["failed"], "min_chars")
        self.assertIn("Hello World", exc.data["text"])

    def test_fetch_invalid_scheme(self) -> None:
        tool = web_tools.WebFetchTool()
        with self.assertRaises(web_tools.WebFetchError) as ctx:
            tool.execute({"url": "ftp://example.com"})
        self.assertEqual(ctx.exception.data["code"], "E_INVALID_INPUT")

    def test_render_dependency_path(self) -> None:
        tool = web_tools.WebFetchRenderTool()
        with self.assertRaises(ValueError):
            tool.execute({"url": ""})
        has_playwright = ocr_tool._available("playwright")
        if has_playwright:
            self.skipTest("环境已装 playwright，缺依赖分支不适用")
        with self.assertRaises(ImportError) as ctx:
            tool.execute({"url": self.url})
        self.assertIn("playwright", str(ctx.exception))

class OcrAndArchiveTest(unittest.TestCase):
    """image_ocr / archive。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_ocr_region_validation_and_dependency(self) -> None:
        img = self.root / "img.png"
        img.write_bytes(b"\x89PNG dummy")
        tool = ocr_tool.ImageOcrTool()
        with self.assertRaises(ValueError):
            tool.execute({"path": str(img), "region": "1,2,3"})
        has_engine = ocr_tool._available("pytesseract") or ocr_tool._available("easyocr")
        if has_engine:
            self.skipTest("环境已装 OCR 引擎，缺依赖分支不适用")
        with self.assertRaises(ocr_tool.MissingDependency) as ctx:
            tool.execute({"path": str(img)})
        self.assertIn("install_command", ctx.exception.data["dependencies"])

    def test_archive_list_create_extract(self) -> None:
        src = self.root / "pack"
        src.mkdir()
        (src / "a.txt").write_text("A", encoding="utf-8")
        (src / "b.txt").write_text("B", encoding="utf-8")
        tool = archive_tool.ArchiveTool()
        zip_path = self.root / "out.zip"
        prev = tool.execute({"action": "create", "source": str(src), "dest": str(zip_path)})
        self.assertTrue(prev["preview"])
        self.assertEqual(prev["would_add_count"], 2)
        self.assertFalse(zip_path.exists())
        executors = archive_tool.build_executors()
        done = executors["archive"]({"action": "create", "source": str(src), "dest": str(zip_path)})
        self.assertTrue(done["written"])
        self.assertEqual(done["path"], str(zip_path))
        self.assertTrue(zip_path.exists())
        lst = tool.execute({"action": "list", "source": str(zip_path)})
        self.assertFalse(lst["needs_commit"])
        self.assertEqual(lst["count"], 2)
        dest = self.root / "unpack"
        prev2 = tool.execute({"action": "extract", "source": str(zip_path), "dest": str(dest)})
        self.assertEqual(prev2["would_extract_count"], 2)
        self.assertFalse(dest.exists())
        executors["archive"]({"action": "extract", "source": str(zip_path), "dest": str(dest)})
        self.assertEqual((dest / "pack" / "a.txt").read_text(encoding="utf-8"), "A")
        with self.assertRaises(ValueError):
            tool.execute({"action": "bad", "source": str(zip_path)})

    def test_archive_unknown_format(self) -> None:
        odd = self.root / "x.bin"
        odd.write_bytes(b"not an archive")
        tool = archive_tool.ArchiveTool()
        with self.assertRaises(ValueError):
            tool.execute({"action": "list", "source": str(odd)})

class BatchERegistrationTest(unittest.TestCase):
    """工具注册链路（六个来源共 12 件）+ 门控预览名单一致性。"""

    def test_batch_e_plugins_register(self) -> None:
        registry = ToolRegistry()
        expected = []
        for plugin in locate_tools.build_plugins():
            registry.register(plugin)
            expected.append(plugin.name)
        for plugin in text_data_tools.build_plugins():
            registry.register(plugin)
            expected.append(plugin.name)
        for plugin in system_tools.build_plugins():
            registry.register(plugin)
            expected.append(plugin.name)
        for plugin in web_tools.build_plugins():
            registry.register(plugin)
            expected.append(plugin.name)
        for plugin in ocr_tool.build_plugins():
            registry.register(plugin)
            expected.append(plugin.name)
        for plugin in archive_tool.build_plugins():
            registry.register(plugin)
            expected.append(plugin.name)
        self.assertEqual(len(expected), 12)
        for name in expected:
            self.assertIsNotNone(registry.get(name), f"未注册：{name}")

    def test_archive_declares_write_path_keys(self) -> None:
        from agent.capabilities.builtin import archive_tool
        from agent.capabilities.registry import ToolRegistry

        reg = ToolRegistry()
        for plugin in archive_tool.build_plugins():
            reg.register(plugin)
        plugin = reg.get("archive")
        self.assertIsNotNone(plugin)
        self.assertEqual(tuple(plugin.write_path_keys), ("dest", "source"))

if __name__ == "__main__":
    unittest.main()
