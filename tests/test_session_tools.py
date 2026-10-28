# -*- coding: utf-8 -*-
"""会话协作工具测试。

覆盖：mesh 注册表 / 待发送队列 / 原子投递与持久化容错、会话创建与命名、点对点发送
（包装 / 身份 / 校验 / 排队与直启）、多播与广播信封、运行器端到端（触发执行 + 队列抽干）。
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.model_call import StreamDelta  # noqa: E402
from agent.core.tool_call import ToolCallRequest  # noqa: E402
from agent.mechanisms.mesh import MeshState  # noqa: E402
from tests.testkit import no_plugins  # noqa: E402

CID_A = "senderagent1"
CID_B = "targetagent1"
CID_C = "targetagent2"

class _ProbeProvider:
    """记录请求消息的假模型；首个请求可挂起（制造"忙"窗口）。"""

    def __init__(self, gate_first: bool = False) -> None:
        self.seen = []
        self.gate = threading.Event()
        self._gate_first = gate_first
        self._count = 0
        self._lock = threading.Lock()

    def stream(self, request):
        with self._lock:
            self.seen.append([dict(m) for m in request.messages])
            self._count += 1
            idx = self._count
        if self._gate_first and idx == 1:
            self.gate.wait(timeout=10)
        yield StreamDelta(kind="text", text=f"ack-{idx}")

class _MeshBase(unittest.TestCase):
    """公共夹具：临时目录 + 独立 mesh + 装配 app；默认关闭激活器（信封类测试确定性）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.mesh = MeshState(storage_dir=self.root / "mesh")
        self.app = build_app(mesh=self.mesh)
        self.mesh.set_activator(None)
        self._seq = 0

    def _call(self, name, arguments=None, cid=CID_A):
        self._seq += 1
        call = ToolCallRequest(call_id=f"c{self._seq}", name=name, arguments=arguments or {})
        ctx = SimpleNamespace(conversation_id=cid) if cid else None
        return self.app.pipeline.execute(self.app.registry, call, ctx)

    def _register(self, cid, name="成员", role="QA", tags=None):
        self.mesh.upsert_agent(cid, name=name, role=role, tags=list(tags or ["grp"]), status="idle")

class MeshCoreTest(_MeshBase):
    def test_upsert_get_list_roundtrip(self):

        meta = self.mesh.upsert_agent(CID_B, name="小B", role="QA", tags=["grp"])
        self.assertEqual(meta["cid"], CID_B)
        again = self.mesh.upsert_agent(CID_B, name="小B2")
        self.assertEqual(again["name"], "小B2")
        self.assertEqual(again["role"], "QA")  # None 不覆盖
        self.assertEqual(len(self.mesh.list_agents()), 1)
        self.assertEqual(self.mesh.get_agent("nobody0000"), {})

    def test_queue_fifo_and_size(self):

        self.assertEqual(self.mesh.queue_size(CID_B), 0)
        self.mesh.queue.enqueue(CID_B, content="m1")
        self.mesh.queue.enqueue(CID_B, content="m2")
        self.assertEqual(self.mesh.queue_size(CID_B), 2)
        first = self.mesh.queue.claim_after_turn(CID_B)
        second = self.mesh.queue.claim_after_turn(CID_B)
        self.assertEqual(first["content"], "m1")
        self.assertEqual(second["content"], "m2")
        self.mesh.queue.complete(CID_B, first["id"])
        self.mesh.queue.complete(CID_B, second["id"])
        self.assertIsNone(self.mesh.queue.claim_after_turn(CID_B))

    def test_submit_paths(self):

        r1 = self.mesh.submit(CID_B, {"content": "x"})  # 无激活器 → 排队
        self.assertTrue(r1["queued"] and r1["queued_count"] == 1 and r1["run_id"] == "")
        claimed = self.mesh.queue.claim_after_turn(CID_B)
        self.mesh.queue.complete(CID_B, claimed["id"])
        self.mesh.set_activator(lambda cid, msg: "run-1")
        r2 = self.mesh.submit(CID_B, {"content": "y"})  # 闲 → 启动
        self.assertFalse(r2["queued"])
        self.assertEqual(r2["run_id"], "run-1")
        self.assertTrue(self.mesh.try_begin_run(CID_B))  # 模拟忙
        r3 = self.mesh.submit(CID_B, {"content": "z"})  # 忙 → 排队
        self.assertTrue(r3["queued"] and r3["queued_count"] == 1)
        self.mesh.abort_run(CID_B)
        self.mesh.set_activator(lambda cid, msg: "")  # 竞争失败 → 回退排队
        r4 = self.mesh.submit(CID_B, {"content": "w"})
        self.assertTrue(r4["queued"] and r4["queued_count"] == 2)

    def test_renew_run_keeps_claim(self):

        self.mesh.set_activator(lambda cid, msg: "run-x")
        self.assertTrue(self.mesh.try_begin_run(CID_B))
        self.assertTrue(self.mesh.renew_run(CID_B))
        self.assertTrue(self.mesh.is_running(CID_B))
        self.mesh.end_run(CID_B)
        self.assertFalse(self.mesh.is_running(CID_B))

    def test_agents_persistence_roundtrip(self):

        self._register(CID_B, name="小B", tags=["grp"])
        again = MeshState(storage_dir=self.root / "mesh")
        self.assertEqual(again.get_agent(CID_B)["name"], "小B")
        d = self.root / "mesh"
        (d / "agents.json").write_text("{ bad json", encoding="utf-8")
        m2 = MeshState(storage_dir=d)
        self.assertEqual(m2.get_agent(CID_C), {})

    def test_session_exists_registry_and_callback(self):

        self.assertFalse(self.mesh.session_exists(CID_B))
        self._register(CID_B)
        self.assertTrue(self.mesh.session_exists(CID_B))
        self.mesh.set_session_exists(lambda cid: cid == CID_C)
        self.assertTrue(self.mesh.session_exists(CID_C))
        self.assertFalse(self.mesh.session_exists("nope0001"))

