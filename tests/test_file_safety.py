# -*- coding: utf-8 -*-
"""版本化备份与回收目录：按路径哈希分组、每版本自描述、按年龄清理。"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.mechanisms.file_safety import (  # noqa: E402
    METADATA_NAME,
    ORIGINAL_NAME,
    FileBackups,
    Recycle,
    _version_time_text,
    path_hash,
)


class LayoutTest(unittest.TestCase):
    """结构：`<root>/<路径哈希>/<版本目录>/{original,metadata.json}`。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.root = self.base / "file_backup"
        self.backups = FileBackups(self.root)
        self.f = self.base / "报告 带空格.md"
        self.f.write_text("版本一", encoding="utf-8")

    def test_files_are_grouped_by_path_hash(self) -> None:
        """同一文件的所有版本在同一个哈希目录下。"""
        mid1 = self.backups.create(self.f)
        time.sleep(1.05)
        mid2 = self.backups.create(self.f)
        assert mid1 and mid2
        g1, g2 = mid1.split(":")[0], mid2.split(":")[0]
        self.assertEqual(g1, g2)
        self.assertEqual(g1, path_hash(self.f))
        ver_dirs = sorted(p.name for p in (self.root / g1).iterdir())
        self.assertEqual(len(ver_dirs), 2)
        for name in ver_dirs:
            self.assertRegex(name, r"^\d{8}_\d{6}_\d{3}_\d{4}_[0-9a-z]{4}$")

    def test_same_second_versions_keep_chronological_order(self) -> None:
        """同一秒内的多次改动必须能排出先后 —— 时间戳要精确到毫秒。

        只到秒时，同一秒内只能靠 4 位随机段排序，而随机段与先后无关：
        `file_undo list` 顺序错乱、`undo` 可能挑错版本。
        """
        ids = []
        for i in range(6):                      # 不 sleep，故意压进同一秒
            self.f.write_text(f"v{i}", encoding="utf-8")
            mid = self.backups.create(self.f, mode="write", diff_text=f"-v{i-1} +v{i}")
            assert mid is not None
            ids.append(mid)
        # 时间戳部分必须严格递增
        stamps = [m.split(":")[1][:19] for m in ids]
        self.assertEqual(stamps, sorted(stamps), msg=str(stamps))
        # list_for 新→旧，与写入顺序相反
        got = [m["diff_text"] for m in self.backups.list_for(self.f)]
        self.assertEqual(got, [f"-v{i-1} +v{i}" for i in range(5, -1, -1)])

    def test_versions_are_self_describing(self) -> None:
        mid = self.backups.create(self.f, mode="write", diff_text="旧→新")
        assert mid is not None
        group, ver = mid.split(":")
        d = self.root / group / ver
        self.assertTrue((d / ORIGINAL_NAME).is_file())
        meta = json.loads((d / METADATA_NAME).read_text(encoding="utf-8"))
        self.assertEqual(meta["mod_id"], mid)
        self.assertEqual(meta["path"], str(self.f.resolve()))
        self.assertEqual(meta["bytes"], len("版本一".encode()))
        self.assertEqual(meta["mode"], "write")
        self.assertEqual(meta["diff_text"], "旧→新")
        self.assertTrue(meta["original_sha256"])
        # 键名是 `time`（`file_undo` 列历史时按这个名字读）
        self.assertIn("time", meta)
        self.assertNotIn("timestamp", meta)

    def test_long_diff_is_clipped_and_marked(self) -> None:
        """超长 diff 截断后要标明截断了 —— 静默截断会被读成"改动就这么点"。"""
        mid = self.backups.create(self.f, mode="write", diff_text="x" * 5000)
        assert mid is not None
        group, ver = mid.split(":")
        meta = json.loads((self.root / group / ver / METADATA_NAME).read_text(encoding="utf-8"))
        self.assertLess(len(meta["diff_text"]), 5000)
        self.assertIn("已截断", meta["diff_text"])
        self.assertEqual(meta["diff_text"][:2000], "x" * 2000)

    def test_directory_names_carry_no_filename(self) -> None:
        """目录名一律是短码 + 时间戳 —— 不塞文件名，也就不出现一串 `_`。"""
        other = self.base / "总结.md"
        other.write_text("x", encoding="utf-8")
        self.backups.create(self.f)
        self.backups.create(other)
        for p in self.root.rglob("*"):
            if not p.is_dir():
                continue
            # 目录名要么是 16 位十六进制短码，要么是 `YYYYMMDD_HHMMSS_mmm_序号_随机`
            self.assertTrue(
                re.fullmatch(r"[0-9a-f]{16}|\d{8}_\d{6}_\d{3}_\d{4}_[0-9a-z]{4}", p.name),
                msg=f"目录名不该含文件名：{p.name}")

    def test_two_different_files_never_share_a_group(self) -> None:
        """中文名不同的两个文件必须各自一组（净化方案下会互相分不开）。"""
        other = self.base / "总结.md"
        other.write_text("w", encoding="utf-8")
        mid_a = self.backups.create(self.f)
        mid_b = self.backups.create(other)
        assert mid_a and mid_b
        self.assertNotEqual(mid_a.split(":")[0], mid_b.split(":")[0])
        self.assertEqual(len(self.backups.list_for(self.f)), 1)
        self.assertEqual(len(self.backups.list_for(other)), 1)

    def test_list_for_is_newest_first(self) -> None:
        first = self.backups.create(self.f)
        time.sleep(1.05)
        second = self.backups.create(self.f)
        got = [m["mod_id"] for m in self.backups.list_for(self.f)]
        self.assertEqual(got, [second, first])

    def test_broken_metadata_only_affects_its_own_version(self) -> None:
        good = self.backups.create(self.f)
        bad = self.backups.create(self.f)
        assert good and bad
        group, ver = bad.split(":")
        (self.root / group / ver / METADATA_NAME).write_text("{ 不是 json", encoding="utf-8")
        self.assertEqual([m["mod_id"] for m in self.backups.list_for(self.f)], [good])
        # 内容仍读得回来：元数据坏了不代表备份没了
        self.assertEqual(self.backups.read(bad), "版本一".encode())

    def test_read_returns_the_bytes_that_were_backed_up(self) -> None:
        raw = "内容 with 中文 and \r\n".encode()
        self.f.write_bytes(raw)
        mid = self.backups.create(self.f)
        assert mid is not None
        self.assertEqual(self.backups.read(mid), raw)

    def test_unknown_mod_id_is_none(self) -> None:
        for bad in ("", "没有冒号", "abc:", ":def", "abc:def:ghi", "不存在的组:不存在的版本"):
            self.assertIsNone(self.backups.meta(bad), msg=bad)
            self.assertIsNone(self.backups.read(bad), msg=bad)

    def test_create_returns_none_for_missing_file(self) -> None:
        self.assertIsNone(self.backups.create(self.base / "nope.txt"))


