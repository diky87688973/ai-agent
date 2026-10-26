# -*- coding: utf-8 -*-
"""交互式真实对话壳：真实模型 + 工具 + id 制四步门控 + 会话持久化。

用法（工程根目录运行）：
  python -m agent.entry.cli                  # 交互模式（新建会话）
  python -m agent.entry.cli --session <ID>   # 恢复并继续指定会话
  python -m agent.entry.cli "一句话问题"      # 单回合模式
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

from agent.core import event_name as ev
from agent.core.error_report import report_error
from agent.mechanisms.session_store import new_conversation_id

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
                res = d.get("data") if isinstance(d.get("data"), dict) else {}
                if res.get("confirm_id"):
                    entry = previews.pop(str(d.get("call_id") or ""), None)
                    if entry is not None:
                        _ask_confirm(gate, str(entry.get("name") or ""), str(res.get("confirm_id")), dict(entry.get("args") or {}))
            elif t == ev.TOOL_FAILED:
                print(f"\n  [工具失败] {d.get('error') or '未知错误'}")
            elif t == ev.TOOL_CANCELED:
                print("\n  [工具已取消]")
            elif t == ev.TOOL_SUSPENDED:
                print("\n  [工具等待确认]")
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
        report_error("agent.shell.cli.interactive.run_one", exc)
        print(f"\n[请求失败] {type(exc).__name__}: {exc}")
    print()


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """解析入口参数。

    与装配分开：`--help` 与参数错误都在建 app 之前返回，
    缺配置时也能读到用法说明。
    """
    parser = argparse.ArgumentParser(
        prog="agent.entry.cli", description="AI Agent 交互式对话（真实模型）"
    )
    parser.add_argument("text", nargs="?", default="", help="单回合文本；缺省进入交互模式")
    parser.add_argument("--session", default="", help="会话 ID（恢复/继续）")
    parser.add_argument("--system", default="", help="附加系统指令")
    return parser.parse_args(list(argv) if argv is not None else None)


def build_session(
    argv: Optional[list] = None,
    *,
    app: Any,
    parsed: Optional[argparse.Namespace] = None,
) -> "tuple[Any, str, Any, Any, str]":
    """在给定 app 上装配一次交互会话：返回 (app, cid, engine, gate, single_text)。

    门控解析：一律用 `app.gate_for(cid)` 取该会话自己的门控——
    预览快照由管道路径登记在会话门控上，若此处用默认桶门控确认，确认会落空、
    提交被拒（"预览尚未确认"）。

    `app` 必须是装配好的底座：壳层不导入装配根，构造 app 是 `agent.entry.cli` 的职责。
    `parsed` 是已经解析好的参数；不给才解析 `argv`（`main` 先解析、后装配）。
    """
    args = parsed if parsed is not None else parse_args(argv)

    cid = str(args.session).strip() or new_conversation_id()
    runner = getattr(app, "runner", None)
    if runner is not None:
        engine = runner.build_engine(cid, extra_system=str(args.system))
    else:
        system_prompt = _SYSTEM_TEMPLATE.format(cwd=Path.cwd())
        if str(args.system).strip():
            system_prompt += "\n\n[附加指令]\n" + str(args.system).strip()
        engine = app.session(cid, system_prompt=system_prompt)
    gate = app.gate_for(cid)
    return app, cid, engine, gate, str(args.text or "")


def main(argv: Optional[list] = None, *, app_factory: Any) -> int:
    """交互式入口。`app_factory` 由 `agent.entry.cli` 提供（壳层不装配 app）。"""
    parsed = parse_args(argv)
    app = app_factory()
    if app is None:
        return 2
    try:
        app, cid, engine, gate, single = build_session(None, app=app, parsed=parsed)
    except ValueError as exc:
        print(f"[cli] {exc}", file=sys.stderr)
        app.dispose()
        return 2
    except Exception as exc:
        report_error("agent.shell.cli.interactive.build_session", exc)
        print(f"[cli] 无法创建会话：{type(exc).__name__}: {exc}", file=sys.stderr)
        app.dispose()
        return 2

    models = app.available_models()
    model = app.model_for(cid) or (models[0] if models else "")

    print("=== AI Agent 对话（真实模型）===")
    print(f"模型：{model}    会话：{cid}")
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
        print(f"[session] {cid}")
        # 会话生命周期落点：退出即释放本会话运行态（已落盘记录不受影响）
        app.dispose()