class CreateListTest(_MeshBase):
    def test_create_single_and_meta(self):

        r = self._call("session_create", {})
        self.assertTrue(r.ok)
        self.assertEqual(r.data["count"], 1)
        agent = r.data["agents"][0]
        self.assertEqual(agent["name"], "Agent")
        self.assertEqual(agent["role"], "Agent")
        self.assertIn("【Agent 身份】", r.data["meta"]["system"])
        self.assertEqual(r.data["meta"]["status"], "idle")
        self.assertEqual(r.data["cid"], agent["cid"])  # 首条展开

    def test_create_alias_name_persona_tags(self):

        r = self._call("session_create", {"role": "worker", "name": "小甲", "persona": "只做测试", "tags": "a，b"})
        agent = r.data["agents"][0]
        self.assertEqual(agent["role"], "全栈开发")
        self.assertEqual(agent["name"], "小甲")
        self.assertEqual(agent["tags"], ["a", "b"])
        self.assertEqual(r.data["meta"]["persona"], "只做测试")
        r2 = self._call("session_create", {"role": "qa"})
        self.assertEqual(r2.data["agents"][0]["role"], "QA")

    def test_create_batch_count_and_prefix(self):

        r = self._call("session_create", {"count": 3, "name": "工"})
        self.assertEqual([a["name"] for a in r.data["agents"]], ["工1", "工2", "工3"])
        self.assertEqual(len({a["cid"] for a in r.data["agents"]}), 3)
        r2 = self._call("session_create", {"count": 2})
        self.assertEqual([a["name"] for a in r2.data["agents"]], ["Agent", "Agent2"])
        self.assertEqual(self._call("session_create", {"count": 0}).data["count"], 1)
        self.assertEqual(self._call("session_create", {"count": "x"}).data["count"], 1)

    def test_list_status_and_sort(self):

        self._register(CID_C, name="小B", role="QA", tags=["grp"])
        self._register(CID_B, name="小A", role="全栈开发", tags=["grp"])
        r = self._call("session_list", {})
        self.assertTrue(r.ok)
        self.assertEqual([a["name"] for a in r.data["agents"]], ["小A", "小B"])
        self.assertEqual(r.data["agents"][0]["status"], "idle")
        self.assertEqual(r.data["agents"][0]["queueSize"], 0)
        self.mesh.queue.enqueue(CID_B, content="x")
        row = [a for a in self._call("session_list", {}).data["agents"] if a["cid"] == CID_B][0]
        self.assertEqual(row["status"], "queued")
        self.assertTrue(self.mesh.try_begin_run(CID_B))
        row2 = [a for a in self._call("session_list", {}).data["agents"] if a["cid"] == CID_B][0]
        self.assertEqual(row2["status"], "running")

