# -*- coding: utf-8 -*-
"""验收：真实模型端到端（headless）。

场景：真实 DeepSeek 对话——模型自主读 / 写文件，四步门控生效（预览 → 宿主确认 →
提交 → 重读），事实落盘并可重载。
检查项：① 文件产出正确；② 预览发生且确认生效；③ 提交成功且完成重读；
④ 对话收束无 error；⑤ 事件落盘且可重载。
运行：python scripts/acceptance_mvp3.py
前置：工程根 `config.ini` 的 [model_reasoning]（api_base_url / api_key / model）。
退出码：0 = 全部 PASS；1 = 有 FAIL；2 = 缺配置（CI 按跳过处理）。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.config import get_model_reasoning  # noqa: E402
from agent.core import event_name as ev  # noqa: E402
from agent.mechanisms.model_provider import OpenAICompatibleProvider  # noqa: E402

# 写盘辅助在 QualityGate 上（gate.peek / gate.confirm）
from agent.mechanisms.session_store import SessionStore  # noqa: E402

SYSTEM_PROMPT = """你是 AI Agent（演示智能体），在给定的工作目录中完成用户任务。

【可用工具】read_file / grep_files / glob_files / write_file / echo。

【写盘纪律——宿主强制执行，违反会被拒绝】
1. **三步走**（链路只有这一条）：
   ① write_file(path, content) → 预览，不落盘；
   ② review_conclusion(file_name, conclusion, confirm_id) → 审阅本次改动并给出验证证据，解锁预览；
   ③ commit_write(confirm_id) → 落盘（只传 confirm_id，不要重传内容）；
2. 提交成功后必须 read_file 读回复核；
3. 若工具返回错误/被拒绝（附明确原因），**先读错误里的指引**再按它修正重试，不得跳过纪律步骤。

