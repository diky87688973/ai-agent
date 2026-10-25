# -*- coding: utf-8 -*-
"""验收：真实模型端到端（headless）。

场景：真实 DeepSeek 对话——模型自主读 / 写文件，四步门控生效（预览 → 宿主确认 →
提交 → 重读），事实落盘并可重载。
检查项：① 文件产出正确；② 预览发生且确认生效；③ 提交成功且完成重读；
④ 对话收束无 error；⑤ 事件落盘且可重载。
运行：python scripts/acceptance_mvp3.py
前置：`plugins/multi_model/plugin-config.ini` 至少有一个有效模型；
需显式设置 `AI_AGENT_REAL_MODEL_ACCEPTANCE=1` 才运行。
退出码：0 = 全部 PASS；1 = 有 FAIL；2 = 缺模型或未启用（CI 按跳过处理）。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.core import event_name as ev  # noqa: E402

# 写盘辅助在 QualityGate 上（gate.peek / gate.confirm）
from agent.mechanisms.session_store import SessionStore  # noqa: E402

SYSTEM_PROMPT = """你是 AI Agent（演示智能体），在给定的工作目录中完成用户任务。

【可用工具】read_file / grep_files / glob_files / write_file / echo。

【写盘纪律——宿主强制执行，违反会被拒绝】
1. 三步走（链路只有这一条）：
   ① write_file(path, content) → 预览，不落盘；
   ② review_conclusion(file_name, conclusion, confirm_id) → 审阅本次改动并给出验证证据，解锁预览；
   ③ commit_write(confirm_id) → 落盘（只传 confirm_id，不要重传内容）；
2. 提交成功后必须 read_file 读回复核；
3. 若工具返回错误/被拒绝（附明确原因），先读错误里的指引再按它修正重试，不得跳过纪律步骤。

