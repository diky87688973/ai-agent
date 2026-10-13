# -*- coding: utf-8 -*-
"""知识库插件测试。

覆盖：`[knowledge]` 配置读取（缺节 / 目录不存在 / 引号容忍）/ 路径安全
（八项边界）/ 文件校验 / 读取（含 xlsx 依赖降级与假库路径）/ 文件列表 /
勾选状态（全量替换、持久化、单会话恢复）/ 组包格式；ContextSources 注册与隔离；
管线注入刷新与回合端到端署名注入。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.model_call import StreamDelta  # noqa: E402
from agent.mechanisms.context_pipeline import ContextPipeline, ContextSources  # noqa: E402

_PLUGIN_DIR = _ROOT / "plugins"
_PLUGIN_MOD = "fan_agent_plugins.knowledge"

def _load_plugin_module():
    """从磁盘加载知识库插件模块（独立实例）。"""
    path = _PLUGIN_DIR / "knowledge" / "plugin.py"
    spec = importlib.util.spec_from_file_location(_PLUGIN_MOD, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PLUGIN_MOD] = module
    spec.loader.exec_module(module)
    return module

_PLUGIN = _load_plugin_module()

def _make_tree(root: Path) -> None:
    """构造样例知识库目录。"""
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "a.md").write_text("知识A", encoding="utf-8")
    (root / "docs" / "b.txt").write_text("知识B", encoding="utf-8")
    (root / ".hidden").write_text("x", encoding="utf-8")
    (root / ".git").mkdir(exist_ok=True)
    (root / ".git" / "config").write_text("x", encoding="utf-8")
    (root / "__pycache__").mkdir(exist_ok=True)
    (root / "__pycache__" / "c.txt").write_text("x", encoding="utf-8")

class KBRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = self.base / "kb"
        _make_tree(self.root)

    def test_disabled_when_root_missing(self) -> None:

        r = _PLUGIN.KBRuntime(None)
        self.assertFalse(r.enabled)
        self.assertEqual(r.list_files(), [])
        self.assertEqual(r.build_system_messages("c1"), [])
        self.assertEqual(r.attached_count("c1"), 0)

    def test_safe_resolve_boundaries(self) -> None:

        r = _PLUGIN.KBRuntime(self.root)
        self.assertIsNotNone(r.safe_resolve("a.md"))
        self.assertIsNotNone(r.safe_resolve("docs/b.txt"))
        self.assertIsNone(r.safe_resolve("../escape.txt"))
        self.assertIsNone(r.safe_resolve(".hidden"))
        self.assertIsNone(r.safe_resolve(".git/config"))
        self.assertIsNone(r.safe_resolve("/abs.txt"))
        self.assertIsNone(r.safe_resolve("docs"))
        self.assertIsNone(r.safe_resolve("missing.txt"))

    def test_file_allowed_size_and_hidden(self) -> None:

        r_small = _PLUGIN.KBRuntime(self.root, max_file_size=5)
        allowed, reason = r_small.file_allowed(self.root / "a.md")
        self.assertFalse(allowed)
        self.assertIn("超过上限", reason)
        r = _PLUGIN.KBRuntime(self.root)
        self.assertTrue(r.file_allowed(self.root / "a.md")[0])
        self.assertFalse(r.file_allowed(self.root / ".hidden")[0])

    def test_read_text_plain_and_bad_bytes(self) -> None:

        self.assertEqual(_PLUGIN._read_kb_file_text(self.root / "a.md"), "知识A")
        bad = self.root / "bad.txt"
        bad.write_bytes(b"ok\xff\xfe")
        self.assertIn("ok", _PLUGIN._read_kb_file_text(bad))

    def test_read_text_xlsx_missing_lib(self) -> None:

        x = self.root / "t.xlsx"
        x.write_bytes(b"PK")
        old = sys.modules.get("openpyxl")
        sys.modules["openpyxl"] = None  # 模拟未安装
        try:
            self.assertIn("openpyxl", _PLUGIN._read_kb_file_text(x))
        finally:
            if old is None:
                sys.modules.pop("openpyxl", None)
            else:
                sys.modules["openpyxl"] = old

    def test_read_text_xlsx_fake_lib(self) -> None:

        x = self.root / "t2.xlsx"
        x.write_bytes(b"PK")
        fake = types.ModuleType("openpyxl")

        class _WS:
            title = "Sheet1"

            def iter_rows(self, values_only=True):
                yield ("a", "b")
                yield (1, None)

        class _WB:
            worksheets = [_WS()]

            def close(self):
                pass

        fake.load_workbook = lambda *a, **k: _WB()
        old = sys.modules.get("openpyxl")
        sys.modules["openpyxl"] = fake
        try:
            text = _PLUGIN._read_kb_file_text(x)
            self.assertIn("[Sheet: Sheet1]", text)
            self.assertIn("a\tb", text)
            # 尾列空值被裁掉：`(1, None)` 渲染成 `1` 而不是 `1\t`
            self.assertIn("1", text)
            self.assertNotIn("1\t", text)
        finally:
            if old is None:
                sys.modules.pop("openpyxl", None)
            else:
                sys.modules["openpyxl"] = old

    def test_set_checked_replace_filter_clear(self) -> None:

        r = _PLUGIN.KBRuntime(self.root)
        acc = r.set_checked("c1", ["a.md", "docs/b.txt", "../bad.txt", ".hidden", "missing.txt"])
        self.assertEqual(acc, ["a.md", "docs/b.txt"])
        self.assertEqual(r.get_checked("c1"), {"a.md", "docs/b.txt"})
        acc2 = r.set_checked("c1", ["a.md"])  # 全量替换
        self.assertEqual(acc2, ["a.md"])
        self.assertEqual(r.set_checked("c1", []), [])  # 空清除
        self.assertEqual(r.get_checked("c1"), set())

    def test_persist_and_reload(self) -> None:

        # 勾选状态落在插件自己的数据目录（`ctx.data_dir`），不再放 KB 根目录旁边
        r = _PLUGIN.KBRuntime(self.root, data_dir=self.base)
        r.set_checked("c1", ["a.md"])
        state = self.base / "checked_state.json"
        self.assertTrue(state.is_file())
        r2 = _PLUGIN.KBRuntime(self.root, data_dir=self.base)
        r2.load_checked()
        self.assertEqual(r2.get_checked("c1"), {"a.md"})

    def test_get_checked_single_cid_recovery(self) -> None:

        state = self.base / "checked_state.json"
        state.write_text(json.dumps({"c2": ["docs/b.txt"]}, ensure_ascii=False), encoding="utf-8")
        r = _PLUGIN.KBRuntime(self.root, data_dir=self.base)
        # 落盘状态在启动时**全量**读入（`load_checked`）；
        # 不读就没有，所以先 load 再断言
        r.load_checked()
        self.assertEqual(r.get_checked("c2"), {"docs/b.txt"})
        # 没 load 过的实例不应凭空知道别的会话选了什么
        fresh = _PLUGIN.KBRuntime(self.root, data_dir=self.base)
        self.assertEqual(fresh.get_checked("c2"), set())

    def test_build_system_messages_and_count(self) -> None:

        r = _PLUGIN.KBRuntime(self.root)
        r.set_checked("c1", ["a.md", "docs/b.txt"])
        msgs = r.build_system_messages("c1")
        self.assertEqual(len(msgs), 2)
        self.assertTrue(msgs[0].startswith("【知识库：a.md】"))
        self.assertIn("知识A", msgs[0])
        self.assertTrue(msgs[1].startswith("【知识库：docs/b.txt】"))
        self.assertEqual(r.attached_count("c1"), 2)
        self.assertEqual(r.build_system_messages("other"), [])

    def test_build_skips_over_limit_after_check(self) -> None:

        r = _PLUGIN.KBRuntime(self.root)
        r.set_checked("c1", ["a.md"])
        r_small = _PLUGIN.KBRuntime(self.root, max_file_size=3)
        self.assertEqual(r_small.build_system_messages("c1"), [])  # 组包时复检大小
        self.assertEqual(r_small.attached_count("c1"), 0)

    def test_list_files_excludes_hidden_and_pycache(self) -> None:

        r = _PLUGIN.KBRuntime(self.root)
        paths = [f["path"] for f in r.list_files()]
        self.assertIn("a.md", paths)
        self.assertIn("docs/b.txt", paths)
        self.assertNotIn(".hidden", paths)
        self.assertNotIn(".git/config", paths)
        self.assertNotIn("__pycache__/c.txt", paths)
        self.assertTrue(all("name" in f and "mtime" in f for f in r.list_files()))

class KBConfigTest(unittest.TestCase):
    """本插件配置（`plugins/knowledge/config.ini`）读取。

    缺文件 / 缺节 / 目录不存在都静默降级为未启用 —— 判定失败不报错。
    """

    def test_config_lives_in_the_plugin_directory(self) -> None:
        """配置跟着插件走，不在内核的 `config.ini` 里。"""
        p = _PLUGIN._config_path()
        self.assertEqual(p.parent, _PLUGIN.__file__ and Path(_PLUGIN.__file__).resolve().parent)
        self.assertEqual(p.name, "config.ini")
        self.assertTrue((p.parent / "config.ini.example").is_file(),
                        msg="插件目录下应当有一个模板")

    def test_missing_section_disables(self) -> None:

        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "config.ini"
            ini.write_text("[model_reasoning]\nmodel = x\n", encoding="utf-8")
            self.assertIsNone(_PLUGIN._load_kb_config(ini)["dir"])

    def test_missing_file_disables(self) -> None:

        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(
                _PLUGIN._load_kb_config(Path(tmp) / "not-here.ini")["dir"])

    def test_nonexistent_dir_disables_without_error(self) -> None:

        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "config.ini"
            ini.write_text(
                "[knowledge]\ndir = Z:/definitely-not-here\nmax_file_size = 100\n",
                encoding="utf-8")
            cfg = _PLUGIN._load_kb_config(ini)
            self.assertIsNone(cfg["dir"], msg="目录不存在应静默降级为未启用")
            self.assertEqual(cfg["max_file_size"], 100)

    def test_existing_dir_enables(self) -> None:

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            kb_dir = base / "kb"
            kb_dir.mkdir()
            ini = base / "config.ini"
            ini.write_text(f"[knowledge]\ndir = {kb_dir.as_posix()}\n", encoding="utf-8")
            self.assertEqual(_PLUGIN._load_kb_config(ini)["dir"], kb_dir.resolve())

    def test_values_tolerate_quotes_and_blank_lines(self) -> None:

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            kb_dir = base / "kb"
            kb_dir.mkdir()
            ini = base / "config.ini"
            ini.write_text(
                f"[knowledge]\ndir = \"{kb_dir.as_posix()}\"\nmax_file_size =\n",
                encoding="utf-8")
            cfg = _PLUGIN._load_kb_config(ini)
            self.assertEqual(cfg["dir"], kb_dir.resolve(), msg="包裹引号应被剥掉")
            self.assertEqual(cfg["max_file_size"], _PLUGIN.DEFAULT_MAX_FILE_SIZE)

    def test_disabled_kb_returns_empty(self) -> None:

        kb = _PLUGIN.KBRuntime(None)
        self.assertFalse(kb.enabled)
        self.assertEqual(kb.list_files(), [])
        self.assertIsNone(kb.safe_resolve("a.md"))

class ContextSourcesTest(unittest.TestCase):
    def test_order_and_disposer(self) -> None:

        cs = ContextSources()
        d1 = cs.add(lambda cid: ["A1"])
        cs.add(lambda cid: ["B1", "B2"])
        self.assertEqual(cs.collect("c"), ["A1", "B1", "B2"])
        d1()
        d1()  # 幂等
        self.assertEqual(cs.collect("c"), ["B1", "B2"])

    def test_exception_isolated(self) -> None:

        cs = ContextSources()

        def bad(cid):
            raise RuntimeError("boom")

        cs.add(bad)
        cs.add(lambda cid: ["ok"])
        self.assertEqual(cs.collect("c"), ["ok"])

    def test_validation_and_empty_filter(self) -> None:

        cs = ContextSources()
        with self.assertRaises(ValueError):
            cs.add(None)
        cs.add(lambda cid: ["", "  ", None, "留白"])
        self.assertEqual(cs.collect("c"), ["留白"])

class _RecordingProvider:
    """记录请求的假模型（一轮文本应答结束回合）。"""

    def __init__(self):
        self.requests = []

    def stream(self, request):
        self.requests.append(request)
        yield StreamDelta(kind="text", text="好的")

class InjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = self.base / "kb"
        _make_tree(self.root)

    def test_pipeline_refresh_and_replace(self) -> None:

        runtime = _PLUGIN.KBRuntime(self.root)
        runtime.set_checked("c1", ["a.md"])
        cs = ContextSources()
        cs.add(runtime.build_system_messages)
        pipeline = ContextPipeline("c1", sources=cs)
        pipeline.rebuild_from_messages([])
        msgs = pipeline.flatten_to_messages()
        kb = [m for m in msgs if "【知识库：" in str(m.get("content", ""))]
        self.assertEqual(len(kb), 1)
        self.assertIn("知识A", str(kb[0]["content"]))
        runtime.set_checked("c1", ["docs/b.txt"])  # 换勾选 → 刷新替换（不累积）
        pipeline.rebuild_from_messages([])
        kb2 = [m for m in pipeline.flatten_to_messages() if "【知识库：" in str(m.get("content", ""))]
        self.assertEqual(len(kb2), 1)
        self.assertIn("知识B", str(kb2[0]["content"]))
        self.assertNotIn("知识A", str(kb2[0]["content"]))

    def test_turn_end_to_end_injection(self) -> None:

        rec = _RecordingProvider()
        app = build_app(provider=rec)
        app.context_sources.add(lambda cid: ["【知识库：probe】\n内容P"])
        list(app.session("c-kb", system_prompt="你是助手").start_turn("你好"))
        self.assertTrue(rec.requests)
        flat = rec.requests[0].messages
        kb_msgs = [m for m in flat if "【知识库：probe】" in str(m.get("content", ""))]
        self.assertEqual(len(kb_msgs), 1)
        self.assertEqual(kb_msgs[0].get("role"), "system")

if __name__ == "__main__":
    unittest.main()
