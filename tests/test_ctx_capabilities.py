# -*- coding: utf-8 -*-
"""装配上下文的能力面：字段枚举、缺字段即抛、依赖图无环，以及插件的直取约定。"""
from __future__ import annotations

import dataclasses
import pathlib
import re
import unittest
from typing import List, Tuple

from agent.boot.config import BootConfig, HostBootConfig
from agent.core.plugin_meta import read_plugin_meta
from agent.core.slot_assembly import (
    BuildContext,
    SlotAssembly,
)
from agent.core.slot_config import topo_order
from agent.core.slot_fragments import load_merged
from agent.core.slot_spec import SlotSpec

REPO = pathlib.Path(__file__).resolve().parent.parent
PLUGINS = REPO / "plugins"

#: 装配期上下文的能力面：多一个字段就是多一个万能袋入口，故逐字写死。
CTX_FIELDS = ("spec", "config", "built", "resolver",
              "boot_config", "data_dir", "plugin_meta")

#: 允许对 `ctx` 做 getattr 的行：这里的 ctx 是回合级上下文
#: （`agent.core.session_scope.current_context()`），不是装配期 BuildContext。
TURN_SCOPE_CTX = {
    ("plugins/visual_operator_2/tools.py", 21): "回合级 ctx：取 conversation_id",
    ("plugins/visual_operator_2/tools.py", 26): "回合级 ctx：取 call_id",
}

#: 禁的两种形态：对 ctx 本体取字面量属性、对 ctx 派生对象再兜底。
GETATTR_ON_CTX = re.compile(r"getattr\(\s*ctx\s*,|getattr\(\s*ctx\.[A-Za-z_][A-Za-z_0-9]*\s*,")


def _boot(plugin_data_root: pathlib.Path) -> BootConfig:
    host = HostBootConfig(data_root=plugin_data_root,
                          plugins_root=PLUGINS,
                          plugin_data_root=plugin_data_root)
    return BootConfig(data_root=plugin_data_root, host_config=host)


class CapabilitySurfaceTest(unittest.TestCase):
    """能力面必须是可枚举的定值：有人塞第 8 项就该红。"""

    def test_ctx_has_exactly_seven_capabilities(self) -> None:
        names = tuple(item.name for item in dataclasses.fields(BuildContext))
        self.assertEqual(names, CTX_FIELDS)

    def test_missing_ctx_attribute_raises(self) -> None:
        """缺字段必须当场抛 AttributeError，不许退化成 None 静默失效。"""
        spec = SlotSpec(path="app/a", kind="service")
        ctx = BuildContext(spec=spec, config=None)  # type: ignore[arg-type]
        for name in ("data_dir", "plugin_meta", "boot_config"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(ctx, name), f"{name} 应是字段")
        hollow = type("Hollow", (), {"spec": spec})()
        self.assertRaises(AttributeError, getattr, hollow, "data_dir")


class PluginGetattrTest(unittest.TestCase):
    """插件代码里不许对 ctx 做 getattr 兜底。"""

    @staticmethod
    def _hits() -> List[Tuple[str, int, str]]:
        hits: List[Tuple[str, int, str]] = []
        for path in sorted(PLUGINS.rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(text.splitlines(), 1):
                if GETATTR_ON_CTX.search(line):
                    rel = path.relative_to(REPO).as_posix()
                    hits.append((rel, lineno, line.strip()))
        return hits

    def test_no_getattr_on_plugin_ctx(self) -> None:
        left = [row for row in self._hits() if (row[0], row[1]) not in TURN_SCOPE_CTX]
        detail = "\n".join(f"{f}:{n}: {s}" for f, n, s in left)
        self.assertEqual(left, [], f"插件里出现 ctx 兜底：\n{detail}")

    def test_whitelist_entries_still_exist(self) -> None:
        """白名单必须还能对上真实代码，否则就是僵死豁免。"""
        for (rel, lineno), reason in TURN_SCOPE_CTX.items():
            with self.subTest(file=rel, line=lineno):
                text = (REPO / rel).read_text(encoding="utf-8")
                lines = text.splitlines()
                self.assertLessEqual(lineno, len(lines), f"{rel} 行数变少：{reason}")
                self.assertIn("getattr(ctx", lines[lineno - 1].replace(" ", ""),
                              f"{rel}:{lineno} 已不再是 getattr 兜底：{reason}")


class PluginMetaTest(unittest.TestCase):
    """插件身份读法：编码与容错都要对真实插件成立。"""

    def test_plugin_meta_reads_all_real_plugins(self) -> None:
        dirs = sorted(item for item in PLUGINS.iterdir() if item.is_dir())
        self.assertTrue(dirs)
        for item in dirs:
            with self.subTest(plugin=item.name):
                meta = read_plugin_meta(item)
                self.assertTrue(str(meta.get("name") or "").strip(),
                                f"{item.name} 的 name 读不出来")

    def test_bom_plugin_is_readable(self) -> None:
        """visual_operator 的 meta 带 UTF-8 BOM；直读 utf-8 会炸。"""
        raw = (PLUGINS / "visual_operator" / "plugin-meta.json").read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "该文件应仍带 BOM")
        self.assertEqual(read_plugin_meta(PLUGINS / "visual_operator")["name"],
                         "Visual Operator")


class DataDirTest(unittest.TestCase):
    """数据目录判据只有一条：owner 目录存在于 plugins/ 下。"""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory(prefix="ctxdirs-")
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        self.assembly = SlotAssembly(load_merged(REPO), boot_config=_boot(self.root))

    def _ctx(self, owner: str) -> BuildContext:
        spec = SlotSpec(path="app/x", kind="service", owner=owner)
        return self.assembly.context_for(spec)

    def test_data_dir_for_three_owner_kinds(self) -> None:
        plugin_ctx = self._ctx("knowledge")
        self.assertEqual(plugin_ctx.data_dir, self.root / "knowledge")
        self.assertTrue(plugin_ctx.data_dir.is_dir())
        self.assertEqual(plugin_ctx.plugin_meta.get("name"), "知识库")

        self.assertIsNone(self._ctx("__host__").data_dir)
        self.assertIsNone(self._ctx("auth").data_dir)
        self.assertEqual(dict(self._ctx("__host__").plugin_meta), {})


class RequiresGraphTest(unittest.TestCase):
    """依赖图必须无环，且每条依赖都排在用它的节点之前。"""

    def test_requires_graph_is_acyclic(self) -> None:
        config = load_merged(REPO)
        order = topo_order(config)  # 成环即抛 SlotConfigError
        self.assertEqual(len(order), len(config.specs))
        position = {path: index for index, path in enumerate(order)}
        for path, spec in config.specs.items():
            for port, target in spec.requires.items():
                with self.subTest(path=path, port=port):
                    self.assertLess(position[target], position[path],
                                    f"{path} 的依赖 {target} 排在了它后面")


if __name__ == "__main__":
    unittest.main()
