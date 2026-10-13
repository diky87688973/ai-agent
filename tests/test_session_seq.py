# -*- coding: utf-8 -*-
"""会话日志存储坐标（`seq`）测试。

**为什么需要坐标**：SSE 断线重连要知道"从哪继续"。没有坐标就只有两个坏选择——
重放全部（重复内容）或干脆丢掉中间那段（静默缺口）。`seq` 就是那个坐标。

它是**存储位置**（该会话日志内的 0 基行号），不是事件语义：
- 写进落盘行的 `seq` 字段；
- **不给 `Event` 加字段**（否则波及所有构造点与相等性比较）；
- 实时路径由 `App.session` 的落盘旁路标进载荷 `_seq`；
- 缺少 `seq` 的日志读取时按行位置补号，两类行的坐标口径一致。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.core.events import Event  # noqa: E402
from agent.mechanisms.session_store import SessionStore  # noqa: E402

CID = "seq-test-0001"

class SeqAssignmentTest(unittest.TestCase):
    """写入即定位：序号按会话日志位置连续编。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SessionStore(Path(self._tmp.name))

    def test_seq_is_written_to_each_line(self) -> None:
        self.store.append(CID, [Event("a", {"i": 0}), Event("b", {"i": 1})])
        self.store.append(CID, [Event("c", {"i": 2})])
        lines = self.store.raw_path(CID).read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(l)["s"] for l in lines], [0, 1, 2])

    def test_seq_continues_across_appends(self) -> None:
        """跨批连续：第二批接着第一批的号，不从头开始（约 500 行一批的 flush 依赖此）。"""
        for batch in range(4):
            self.store.append(CID, [Event("x", {"batch": batch}) for _ in range(3)])
        pairs = self.store.load_with_seq(CID)
        self.assertEqual([seq for seq, _ in pairs], list(range(12)))

    def test_line_count_matches_next_seq(self) -> None:
        """`line_count` 就是"下一个可用序号"——`App._seq_next` 靠它播种。"""
        self.assertEqual(self.store.line_count(CID), 0)
        self.store.append(CID, [Event("a"), Event("b")])
        self.assertEqual(self.store.line_count(CID), 2)
        self.store.append(CID, [Event("c")])
        self.assertEqual(self.store.line_count(CID), 3)

    def test_blank_lines_do_not_shift_positions(self) -> None:
        """空行不占号：否则"下一个序号"会随空白漂移。"""
        self.store.append(CID, [Event("a")])
        with self.store.raw_path(CID).open("a", encoding="utf-8") as fh:
            fh.write("\n\n")
        self.store.append(CID, [Event("b")])
        pairs = self.store.load_with_seq(CID)
        self.assertEqual([seq for seq, _ in pairs], [0, 1])
        self.assertEqual([e.type for _, e in pairs], ["a", "b"])

    def test_load_still_returns_plain_events(self) -> None:
        """`load()` 的返回形状**不变**（既有调用方与测试都按纯事件列表用）。"""
        self.store.append(CID, [Event("a"), Event("b")])
        events = self.store.load(CID)
        self.assertEqual([e.type for e in events], ["a", "b"])
        self.assertTrue(all(isinstance(e, Event) for e in events))

    def test_seq_lives_in_payload_and_top_level_only(self) -> None:
        """坐标在落盘行里只占顶层 `seq` 一处；**业务字段不被污染**。

        设计要点：坐标必须在事件**产出瞬间**由 `emit` 标进载荷（`_seq`）——
        事件一产出就被发布到总线，落盘在其后；落盘时才标的话实时订阅者永远看不到它
        （落盘 9 行 seq 连续，实时流 0 帧带 seq）。
        给前端的帧由适配层负责把它摘掉（见 `test_replay_never_leaks_seq_into_frame_payloads`）。
        """
        self.store.append(CID, [Event("a", {"keep": 1})])
        _seq, event = self.store.load_with_seq(CID)[0]
        # 业务字段原样保留；坐标与补回的会话 ID 另占键，不算业务字段
        self.assertEqual({k: v for k, v in event.data.items()
                          if k not in ("_seq", "conversation_id")}, {"keep": 1})
        row = json.loads(self.store.raw_path(CID).read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["s"], 0)
        # **落盘行里没有第二份坐标**（data 里不重复存 `_seq`）
        self.assertNotIn("_seq", row["d"])

    def test_conversation_id_is_not_persisted(self) -> None:
        """会话 ID 由文件名承载，落盘行里不存；读回时按会话补进载荷。

        落盘每行存一遍会话 ID（36 字节）纯属重复：读盘的人手上已经有文件名。
        但**内存里的事件必须带它** —— SSE 靠它把帧分派到正确的会话页面。
        """
        self.store.append(CID, [Event("a", {"keep": 1})])
        row = json.loads(self.store.raw_path(CID).read_text(encoding="utf-8").splitlines()[0])
        self.assertNotIn("conversation_id", row["d"])
        self.assertNotIn("conversation_id", row)
        # 读回时补上，且与文件名一致
        _seq, event = self.store.load_with_seq(CID)[0]
        self.assertEqual(event.data.get("conversation_id"), CID)