class PathHashTest(unittest.TestCase):
    def test_same_path_same_hash(self) -> None:
        p = Path(r"D:\some\dir\文件.md")
        self.assertEqual(path_hash(p), path_hash(Path(r"D:\some\dir\文件.md")))

    def test_different_paths_differ(self) -> None:
        self.assertNotEqual(path_hash(Path(r"D:\a\同名.md")), path_hash(Path(r"D:\b\同名.md")))

    def test_hash_is_short_hex(self) -> None:
        h = path_hash(Path(r"D:\x.md"))
        self.assertEqual(len(h), 16)
        self.assertRegex(h, r"^[0-9a-f]{16}$")


class PruneTest(unittest.TestCase):
    """按版本目录名里的日期段清理；某文件的版本清空后收掉它的哈希目录。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "file_backup"
        self.backups = FileBackups(self.root)
        self.f = Path(self._tmp.name) / "x.txt"
        self.f.write_text("v", encoding="utf-8")

    def _plant(self, days_ago: int, rand: str, path: Path | None = None) -> str:
        """造一个版本目录：`YYYYMMDD_HHMMSS_mmm_序号_随机`（格式必须与生产一致）。"""
        target = path or self.f
        day = time.strftime("%Y%m%d", time.localtime(time.time() - days_ago * 86400))
        group = self.root / path_hash(target)
        ver = f"{day}_120000_000_0000_{rand}"
        d = group / ver
        d.mkdir(parents=True, exist_ok=True)
        (d / ORIGINAL_NAME).write_bytes(b"old")
        (d / METADATA_NAME).write_text(json.dumps({
            "mod_id": f"{group.name}:{ver}", "path": str(target.resolve()),
        }), encoding="utf-8")
        return ver

    def test_prune_removes_older_than_retention(self) -> None:
        self._plant(30, "aaaa")
        self._plant(8, "bbbb")
        self._plant(2, "cccc")
        self._plant(0, "dddd")
        removed, kept = self.backups.prune(retention_days=7)
        self.assertEqual((removed, kept), (2, 2))
        left = sorted(p.name for p in (self.root / path_hash(self.f)).iterdir())
        self.assertEqual(len(left), 2)

    def test_prune_removes_the_group_once_all_versions_are_gone(self) -> None:
        self._plant(30, "aaaa")
        removed, kept = self.backups.prune(retention_days=7)
        self.assertEqual((removed, kept), (1, 0))
        self.assertFalse((self.root / path_hash(self.f)).exists())

    def test_prune_keeps_the_group_while_any_version_survives(self) -> None:
        self._plant(30, "aaaa")
        self._plant(1, "bbbb")
        self.backups.prune(retention_days=7)
        self.assertTrue((self.root / path_hash(self.f)).is_dir())

    def test_prune_leaves_unparseable_version_names(self) -> None:
        """版本名不含合法日期时不动 —— 可能是人工放进来的。"""
        group = self.root / path_hash(self.f)
        (group / "手工放的").mkdir(parents=True)
        self._plant(30, "aaaa")
        removed, kept = self.backups.prune(retention_days=7)
        self.assertEqual((removed, kept), (1, 1))
        self.assertTrue((group / "手工放的").is_dir())

    def test_prune_on_missing_root_is_noop(self) -> None:
        self.assertEqual(FileBackups(self.root / "不存在").prune(7), (0, 0))

    def test_prune_ignores_stray_files_at_the_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "readme.txt").write_text("x", encoding="utf-8")
        self._plant(30, "aaaa")
        removed, _kept = self.backups.prune(retention_days=7)
        self.assertEqual(removed, 1)
        self.assertTrue((self.root / "readme.txt").is_file())


class VersionTimeTextTest(unittest.TestCase):
    def test_reverse_parses_the_timestamp(self) -> None:
        self.assertEqual(_version_time_text("20261013_140836_454_0007_4543"), "2026-10-13 14:08:36")
        self.assertEqual(_version_time_text("20260101_000000_000_0000_abcd"), "2026-01-01 00:00:00")

    def test_returns_empty_when_format_does_not_match(self) -> None:
        for bad in ("", "no-date", "20261013_1408_454_0007_4543", "20261013_140836_4543",
                    "20261013_140836_ZZZ_0007_4543", "20261013_140836_454_4543",
                    "手工放的"):
            self.assertEqual(_version_time_text(bad), "", msg=bad)


class RecycleTest(unittest.TestCase):
    def test_move_puts_the_file_under_a_day_directory(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        recycle = Recycle(Path(tmp.name) / "rc")
        src = Path(tmp.name) / "gone.txt"
        src.write_text("bye", encoding="utf-8")
        dest = recycle.move(src)
        self.assertFalse(src.exists())
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.parent.name, time.strftime("%Y%m%d"))
        self.assertEqual(dest.read_text(encoding="utf-8"), "bye")

    def test_target_for_sanitizes_the_name(self) -> None:
        recycle = Recycle(Path("D:/rc"))
        dest = recycle.target_for(Path("D:/a/报告 带空格.md"))
        self.assertNotIn(" ", dest.name)
        self.assertTrue(dest.name.startswith("_"))


if __name__ == "__main__":
    unittest.main()