【行为】先读取任务文件弄清楚要求，再动手；完成后一句话汇报（文件路径 + 关键内容）。"""

TASK_TEXT = "任务：请在 result.txt 中写入一行文字：MVP-3 验收通过\n"
USER_TEXT_TMPL = "工作区目录：{ws}\n请读取工作区中的 task.txt，完成其中的任务。"


def _short(text: str, limit: int = 200) -> str:
    s = str(text or "")
    return s if len(s) <= limit else s[:limit] + "…"


def _is_target(path: str) -> bool:
    return str(path).replace("\\", "/").rstrip("/").endswith("result.txt")


def main() -> int:
    cfg = get_model_reasoning()
    if not cfg["api_key"] or not cfg["api_base_url"]:
        print("缺少配置：工程根 config.ini 的 [model_reasoning]（api_base_url / api_key）")
        return 2

    print("=== MVP-3 验收：真实模型端到端（headless）===")
    print(f"模型：{cfg['model']} @ {cfg['api_base_url']}")

    with tempfile.TemporaryDirectory(prefix="mvp3-") as tmp:
        ws = Path(tmp)
        (ws / "task.txt").write_text(TASK_TEXT, encoding="utf-8")
        store = SessionStore(ws / "data")
        provider = OpenAICompatibleProvider(
            base_url=cfg["api_base_url"], api_key=cfg["api_key"], model=cfg["model"]
        )
        app = build_app(provider=provider, store=store)
        cid = "mvp3-" + uuid4().hex[:12]
        engine = app.session(cid, system_prompt=SYSTEM_PROMPT)
        # 会话级门控：宿主确认须落在该会话自己的门控上
        session_gate = app.gate_for(cid)
        target = ws / "result.txt"

        # ── 运行回合：事件流旁路处理（打印 + host 自动确认预览）──
        previews: Dict[str, Dict[str, Any]] = {}
        confirms: List[Tuple[str, bool]] = []
        seq: List[Dict[str, Any]] = []  # 工具调用序列 {name, path, dry, call_id}
        results: Dict[str, bool] = {}  # call_id → ok
        rejects: List[str] = []
        errors: List[str] = []
        ended = False
        text = USER_TEXT_TMPL.format(ws=ws)
        print(f"\n[回合] {text}\n")
        try:
            for event in engine.start_turn(text):
                t = event.type
                d = event.data
                if t == ev.TOOL_STARTED:
                    args = d.get("arguments") or {}
                    name = str(d.get("name") or "")
                    if name == "commit_write":
                        _rec = session_gate.peek(str(args.get("confirm_id") or "")) or {}
                        path = str((_rec.get("arguments") or {}).get("path") or "")
                    else:
                        path = str(args.get("path") or "")
                    dry = name == "write_file"
                    seq.append(
                        {
                            "name": name,
                            "path": path,
                            "dry": dry,
                            "call_id": str(d.get("call_id") or ""),
                        }
                    )
                    if name == "write_file":
                        print(f"  [tool] write_file（{'预览' if dry else '提交'}）{path}")
                        if dry:
                            previews[str(d.get("call_id"))] = args
                    else:
                        print(f"  [tool] {name} {path}".rstrip())
                elif t == ev.TOOL_DONE:
                    # 内核词汇：`tool_done` **本身就是成功帧**（没有 `ok` 字段），
                    # 失败走 `tool_failed`。读 `d.get("ok")` 会恒为 False，
                    # 把所有工具都误判成"被拒"。
                    call_id = str(d.get("call_id") or "")
                    ok = "error" not in d
                    results[call_id] = ok
                    res = d.get("data") if isinstance(d.get("data"), dict) else {}
                    if ok and res.get("confirm_id"):
                        args = previews.pop(call_id, None)
                        if args is not None:
                            p = str(args.get("path") or "")
                            okc = session_gate.confirm(
                                str(res.get("confirm_id")),
                            )
                            confirms.append((p, bool(okc)))
                            print(f"  [host] 已确认预览：{p}")
                    elif not ok:
                        err = str(d.get("error") or "")
                        rejects.append(err)
                        print(f"  [reject] {_short(err)}")
                elif t == ev.TOOL_FAILED:
                    err = str(d.get("error") or "")
                    rejects.append(err)
                    results[str(d.get("call_id") or "")] = False
                    print(f"  [reject] {_short(err)}")
                elif t == ev.MODEL_MESSAGE:
                    content = str(d.get("content") or "").strip()
                    if content:
                        print(f"  [assistant] {_short(content, 300)}")
                elif t == ev.ERROR:
                    errors.append(str(d))
                    print(f"  [error] {d}")
                elif t == ev.TURN_ENDED:
                    ended = True
                    print(f"  [turn] 结束（steps={d.get('steps')}）")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            print(f"  [异常] {type(exc).__name__}: {exc}")

        # ── 检查项 ──
        print("\n检查项：")
        checks: List[Tuple[str, bool]] = []

        content = target.read_text(encoding="utf-8") if target.is_file() else ""
        checks.append(("① 文件产出：result.txt 内容正确", "MVP-3 验收通过" in content))

        preview_ok = any(
            c["name"] == "write_file" and c["dry"] and results.get(c["call_id"]) for c in seq
        )
        # 三步写盘必须由 review_conclusion 解锁：host 手动 confirm 不算完成本项检查，
        # 所以这里看的是"预览成功 + review_conclusion 成功"，而不是"预览成功"。
        reviewed = any(c["name"] == "review_conclusion" and results.get(c["call_id"]) for c in seq)
        checks.append(
            ("② 三步·预览与 review 解锁：预览发生且 review_conclusion 生效", preview_ok and reviewed)
        )

        commit_idx: Optional[int] = None
        for i, c in enumerate(seq):
            if (
                c["name"] == "commit_write"
                and _is_target(c["path"])
                and results.get(c["call_id"])
            ):
                commit_idx = i
                break
        reread = False
        if commit_idx is not None:
            for c in seq[commit_idx + 1 :]:
                if c["name"] == "read_file" and _is_target(c["path"]) and results.get(c["call_id"]):
                    reread = True
                    break
        checks.append(("③ 三步·提交与重读：提交成功后完成重读", commit_idx is not None and reread))

        checks.append(("④ 对话收束：turn_ended 且无 error 事件", ended and not errors))

        loaded = store.load(cid)
        checks.append(
            ("⑤ 事实持久化：事件落盘且可重载", bool(loaded) and len(loaded) == len(engine.log.events))
        )

        ok_all = True
        for label, passed in checks:
            print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
            ok_all = ok_all and passed

        print(
            f"\n[统计] 工具调用={len(seq)} 被拒={len(rejects)} 确认={len(confirms)} "
            f"事件={len(engine.log.events)}"
        )
        print()
        if ok_all:
            print("验收通过：全部检查项 PASS。")
            return 0
        print("验收未通过。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