class SeqMissingTest(unittest.TestCase):
    """缺坐标的行按**行位置**补号 —— 手写或外部工具产生的日志也要能读。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SessionStore(Path(self._tmp.name))

    def _write_without_seq(self) -> None:
        """手写一个不带坐标的日志（模拟外部工具或人工写入）。"""
        path = self.store.raw_path(CID)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {"t": "turn_started", "d": {"run_id": "r"}},
            {"t": "input_claimed", "d": {"content": "甲"}},
            {"t": "turn_ended", "d": {}},
        ]
        path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
            encoding="utf-8",
        )

    def test_missing_seq_falls_back_to_line_position(self) -> None:
        """没有坐标的行按行位置补号——足以让"刷新后全量回放"工作。"""
        self._write_without_seq()
        pairs = self.store.load_with_seq(CID)
        self.assertEqual([seq for seq, _ in pairs], [0, 1, 2])
        self.assertEqual([e.type for _, e in pairs],
                         ["turn_started", "input_claimed", "turn_ended"])

    def test_appended_rows_use_global_seq(self) -> None:
        """继续追加时新行用**全局坐标**，必然大于同文件里的补号。

        全局坐标跨会话唯一，续传游标才成立；补号只服务"全量回放"。
        """
        self._write_without_seq()
        self.store.append(CID, [Event("assistant_delta", {"text": "乙"})])
        pairs = self.store.load_with_seq(CID)
        seqs = [seq for seq, _ in pairs]
        self.assertEqual([e.type for _, e in pairs],
                         ["turn_started", "input_claimed", "turn_ended", "assistant_delta"])
        self.assertEqual(seqs[:3], [0, 1, 2])
        self.assertGreater(seqs[3], 2, msg=f"新行该用全局坐标：{seqs}")

    def test_coordinates_stay_unique_and_monotonic(self) -> None:
        self._write_without_seq()
        self.store.append(CID, [Event("x"), Event("y")])
        seqs = [seq for seq, _ in self.store.load_with_seq(CID)]
        self.assertEqual(len(seqs), len(set(seqs)))
        self.assertEqual(seqs, sorted(seqs))


class SeqTailTest(unittest.TestCase):
    """`tail_from` 是续传的读取原语。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SessionStore(Path(self._tmp.name))
        self.store.append(CID, [Event(f"e{i}") for i in range(5)])

    def test_tail_from_is_exclusive(self) -> None:
        """`seq > after` —— 严格大于，游标自身那帧不会重复补。"""
        got = [seq for seq, _ in self.store.tail_from(CID, 2)]
        self.assertEqual(got, [3, 4])

    def test_tail_from_negative_returns_everything(self) -> None:
        got = [seq for seq, _ in self.store.tail_from(CID, -1)]
        self.assertEqual(got, [0, 1, 2, 3, 4])

    def test_tail_from_beyond_end_is_empty(self) -> None:
        self.assertEqual(self.store.tail_from(CID, 99), [])

    def test_missing_conversation_is_empty_not_error(self) -> None:
        self.assertEqual(self.store.tail_from("no-such-conv", -1), [])
        self.assertEqual(self.store.load_with_seq("no-such-conv"), [])

    def test_bad_conversation_id_raises_like_load(self) -> None:
        """非法 cid 仍要拒绝（防路径穿越）——坐标功能不能成为绕过口。"""
        with self.assertRaises(ValueError):
            self.store.tail_from("../etc/passwd", -1)

class SeqEmptyAndErrorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = SessionStore(Path(self._tmp.name))

    def test_append_empty_batch_writes_nothing(self) -> None:
        self.assertEqual(self.store.append(CID, []), 0)
        self.assertEqual(self.store.line_count(CID), 0)
        self.assertFalse(self.store.raw_path(CID).exists())

    def test_unparseable_line_is_skipped(self) -> None:
        """坏行跳过不渲染；**已有事件仍保留各自的落盘坐标**（坐标来自字段，不靠数位置）。

        （`"foo"` 这种是**合法 JSON**（字符串字面量），只是不是对象；
        真正不可解析的是 `{oops`。）
        """
        self.store.append(CID, [Event("a"), Event("b")])
        path = self.store.raw_path(CID)
        lines = path.read_text(encoding="utf-8").splitlines()
        lines.insert(1, "{oops")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        pairs = self.store.load_with_seq(CID)
        self.assertEqual([e.type for _, e in pairs], ["a", "b"])
        self.assertEqual([seq for seq, _ in pairs], [0, 1])

    def test_non_object_json_lines_do_not_produce_events(self) -> None:
        """合法但非对象的行（`"foo"` / `123`）不产生事件，也不影响已有事件的坐标。"""
        self.store.append(CID, [Event("a")])
        path = self.store.raw_path(CID)
        path.write_text(
            path.read_text(encoding="utf-8") + '"foo"\n' + "123\n", encoding="utf-8"
        )
        pairs = self.store.load_with_seq(CID)
        self.assertEqual([e.type for _, e in pairs], ["a"])
        self.assertEqual([seq for seq, _ in pairs], [0])

    def test_append_after_external_edit_does_not_collide(self) -> None:
        """外部插入行后追加，新事件**不与既有坐标撞号**（全局分配器在存储层，不受文件行数影响）。

        坐标必须由存储层单点分配，并与磁盘最大值播种对齐：若在内存里维护下一个序号，
        外部改动文件后它会与真实位置错开，新事件就会被编上已被占用的号（如 `[0, 1]` 撞号）。
        """
        self.store.append(CID, [Event("a")])
        path = self.store.raw_path(CID)
        # 外部插入两行（模拟手工编辑 / 拼接日志）
        path.write_text(
            path.read_text(encoding="utf-8") + '"foo"\n' + "123\n", encoding="utf-8"
        )
        self.store.append(CID, [Event("b")])
        pairs = self.store.load_with_seq(CID)
        seqs = [seq for seq, _ in pairs]
        self.assertEqual([e.type for _, e in pairs], ["a", "b"])
        self.assertEqual(len(seqs), len(set(seqs)), msg="坐标不得重复")
        self.assertEqual(seqs, sorted(seqs))       # 与文件顺序一致（单调）

    def test_coordinates_are_global_across_conversations(self) -> None:
        """坐标**跨会话单调**：这是续传游标能只用一条流一个光标的前提。"""
        other = "seq-test-0002"
        self.store.append(CID, [Event("a"), Event("b")])
        self.store.append(other, [Event("c")])
        first = [q for q, _ in self.store.load_with_seq(CID)]
        second = [q for q, _ in self.store.load_with_seq(other)]
        self.assertTrue(min(second) > max(first), msg=f"{first} vs {second}")

    def test_tail_across_uses_one_cursor_for_all_conversations(self) -> None:
        """`tail_across`：一个游标跨会话续传，按坐标升序。"""
        other = "seq-test-0002"
        self.store.append(CID, [Event("a"), Event("b")])
        self.store.append(other, [Event("c")])
        rows = self.store.tail_across(0, limit=10)
        self.assertEqual([e.type for _, _, e in rows], ["b", "c"])
        self.assertEqual([cid for _, cid, _ in rows], [CID, other])
        self.assertEqual([q for q, _, _ in rows], sorted(q for q, _, _ in rows))

    def test_allocate_seq_survives_restart_without_collision(self) -> None:
        """重启后重新构造 store 也不能从 0 重发号（否则与磁盘上的坐标撞号）。"""
        self.store.append(CID, [Event("a"), Event("b"), Event("c")])
        fresh = SessionStore(Path(self._tmp.name))
        got = fresh.allocate_seq(1)
        self.assertGreater(got, 2, msg=f"新号必须大于磁盘最大值：{got}")
        fresh.append(CID, [Event("d", {"_seq": got})])
        seqs = [q for q, _ in fresh.load_with_seq(CID)]
        self.assertEqual(len(seqs), len(set(seqs)), msg="重启后撞号")

    def test_encrypted_mode_round_trips_seq(self) -> None:
        """加密模式下 seq 也必须能读回（它写在明文里，再整体加密）。"""
        encrypted = SessionStore(Path(self._tmp.name), encryption="local")
        encrypted.append(CID, [Event("a", {"x": 1}), Event("b", {"x": 2})])
        raw = encrypted.raw_path(CID).read_text(encoding="utf-8")
        self.assertNotIn('"type"', raw, msg="落盘应是密文")
        pairs = encrypted.load_with_seq(CID)
        self.assertEqual([seq for seq, _ in pairs], [0, 1])
        self.assertEqual([e.type for _, e in pairs], ["a", "b"])

if __name__ == "__main__":
    unittest.main()
