# -*- coding: utf-8 -*-
"""门禁负向用例（X2）：每条门禁都要能真的红。

只测"当前仓库能过"等于没测：门禁写成 `return []` 也能过。这里给每个检查器
喂一个必须失败的最小输入，再喂一个合法输入，钉住"判据存在且方向正确"。
"""
from __future__ import annotations

import ast
import io
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import check_applicability  # noqa: E402
import check_architecture_hygiene as hygiene  # noqa: E402
import check_comment_style  # noqa: E402
import check_complexity  # noqa: E402
import check_config_drift  # noqa: E402
import check_confirm_wording  # noqa: E402
import check_coverage  # noqa: E402
import check_imports  # noqa: E402
import check_python_floor  # noqa: E402
import check_readme  # noqa: E402
import check_ui_js  # noqa: E402
import gen_ci_workflow  # noqa: E402
import gen_complexity_md  # noqa: E402
import gen_unit_tests_md  # noqa: E402
from ci_steps import acceptance_skip_problems  # noqa: E402


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8")
    return path


class ImportDirectionGateTest(unittest.TestCase):
    """A2：向上导入与反向依赖装配根都必须被抓到。"""

    def _package(self, files: dict[str, str]) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "agent"
        for rel, text in files.items():
            _write(root / rel, text)
        return root

    def test_upward_import_fails(self) -> None:
        root = self._package({"core/a.py": "from agent.shell import web\n"})
        problems = check_imports.check(root)
        self.assertTrue(problems)
        self.assertIn("[core]", problems[0])
        self.assertIn("[shell]", problems[0])

    def test_composition_root_import_fails(self) -> None:
        root = self._package({"shell/a.py": "from agent.app import build_app\n"})
        problems = check_imports.check(root)
        self.assertTrue(problems)
        self.assertIn("装配根", problems[0])

    def test_type_checking_annotation_is_allowed(self) -> None:
        root = self._package({
            "shell/a.py": (
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from agent.app import App\n"
            ),
        })
        self.assertEqual(check_imports.check(root), [])

    def test_downward_import_passes(self) -> None:
        root = self._package({
            "core/a.py": "VALUE = 1\n",
            "mechanisms/b.py": "from agent.core import a\n",
            "shell/c.py": "from agent.mechanisms import b\n",
        })
        self.assertEqual(check_imports.check(root), [])


class ArchitectureHygieneGateTest(unittest.TestCase):
    """跨层私有导入 / 内核插件名 / quality_gate 回流。"""

    def _package(self, files: dict[str, str]) -> tuple[Path, Path]:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        root = base / "agent"
        for rel, text in files.items():
            _write(root / rel, text)
        plugins = base / "plugins"
        _write(plugins / "knowledge" / "plugin.py", "VALUE = 1\n")
        return root, plugins

    def test_cross_layer_private_import_fails(self) -> None:
        root, _ = self._package({"core/a.py": "from agent.shell.fspaths import _env_path\n"})
        self.assertTrue(hygiene.check_cross_layer_private_imports(root))

    def test_same_layer_private_import_passes(self) -> None:
        root, _ = self._package({"shell/a.py": "from agent.shell.web.web_api import date_group\n"})
        self.assertEqual(hygiene.check_cross_layer_private_imports(root), [])

    def test_plugin_name_in_core_fails(self) -> None:
        root, plugins = self._package({"core/a.py": "SOURCE = 'knowledge'\n"})
        self.assertTrue(hygiene.check_kernel_plugin_names(root, plugins))

    def test_quality_gate_shim_import_fails(self) -> None:
        root, plugins = self._package({"core/a.py": "from agent.mechanisms import quality_gate\n"})
        self.assertTrue(hygiene.check_no_quality_gate_shim(root, plugins, root))

    def test_quality_gate_real_module_passes(self) -> None:
        root, plugins = self._package({"core/a.py": "from agent.mechanisms.quality import gate\n"})
        self.assertEqual(hygiene.check_no_quality_gate_shim(root, plugins, root), [])


