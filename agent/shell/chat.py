# -*- coding: utf-8 -*-
"""交互式真实对话壳（headless）：真实模型 + 工具 + id 制四步门控 + 会话持久化。

用法（工程根目录运行）：
  python -m agent.shell.chat                  # 交互模式（新建会话）
  python -m agent.shell.chat --session <ID>   # 恢复并继续指定会话
  python -m agent.shell.chat "一句话问题"      # 单回合模式
写盘确认：模型预览写文件时，终端展示变更内容并询问 [y/N]，输入 y 确认该预览；
模型随后凭 confirm_id 提交（commit_write），提交内容由预览快照恢复。
退出：/exit、/quit 或 Ctrl+C。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from agent.app import build_app
from agent.config import default_data_root, get_context, get_model_reasoning
from agent.core import event_name as ev
from agent.mechanisms.model_provider import OpenAICompatibleProvider
from agent.mechanisms.session_store import SessionStore, new_conversation_id

_PREVIEW_TOOL_NAMES = (
    "write_file",
    "replace_in_file",
    "apply_patch",
    "read_write",
    "delete_file",
    "file_ops",
    "file_undo",
)

_SYSTEM_TEMPLATE = """你是 AI Agent——一个严谨的通用助手，能读写文件、执行命令，写代码只是其中一项。用户在你的工作目录中协作。

【写盘纪律（宿主强制执行，违反会被拒绝）】
1. 写类工具（write_file / replace_in_file / apply_patch / read_write / delete_file / file_ops / file_undo）两步走：先调用该工具本身预览（不落盘，返回 confirm_id）；用户确认后，用 commit_write(confirm_id) 提交——提交只传 confirm_id，不要重传参数；
2. 提交成功后必须 read_file 读回复核（删除 / 移动类除外）；
3. 误改可用 file_undo 回滚（list 查历史、undo 凭 mod_id）；工具返回结构化错误时，按提示修正后重试。

