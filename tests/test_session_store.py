# -*- coding: utf-8 -*-
"""SessionStore 加密持久化测试。"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.core.events import make_event  # noqa: E402
from agent.mechanisms.session_store import (  # noqa: E402
    MAGIC,
    SessionStore,
    is_valid_conversation_id,
    new_conversation_id,
)


class ConversationIdTest(unittest.TestCase):
    """会话 ID 校验与生成。"""

    def test_valid_and_invalid(self) -> None:

        self.assertTrue(is_valid_conversation_id("abc12345"))
        self.assertTrue(is_valid_conversation_id("A" * 128))
        for bad in ["", "short", "a" * 129, "with space", "中文标识", "x/y", "../../etc/passwd"]:
            self.assertFalse(is_valid_conversation_id(bad), bad)

    def test_new_id_is_valid(self) -> None:

        cid = new_conversation_id()
        self.assertTrue(is_valid_conversation_id(cid))
        self.assertNotEqual(cid, new_conversation_id())

class _StoreTest(unittest.TestCase):
    """公共夹具：独立临时 data_root + 合法会话 ID。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.cid = new_conversation_id()

class LayoutTest(_StoreTest):
    """落盘布局。"""

    def test_layout_single_file_per_session(self) -> None:

        store = SessionStore(self.root)
        store.append(self.cid, [make_event("turn_started")])
        path = store.raw_path(self.cid)
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, f"{self.cid}.raw")
        self.assertEqual(path.parent.name, "sessions")

class WriteReadTest(_StoreTest):
    """ / ：写入与读取语义。"""

    def test_roundtrip_plaintext(self) -> None:
        store = SessionStore(self.root)
        events = [
            make_event("turn_started", conversation_id=self.cid),
            make_event("input_claimed", content="你好"),
        ]

        self.assertEqual(store.append(self.cid, events), 2)
        lines = store.raw_path(self.cid).read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 2)

        loaded = store.load(self.cid)
        self.assertEqual([e.type for e in loaded], ["turn_started", "input_claimed"])
        self.assertEqual(loaded[1].data["content"], "你好")

    def test_append_empty_noop(self) -> None:

        store = SessionStore(self.root)
        self.assertEqual(store.append(self.cid, []), 0)
        self.assertFalse(store.raw_path(self.cid).exists())

    def test_corrupt_line_skipped(self) -> None:

        store = SessionStore(self.root, encryption="local")
        store.append(self.cid, [make_event("ok1")])
        path = store.raw_path(self.cid)
        with path.open("a", encoding="utf-8") as fh:
            fh.write("{broken json\n")
            fh.write("\n")
        store.append(self.cid, [make_event("ok2")])
        loaded = store.load(self.cid)
        self.assertEqual([e.type for e in loaded], ["ok1", "ok2"])

    def test_missing_file_returns_empty(self) -> None:

        store = SessionStore(self.root)
        self.assertEqual(store.load(self.cid), [])

    def test_invalid_utf8_bytes_tolerated(self) -> None:
        """非法 UTF-8 字节行跳过，其余事件照常读回。"""

        store = SessionStore(self.root)
        store.append(self.cid, [make_event("ok1")])
        with store.raw_path(self.cid).open("ab") as fh:
            fh.write(bytes([0xFF, 0xFE]) + b" broken" + bytes([10]))
        store.append(self.cid, [make_event("ok2")])
        loaded = store.load(self.cid)
        self.assertEqual([e.type for e in loaded], ["ok1", "ok2"])

    def test_invalid_cid_rejected(self) -> None:
        store = SessionStore(self.root)
        with self.assertRaises(ValueError):
            store.append("../../evil", [make_event("x")])
        with self.assertRaises(ValueError):
            store.load("short")

