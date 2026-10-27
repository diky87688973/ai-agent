# -*- coding: utf-8 -*-
"""知识库插件测试。

覆盖：`[config]` 配置读取（缺节 / 目录不存在 / 引号容忍）/ 路径安全
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
from agent.mechanisms.context import ContextPipeline, ContextSources  # noqa: E402
from agent.mechanisms.session_store import SessionStore  # noqa: E402  # noqa: E402
from tests.testkit import no_plugins  # noqa: E402

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
        # 落盘状态在启动时全量读入（`load_checked`）；
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
    """本插件配置（`plugins/knowledge/plugin-config.ini`）读取。

    缺文件 / 缺节 / 目录不存在都静默降级为未启用 —— 判定失败不报错。
    """

    def test_config_lives_in_the_plugin_directory(self) -> None:
        """配置跟着插件走，不在内核的 `config.ini` 里。"""
        p = _PLUGIN._config_path()
        self.assertEqual(p.parent, _PLUGIN.__file__ and Path(_PLUGIN.__file__).resolve().parent)
        self.assertEqual(p.name, "plugin-config.ini")
        self.assertTrue((p.parent / "plugin-meta.json").is_file(),
                        msg="插件目录下应当有身份元数据")

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
                "[config]\ndir = Z:/definitely-not-here\nmax_file_size = 100\n",
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
            ini.write_text(f"[config]\ndir = {kb_dir.as_posix()}\n", encoding="utf-8")
            self.assertEqual(_PLUGIN._load_kb_config(ini)["dir"], kb_dir.resolve())

    def test_values_tolerate_quotes_and_blank_lines(self) -> None:

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            kb_dir = base / "kb"
            kb_dir.mkdir()
            ini = base / "config.ini"
            ini.write_text(
                f"[config]\ndir = \"{kb_dir.as_posix()}\"\nmax_file_size =\n",
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
        self.assertEqual([t for _, _, t in cs.collect_segments("c").items], ["A1", "B1", "B2"])
        d1()
        d1()  # 幂等
        self.assertEqual([t for _, _, t in cs.collect_segments("c").items], ["B1", "B2"])

    def test_exception_isolated(self) -> None:

        cs = ContextSources()

        def bad(cid):
            raise RuntimeError("boom")

        cs.add(bad)
        cs.add(lambda cid: ["ok"])
        self.assertEqual([t for _, _, t in cs.collect_segments("c").items], ["ok"])

    def test_validation_and_empty_filter(self) -> None:

        cs = ContextSources()
        with self.assertRaises((ValueError, TypeError)):
            cs.add(None)
        cs.add(lambda cid: ["", "  ", None, "留白"])
        self.assertEqual([t for _, _, t in cs.collect_segments("c").items], ["留白"])

class _RecordingProvider:
    """记录请求的假模型（一回合文本应答结束回合）。"""

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
        cs = ContextSources()
        # 勾选一变就声明"内容变了"：装配侧一趟只收集一次，不打招呼就看不到新勾选。
        runtime._sources_bump = cs.bump
        runtime.set_checked("c1", ["a.md"])
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

        # 本用例手工注册注入源，不需要装载任何插件：不隔离的话，开发者本机的
        # 多模型插件配置会让目录接管路由，请求就不走这里注入的 provider 了。
        no_plugins(self)
        rec = _RecordingProvider()
        app = build_app(provider=rec)
        app.context_sources.add(lambda cid: ["【知识库：probe】\n内容P"])
        list(app.session("c-kb", system_prompt="你是助手").start_turn("你好"))
        self.assertTrue(rec.requests)
        flat = rec.requests[0].messages
        kb_msgs = [m for m in flat if "【知识库：probe】" in str(m.get("content", ""))]
        self.assertEqual(len(kb_msgs), 1)
        self.assertEqual(kb_msgs[0].get("role"), "system")


class PluginSourceContractTest(unittest.TestCase):
    """插件注入源的契约：注册进「知识库」段、每回合刷新、disposer 后消失。

    插件只经 `ctx.add_context_source` 说话 —— 内核不知道"知识库插件"的存在，
    也不知道它读了什么文件。这里钉住的就是这条边界。
    """

    def _run(self, app, spy, cid: str):
        engine = app.session(cid, system_prompt="你是助手。")
        for _ev in engine.start_turn("问"):
            pass
        return spy.requests[-1].messages

    def _app(self, root: Path):
        # 注入源在本类里手工注册，插件装配只会带来环境差异（尤其是开发者本机的
        # 多模型配置会让目录接管路由，spy 收不到请求）。
        no_plugins(self)
        spy = _RecordingProvider()
        app = build_app(provider=spy, store=SessionStore(root / "data"),
                        backup_root=root / "bk", recycle_root=root / "rc")
        return app, spy

    def test_source_text_lands_in_the_knowledge_block(self) -> None:
        import tempfile
        root = Path(tempfile.mkdtemp(prefix="kbcontract_"))
        try:
            app, spy = self._app(root)
            app.context_sources.add(lambda cid: ["【知识库：probe】\n内容P"])
            msgs = self._run(app, spy, "kb-contract-0001")
            hits = [m for m in msgs if "内容P" in str(m.get("content"))]
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].get("role"), "system")
            # 位置：在任何对话消息之前（头部）
            idx = msgs.index(hits[0])
            first_user = next(i for i, m in enumerate(msgs)
                              if str(m.get("role")) == "user")
            self.assertLess(idx, first_user)
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)

    def test_source_is_refreshed_every_turn(self) -> None:
        """注入源每回合都重读：第 2 回合改内容，请求里立刻反映。"""
        import shutil
        import tempfile
        root = Path(tempfile.mkdtemp(prefix="kbcontract2_"))
        try:
            app, spy = self._app(root)
            state = {"text": "第一版"}
            app.context_sources.add(lambda cid: [f"【知识库：probe】\n{state['text']}"])
            msgs1 = self._run(app, spy, "kb-contract-0002")
            state["text"] = "第二版"
            engine = app.session("kb-contract-0002", system_prompt="你是助手。")
            for _ev in engine.start_turn("再问"):
                pass
            msgs2 = spy.requests[-1].messages
            self.assertTrue(any("第一版" in str(m.get("content")) for m in msgs1))
            joined2 = "".join(str(m.get("content")) for m in msgs2)
            self.assertIn("第二版", joined2)
            self.assertNotIn("第一版", joined2)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_disposer_removes_the_source(self) -> None:
        import shutil
        import tempfile
        root = Path(tempfile.mkdtemp(prefix="kbcontract3_"))
        try:
            app, spy = self._app(root)
            disposer = app.context_sources.add(lambda cid: ["【知识库：probe】\n内容P"])
            self._run(app, spy, "kb-contract-0003")
            disposer()
            engine = app.session("kb-contract-0003", system_prompt="你是助手。")
            for _ev in engine.start_turn("再问"):
                pass
            self.assertFalse(any("内容P" in str(m.get("content"))
                                 for m in spy.requests[-1].messages))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_plugin_sources_do_not_touch_the_kernel(self) -> None:
        """插件来源只经注册表进出；内核不持有插件对象。"""
        from agent.mechanisms.context import ContextSources
        sources = ContextSources()
        seen = []
        disposer = sources.add(lambda cid: seen.append(cid) or ["文本"])
        self.assertEqual([t for _, _, t in sources.collect_segments("c1").items], ["文本"])
        self.assertEqual(seen, ["c1"])
        disposer()
        self.assertEqual(sources.collect_segments("c1").items, ())

    def test_segments_carry_their_own_name_and_prefix(self) -> None:
        """段名与注入前缀由来源声明：内核不解释正文是什么。"""
        from agent.mechanisms.context import ContextSources, SourceMeta
        sources = ContextSources()
        sources.add(lambda cid: ["正文"], SourceMeta(key="kb", label="知识库",
                                                   prefix="【知识库：a.md】\n"))
        seg = sources.collect_segments("c1")
        self.assertEqual([(k, lb) for k, lb, _t in seg.items], [("kb", "知识库")])
        self.assertEqual(seg.items[0][2], "【知识库：a.md】\n正文")

    def test_two_sources_of_one_plugin_stay_separate(self) -> None:
        """同一插件可以贡献多段：数量按位置对，不互相覆盖。"""
        from agent.mechanisms.context import ContextSources, SourceMeta
        sources = ContextSources()
        sources.add(lambda cid: ["清单"], SourceMeta(key="skills", label="Skills",
                                                   count=lambda cid: 31))
        sources.add(lambda cid: ["常驻"], SourceMeta(key="skills", label="常驻 Skills",
                                                   count=lambda cid: 1))
        seg = sources.collect_segments("c1")
        self.assertEqual([lb for _k, lb, _t in seg.items], ["Skills", "常驻 Skills"])
        self.assertEqual(seg.counts, (31, 1))


class PluginConfigIsolationTest(unittest.TestCase):
    """内核 `config.ini` 只含内核设置；插件设置在插件自己目录下的 plugin-config.ini。"""

    #: 内核配置允许出现的节（多一个就说明插件设置漏进了内核配置）
    KERNEL_SECTIONS = {"model_reasoning", "agent", "context", "update", "auth"}

    def test_kernel_templates_have_no_plugin_section(self) -> None:
        from agent.config import PROJECT_ROOT, load_ini
        path = PROJECT_ROOT / "config.ini"
        if path.exists():
            extra = set(load_ini(path).sections()) - self.KERNEL_SECTIONS
            self.assertEqual(extra, set(), msg=f"{path.name} 里有插件设置：{sorted(extra)}")

    def test_each_plugin_reads_its_own_config_file(self) -> None:
        import importlib.util
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent
        for name in ("knowledge", "skills", "ai_speak"):
            entry = root / "plugins" / name / "plugin.py"
            plugin_root = entry.parent
            mod_name = f"fan_agent_plugins.cfgprobe_{name}"
            spec = importlib.util.spec_from_file_location(
                mod_name,
                str(entry),
                submodule_search_locations=[str(plugin_root)],
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            path = mod._config_path()
            self.assertEqual(path.parent, root / "plugins" / name)
            self.assertEqual(path.name, "plugin-config.ini")

    def test_skills_dir_comes_from_its_own_config(self) -> None:
        import importlib.util
        import tempfile
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent
        entry = root / "plugins" / "skills" / "plugin.py"
        mod_name = "fan_agent_plugins.cfgprobe_skills_dir"
        spec = importlib.util.spec_from_file_location(
            mod_name,
            str(entry),
            submodule_search_locations=[str(entry.parent)],
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        tmp = _P(tempfile.mkdtemp(prefix="skcfg_"))
        target = tmp / "skills"
        target.mkdir()
        ini = tmp / "plugin-config.ini"
        ini.write_text(f"[config]\ndir = {target.as_posix()}\nmax_file_size = 321\n",
                       encoding="utf-8")
        cfg = mod._load_config(ini)
        self.assertEqual(cfg["dir"], target)
        self.assertEqual(cfg["max_file_size"], 321)
        empty = tmp / "empty.ini"
        empty.write_text("[config]\ndir =\n", encoding="utf-8")
        self.assertIsNone(mod._load_config(empty)["dir"])

class KnowledgeTextOnlyTest(unittest.TestCase):
    """知识库只收文本类文件：非文本不列、不可勾（读出来是替换字符与 NUL，只占预算）。"""

    def _files(self, tmp):
        import importlib.util
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kb_text_probe", str(root / "plugins" / "knowledge" / "plugin.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mod._KnowledgeFiles(tmp, 200000)

    def test_text_suffix_rules(self) -> None:
        import tempfile
        from pathlib import Path as _P
        tmp = _P(tempfile.mkdtemp(prefix="kbtext_"))
        mod, _files = self._files(tmp)
        for name in ("a.md", "b.txt", "c.csv", "d.json", "e.yaml", "f.py", "noext", "g.xlsx"):
            self.assertTrue(mod.is_text_like(name), msg=f"{name} 应算文本")
        for name in ("a.png", "b.bin", "c.zip", "d.pdf", "e.exe", "f.docx"):
            self.assertFalse(mod.is_text_like(name), msg=f"{name} 不该算文本")

    def test_binary_is_neither_listed_nor_selectable(self) -> None:
        import tempfile
        from pathlib import Path as _P
        tmp = _P(tempfile.mkdtemp(prefix="kbtext2_"))
        (tmp / "doc.md").write_text("正文", encoding="utf-8")
        (tmp / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
        (tmp / "blob.bin").write_bytes(b"\x00\xff" * 20)
        mod, files = self._files(tmp)
        paths = [row["path"] for row in files.list_files()]
        self.assertEqual(paths, ["doc.md"], msg=f"列出内容不对：{paths}")
        ok, why = files.file_allowed(tmp / "img.png")
        self.assertFalse(ok)
        self.assertIn("非文本", why)
        ok2, _why2 = files.file_allowed(tmp / "blob.bin")
        self.assertFalse(ok2)

    def test_runtime_rejects_binary_check(self) -> None:
        import tempfile
        from pathlib import Path as _P
        tmp = _P(tempfile.mkdtemp(prefix="kbtext3_"))
        (tmp / "doc.md").write_text("正文", encoding="utf-8")
        (tmp / "img.png").write_bytes(b"\x89PNG" + b"\x00" * 20)
        mod, _files = self._files(tmp)
        rt = mod.KBRuntime(tmp, 200000, data_dir=_P(tempfile.mkdtemp(prefix="kbstate_")))
        rt.set_checked("c1", ["doc.md", "img.png"])
        self.assertEqual(sorted(rt.get_checked("c1")), ["doc.md"])

class KnowledgeExtraSuffixesTest(unittest.TestCase):
    """配置 `extra_suffixes`：英文逗号分隔，追加可收录的扩展名。"""

    def _mod(self):
        import importlib.util
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "kb_extra_probe", str(root / "plugins" / "knowledge" / "plugin.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_parse_forms(self) -> None:
        mod = self._mod()
        self.assertEqual(mod.parse_extra_suffixes("txt, ini"), (".txt", ".ini"))
        self.assertEqual(mod.parse_extra_suffixes(".txt,.ini"), (".txt", ".ini"))
        self.assertEqual(mod.parse_extra_suffixes("TXT , .Ini ,txt,"), (".txt", ".ini"))
        self.assertEqual(mod.parse_extra_suffixes(""), ())
        self.assertEqual(mod.parse_extra_suffixes(None), ())
        self.assertEqual(mod.parse_extra_suffixes("  "), ())

    def test_extra_extends_the_whitelist(self) -> None:
        mod = self._mod()
        self.assertFalse(mod.is_text_like("a.dat"))
        self.assertTrue(mod.is_text_like("a.dat", (".dat",)))
        self.assertFalse(mod.is_text_like("a.png", (".dat",)))

    def test_config_key_is_read_and_used(self) -> None:
        import tempfile
        from pathlib import Path as _P
        mod = self._mod()
        tmp = _P(tempfile.mkdtemp(prefix="kbextra_"))
        (tmp / "x.dat").write_text("自定义类型", encoding="utf-8")
        (tmp / "y.png").write_bytes(b"\x89PNG\x00")
        ini = tmp / "plugin-config.ini"
        ini.write_text(f"[config]\ndir = {tmp.as_posix()}\n"
                       "max_file_size = 200000\nextra_suffixes = dat\n", encoding="utf-8")
        cfg = mod._load_kb_config(ini)
        self.assertEqual(cfg["extra_suffixes"], (".dat",))
        files = mod._KnowledgeFiles(cfg["dir"], cfg["max_file_size"], cfg["extra_suffixes"])
        paths = [row["path"] for row in files.list_files()]
        self.assertIn("x.dat", paths)
        self.assertNotIn("y.png", paths)
        self.assertTrue(files.file_allowed(tmp / "x.dat")[0])
        self.assertFalse(files.file_allowed(tmp / "y.png")[0])

    def test_missing_key_keeps_default_whitelist(self) -> None:
        mod = self._mod()
        self.assertEqual(mod.parse_extra_suffixes(None), ())
        self.assertTrue(mod.is_text_like("a.md"))
        self.assertFalse(mod.is_text_like("a.dat"))

class PluginPanelRenderContractTest(unittest.TestCase):
    """插件脚本只载一次，所以面板渲染必须由 `ai-agent:panel-opened` 驱动。

    脚本在开屏被预载（段色注册要赶在上下文条第一次渲染前），那时面板 DOM 还不存在，
    脚本里的首次渲染必然是空跑 —— 没有这个事件，面板就永远停在初始占位。
    """

    def _shell_js(self) -> str:
        from agent.shell.web.ui_bundle import read_ui_js
        return read_ui_js()

    def test_open_pane_broadcasts_panel_opened(self) -> None:
        js = self._shell_js()
        self.assertIn("ai-agent:panel-opened", js)
        idx = js.index("function openPane(")
        self.assertIn("ai-agent:panel-opened", js[idx:idx + 4000],
                      msg="广播要在 openPane 里（每个面板打开都发）")

    def test_open_plugin_panel_passes_its_plugin_name(self) -> None:
        js = self._shell_js()
        idx = js.index("function openPluginPanel(")
        chunk = js[idx:idx + 800]
        self.assertIn("plugin:pluginKey", chunk,
                      msg="不带插件名，脚本认不出这是不是自己的面板")
        self.assertIn('pluginKey+"__"+panelKey', chunk,
                      msg="面板 DOM id 须带插件名前缀，避免跨插件撞名")

    def test_panel_has_a_refresh_button_on_the_subtitle(self) -> None:
        """小标题右侧一个刷新：知识库目录是外部目录，不重开面板也要能取到新文件。"""
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent
        js = (root / "plugins" / "knowledge" / "ui" / "panel.js").read_text(encoding="utf-8")
        css = (root / "plugins" / "knowledge" / "ui" / "panel.css").read_text(encoding="utf-8")
        self.assertIn("kb-refresh", js)
        self.assertIn("pane-btn", js, msg="按钮样式用壳层那套，与文件查看器的刷新同款")
        idx = js.index("kb-hint-bar")
        self.assertIn("kb-refresh", js[idx:idx + 500], msg="刷新要挂在小标题那一行")
        self.assertIn("kb-refresh", css)
        self.assertIn("display:flex", css[css.index(".kb-hint-bar"):css.index(".kb-hint-bar") + 300])

    def test_refresh_handler_re_renders(self) -> None:
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent
        js = (root / "plugins" / "knowledge" / "ui" / "panel.js").read_text(encoding="utf-8")
        idx = js.index('target.closest(".kb-refresh")')
        self.assertIn("render()", js[idx:idx + 300], msg="点了刷新要重新取数并渲染")

    def test_panels_render_on_the_event(self) -> None:
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent
        for name in ("knowledge",):
            panel = root / "plugins" / name / "ui" / "panel.js"
            if not panel.exists():
                continue
            text = panel.read_text(encoding="utf-8")
            self.assertIn("ai-agent:panel-opened", text,
                          msg=f"plugins/{name}/ui/panel.js 没订阅打开事件")

    def test_knowledge_panel_matches_composite_dom_id(self) -> None:
        """壳层广播的 panel 是 `knowledge__kb`，不能只认逻辑 id `kb`。"""
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent
        text = (root / "plugins" / "knowledge" / "ui" / "panel.js").read_text(
            encoding="utf-8")
        self.assertIn('plugin === "knowledge"', text)
        self.assertIn("panelId", text)
        shell = self._shell_js()
        idx = shell.index("ai-agent:panel-opened")
        chunk = shell[idx:idx + 280]
        self.assertIn("panelId", chunk, msg="打开事件须带逻辑 panelId")

if __name__ == "__main__":
    unittest.main()


class SkillsConfigSourceTest(unittest.TestCase):
    """Skills 设置只有工程 config.ini 一处来源（插件目录下没有同名配置）。"""

    def test_plugin_dir_has_no_own_config(self) -> None:
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent / "plugins" / "skills"
        self.assertFalse((root / "config.ini").exists(),
                         msg="插件目录下不该有第二份 Skills 配置")

    def test_reader_reads_the_project_config(self) -> None:
        import importlib.util
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent
        entry = root / "plugins" / "skills" / "plugin.py"
        mod_name = "fan_agent_plugins.skills_plugin_probe"
        spec = importlib.util.spec_from_file_location(
            mod_name,
            str(entry),
            submodule_search_locations=[str(entry.parent)],
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        cfg = mod._load_config()
        self.assertEqual(cfg["max_file_size"], 200000)
        if cfg["dir"] is not None:
            self.assertTrue(_P(cfg["dir"]).is_dir())

    def test_reader_takes_a_given_ini(self) -> None:
        import importlib.util
        import tempfile
        from pathlib import Path as _P
        root = _P(__file__).resolve().parent.parent
        entry = root / "plugins" / "skills" / "plugin.py"
        mod_name = "fan_agent_plugins.skills_plugin_probe2"
        spec = importlib.util.spec_from_file_location(
            mod_name,
            str(entry),
            submodule_search_locations=[str(entry.parent)],
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
        tmp = _P(tempfile.mkdtemp(prefix="skcfg_"))
        target = tmp / "skills"
        target.mkdir()
        ini = tmp / "config.ini"
        ini.write_text(f"[config]\ndir = {target.as_posix()}\nmax_file_size = 321\n",
                       encoding="utf-8")
        cfg = mod._load_config(ini)
        self.assertEqual(cfg["dir"], target)
        self.assertEqual(cfg["max_file_size"], 321)
