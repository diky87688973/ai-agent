# -*- coding: utf-8 -*-
"""架构约束：门控旁路 AST 检测（负例伪装 + 正例放行）。"""
from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

from check_architecture_hygiene import (  # noqa: E402
    check_compactor_contract_boundary,
    check_gate_single_path,
    check_no_quality_gate_shim,
    check_no_silent_system_prompt,
    check_provider_module_boundary,
    check_same_layer_private_imports,
    check_test_method_names,
)


def _agent_tree(tmp: Path) -> Path:
    """临时目录下搭出 agent/core 结构，供 check_gate_single_path 扫描。"""
    pkg = tmp / "agent"
    (pkg / "core").mkdir(parents=True)
    (pkg / "core" / "__init__.py").write_text("", encoding="utf-8")
    return pkg


def _write(pkg: Path, rel: str, src: str) -> Path:
    path = pkg / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(src).lstrip(), encoding="utf-8")
    return path


class GateSinglePathAstTest(unittest.TestCase):
    """负例：Attribute / Call / Assign / 导入别名伪装须被 AST 抓住。"""

    def _assert_catches(self, src: str, symbol: str) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-neg-") as tmp:
            pkg = _agent_tree(Path(tmp))
            _write(pkg, "core/probe.py", src)
            hits = check_gate_single_path(pkg)
            self.assertTrue(hits, f"应检出「{symbol}」，实际无违规")
            self.assertTrue(
                any(symbol in h for h in hits),
                f"违规中应含「{symbol}」，得到：{hits}",
            )

    def test_fallback_gate_attribute(self) -> None:
        self._assert_catches(
            """
            class C:
                def run(self):
                    return self._fallback_gate
            """,
            "_fallback_gate",
        )

    def test_gate_resolver_call_attr(self) -> None:
        self._assert_catches(
            """
            def f(mod):
                return mod.gate_resolver()
            """,
            "gate_resolver",
        )

    def test_tool_path_keys_name(self) -> None:
        self._assert_catches(
            """
            def f():
                return _TOOL_PATH_KEYS
            """,
            "_TOOL_PATH_KEYS",
        )

    def test_register_write_path_keys_call(self) -> None:
        self._assert_catches(
            """
            def f(reg):
                reg.register_write_path_keys("x", ("path",))
            """,
            "register_write_path_keys",
        )

    def test_unregister_write_path_keys_import_alias(self) -> None:
        self._assert_catches(
            """
            from somewhere import unregister_write_path_keys as drop_keys
            drop_keys("x")
            """,
            "unregister_write_path_keys",
        )

    def test_preview_tools_keyword(self) -> None:
        self._assert_catches(
            """
            def build(preview_tools=None):
                return preview_tools

            build(preview_tools={"a"})
            """,
            "preview_tools",
        )

    def test_content_tools_assign_attr(self) -> None:
        self._assert_catches(
            """
            class Bag:
                pass

            bag = Bag()
            bag.content_tools = {"x"}
            """,
            "content_tools",
        )

    def test_preview_tools_tuple_unpack(self) -> None:
        self._assert_catches(
            """
            preview_tools, other = {"a"}, 1
            """,
            "preview_tools",
        )

    def test_innocuous_code_passes(self) -> None:
        src = """
        # 注释里写 _fallback_gate / preview_tools= / gate_resolver 不应误伤
        FALLBACK_NOTE = "use session.gate not _fallback_gate substring"

        def resolve_path_keys(tool):
            return tuple(getattr(tool, "write_path_keys", ()) or ())

        def build_gate(*, registry, sessions):
            return {"registry": registry, "sessions": sessions}
        """
        with tempfile.TemporaryDirectory(prefix="hygiene-pos-") as tmp:
            pkg = _agent_tree(Path(tmp))
            _write(pkg, "core/ok.py", src)
            self.assertEqual(check_gate_single_path(pkg), [])