class CryptoTest(_StoreTest):
    """加密 envelope / 模式 / 算法 / 密钥。"""

    def test_roundtrip_local_encrypted(self) -> None:
        store = SessionStore(self.root, encryption="local")
        content = "秘密内容\n第二行"
        store.append(self.cid, [make_event("model_message", content=content)])
        raw = store.raw_path(self.cid).read_text(encoding="utf-8")

        self.assertIn(MAGIC, raw)
        self.assertNotIn("秘密内容", raw)
        loaded = store.load(self.cid)
        self.assertEqual(loaded[0].data["content"], content)

    def test_mixed_plain_and_encrypted(self) -> None:

        plain = SessionStore(self.root)
        plain.append(self.cid, [make_event("plain")])
        encrypted = SessionStore(self.root, encryption="local")
        encrypted.append(self.cid, [make_event("enc")])
        loaded = encrypted.load(self.cid)
        self.assertEqual([e.type for e in loaded], ["plain", "enc"])

    def test_tamper_detected(self) -> None:

        store = SessionStore(self.root, encryption="local")
        store.append(self.cid, [make_event("secret", v=1)])
        path = store.raw_path(self.cid)
        obj = json.loads(path.read_text(encoding="utf-8").strip())
        data = str(obj["data"])
        obj["data"] = ("A" if data[0] != "A" else "B") + data[1:]
        path.write_text(json.dumps(obj, separators=(",", ":")) + "\n", encoding="utf-8")
        self.assertEqual(store.load(self.cid), [])

    def test_unknown_mode_falls_back_none(self) -> None:

        store = SessionStore(self.root, encryption="weird")
        self.assertEqual(store.encryption, "none")
        store.append(self.cid, [make_event("plain")])
        raw = store.raw_path(self.cid).read_text(encoding="utf-8")
        self.assertNotIn(MAGIC, raw)

    def test_key_reuse_across_instances(self) -> None:

        first = SessionStore(self.root, encryption="local")
        first.append(self.cid, [make_event("a", v=1)])
        self.assertTrue((self.root / "cache" / "session_encryption.key").is_file())
        second = SessionStore(self.root, encryption="local")  # 模拟重启
        loaded = second.load(self.cid)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].type, "a")

    def test_concurrent_key_init(self) -> None:
        """并发首用（多线程多实例）不双建密钥；各文件均可解密。"""

        stores = [SessionStore(self.root, encryption="local") for _ in range(4)]
        cids = [new_conversation_id() for _ in stores]
        errors: list[str] = []
        barrier = threading.Barrier(len(stores))

        def work(store: SessionStore, cid: str) -> None:
            try:
                barrier.wait(timeout=5)
                store.append(cid, [make_event("evt", cid=cid)])
            except Exception as exc:  # 记录而非中断（测试用具）
                errors.append(repr(exc))

        threads = [
            threading.Thread(target=work, args=(store, cid))
            for store, cid in zip(stores, cids)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(errors, [])
        key_files = list((self.root / "cache").glob("session_encryption.key"))
        self.assertEqual(len(key_files), 1)
        reader = SessionStore(self.root, encryption="local")
        for cid in cids:
            loaded = reader.load(cid)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].data["cid"], cid)