【环境】当前工作目录：{cwd}
用简体中文回答；需要动手时直接用工具。"""


def _brief_args(args: Dict[str, Any]) -> str:
    """预览参数摘要（长内容折叠为大小，避免刷屏）。"""
    brief: Dict[str, Any] = {}
    for key, value in args.items():
        text = str(value)
        if key in ("content", "patch_text") or len(text) > 80:
            brief[key] = f"<{len(text)} 字符>"
        else:
            brief[key] = value
    return json.dumps(brief, ensure_ascii=False)


def _ask_confirm(gate: Any, name: str, confirm_id: str, args: Dict[str, Any]) -> None:
    """展示待确认变更并询问用户；y 才确认该预览（模型凭同一 ID 提交）。"""
    path = str(args.get("path") or args.get("dest_path") or args.get("dest") or args.get("source") or "")
    print(f"  ── 待确认变更：{name} {path}".rstrip())
    if name == "write_file" and "content" in args:
        content = str(args.get("content") or "")
        print(f"     （{len(content.encode('utf-8'))} 字节）")
        lines = content.splitlines() or [""]
        for line in lines[:12]:
            print(f"     | {line}")
        if len(lines) > 12:
            print("     | …")
    else:
        print(f"     | {_brief_args(args)}")
    try:
        ans = input("  [确认] 允许提交此变更？[y/N] ").strip().lower()
    except EOFError:
        ans = ""
    if ans in ("y", "yes"):
        gate.confirm(confirm_id)
        print("  [已确认] 模型现在可以凭同一 ID 提交。")
    else:
        print("  [未确认] 模型若提交会被拒绝。")


def run_one(engine: Any, gate: Any, text: str) -> None:
    """跑一个回合：流式打印 + 预览确认交互。"""
    previews: Dict[str, Dict[str, Any]] = {}
    printed_any = False
    try:
        for event in engine.start_turn(text):
            t = event.type
            d = event.data
            if t == ev.ASSISTANT_DELTA:
                sys.stdout.write(str(d.get("text") or ""))
                sys.stdout.flush()
                printed_any = True
            elif t == ev.TOOL_STARTED:
                args = d.get("arguments") or {}
                name = str(d.get("name") or "")
                if name in _PREVIEW_TOOL_NAMES:
                    target = str(args.get("path") or args.get("dest_path") or args.get("dest") or args.get("source") or "")
                    print(f"\n  [tool] {name}（预览）{target}".rstrip())
                    previews[str(d.get("call_id"))] = {"name": name, "args": args}
                elif name == "commit_write":
                    print(f"\n  [tool] commit_write（提交）{args.get('confirm_id')}")
                else:
                    print(f"\n  [tool] {name} {args.get('path') or ''}".rstrip())
            elif t == ev.TOOL_DONE:
                ok = bool(d.get("ok"))
                res = d.get("data") if isinstance(d.get("data"), dict) else {}
                if ok and res.get("confirm_id"):
                    entry = previews.pop(str(d.get("call_id") or ""), None)
                    if entry is not None:
                        _ask_confirm(gate, str(entry.get("name") or ""), str(res.get("confirm_id")), dict(entry.get("args") or {}))
                elif not ok:
                    print(f"\n  [被拒/失败] {d.get('error')}")
            elif t == ev.MODEL_MESSAGE:
                if not printed_any:
                    content = str(d.get("content") or "")
                    if content:
                        sys.stdout.write(content)
                sys.stdout.write("\n")
                sys.stdout.flush()
                printed_any = True
            elif t == ev.ERROR:
                print(f"\n  [error] {d.get('detail') or d}")
    except KeyboardInterrupt:
        print("\n[已中断本次回合]")
    except Exception as exc:
        print(f"\n[请求失败] {type(exc).__name__}: {exc}")
    print()


def build_session(
    argv: Optional[list] = None,
) -> "tuple[Any, str, Any, Any, str] | None":
    """装配一次交互会话：返回 (app, cid, engine, gate, single_text)；缺配置返回 None。

    门控解析：一律用 `app.gate_for(cid)` 取**该会话自己的**门控——
    预览快照由管道路径登记在会话门控上，若此处用默认桶门控确认，确认会落空、
    提交被拒（"预览尚未确认"）。
    """
    parser = argparse.ArgumentParser(
        prog="agent.shell.chat", description="AI Agent 交互式对话（真实模型）"
    )
    parser.add_argument("text", nargs="?", default="", help="单回合文本；缺省进入交互模式")
    parser.add_argument("--session", default="", help="会话 ID（恢复/继续）")
    parser.add_argument("--system", default="", help="附加系统指令")
    args = parser.parse_args(list(argv) if argv is not None else None)

    cfg = get_model_reasoning()
    if not cfg["api_key"] or not cfg["api_base_url"]:
        print("缺少配置：agent/config.ini 的 [model_reasoning]（api_base_url / api_key / model）")
        return None

    provider = OpenAICompatibleProvider(
        base_url=cfg["api_base_url"], api_key=cfg["api_key"], model=cfg["model"],
        # 与 Web 壳同一口径：历史轮次的思维链默认不回传。
        replay_history_reasoning=bool(get_context().get("replay_history_reasoning")),
    )
    store = SessionStore(default_data_root())
    app = build_app(provider=provider, store=store)
    cid = str(args.session).strip() or new_conversation_id()
    system_prompt = _SYSTEM_TEMPLATE.format(cwd=Path.cwd())
    if str(args.system).strip():
        system_prompt += "\n\n[附加指令]\n" + str(args.system).strip()
    engine = app.session(cid, system_prompt=system_prompt)
    gate = app.gate_for(cid)
    return app, cid, engine, gate, str(args.text or "")


def main(argv: Optional[list] = None) -> int:
    built = build_session(argv)
    if built is None:
        return 2
    app, cid, engine, gate, single = built
    cfg = get_model_reasoning()

    print("=== AI Agent 对话（真实模型）===")
    print(f"模型：{cfg['model']}    会话：{cid}")
    print(f"（再次运行加 --session {cid} 可继续本会话；/exit 退出）")

    try:
        if single:
            run_one(engine, gate, single)
            return 0

        while True:
            try:
                text = input("你> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not text:
                continue
            if text in ("/exit", "/quit", "exit", "quit"):
                break
            run_one(engine, gate, text)
        print("[会话结束]")
        return 0
    finally:
        # 会话生命周期落点：退出即释放本会话运行态（已落盘记录不受影响）
        app.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
