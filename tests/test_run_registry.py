# -*- coding: utf-8 -*-
"""`RunRegistry` 的回归测试：运行态登记必须"可跨进程查、崩溃自愈、抽干不留空窗"。

两条硬约束：
① 登记必须跨进程可见——放在进程内存字典里，多实例部署会把别的实例正在跑的
   回合报成"没在跑"；
② 抽干链不得露出空闲窗口——`release → pop → claim` 的中间态会让另一次投递
   再激活一趟，同一个回合被执行两遍。
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path

from agent.mechanisms.mesh import MeshState
from agent.mechanisms.run_registry import (
    FileRunRegistry,
    InMemoryRunRegistry,
    build_run_registry,
)

CID = "aaaabbbbccccdddd"


class InMemoryRunRegistryTest(unittest.TestCase):
    """纯内存实现：单实例语义。"""

    def test_claim_release_renew(self) -> None:
        reg = InMemoryRunRegistry()
        self.assertTrue(reg.claim(CID, "r1"))
        self.assertFalse(reg.claim(CID, "r2"), "已占位时不能再占（这是「忙」的判据）")
        self.assertTrue(reg.running(CID))
        self.assertEqual(reg.active_run_id(CID), "r1")
        # renew：换 id 但不释放（抽干下一条时用）
        self.assertTrue(reg.renew(CID, "r2"))
        self.assertEqual(reg.active_run_id(CID), "r2")
        self.assertTrue(reg.running(CID), "renew 不得释放占位")
        reg.release(CID)
        self.assertFalse(reg.running(CID))
        self.assertFalse(reg.renew(CID, "r3"), "没占位时 renew 不该凭空占")
        reg.release(CID)          # 幂等
        self.assertEqual(reg.running_cids(), [])

    def test_running_cids_snapshot(self) -> None:
        reg = InMemoryRunRegistry()
        reg.claim("aaaa1111", "r1")
        reg.claim("bbbb2222", "r2")
        self.assertEqual(reg.running_cids(), ["aaaa1111", "bbbb2222"])


class FileRunRegistryTest(unittest.TestCase):
    """落盘实现：跨实例可见 + 崩溃自愈。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "runs"

    def test_state_is_visible_across_instances(self) -> None:
        """核心诉求：另一个实例（另一个 registry 对象）能看到"在跑"。"""
        a = FileRunRegistry(self.dir)
        b = FileRunRegistry(self.dir)
        self.assertFalse(b.running(CID))
        self.assertTrue(a.claim(CID, "r1"))
        self.assertTrue(b.running(CID), "跨实例必须可见 —— 否则多实例下会给错答案")
        self.assertIn(CID, b.running_cids())
        self.assertFalse(b.claim(CID, "r2"), "另一个实例也应看到「忙」")
        a.release(CID)
        self.assertFalse(b.running(CID))

    def test_stale_entry_self_heals(self) -> None:
        """崩溃残留（进程被 kill，心跳停）：超过存活期后应被判为过期并清掉。"""
        reg = FileRunRegistry(self.dir, ttl_seconds=0.05)
        self.assertTrue(reg.claim(CID, "r1"))
        self.assertTrue(reg.running(CID))
        time.sleep(0.12)
        self.assertFalse(reg.running(CID), "过期条目不得再算作在跑")
        self.assertFalse((self.dir / f"{CID}.json").is_file(), "过期条目应被清理")
        self.assertTrue(reg.claim(CID, "r2"), "清掉之后应能重新占位")

    def test_touch_keeps_long_run_alive(self) -> None:
        """长任务靠续心跳保活（否则 120 秒的 ping 会被误判成已结束）。"""
        reg = FileRunRegistry(self.dir, ttl_seconds=0.3)
        self.assertTrue(reg.claim(CID, "r1"))
        for _ in range(4):
            time.sleep(0.12)
            self.assertTrue(reg.running(CID), "有心跳就不该过期")
        self.assertFalse(reg.running("ffff0000"), "没占位的会话当然不在跑")

    def test_broken_file_is_treated_as_not_running(self) -> None:
        """坏文件不能让读取方崩，也不能把垃圾当成"在跑"。"""
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{CID}.json").write_text("{ 不是合法 JSON", encoding="utf-8")
        reg = FileRunRegistry(self.dir)
        self.assertFalse(reg.running(CID))
        self.assertFalse((self.dir / f"{CID}.json").is_file(), "坏文件应被清掉")

    def test_build_switches_implementation_by_directory(self) -> None:
        self.assertIsInstance(build_run_registry(None), InMemoryRunRegistry)
        self.assertIsInstance(build_run_registry(self.dir), FileRunRegistry)


class DrainWindowTest(unittest.TestCase):
    """抽干链不得露出空闲窗口：`end_run` 返回下一条时必须已占位。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.mesh = MeshState(storage_dir=Path(self._tmp.name) / "mesh")

    def test_drain_never_exposes_idle_window(self) -> None:
        """`end_run` 返回下一条时，占位必须一次都没松过。

        做法：在 `end_run` 执行期间，从另一个线程反复问 `is_running` ——
        只有全程不释放（`renew`）才会从头到尾都是 True；`release → pop → claim`
        会在中间被观察到 False。
        """
        self.assertTrue(self.mesh.try_begin_run(CID))
        self.mesh.submit(CID, {"content": "第二条"})     # 入队，等抽干

        seen: list = []
        stop = threading.Event()

        def poll() -> None:
            while not stop.is_set():
                seen.append(self.mesh.is_running(CID))

        watcher = threading.Thread(target=poll, daemon=True)
        watcher.start()
        try:
            nxt = self.mesh.end_run(CID)
        finally:
            stop.set()
            watcher.join(timeout=2)

        self.assertEqual((nxt or {}).get("content"), "第二条")
        self.assertTrue(self.mesh.is_running(CID), "抽干后应仍占位（下一条正在跑）")
        self.assertTrue(seen, "观察线程应采到样本")
        self.assertNotIn(False, seen,
                         "抽干期间露出了空闲窗口 —— 别的投递会据此再激活一趟，"
                         "导致同一个回合被执行两遍")

    def test_drain_then_release(self) -> None:
        """队列空时才释放。"""
        self.assertTrue(self.mesh.try_begin_run(CID))
        self.assertIsNone(self.mesh.end_run(CID))
        self.assertFalse(self.mesh.is_running(CID))


if __name__ == "__main__":
    unittest.main()


class PidAliveTest(unittest.TestCase):
    """`_pid_alive` 的判活边界。

    判活必须覆盖无控制台的进程（Windows 服务 / 计划任务 / `pythonw` /
    分离启动）：这条路径上 `os.kill(pid, 0)` 对活着的进程也会抛
    `OSError [WinError 87]`，所以探活不能以 `OSError` 判定死亡 ——
    判死的后果是 `claim()` 成功之后 `running()` 立刻返回 False，
    同会话并发保护（`/api/chat/send` 的 409）与界面停止键同时失效。

    实现按此约定：Windows 走 `OpenProcess`（不需要控制台），其它错误一律按"活着"处理。
    本组用例不依赖控制台，所以在有/无控制台两种跑法下都应通过。
    """

    def test_live_pid_is_alive(self) -> None:
        """当前进程的 pid 必须判活 —— 这是最直接的判据。"""
        self.assertTrue(FileRunRegistry._pid_alive(os.getpid()))

    def test_nonexistent_pid_is_dead(self) -> None:
        """不存在的 pid 必须判死，否则过期记录永远不回收。"""
        self.assertFalse(FileRunRegistry._pid_alive(999999))

    def test_invalid_pid_forms_are_dead(self) -> None:
        """非法形态不抛异常，一律判死（None / 0 / 负数 / 非数字）。"""
        for bad in (None, 0, -1, "abc", "", object()):
            self.assertFalse(FileRunRegistry._pid_alive(bad), f"{bad!r} 应判死")

    def test_claim_then_running_is_true_in_this_process(self) -> None:
        """`claim()` 之后 `running()` 必须为 True（记录里写的是本进程 pid）。"""
        with tempfile.TemporaryDirectory() as d:
            reg = FileRunRegistry(Path(d))
            rid = reg.claim(CID, "r-pid")
            self.assertTrue(rid)
            self.assertTrue(reg.running(CID),
                            "占位后立刻判为不在跑 —— 并发保护失效（见类 docstring）")
            self.assertIn(CID, reg.running_cids())