class CrossProcessAppendTest(_StoreTest):
    """**多进程**并发写同一个 `.raw` 不得丢行、不得写坏。

    进程内锁挡不住别的进程：4 个进程并发写会丢行且**不报错**。
    因此写路径按文件串行（`agent/mechanisms/session_store.py` 的 `_cross_process_lock`
    用 `msvcrt` 文件锁实现）。

    为什么必须用**真子进程**：进程内锁在同一个解释器里怎么测都"正确"，
    只有真起多进程才走得到 `LK_NBLCK` 那条路径。所以这里用 `subprocess`，
    每个子进程独立 `SessionStore` 实例、独立打开同一个文件。
    """

    #: 每个子进程写多少条（4 进程 × 25 = 100 条）
    PER_PROC = 25
    PROCS = 4

    def _run_workers(self, script: Path, n: int) -> tuple[list[str], list[int]]:
        """同时起 n 个真子进程跑同一个脚本；返回 (失败说明, 退出码列表)。"""
        import os
        import subprocess

        env = dict(os.environ)
        env["AI_AGENT_DATA_ROOT"] = str(self.root)
        # 无控制台的运行环境（Windows 服务 / 计划任务 / `pythonw`）里子进程报错更隐蔽，
        # 这里显式加 CREATE_NO_WINDOW，让两种跑法都能复现同一路径。
        # POSIX 上 creationflags 没有对应项，用 start_new_session 取得同等隔离。
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        procs = [
            subprocess.Popen(
                [sys.executable, str(script), str(self.root), self.cid, str(self.PER_PROC), str(i)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                creationflags=flags, start_new_session=(os.name != "nt"),
            )
            for i in range(n)
        ]
        fails: list[str] = []
        codes: list[int] = []
        for p in procs:
            try:
                _out, err = p.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                p.kill()
                fails.append("子进程超时未退出（多半卡在跨进程锁上）")
                codes.append(-1)
                continue
            codes.append(p.returncode)
            if p.returncode != 0:
                fails.append((err or b"").decode("utf-8", "replace")[-500:])
        return fails, codes

    def test_concurrent_appends_lose_nothing(self) -> None:
        """4 进程 × 25 条并发写同一会话 → 100 条全在，且每行都是合法 JSON。"""
        script = self.root / "_worker.py"
        script.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "root, cid, per, idx = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]\n"
            "sys.path.insert(0, sys.argv[0] and r'" + str(_ROOT) + "')\n"
            "from agent.core.events import make_event\n"
            "from agent.mechanisms.session_store import SessionStore\n"
            "store = SessionStore(Path(root))\n"
            "for i in range(per):\n"
            "    store.append(cid, [make_event('evt', cid=cid, who=idx, n=i)])\n",
            encoding="utf-8",
        )
        fails, codes = self._run_workers(script, self.PROCS)
        self.assertEqual(fails, [], f"子进程失败：{fails}")
        self.assertEqual(codes, [0] * self.PROCS, f"退出码：{codes}")

        raw = SessionStore(self.root).raw_path(self.cid)
        lines = [ln for ln in raw.read_text(encoding="utf-8").split("\n") if ln.strip()]
        self.assertEqual(
            len(lines), self.PROCS * self.PER_PROC,
            f"丢行了：期望 {self.PROCS * self.PER_PROC} 行、实得 {len(lines)} 行"
            "（跨进程锁失效的典型症状就是静默少行）",
        )
        for i, ln in enumerate(lines, 1):
            try:
                obj = json.loads(ln)
            except json.JSONDecodeError as exc:
                self.fail(f"第 {i} 行不是合法 JSON（写坏了）：{exc}；内容={ln[:200]!r}")
            self.assertIsInstance(obj, dict)

    def test_concurrent_appends_all_visible_after_load(self) -> None:
        """读回来也要是 100 条 —— 行数够但解析丢片同样是数据丢失。"""
        script = self.root / "_worker2.py"
        script.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "root, cid, per, idx = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]\n"
            "sys.path.insert(0, sys.argv[0] and r'" + str(_ROOT) + "')\n"
            "from agent.core.events import make_event\n"
            "from agent.mechanisms.session_store import SessionStore\n"
            "store = SessionStore(Path(root))\n"
            "store.append(cid, [make_event('evt', cid=cid, who=idx, n=i)] for i in range(per))\n",
            encoding="utf-8",
        )
        # 上一个脚本是"逐条 append"，这个是"一次 append 多条"，两条路径都要过。
        script.write_text(
            script.read_text(encoding="utf-8").replace(
                "store.append(cid, [make_event('evt', cid=cid, who=idx, n=i)] for i in range(per))\n",
                "events = [make_event('evt', cid=cid, who=idx, n=i) for i in range(per)]\n"
                "store.append(cid, events)\n",
            ),
            encoding="utf-8",
        )
        fails, codes = self._run_workers(script, self.PROCS)
        self.assertEqual(fails, [], f"子进程失败：{fails}")
        self.assertEqual(codes, [0] * self.PROCS, f"退出码：{codes}")

        loaded = SessionStore(self.root).load(self.cid)
        self.assertEqual(len(loaded), self.PROCS * self.PER_PROC,
                         f"读回 {len(loaded)} 条，期望 {self.PROCS * self.PER_PROC} 条")
        seen = {(e.data.get("who"), e.data.get("n")) for e in loaded}
        self.assertEqual(len(seen), self.PROCS * self.PER_PROC,
                         "有条目重复或缺失（写串了）")

if __name__ == "__main__":
    unittest.main()
