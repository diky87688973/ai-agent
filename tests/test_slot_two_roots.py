# -*- coding: utf-8 -*-
"""两个根分开：片段从哪来，工厂就从哪解析。

同一份静态片段 + 临时目录里的插件片段 → 合并结果的 `plugins_root` 就是临时目录，
插件节点的 `origin` 是插件名。缺省时退回 `<仓库根>/plugins`，现有行为不变。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.core.slot_assembly import SlotAssembly  # noqa: E402
from agent.core.slot_fragments import (  # noqa: E402
    HOST_OWNER,
    load_merged,
)
from agent.core.slot_spec import SlotConfigError  # noqa: E402

#: 最小静态片段：一个宿主节点 + 一条归属授权，够插件声明自己的节点。
_STATIC = {
    "version": 1,
    "root": "app",
    "owners": {"app/plugins": "__host__"},
    "slots": [
        {"path": "app/host", "kind": "container"},
        {"path": "app/host/services", "kind": "container"},
        {"path": "app/plugins", "kind": "container"},
    ],
}


def _write_fragment(plugins_root: Path, name: str, slots: list) -> Path:
    """在 `<plugins_root>/<name>/` 下放一份插件片段。"""
    target = plugins_root / name
    target.mkdir(parents=True, exist_ok=True)
    (target / "plugin-slots.json").write_text(
        json.dumps({"version": 1, "root": "app", "slots": slots},
                   ensure_ascii=False),
        encoding="utf-8")
    return target


class TwoRootsTest(unittest.TestCase):
    """`plugins_root` 决定片段来源，也决定工厂解析根。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tworoots-")
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        (self.repo / "plugin-slots.json").write_text(
            json.dumps(_STATIC, ensure_ascii=False), encoding="utf-8")
        self.plugins = Path(self._tmp.name) / "elsewhere" / "plugins"
        self.plugins.mkdir(parents=True)

    def test_plugins_root_is_carried_into_config(self) -> None:
        _write_fragment(self.plugins, "alpha", [])
        config = load_merged(self.repo, plugins_root=self.plugins)
        self.assertEqual(config.plugins_root, self.plugins)

    def test_fragment_comes_from_given_plugins_root(self) -> None:
        """片段从传进来的插件根收，不从 `<repo>/plugins` 收。"""
        _write_fragment(self.plugins, "alpha", [{
            "path": "app/plugins/alpha/tool", "kind": "tool",
            "factory": "plugin:make_tool",
        }])
        config = load_merged(self.repo, plugins_root=self.plugins)
        path = "app/plugins/alpha/tool"
        self.assertIn(path, config.specs)
        self.assertEqual(config.origin_of(path), "alpha")
        self.assertNotEqual(config.origin_of(path), HOST_OWNER)

    def test_repo_plugins_dir_is_not_scanned_when_root_given(self) -> None:
        """仓库自己的 `plugins/` 有片段也不该被收进来。"""
        _write_fragment(self.repo / "plugins", "beta", [{
            "path": "app/plugins/beta/tool", "kind": "tool",
            "factory": "plugin:make_tool",
        }])
        _write_fragment(self.plugins, "alpha", [])
        config = load_merged(self.repo, plugins_root=self.plugins)
        self.assertNotIn("app/plugins/beta/tool", config.specs)

    def test_default_plugins_root_is_repo_plugins(self) -> None:
        """不传 plugins_root 时缺省是 `<repo>/plugins`，现有行为不变。"""
        _write_fragment(self.repo / "plugins", "alpha", [{
            "path": "app/plugins/alpha/tool", "kind": "tool",
            "factory": "plugin:make_tool",
        }])
        config = load_merged(self.repo)
        self.assertEqual(config.plugins_root, self.repo / "plugins")
        self.assertIn("app/plugins/alpha/tool", config.specs)

    def test_factory_resolves_against_config_plugins_root(self) -> None:
        """工厂解析根就是 config.plugins_root：临时插件根的插件能被导入。"""
        plugin = _write_fragment(self.plugins, "alpha", [{
            "path": "app/plugins/alpha/tool", "kind": "tool",
            "factory": "plugin:make_tool",
        }])
        (plugin / "plugin.py").write_text(
            "def make_tool(ctx):\n    return ('tool', 'alpha')\n",
            encoding="utf-8")
        self.addCleanup(self._forget, "alpha")
        config = load_merged(self.repo, plugins_root=self.plugins)
        seen = []

        def factories(origin, spec, path, plugins_root):
            from agent.capabilities.plugins import resolve_plugin_factory
            seen.append((origin, plugins_root))
            return resolve_plugin_factory(plugins_root, origin, spec, path, _ROOT)

        assembly = SlotAssembly(config, plugin_factories=factories).build()
        self.addCleanup(assembly.dispose)
        self.assertEqual(assembly.get("app/plugins/alpha/tool"), ("tool", "alpha"))
        self.assertEqual(seen, [("alpha", self.plugins)])

    def test_missing_plugins_root_is_an_explicit_error(self) -> None:
        """单片段解析（无插件根）遇到插件 factory：明确报错，不猜路径。"""
        _write_fragment(self.plugins, "alpha", [{
            "path": "app/plugins/alpha/tool", "kind": "tool",
            "factory": "plugin:make_tool",
        }])
        config = load_merged(self.repo, plugins_root=self.plugins)
        bare = type(config)(root=config.root, version=config.version,
                            specs=config.specs, origins=config.origins)
        self.assertIsNone(bare.plugins_root)
        assembly = SlotAssembly(bare)
        with self.assertRaises(SlotConfigError) as caught:
            assembly.build()
        message = str(caught.exception)
        self.assertIn("无 plugins_root", message)
        self.assertIn("app/plugins/alpha/tool", message)

    def _forget(self, name: str) -> None:
        from agent.capabilities.plugins import plugin_module_name

        prefix = plugin_module_name(name)
        for key in list(sys.modules):
            if key == prefix or key.startswith(prefix + "."):
                sys.modules.pop(key, None)


if __name__ == "__main__":
    unittest.main()
