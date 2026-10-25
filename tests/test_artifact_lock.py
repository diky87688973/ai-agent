# -*- coding: utf-8 -*-
"""产物锁与覆盖率发布：同一份共享文件被并行写时必须串行或明确跳过。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import artifact_lock as locks  # noqa: E402
import check_coverage  # noqa: E402
import run_coverage  # noqa: E402

#: 一定不存在的进程号：用来模拟"持锁进程已被强杀"
DEAD_PID = 0x7FFFFFFF


def _write_holder(lock: locks.ArtifactLock, pid: int, token: str = "t",
                  purpose: str = "crashed") -> None:
    lock.path.mkdir(parents=True, exist_ok=True)
    payload = {"pid": pid, "purpose": purpose, "since": time.time(), "token": token}
    (lock.path / locks.HOLDER_FILE).write_text(
        json.dumps(payload), encoding="utf-8")


class ArtifactLockTest(unittest.TestCase):
    """锁的互斥、回收与释放语义。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _lock(self, name: str = "coverage", purpose: str = "") -> locks.ArtifactLock:
        lock = locks.ArtifactLock(self.root, name, purpose=purpose)
        self.addCleanup(lock.release)
        return lock

    def test_acquire_records_holder(self) -> None:
        lock = self._lock(purpose="first")
        lock.acquire()
        payload = json.loads((lock.path / locks.HOLDER_FILE).read_text(encoding="utf-8"))
        self.assertEqual(payload["pid"], os.getpid())
        self.assertEqual(payload["purpose"], "first")
        self.assertTrue(payload["token"])

    def test_second_owner_is_rejected_with_holder_info(self) -> None:
        first = self._lock(purpose="first")
        first.acquire()
        with self.assertRaises(locks.LockBusy) as ctx:
            locks.ArtifactLock(self.root, "coverage").acquire()
        self.assertEqual(ctx.exception.holder.pid, os.getpid())
        self.assertIn(f"pid={os.getpid()}", str(ctx.exception))

    def test_release_frees_lock_for_next_owner(self) -> None:
        first = self._lock(purpose="first")
        first.acquire()
        first.release()
        self.assertFalse(first.path.exists())
        second = self._lock(purpose="second")
        second.acquire()
        self.assertTrue(second.held)

    def test_release_is_idempotent(self) -> None:
        lock = self._lock()
        lock.acquire()
        lock.release()
        lock.release()
        self.assertFalse(lock.held)

    def test_holder_with_dead_pid_is_reclaimed(self) -> None:
        lock = self._lock()
        _write_holder(lock, DEAD_PID)
        lock.acquire()
        self.assertTrue(lock.held)

    def test_half_written_lock_holds_until_grace_period(self) -> None:
        lock = self._lock()
        lock.path.mkdir(parents=True)
        with self.assertRaises(locks.LockBusy):
            lock.acquire()

    def test_half_written_lock_is_reclaimed_after_grace_period(self) -> None:
        lock = self._lock()
        lock.path.mkdir(parents=True)
        old = time.time() - locks.WRITE_GRACE_S - 1.0
        os.utime(lock.path, (old, old))
        lock.acquire()
        self.assertTrue(lock.held)

    def test_force_breaks_live_holder(self) -> None:
        first = self._lock(purpose="first")
        first.acquire()
        first_token = first.holder.token if first.holder else ""
        second = self._lock(purpose="second")
        second.acquire(force=True)
        payload = json.loads((second.path / locks.HOLDER_FILE).read_text(encoding="utf-8"))
        self.assertEqual(payload["purpose"], "second")
        self.assertNotEqual(payload["token"], first_token)

    def test_wait_succeeds_after_holder_releases(self) -> None:
        first = self._lock(purpose="first")
        first.acquire()

        def release_later() -> None:
            time.sleep(0.2)
            first.release()

        thread = threading.Thread(target=release_later)
        thread.start()
        self.addCleanup(thread.join)
        second = self._lock(purpose="second")
        second.acquire(wait_s=3.0, poll_s=0.02)
        self.assertTrue(second.held)

    def test_release_keeps_foreign_lock(self) -> None:
        lock = self._lock()
        lock.acquire()
        _write_holder(lock, os.getpid(), token="another-owner")
        lock.release()
        self.assertTrue(lock.path.exists())

    def test_parse_holder_rejects_garbage(self) -> None:
        self.assertIsNone(locks.parse_holder("not json"))
        self.assertIsNone(locks.parse_holder("{}"))
        self.assertIsNone(locks.parse_holder('{"pid": 0}'))
        self.assertIsNotNone(locks.parse_holder('{"pid": 12}'))


class CoveragePublishTest(unittest.TestCase):
    """覆盖率数据先落独立文件再发布，读侧不会读到半份数据。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_build_command_writes_unique_data_file(self) -> None:
        cmd = run_coverage.build_command(Path(".coverage.tmp.4242"))
        self.assertIn("--data-file=.coverage.tmp.4242", cmd)
        self.assertIn("unittest", cmd)
        self.assertIn("discover", cmd)
        self.assertNotIn(".coverage", cmd)

    def test_publish_replaces_target(self) -> None:
        tmp = self.root / ".coverage.tmp.1"
        tmp.write_bytes(b"new")
        target = self.root / ".coverage"
        target.write_bytes(b"old")
        run_coverage.publish(tmp, target, root=self.root)
        self.assertEqual(target.read_bytes(), b"new")
        self.assertFalse(tmp.exists())


class CoverageBusyTest(unittest.TestCase):
    """有写者持锁时，覆盖率校验必须跳过而不是拿半份数据判失败。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_check_locked_skips_when_data_changes_during_measure(self) -> None:
        data = self.root / ".coverage"
        data.write_bytes(b"x")

        def fake_measure(path: Path) -> dict:
            path.write_bytes(b"yy")
            return {"agent/core": (10, 0)}

        with mock.patch.object(check_coverage, "measure", fake_measure), \
                redirect_stdout(StringIO()):
            self.assertEqual(check_coverage._check_locked(data), 2)

    def test_main_skips_when_writer_holds_lock(self) -> None:
        holder = locks.ArtifactLock(self.root, "coverage", purpose="writer")
        holder.acquire()
        self.addCleanup(holder.release)
        with mock.patch.object(check_coverage, "ROOT", self.root), \
                mock.patch.object(check_coverage, "LOCK_WAIT_S", 0.0), \
                redirect_stdout(StringIO()):
            self.assertEqual(check_coverage.main(), 2)

    def test_stamp_is_none_for_missing_file(self) -> None:
        self.assertIsNone(check_coverage.stamp(self.root / "absent"))


if __name__ == "__main__":
    unittest.main()