【行为】先读取任务文件弄清楚要求，再动手；完成后一句话汇报（文件路径 + 关键内容）。"""

TASK_TEXT = "任务：请在 result.txt 中写入一行文字：MVP-3 验收通过\n"
USER_TEXT_TMPL = "工作区目录：{ws}\n请读取工作区中的 task.txt，完成其中的任务。"


def _short(text: str, limit: int = 200) -> str:
    s = str(text or "")
    return s if len(s) <= limit else s[:limit] + "…"


def _is_target(path: str) -> bool:
    return str(path).replace("\\", "/").rstrip("/").endswith("result.txt")


def _record_started(data: dict, seq: list, previews: dict, session_gate: Any) -> None:
    args = data.get("arguments") or {}
    name = str(data.get("name") or "")
    if name == "commit_write":
        rec = session_gate.peek(str(args.get("confirm_id") or "")) or {}
        path = str((rec.get("arguments") or {}).get("path") or "")
    else:
        path = str(args.get("path") or "")
    dry = name == "write_file"
    seq.append({"name": name, "path": path, "dry": dry,
                "call_id": str(data.get("call_id") or "")})
    if name == "write_file":
        print(f"  [tool] write_file（{'预览' if dry else '提交'}）{path}")
        if dry:
            previews[str(data.get("call_id"))] = args
    else:
        print(f"  [tool] {name} {path}".rstrip())


def _record_done(data: dict, results: dict, previews: dict,
                 session_gate: Any, confirms: list, rejects: list) -> None:
    call_id = str(data.get("call_id") or "")
    results[call_id] = "error" not in data
    payload = data.get("data") if isinstance(data.get("data"), dict) else {}
    if results[call_id] and payload.get("confirm_id"):
        args = previews.pop(call_id, None)
        if args is not None:
            path = str(args.get("path") or "")
            confirmed = session_gate.confirm(str(payload.get("confirm_id")))
            confirms.append((path, bool(confirmed)))
            print(f"  [host] 已确认预览：{path}")
    elif not results[call_id]:
        error = str(data.get("error") or "")
        rejects.append(error)
        print(f"  [reject] {_short(error)}")


def _run_events(engine: Any, session_gate: Any, text: str):
    previews, confirms, seq = {}, [], []
    results, rejects, errors = {}, [], []
    ended = False
    try:
        for event in engine.start_turn(text):
            kind, data = event.type, event.data
            if kind == ev.TOOL_STARTED:
                _record_started(data, seq, previews, session_gate)
            elif kind == ev.TOOL_DONE:
                _record_done(data, results, previews, session_gate, confirms, rejects)
            elif kind == ev.TOOL_FAILED:
                error = str(data.get("error") or "")
                rejects.append(error)
                results[str(data.get("call_id") or "")] = False
                print(f"  [reject] {_short(error)}")
            elif kind == ev.MODEL_MESSAGE:
                content = str(data.get("content") or "").strip()
                if content:
                    print(f"  [assistant] {_short(content, 300)}")
            elif kind == ev.ERROR:
                errors.append(str(data))
                print(f"  [error] {data}")
            elif kind == ev.TURN_ENDED:
                ended = True
                print(f"  [turn] 结束（steps={data.get('steps')}）")
    except Exception as exc:
        print(f"[scripts.acceptance_mvp3.main] {type(exc).__name__}: {exc}",
              file=sys.stderr, flush=True)
        errors.append(f"{type(exc).__name__}: {exc}")
        print(f"  [异常] {type(exc).__name__}: {exc}")
    return seq, results, rejects, errors, confirms, ended


def _check_results(target: Path, store: Any, cid: str, engine: Any,
                   seq: list, results: dict, ended: bool, errors: list) -> bool:
    print("\n检查项：")
    content = target.read_text(encoding="utf-8") if target.is_file() else ""
    checks = [("① 文件产出：result.txt 内容正确", "MVP-3 验收通过" in content)]
    preview_ok = any(
        c["name"] == "write_file" and c["dry"] and results.get(c["call_id"])
        for c in seq)
    reviewed = any(
        c["name"] == "review_conclusion" and results.get(c["call_id"]) for c in seq)
    checks.append(("② 三步·预览与 review 解锁：预览发生且 review_conclusion 生效",
                   preview_ok and reviewed))
    commit_idx = next((i for i, c in enumerate(seq)
                       if c["name"] == "commit_write" and _is_target(c["path"])
                       and results.get(c["call_id"])), None)
    reread = commit_idx is not None and any(
        c["name"] == "read_file" and _is_target(c["path"])
        and results.get(c["call_id"]) for c in seq[commit_idx + 1:])
    checks.append(("③ 三步·提交与重读：提交成功后完成重读",
                   commit_idx is not None and reread))
    checks.append(("④ 对话收束：turn_ended 且无 error 事件", ended and not errors))
    loaded = store.load(cid)
    checks.append(("⑤ 事实持久化：事件落盘且可重载",
                   bool(loaded) and len(loaded) == len(engine.log.events)))
    ok_all = True
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
        ok_all = ok_all and passed
    return ok_all


def main() -> int:
    if os.environ.get("AI_AGENT_REAL_MODEL_ACCEPTANCE") != "1":
        print("跳过真实模型验收：设置 AI_AGENT_REAL_MODEL_ACCEPTANCE=1 后运行")
        return 2
    with tempfile.TemporaryDirectory(prefix="mvp3-") as tmp:
        ws = Path(tmp)
        (ws / "task.txt").write_text(TASK_TEXT, encoding="utf-8")
        store = SessionStore(ws / "data")
        app = build_app(store=store)
        if app.model_config_state != "catalog" or not app.available_models():
            app.dispose()
            print("缺少模型：请在 plugins/multi_model/plugin-config.ini 配置至少一个 [model:<id>] 节")
            return 2
        cid = "mvp3-" + uuid4().hex[:12]
        model = app.model_for(cid) or app.available_models()[0]
        print("=== MVP-3 验收：真实模型端到端（headless）===")
        print(f"模型：{model}")
        engine = app.session(cid, system_prompt=SYSTEM_PROMPT)
        session_gate = app.gate_for(cid)
        target = ws / "result.txt"
        text = USER_TEXT_TMPL.format(ws=ws)
        print(f"\n[回合] {text}\n")
        seq, results, rejects, errors, confirms, ended = _run_events(
            engine, session_gate, text)
        ok_all = _check_results(
            target, store, cid, engine, seq, results, ended, errors)
        print(f"\n[统计] 工具调用={len(seq)} 被拒={len(rejects)} "
              f"确认={len(confirms)} 事件={len(engine.log.events)}\n")
        if ok_all:
            print("验收通过：全部检查项 PASS。")
            return 0
        print("验收未通过。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
