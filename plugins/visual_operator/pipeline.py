# -*- coding: utf-8 -*-
"""`desktop_act` 的批量执行骨架：校验、超时、步日志与失败即停。"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from agent.core.error_report import report_error

MAX_STEPS = 12
MAX_SECONDS = 60.0

#: 批量中出现这些目标文字时整体拒绝：逐条执行并由用户确认。
DESTRUCTIVE = ("关闭", "删除", "支付", "购买", "退订", "取消订单",
               "close", "delete", "pay", "buy", "unsubscribe")



@dataclass
class BatchResult:
    ok: bool
    steps: List[Dict[str, Any]] = field(default_factory=list)
    failed_step: Optional[int] = None
    error: str = ""
    data: Any = None


def normalize_steps(raw: Any) -> List[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """把 `[{verb: args, expect: {...}}, ...]` 归一化并做上限检查。"""
    if not isinstance(raw, list) or not raw:
        raise ValueError("steps 必须是非空数组")
    if len(raw) > MAX_STEPS:
        raise ValueError(f"steps 最多 {MAX_STEPS} 步，实际 {len(raw)}")
    normalized: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 步必须是对象")
        keys = [key for key in item if key not in ("expect", "capture")]
        if len(keys) != 1:
            raise ValueError(f"第 {index} 步必须且只能有一个动作")
        verb = str(keys[0])
        args = item[verb]
        if not isinstance(args, dict):
            if verb == "app" and isinstance(args, str):
                args = {"path": args}
            elif verb == "open" and isinstance(args, str):
                args = {"target": args}
            elif verb == "window" and isinstance(args, str):
                args = {"action": "activate", "window": args}
            elif verb == "wait" and isinstance(args, (int, float)):
                args = {"until": "change", "timeout_ms": int(args)}
            else:
                raise ValueError(f"第 {index} 步的 {verb} 参数必须是对象")
        expect = item.get("expect") or {}
        if not isinstance(expect, dict):
            raise ValueError(f"第 {index} 步的 expect 必须是对象")
        normalized.append((verb, args, expect))
    return normalized


def is_read_only(verb: str, args: Mapping[str, Any]) -> bool:
    if verb == "find":
        return True
    if verb == "wait":
        return True
    if verb == "eye":
        return not args.get("hover") and not args.get("activate")
    if verb == "window":
        return str(args.get("action") or "list") in ("list", "rect", "wait")
    return False


def destructive_hit(steps: Sequence[Tuple[str, Mapping[str, Any], Mapping[str, Any]]]) -> str:
    for _verb, args, expect in steps:
        text = " ".join(str(value) for value in args.values())
        text += " " + " ".join(str(value) for value in expect.values())
        lowered = text.lower()
        for word in DESTRUCTIVE:
            if word.lower() in lowered:
                return word
    return ""


def sanitize(value: Any) -> Any:
    """步日志只保留可序列化的短结果，不把图片或超长正文带进上下文。"""
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()
                if key not in ("attachments", "image", "raw_image")}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value[:20]]
    if isinstance(value, str):
        return value[:300]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:300]


def run(
    steps: Sequence[Tuple[str, Dict[str, Any], Dict[str, Any]]],
    execute: Callable[[str, Dict[str, Any]], Any],
    assert_step: Callable[[Dict[str, Any], Any], Tuple[bool, Dict[str, Any]]],
    *,
    timeout_ms: int = 60000,
    on_error: str = "stop",
) -> BatchResult:
    """执行已归一化的步骤；失败即停，返回步日志。"""
    if timeout_ms < 100 or timeout_ms > 60000:
        raise ValueError("timeout_ms 取值 100–60000")
    if on_error not in ("stop", "continue"):
        raise ValueError("on_error 只接受 stop / continue")
    started = time.monotonic()
    log: List[Dict[str, Any]] = []
    last_data: Any = None
    for index, (verb, args, expect) in enumerate(steps, 1):
        if (time.monotonic() - started) * 1000 >= timeout_ms:
            return BatchResult(False, log, index, "批量执行超时", last_data)
        row: Dict[str, Any] = {"index": index, "action": verb}
        try:
            data = execute(verb, dict(args))
            last_data = data
            row["result"] = sanitize(data)
        except Exception as exc:
            report_error("plugin.visual_operator.pipeline.execute", exc)
            row.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            log.append(row)
            if on_error == "stop":
                return BatchResult(False, log, index, row["error"], last_data)
            continue
        if expect:
            try:
                passed, detail = assert_step(expect, data)
            except Exception as exc:
                report_error("plugin.visual_operator.pipeline.expect", exc)
                passed, detail = False, {"error": f"{type(exc).__name__}: {exc}"}
            row["expect"] = sanitize(detail)
            if not passed:
                row.update({"ok": False, "error": detail.get("error", "expect 未满足")})
                log.append(row)
                if on_error == "stop":
                    return BatchResult(False, log, index, row["error"], last_data)
                continue
        row["ok"] = True
        log.append(row)
        if (time.monotonic() - started) * 1000 >= timeout_ms:
            return BatchResult(False, log, index, "批量执行超时", last_data)
    return BatchResult(True, log, None, "", last_data)