class SendTest(_MeshBase):
    def test_send_queued_envelope_and_wrap(self):

        self._register(CID_B, name="小B")
        r = self._call("session_send", {"target_id": CID_B, "message": "你好呀", "requires_reply": True})
        self.assertTrue(r.ok)
        self.assertTrue(r.data["queued"])
        self.assertEqual(r.data["queued_count"], 1)
        self.assertEqual(r.data["message_sent"], "你好呀")
        self.assertEqual(r.data["_sender"]["_sender"], CID_A)
        self.assertEqual(r.data["_sender"]["_sender_name"], CID_A[:12])  # 未注册发送方 → 缺省
        self.assertEqual(r.data["_sender"]["_sender_role"], "agent")
        msg = self.mesh.queue.claim_after_turn(CID_B)
        self.assertTrue(msg["content"].startswith(f"[from={CID_A[:12]} | sender_cid={CID_A} | thread_id=auto-{CID_A[:8]}-"))
        self.assertIn("channel=direct", msg["content"])
        self.assertIn("requires_reply=true", msg["content"])
        self.assertTrue(msg["content"].endswith("你好呀"))
        self.assertTrue(msg["payload"]["_agent_peer_message"])
        self.assertEqual(msg["sender"]["cid"], CID_A)
        self.assertTrue(msg["sender"]["requires_reply"])
        self.assertTrue(msg["sender"]["thread_id"].startswith(f"auto-{CID_A[:8]}-"))

    def test_send_sender_identity_from_registry(self):

        self._register(CID_A, name="小A", role="全栈开发")
        self._register(CID_B)
        r = self._call("session_send", {"target_id": CID_B, "message": "hi", "requires_reply": False})
        self.assertTrue(r.ok)
        msg = self.mesh.queue.claim_after_turn(CID_B)
        self.assertTrue(msg["content"].startswith("[from=小A | "))
        self.assertNotIn("requires_reply=true", msg["content"])
        self.assertEqual(msg["sender"]["name"], "小A")
        self.assertFalse(msg["sender"]["requires_reply"])

    def test_send_custom_thread_and_channel(self):

        self._register(CID_B)
        self._call("session_send", {"target_id": CID_B, "message": "x", "requires_reply": False, "thread_id": "t-1", "channel": "group"})
        msg = self.mesh.queue.claim_after_turn(CID_B)
        self.assertEqual(msg["sender"]["thread_id"], "t-1")
        self.assertIn("thread_id=t-1", msg["content"])
        self.assertEqual(msg["payload"]["_channel"], "group")

    def test_send_validations(self):

        self._register(CID_B)
        cases = [
            ({"message": "x", "requires_reply": True}, "missing_target"),
            ({"target_id": CID_B, "requires_reply": True}, "missing_message"),
            ({"target_id": CID_B, "message": "x"}, "missing_requires_reply"),
            ({"target_id": "ghost0000000", "message": "x", "requires_reply": True}, "target_not_found"),
        ]
        for args, token in cases:
            r = self._call("session_send", args)
            self.assertFalse(r.ok, msg=token)
            self.assertIn(token, r.error)
        r = self._call("session_send", {"target_id": CID_B, "message": "x", "requires_reply": True}, cid=None)
        self.assertFalse(r.ok)
        self.assertIn("missing_conversation", r.error)

