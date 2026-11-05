"""后端路径由片段声明提供，不建立旧路径种子账本。"""
from __future__ import annotations

import unittest
from pathlib import Path

from agent.core.slot_fragments import load_merged


class BackendSlotTableTest(unittest.TestCase):
    def test_fragment_paths_do_not_use_retired_backend_prefix(self) -> None:
        root = Path(__file__).resolve().parents[1]
        config = load_merged(root)
        self.assertFalse(any(path.startswith("app/backend/") for path in config.paths()))

    def test_retired_seed_and_tree_files_are_absent(self) -> None:
        root = Path(__file__).resolve().parents[1]
        self.assertFalse((root / "agent/capabilities/backend_paths.py").exists())
        self.assertFalse((root / "agent/boot/slot_tree.json").exists())