class PythonFloorGateTest(unittest.TestCase):
    """3.11 / 3.12 语法必须在 3.10 下限门禁里报出来。"""

    def test_ordinary_function_passes(self) -> None:
        tree = ast.parse("def f(x):\n    return x\n")
        self.assertEqual(check_python_floor._violations(tree), [])

    @unittest.skipUnless(sys.version_info >= (3, 12), "3.12 才能解析 PEP 695")
    def test_pep695_generic_fails(self) -> None:
        tree = ast.parse("def f[T](x):\n    return x\n")
        self.assertTrue(check_python_floor._violations(tree))


class ApplicabilityGateTest(unittest.TestCase):
    """例外申报表：列数、准则编号、原因长度、未知准则、缺表。"""

    _HEADER = "| 准则 | 申报 | 原因 | 风险由谁承担 |\n|---|---|---|---|\n"
    _OK_ROW = "| A1 | 不适用 | 这个仓库没有对应的运行时依赖，因此不适用 | 维护者 |\n"

    def _docs(self, text: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return _write(Path(tmp.name) / "applicability.md", text)

    def _run(self, docs: Path) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch.object(check_applicability, "DOCS", docs), \
                mock.patch("sys.stdout", out):
            code = check_applicability.main()
        return code, out.getvalue()

    def test_unknown_rule_id_fails(self) -> None:
        text = self._HEADER + "| Z9 | 不适用 | 这条规则与本地部署无关 | 维护者 |\n"
        problems = check_applicability.check(text, known_ids={"A1"})
        self.assertTrue(any("标准手册里没有" in p for p in problems))

    def test_short_reason_fails(self) -> None:
        text = self._HEADER + "| A1 | 不适用 | 短 | 维护者 |\n"
        problems = check_applicability.check(text, known_ids={"A1"})
        self.assertTrue(any("原因少于" in p for p in problems))

    def test_well_formed_row_passes(self) -> None:
        text = self._HEADER + self._OK_ROW
        self.assertEqual(check_applicability.check(text, known_ids={"A1"}), [])

    def test_rule_ids_are_wellformed(self) -> None:
        """编号格式错会让整张表无法申报；分节标题混进来会稀释占比。"""
        ids = check_applicability.RULE_IDS
        self.assertGreaterEqual(len(ids), 90)
        self.assertTrue({"A1", "A2", "G1", "X2"} <= ids)
        self.assertNotIn("0.5", ids)
        self.assertNotIn("1.1", ids)
        bad = [i for i in ids if not check_applicability._ID_RE.match(i)]
        self.assertEqual(bad, [])

    def test_stale_id_fails_through_main(self) -> None:
        """端到端：拿真实编号集合比对一条不存在的编号，门禁必须退出 1。"""
        docs = self._docs(self._HEADER + "| Z9 | 不适用 | 这条规则与本地部署无关 | 维护者 |\n")
        code, out = self._run(docs)
        self.assertEqual(code, 1)
        self.assertIn("标准手册里没有", out)

    def test_counts_and_ratio_visible(self) -> None:
        code, out = self._run(self._docs(self._HEADER + self._OK_ROW))
        self.assertEqual(code, 0)
        self.assertRegex(out, r"申报 1 条 / 标准 \d+ 条（N/A \d+\.\d+%）")
        self.assertIn(f"v{check_applicability.VERSION}", out)

    def test_missing_table_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self._run(Path(tmp) / "absent.md")
        self.assertEqual(code, 1)
        self.assertIn("缺少", out)


class ComplexityGateTest(unittest.TestCase):
    """复杂度：未登记的超阈值文件必须失败。"""

    def _root(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        _write(root / "agent" / "big.py", "x = 1\n" * 40)
        return root

    def test_unregistered_big_file_fails(self) -> None:
        root = self._root()
        with tempfile.TemporaryDirectory() as docs_tmp:
            docs = Path(docs_tmp) / "complexity.md"
            docs.write_text("", encoding="utf-8")
            problems = check_complexity.check(
                root, docs, file_reasons={}, func_reasons={},
                max_file_lines=10, max_function_lines=8,
            )
        self.assertTrue(any("未登记的超阈值文件" in p for p in problems))

    def test_registered_big_file_only_reports_doc_drift(self) -> None:
        root = self._root()
        with tempfile.TemporaryDirectory() as docs_tmp:
            docs = Path(docs_tmp) / "complexity.md"
            docs.write_text("", encoding="utf-8")
            problems = check_complexity.check(
                root, docs, file_reasons={"agent/big.py": "历史文件，拆分排期中"},
                func_reasons={}, max_file_lines=10, max_function_lines=8,
            )
        self.assertFalse(any("未登记的超阈值文件" in p for p in problems))


class ConfigDriftGateTest(unittest.TestCase):
    """配置漂移：真实文件只允许使用 schema 登记的键。"""

    def test_real_file_extra_key_reports_line_number(self) -> None:
        problems = check_config_drift.compare_subset(
            "[context]\nsummary_token_threshold = 1\nsumary_token_threshold = 2\n", "c.ini",
            {"context": {"summary_token_threshold": "700000"}},
        )
        self.assertTrue(any("c.ini:3" in p for p in problems))

    def test_real_file_subset_passes(self) -> None:
        problems = check_config_drift.compare_subset(
            "[context]\nsummary_token_threshold = 1\n", "c.ini",
            {"context": {"summary_token_threshold": "700000"}},
        )
        self.assertEqual(problems, [])

    def test_unknown_section_fails(self) -> None:
        problems = check_config_drift.compare_subset(
            "[unknown]\nx = 1\n", "c.ini", {"context": {}},
        )
        self.assertTrue(any("未登记的节" in p for p in problems))

    def test_model_plugin_rejects_unknown_key(self) -> None:
        text = (
            "[model:a]\nprovider = openai\nbase_url = http://x\n"
            "api_key = k\nextra = x\n"
        )
        problems = check_config_drift.compare_plugin_model_real(text, "p.ini")
        self.assertTrue(any("[model:a] 未登记的键 `extra`" in p for p in problems))



class CoverageGateTest(unittest.TestCase):
    """覆盖率：低于下限、缺数据都要失败。"""

    def test_below_floor_fails(self) -> None:
        problems = check_coverage.check({"agent/core": (100, 40)},
                                        {"agent/core": 85})
        self.assertTrue(any("低于下限" in p or "< 下限" in p for p in problems))

    def test_missing_group_fails(self) -> None:
        problems = check_coverage.check({}, {"agent/core": 85})
        self.assertTrue(any("没有覆盖率数据" in p for p in problems))

    def test_at_or_above_floor_passes(self) -> None:
        self.assertEqual(check_coverage.check({"agent/core": (100, 15)},
                                              {"agent/core": 85}), [])


class GeneratedArtifactDriftTest(unittest.TestCase):
    """生成物门禁：直接改动 CI / 单测清单必须被 --check 抓到。"""

    def test_ci_workflow_byte_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ci.yml"
            path.write_text(gen_ci_workflow.render() + "# 手改\n", encoding="utf-8")
            with mock.patch.object(check_ci_workflow, "WORKFLOW", path):
                self.assertTrue(check_ci_workflow.check())

    def test_ci_workflow_current_is_clean(self) -> None:
        self.assertEqual(check_ci_workflow.check(), [])

    def test_unit_tests_md_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unit-tests.md"
            path.write_text("手改的文档\n", encoding="utf-8")
            with mock.patch.object(gen_unit_tests_md, "OUT", path):
                self.assertEqual(gen_unit_tests_md.main(["--check"]), 1)
                self.assertEqual(gen_unit_tests_md.main([]), 0)
                self.assertEqual(gen_unit_tests_md.main(["--check"]), 0)

    def test_render_contains_every_gate_and_acceptance(self) -> None:
        text = gen_ci_workflow.render()
        for step in gen_ci_workflow.gate_steps():
            self.assertIn(" ".join(step.argv), text)
        for name in gen_ci_workflow.ACCEPTANCE:
            self.assertIn(name, text)


class UiJsGateTest(unittest.TestCase):
    """UI JS：调用未定义的辅助函数必须被抓到。"""

    def test_undefined_helper_call_fails(self) -> None:
        self.assertIn("renderMissingThing",
                      check_ui_js._undefined_called("renderMissingThing();"))

    def test_defined_helper_passes(self) -> None:
        self.assertEqual(
            check_ui_js._undefined_called("function renderThing(){}\nrenderThing();"), []
        )

    def test_model_id_literal_is_rejected(self) -> None:
        hits = check_ui_js.model_id_literals(
            "var m = 'deepseek-v4-pro';\nvar ok = 'deepseek';\n")
        self.assertEqual([line for line, _ in hits], [1])

    def test_plain_words_are_not_model_ids(self) -> None:
        self.assertEqual(check_ui_js.model_id_literals("var x = 'claude';\n"), [])


class ReadmeGateTest(unittest.TestCase):
    """README 事实：步数、门禁数、用例数写错或标记缺失都必须失败。"""

    _OK = ("流水线 29 步，17 项门禁\n"
           "→ 单测 → 10 个验收脚本\n"
           "单元测试（1242 个用例）\n"
           "用 data/sessions/ 存会话\n")

    def test_step_count_drift_fails(self) -> None:
        text = self._OK.replace("流水线 29 步", "流水线 28 步")
        self.assertTrue(any("流水线" in p for p in check_readme.check(
            text, 10, 1242, ["sessions"], 29, 17)))

    def test_gate_count_drift_fails(self) -> None:
        text = self._OK.replace("17 项门禁", "11 项门禁")
        self.assertTrue(any("项门禁" in p for p in check_readme.check(
            text, 10, 1242, ["sessions"], 29, 17)))

    def test_acceptance_count_drift_fails(self) -> None:
        text = self._OK.replace("10 个验收脚本", "9 个验收脚本")
        self.assertTrue(any("验收脚本" in p for p in check_readme.check(
            text, 10, 1242, ["sessions"], 29, 17)))

    def test_test_count_drift_fails(self) -> None:
        text = self._OK.replace("1242 个用例", "1200 个用例")
        self.assertTrue(any("用例" in p for p in check_readme.check(
            text, 10, 1242, ["sessions"], 29, 17)))

    def test_missing_marker_fails(self) -> None:
        problems = check_readme.check("无关文本\n", 10, 1242, ["sessions"], 29, 17)
        self.assertGreaterEqual(len(problems), 4)

    def test_unknown_data_dir_fails(self) -> None:
        text = self._OK + "用 data/ghost/ 存别的\n"
        self.assertTrue(any("ghost" in p for p in check_readme.check(
            text, 10, 1242, ["sessions"], 29, 17)))

    def test_consistent_readme_passes(self) -> None:
        self.assertEqual(
            check_readme.check(self._OK, 10, 1242, ["sessions"], 29, 17), []
        )


class CommentStyleGateTest(unittest.TestCase):
    """注释文案：只吃注释/文档串，代码里的同名词不误伤。"""

    def test_todo_comment_fails(self) -> None:
        hits = check_comment_style.scan_text("# TODO 清理\nx = 1\n", ".py",
                                             {**check_comment_style.UNIVERSAL,
                                              **check_comment_style.PRODUCTION_ONLY})
        self.assertTrue(any(name == "遗留备忘" for _ln, name, _text in hits))

    def test_command_to_reader_fails(self) -> None:
        hits = check_comment_style.scan_text("def f():\n    # 不要往返回值里塞数据\n    return 1\n",
                                             ".py",
                                             {**check_comment_style.UNIVERSAL,
                                              **check_comment_style.PRODUCTION_ONLY})
        self.assertTrue(any(name == "对读者下指令" for _ln, name, _text in hits))

    def test_string_literal_is_not_comment(self) -> None:
        hits = check_comment_style.scan_text('MSG = "TODO 以后补"\n', ".py",
                                             {**check_comment_style.UNIVERSAL,
                                              **check_comment_style.PRODUCTION_ONLY})
        self.assertEqual(hits, [])

    def test_clean_comment_passes(self) -> None:
        hits = check_comment_style.scan_text("# 先清再写：失败也不重复写已写的\nx = 1\n", ".py",
                                             {**check_comment_style.UNIVERSAL,
                                              **check_comment_style.PRODUCTION_ONLY})
        self.assertEqual(hits, [])

    def test_markdown_emphasis_comment_fails(self) -> None:
        hits = check_comment_style.scan_text("# 这里**必须**先读\nx = 1\n", ".py",
                                             {**check_comment_style.UNIVERSAL,
                                              **check_comment_style.PRODUCTION_ONLY})
        self.assertTrue(any(name == "排版标记" for _ln, name, _text in hits))

    def test_markdown_emphasis_across_lines_fails(self) -> None:
        src = 'def f():\n    """说明会**折成两行\n    的强调**。"""\n    return 1\n'
        hits = check_comment_style.scan_text(src, ".py",
                                             {**check_comment_style.UNIVERSAL,
                                              **check_comment_style.PRODUCTION_ONLY})
        self.assertTrue(any(name == "排版标记" for _ln, name, _text in hits))

    def test_code_unpacking_is_not_emphasis(self) -> None:
        hits = check_comment_style.scan_text("def f(**kw):\n    return {**kw}\n", ".py",
                                             {**check_comment_style.UNIVERSAL,
                                              **check_comment_style.PRODUCTION_ONLY})
        self.assertEqual(hits, [])


class ConfirmWordingGateTest(unittest.TestCase):
    """写盘指引：缺解锁工具、含糊写法、解释性内容都必须失败。"""

    def _texts(self, **overrides: str) -> dict[str, str]:
        gate = (
            "def gate(rec, args):\n"
            "    if not rec.get(\"confirmed\"):\n"
            "        raise ValueError(\"预览尚未解锁：请调用 review_conclusion，"
            "再凭同一 confirm_id 提交\")\n"
            "    args = {}\n"
        )
        texts = {
            "write_file 的工具描述": "写盘前调用 review_conclusion。",
            "commit_write 的工具描述": "凭 confirm_id 调用 commit_write（先经 review_conclusion 解锁）。",
            "review_conclusion 的工具描述": "调用 review_conclusion 解锁预览。",
            check_confirm_wording.GATE_LABEL: gate,
        }
        texts.update(overrides)
        return texts

    def test_missing_unlock_tool_fails(self) -> None:
        texts = self._texts(**{"write_file 的工具描述": "写盘工具。"})
        self.assertTrue(any("没有点明" in p
                            for p in check_confirm_wording.check_texts(texts)))

    def test_vague_wording_fails(self) -> None:
        texts = self._texts(**{"commit_write 的工具描述": "请先完成确认再提交。"})
        self.assertTrue(any("含糊写法" in p
                            for p in check_confirm_wording.check_texts(texts)))

    def test_explanatory_wording_fails(self) -> None:
        texts = self._texts(**{"review_conclusion 的工具描述":
                               "调用 review_conclusion 解锁，这不是等用户确认。"})
        self.assertTrue(any("解释性内容" in p
                            for p in check_confirm_wording.check_texts(texts)))

    def test_gate_without_next_step_fails(self) -> None:
        texts = self._texts(**{check_confirm_wording.GATE_LABEL:
                               "    if not rec.get(\"confirmed\"):\n"
                               "        raise ValueError(\"未解锁\")\n"
                               "    args = {}\n"})
        problems = check_confirm_wording.check_texts(texts)
        self.assertTrue(any("下一步调哪个工具" in p for p in problems))
        self.assertTrue(any("confirm_id" in p for p in problems))

    def test_compliant_wording_passes(self) -> None:
        self.assertEqual(check_confirm_wording.check_texts(self._texts()), [])


class AcceptanceSkipGateTest(unittest.TestCase):
    """验收 skip：预算上限与白名单都必须能触发。"""

    def test_over_budget_fails(self) -> None:
        problems = acceptance_skip_problems(["acceptance_batch_a", "acceptance_batch_b"])
        self.assertTrue(any("上限" in p for p in problems))

    def test_non_whitelisted_fails(self) -> None:
        problems = acceptance_skip_problems(["acceptance_batch_a"])
        self.assertTrue(any("非预期 skip" in p for p in problems))

    def test_whitelisted_within_budget_passes(self) -> None:
        self.assertEqual(acceptance_skip_problems(["acceptance_mvp3"]), [])

    def test_duplicates_do_not_count_twice(self) -> None:
        self.assertEqual(
            acceptance_skip_problems(["acceptance_mvp3", "acceptance_mvp3"]), []
        )


# 延迟导入：避免测试收集阶段就因可选依赖失败
import check_ci_workflow  # noqa: E402


class GeneratedComplexityDocGateTest(unittest.TestCase):
    def test_check_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="complexity-doc-") as tmp:
            docs = Path(tmp) / "complexity.md"
            docs.write_text("drifted\n", encoding="utf-8")
            with mock.patch.object(gen_complexity_md, "DOCS", docs):
                self.assertEqual(gen_complexity_md.main(["--check"]), 1)

    def test_check_detects_missing_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="complexity-doc-missing-") as tmp:
            docs = Path(tmp) / "missing.md"
            with mock.patch.object(gen_complexity_md, "DOCS", docs):
                self.assertEqual(gen_complexity_md.main(["--check"]), 1)

    def test_check_detects_extra_content(self) -> None:
        with tempfile.TemporaryDirectory(prefix="complexity-doc-extra-") as tmp:
            docs = Path(tmp) / "complexity.md"
            docs.write_text(gen_complexity_md.build() + "\nextra\n", encoding="utf-8")
            with mock.patch.object(gen_complexity_md, "DOCS", docs):
                self.assertEqual(gen_complexity_md.main(["--check"]), 1)

    def test_check_accepts_generated_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="complexity-doc-ok-") as tmp:
            docs = Path(tmp) / "complexity.md"
            docs.write_text(gen_complexity_md.build(), encoding="utf-8")
            with mock.patch.object(gen_complexity_md, "DOCS", docs):
                self.assertEqual(gen_complexity_md.main(["--check"]), 0)


class ConfigModelExampleGateTest(unittest.TestCase):
    def _model_example(self, extra: str = "") -> str:
        keys = sorted(check_config_drift.MULTI_MODEL_SCHEMA["model"])
        body = "\n".join(f"{k} = x" for k in keys)
        return f"[model:x]\n{body}\n{extra}"

    def test_compare_model_example_detects_extra_key(self) -> None:
        problems = check_config_drift.compare_model_example(
            self._model_example("ghost = 1\n"), "m.ini")
        self.assertTrue(any("ghost" in p for p in problems), problems)

    def test_compare_model_example_detects_changed_section(self) -> None:
        problems = check_config_drift.compare_model_example(
            self._model_example().replace("[model:x]", "[modelx]"), "m.ini")
        self.assertTrue(any("model" in p for p in problems), problems)

    def test_compare_model_example_positive(self) -> None:
        self.assertEqual(
            check_config_drift.compare_model_example(self._model_example(), "m.ini"), [])

    def test_compare_model_example_requires_keys(self) -> None:
        problems = check_config_drift.compare_model_example(
            "[model:x]\nprovider = openai\n", "m.ini")
        self.assertTrue(any("base_url" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
