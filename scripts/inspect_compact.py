#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""压缩检视：对某个会话打印上下文分段与压缩判定，只读不写。

回答的问题是"这一轮到底压了什么、为什么"，比看代码猜快：

  · 当前估算 token 与阈值的关系（会不会触发）
  · 保留窗口多宽、实际保留了几轮、哪几轮会被压掉
  · 已落盘的摘要与它覆盖到的轮次
  · 分块 token 估算（系统提示词 / Skills / 知识库 / 记忆 / 近期 / 模式）

用法：

    python scripts/inspect_compact.py                 # 列出有日志的会话
    python scripts/inspect_compact.py <cid>           # 检视指定会话
    python scripts/inspect_compact.py <cid> --digest  # 附带压缩器视角与素材统计
    python scripts/inspect_compact.py <cid> --data-root D:/somewhere

退出码：0 = 正常；2 = 参数或读取失败。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception as exc:
    # stdout 被重定向或包装时 reconfigure 会抛；失败时保持原编码输出。
    # 编码设置失败不阻断检视本身。
    print(f"[scripts.inspect_compact.module] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

from agent.config import default_data_root, get_context  # noqa: E402
from agent.mechanisms.context.tokens import default_message_tokens  # noqa: E402

SEP = "─" * 68


def _fmt_tokens(n: int) -> str:
    return f"{n:,}"


def _load_store(data_root: Path, cid: str) -> Tuple[List[Any], Any]:
    from agent.mechanisms.session_store import SessionStore

    store = SessionStore(data_root)
    return store.load(cid), store


def _list_conversations(data_root: Path) -> List[Tuple[str, int, int]]:
    """返回 [(cid, 行数, 文件字节数)]，按文件大小降序。"""
    sessions = data_root / "sessions"
    if not sessions.is_dir():
        return []
    out: List[Tuple[str, int, int]] = []
    for p in sorted(sessions.glob("*.raw")):
        try:
            size = p.stat().st_size
            lines = sum(1 for _ in p.open("rb"))
        except OSError as exc:
            print(f"[scripts.inspect_compact._list_conversations] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            continue
        out.append((p.stem, lines, size))
    out.sort(key=lambda x: -x[2])
    return out


def _round_labels(rounds: List[Any]) -> List[str]:
    """把轮次列表压成可直接打印的一行行标签。"""
    labels: List[str] = []
    for i, r in enumerate(rounds):
        msgs = getattr(r, "messages", None) or []
        text = ""
        for m in msgs:
            if str(m.get("role") or "") == "user":
                content = m.get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = str(part.get("text") or "")
                            break
                break
        text = " ".join(str(text).split())[:58]
        n_msg = len(msgs)
        labels.append(f"    #{i + 1:<4} {n_msg:>2} 条消息  {text or '（无文本）'}")
    return labels


def _chunk_report(pipeline: Any) -> List[Tuple[str, int]]:
    """分块 token 估算；拿不到时返回空列表。"""
    from agent.mechanisms.context.tokens import default_message_tokens

    out: List[Tuple[str, int]] = []
    try:
        order = pipeline.CHUNK_ORDER  # 常量挂在类上
    except AttributeError:
        return out
    name_map = getattr(pipeline, "name_map", None)
    if not isinstance(name_map, dict):
        return out
    for chunk in order:
        items = name_map.get(chunk) or []
        total = 0
        for item in items:
            try:
                _role, text, _flag = item
            except (TypeError, ValueError) as exc:
                # 旁路，刻意跳过：块内容的结构由管线决定，这里只做统计展示。
                # 形态对不上的条目直接不计入，不能让一次估算失败打断整个检视。
                print(f"[scripts.inspect_compact._chunk_report] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                continue
            total += default_message_tokens({"role": "system", "content": str(text)})
        out.append((str(chunk), total))
    return out


def inspect(cid: str, data_root: Path, digest: bool) -> int:
    events, _store = _load_store(data_root, cid)
    if not events:
        print(f"读不到会话事实：{cid}")
        print(f"（数据根 {data_root}）")
        return 2

    cfg = get_context()
    threshold = int(cfg.get("summary_token_fallback") or 64000)
    full = int(cfg["full_user_rounds"])

    from agent.core.session_log import SessionLog
    from agent.mechanisms.context import (
        ContextPipeline,
        excerpt_by_target_tokens,
        flat_messages_to_user_rounds,
    )

    log = SessionLog(list(events))
    messages = log.derive_messages()

    pipeline = ContextPipeline(
        cid,
        full_user_rounds=full,
        summary_token_threshold=threshold,
    )
    # `rebuild_from_messages` 只填「近期记忆」块，不做取段 —— 压缩取段发生在
    # `ensure_before_append`。所以这里的估算口径是"整段对话都按原文带上"，
    # 而不是"压缩之后剩多少"。
    pipeline.rebuild_from_messages(messages)
    total = pipeline.total_token_estimate()
    full_tokens = sum(default_message_tokens(m) for m in messages)

    rounds = flat_messages_to_user_rounds(messages)
    # 取段口径与压缩器一致：遮盖末尾 `full_user_rounds` 轮，压它前面那一段。
    excerpt = excerpt_by_target_tokens(messages, keep_turns=full,
                                       token_fn=pipeline.message_tokens)
    to_compress = (flat_messages_to_user_rounds(messages[excerpt[0]:excerpt[1]])
                   if excerpt else [])
    keep_count = len(rounds) - len(to_compress)

    print(SEP)
    print(f"会话 {cid}")
    print(f"数据根 {data_root}")
    print(SEP)

    print("\n【上下文】")
    print(f"  事实条数        {len(events)}")
    print(f"  派生消息条数    {len(messages)}")
    print(f"  用户轮数        {len(rounds)}")
    print(f"  全量估算 token  {_fmt_tokens(full_tokens)}   （全部消息都按原文带上）")
    print(f"  管线估算 token  {_fmt_tokens(total)}   （钩子 + 已放入窗口的块）")
    print(f"  阈值            {_fmt_tokens(threshold)}")
    over = full_tokens > threshold
    print(f"  判定            {'超过阈值 → 会触发压缩' if over else '未超阈值 → 不触发压缩'}")
    if threshold > 0:
        print(f"  占用            {full_tokens / threshold * 100:.1f}%")

    print("\n【遮盖】")
    print("  遮盖的末尾用户轮（不压）        1")
    print(f"  遮盖之前可压的轮                {len(rounds) - 1 if rounds else 0}")
    print(f"  实际按原文保留                  {keep_count} 轮")
    print(f"  会被压成摘要                    {len(to_compress)} 轮")
    if excerpt is not None:
        print(f"  摘要取段（半开区间）            [{excerpt[0]}, {excerpt[1]})")
    else:
        print("  摘要取段                        无（轮数未超出窗口）")

    print("\n【轮次明细】")
    if rounds:
        for line in _round_labels(rounds):
            print(line)
    else:
        print("    （没有用户轮）")

    if to_compress:
        print("\n【将被压掉的轮】")
        for line in _round_labels(to_compress):
            print(line)
    if keep_count:
        print("\n【按原文保留的轮】")
        kept = rounds[len(to_compress):]
        for line in _round_labels(kept):
            print(line)

    chunks = _chunk_report(pipeline)
    if chunks:
        print("\n【分块 token 估算】")
        width = max(len(n) for n, _ in chunks)
        for name, n in chunks:
            bar = "█" * min(40, int(n / max(1, total) * 40)) if total else ""
            print(f"  {name.ljust(width)}  {_fmt_tokens(n):>10}  {bar}")

    if digest:
        print("\n【压缩器视角】")
        from agent.mechanisms.compaction.compactor import ContextCompactor

        def _no_summary(_material: str, **_: Any) -> str:
            return ""

        comp = ContextCompactor(_no_summary, summary_token_threshold=threshold)
        comp.restore_from_events(events)
        view = comp.view_messages(messages)
        sm = comp.summary_messages()
        print(f"  视图消息条数    {len(view)}")
        print(f"  已落盘摘要条数  {len(sm)}")
        for m in sm:
            body = str(m.get("content") or "")
            print(f"      {len(body)} 字符：{' '.join(body.split())[:70]}")
        pending = {"messages": messages[-2:]} if len(messages) >= 2 else None
        # 与 `ModelModule` 同序：先把这一轮真正要发的样子装进管线（摘要 + 未覆盖对话），
        # 再让压缩器估体积。反过来（管线里还是占位对话）算出来的体积偏小，
        # 会得出"不会压缩"的假结论。
        pipeline.set_summary_messages(sm)
        pipeline.set_dialogue(view, covered_end=comp.covered_end)
        assembled = pipeline.assembles([])
        print(f"  装配后估算      {_fmt_tokens(pipeline.total_token_estimate())}")
        try:
            ev = comp.ensure_before_append(pipeline, messages, pending,
                                           assembled=assembled)
        except Exception as exc:
            print(f"[scripts.inspect_compact.inspect] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            ev = None
            print(f"  ensure_before_append 抛错：{type(exc).__name__}: {exc}")
        if ev:
            print(f"  本次会产出的压缩事件：{ev}")
        else:
            print("  本次不产出压缩事件")

    print()
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="压缩检视：打印上下文分段与压缩判定（只读）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("conversation_id", nargs="?", default="", help="会话 id；省略则列出全部会话")
    ap.add_argument("--data-root", default="", help="数据根目录；缺省取 AI_AGENT_DATA_ROOT 或工程 data/")
    ap.add_argument("--digest", action="store_true", help="附带压缩器视角与摘要统计")
    args = ap.parse_args(argv)

    data_root = Path(args.data_root) if args.data_root else default_data_root()

    cid = str(args.conversation_id or "").strip()
    if not cid:
        rows = _list_conversations(data_root)
        print(SEP)
        print(f"数据根 {data_root}")
        print(SEP)
        if not rows:
            print("\n没有找到会话日志。")
            return 0
        print(f"\n{'会话 id':<40}{'事实行':>8}{'大小':>12}")
        for name, lines, size in rows:
            print(f"{name:<40}{lines:>8}{size / 1024:>10.1f} KB")
        print(f"\n共 {len(rows)} 个。用 `python scripts/inspect_compact.py <cid>` 检视其中一个。")
        return 0

    try:
        return inspect(cid, data_root, args.digest)
    except Exception as exc:
        print(f"检视失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