class QualityGateShimAstTest(unittest.TestCase):
    def test_import_quality_gate_caught(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-shim-") as tmp:
            root = Path(tmp)
            pkg = _agent_tree(root)
            _write(
                pkg,
                "core/bad_shim.py",
                """
                import quality_gate
                from agent.mechanisms import quality_gate as qg
                """,
            )
            hits = check_no_quality_gate_shim(
                pkg,
                plugins_dir=root / "plugins",
                tests_dir=root / "tests",
            )
            self.assertTrue(any("quality_gate" in h for h in hits), hits)

    def test_comment_mention_passes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-shim-ok-") as tmp:
            root = Path(tmp)
            pkg = _agent_tree(root)
            _write(
                pkg,
                "core/ok_shim.py",
                """
                # 已迁到 mechanisms.quality，勿再 import quality_gate
                from agent.mechanisms.quality import QualityGate
                """,
            )
            hits = check_no_quality_gate_shim(
                pkg,
                plugins_dir=root / "plugins",
                tests_dir=root / "tests",
            )
            self.assertEqual(hits, [])


class ModuleBoundaryAstTest(unittest.TestCase):
    def test_provider_concrete_sibling_caught(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-provider-") as tmp:
            pkg = _agent_tree(Path(tmp))
            _write(
                pkg,
                "mechanisms/providers/anthropic.py",
                "from agent.mechanisms.providers.openai import OpenAICompatibleProvider\n",
            )
            hits = check_provider_module_boundary(pkg)
            self.assertTrue(any("anthropic" in h and "openai" in h for h in hits), hits)

    def test_provider_neutral_imports_pass(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-provider-ok-") as tmp:
            pkg = _agent_tree(Path(tmp))
            _write(
                pkg,
                "mechanisms/providers/anthropic.py",
                "from agent.mechanisms.providers.base import ModelProvider\n"
                "from agent.mechanisms.providers.sse import stream_with_timeout\n",
            )
            self.assertEqual(check_provider_module_boundary(pkg), [])

    def test_compactor_pipeline_import_caught(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-compactor-") as tmp:
            pkg = _agent_tree(Path(tmp))
            _write(
                pkg,
                "mechanisms/compaction/compactor.py",
                "from agent.mechanisms.context.pipeline import ContextPipeline\n",
            )
            hits = check_compactor_contract_boundary(pkg)
            self.assertTrue(any("pipeline" in h for h in hits), hits)

    def test_compactor_contract_import_passes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-compactor-ok-") as tmp:
            pkg = _agent_tree(Path(tmp))
            _write(
                pkg,
                "mechanisms/compaction/compactor.py",
                "from agent.mechanisms.context.contract import ContextCompactionPolicy\n",
            )
            self.assertEqual(check_compactor_contract_boundary(pkg), [])


class SameLayerPrivateImportTest(unittest.TestCase):
    def test_private_same_layer_caught(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-same-layer-") as tmp:
            pkg = _agent_tree(Path(tmp))
            _write(pkg, "mechanisms/a.py", "SECRET = 1\n")
            _write(pkg, "mechanisms/b.py", "from agent.mechanisms.a import _secret\n")
            hits = check_same_layer_private_imports(pkg)
            self.assertTrue(any("_secret" in h for h in hits), hits)

    def test_public_same_layer_passes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-same-layer-ok-") as tmp:
            pkg = _agent_tree(Path(tmp))
            _write(pkg, "mechanisms/a.py", "SECRET = 1\n")
            _write(pkg, "mechanisms/b.py", "from agent.mechanisms.a import SECRET\n")
            self.assertEqual(check_same_layer_private_imports(pkg), [])


class TestMethodNameGateTest(unittest.TestCase):
    def test_bad_test_prefix_caught(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-testname-") as tmp:
            root = Path(tmp)
            _write(root, "test_bad.py", "def testbad() -> None:\n    pass\n")
            self.assertTrue(check_test_method_names(root))

    def test_public_test_prefix_passes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-testname-ok-") as tmp:
            root = Path(tmp)
            _write(root, "test_ok.py", "def test_good() -> None:\n    pass\n")
            self.assertEqual(check_test_method_names(root), [])


class SilentSystemPromptCheckTest(unittest.TestCase):
    def test_nonstandard_indent_and_as_clause_caught(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-prompt-") as tmp:
            pkg = _agent_tree(Path(tmp))
            _write(
                pkg,
                "shell/a.py",
                """
                def f():
                    resolve_system_prompt()
                    try:
                        work()
                    except Exception as exc:
                        # 说明
                        system_text = ""
                """,
            )
            hits = check_no_silent_system_prompt(pkg)
            self.assertTrue(any("system_text" in h for h in hits), hits)

    def test_external_package_root_does_not_crash(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hygiene-prompt-ext-") as tmp:
            pkg = _agent_tree(Path(tmp))
            _write(
                pkg,
                "shell/a.py",
                "resolve_system_prompt()\ntry:\n    work()\nexcept Exception:\n"
                "    system_text = \"\"\n",
            )
            self.assertTrue(check_no_silent_system_prompt(pkg))


if __name__ == "__main__":
    unittest.main()

    unittest.main()