class MultisendBroadcastTest(_MeshBase):
    def test_multisend_partial_and_all_failed(self):

        self._register(CID_B)
        self._register(CID_C)
        r = self._call("session_multisend", {"target_ids": [CID_B, CID_C], "message": "大家好", "requires_reply": False})
        self.assertTrue(r.ok)
        self.assertEqual(r.data["count"], 2)
        self.assertFalse(r.data["partial"])
        self.assertTrue(r.data["all_sent"])
        self.assertEqual([s["target_id"] for s in r.data["sent"]], [CID_B, CID_C])
        self.assertEqual(self.mesh.queue_size(CID_B), 1)
        self.assertEqual(self.mesh.queue_size(CID_C), 1)
        r2 = self._call("session_multisend", {"target_ids": f"{CID_B}，ghost0000000", "message": "x", "requires_reply": True})
        self.assertTrue(r2.ok)
        self.assertTrue(r2.data["partial"])
        self.assertEqual(r2.data["count"], 1)
        self.assertIn("target_not_found", r2.data["skipped"][0]["error"])
        r3 = self._call("session_multisend", {"target_ids": ["ghost0000000", "ghost0000001"], "message": "x", "requires_reply": True})
        self.assertFalse(r3.ok)
        self.assertIn("all_targets_failed", r3.error)
        self.assertEqual(r3.data["count"], 0)
        self.assertEqual(len(r3.data["skipped"]), 2)

    def test_broadcast_filters_and_envelope(self):

        self._register(CID_B, name="小B", role="QA", tags=["grp"])
        self._register(CID_C, name="小C", role="全栈开发", tags=["grp"])
        self._register(CID_A, name="小A", role="QA", tags=["grp"])
        r = self._call("session_broadcast", {"tag": "grp", "message": "通知", "requires_reply": True})
        self.assertTrue(r.ok)
        self.assertEqual(r.data["count"], 2)  # exclude_self 默认排除小A
        self.assertEqual(sorted(r.data["sent"]), sorted([CID_B, CID_C]))
        r2 = self._call("session_broadcast", {"tag": "grp", "role": "QA", "message": "x", "requires_reply": False, "exclude_self": False})
        self.assertEqual(sorted(r2.data["sent"]), sorted([CID_A, CID_B]))
        r3 = self._call("session_broadcast", {"tag": "none", "message": "x", "requires_reply": False})
        self.assertFalse(r3.ok)
        self.assertIn("all_targets_failed", r3.error)
        r4 = self._call("session_broadcast", {"message": "x", "requires_reply": False})
        self.assertFalse(r4.ok)
        self.assertIn("missing_tag", r4.error)
        r5 = self._call("session_broadcast", {"tag": "grp", "message": "x"})
        self.assertFalse(r5.ok)
        self.assertIn("missing_requires_reply", r5.error)

class RunnerE2ETest(unittest.TestCase):
    """运行器端到端：触发执行、系统提示注入、队列抽干。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.mesh = MeshState(storage_dir=self.root / "mesh")
        self.provider = _ProbeProvider(gate_first=True)
        self.addCleanup(self.provider.gate.set)  # 兜底放行，防线程悬挂
        # 不装插件：本类验的是运行器与 mesh，插件目录会把注入源与模型路由换掉。
        no_plugins(self)
        self.app = build_app(provider=self.provider, mesh=self.mesh)
        self._seq = 0

    def _call(self, name, arguments=None, cid=CID_A):
        self._seq += 1
        call = ToolCallRequest(call_id=f"c{self._seq}", name=name, arguments=arguments or {})
        ctx = SimpleNamespace(conversation_id=cid) if cid else None
        return self.app.pipeline.execute(self.app.registry, call, ctx)

    def test_trigger_and_drain(self):

        r = self._call("session_create", {"role": "worker", "name": "小乙", "tags": "grp"})
        target = r.data["agents"][0]["cid"]
        r1 = self._call("session_send", {"target_id": target, "message": "第一条", "requires_reply": True})
        self.assertTrue(r1.ok)
        self.assertFalse(r1.data["queued"])
        self.assertTrue(r1.data["run_id"])
        self.assertTrue(self.mesh.is_running(target))
        # 占位成功还没进模型：后到消息进入待发送队列，等当前回合结束再起下一回合。
        deadline = time.monotonic() + 5
        while not self.provider.seen and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(self.provider.seen), 1)
        r2 = self._call("session_send", {"target_id": target, "message": "第二条", "requires_reply": False})
        self.assertTrue(r2.data["queued"])
        self.assertEqual(r2.data["queued_count"], 1)
        self.provider.gate.set()
        self.assertTrue(self.app.runner.wait_idle(target, timeout=10))
        seen = self.provider.seen
        self.assertEqual(len(seen), 2)  # 两回合都执行（队列抽干）
        self.assertTrue(any("【Agent 身份】" in str(m.get("content", "")) and m.get("role") == "system" for m in seen[0]))
        self.assertTrue(any("第一条" in str(m.get("content", "")) and str(m.get("content", "")).startswith("[from=") for m in seen[0]))
        self.assertTrue(any("第二条" in str(m.get("content", "")) for m in seen[1]))
        self.assertFalse(self.mesh.is_running(target))

if __name__ == "__main__":
    unittest.main()
