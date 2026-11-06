"""任务来源、时域图与本地控件的输入契约。"""
from __future__ import annotations

import math
import re


def validate_extra(kind: str, data: dict, fields, array, text, number, identifier) -> None:
    if kind == "tasks":
        fields(data, {"batch", "task_ids"}, "data")
        text(data["batch"], "batch", 100)
        ids = array(data["task_ids"], "task_ids", 100)
        for item in ids:
            identifier(item, "task_id")
        if len(set(ids)) != len(ids):
            raise ValueError("任务 ID 不能重复")
    elif kind == "mermaid":
        fields(data, {"code"}, "data")
        code = text(data["code"], "code", 16000).strip()
        if not re.match(r"^(?:flowchart\s+(?:TD|TB|BT|LR|RL)\b|sequenceDiagram\b)", code):
            raise ValueError("仅允许 Mermaid flowchart 与 sequenceDiagram")
        if len(code.splitlines()) > 150 or re.search(r"%%\{|^---|\b(?:click|style|classDef|linkStyle)\b|https?:|javascript:|data:|file:|url\s*\(|<|>",
                                                    code.replace("-->>", "").replace("->>", "").replace("-->", ""), re.M | re.I):
            raise ValueError("图定义不能包含配置指令、HTML、链接或点击动作，且最多150行")
    elif kind == "controls":
        fields(data, {"fields"}, "data")
        controls(array(data["fields"], "fields", 12), fields, array, text, number, identifier)
    else:
        key = "events" if kind == "timeline" else "tasks" if kind == "gantt" else "items"
        fields(data, {"unit", key}, "data")
        text(data["unit"], "unit", 32)
        for item in array(data[key], key, 100, 0):
            if kind == "timeline":
                fields(item, {"label", "at", "detail"}, "event")
                number(item["at"], "at")
                text(item["detail"], "detail", 1000)
            else:
                fields(item, {"label", "start", "end", "status"}, "period")
                if number(item["end"], "end") < number(item["start"], "start"):
                    raise ValueError("end 不能早于 start")
                if item["status"] not in ("waiting", "running", "succeeded", "failed", "cancelled"):
                    raise ValueError("无效的时间段状态")
            text(item["label"], "label")


def controls(items, fields, array, text, number, identifier) -> None:
    ids = set()
    for field in items:
        if not isinstance(field, dict):
            raise ValueError("field 必须是对象")
        kind = field.get("type")
        expected = {"id", "label", "type", "value"}
        expected |= {"options"} if kind in ("select", "tabs") else {"min", "max", "step"} if kind == "range" else set()
        fields(field, expected, "field")
        key = identifier(field["id"], "field.id")
        if key in ids:
            raise ValueError("控件 id 不能重复")
        ids.add(key)
        text(field["label"], "field.label")
        if kind == "toggle":
            if type(field["value"]) is not bool:
                raise ValueError("开关值必须是布尔值")
        elif kind == "range":
            for name in ("min", "max", "step", "value"):
                number(field[name], name)
            if field["min"] >= field["max"] or field["step"] <= 0 or not field["min"] <= field["value"] <= field["max"]:
                raise ValueError("滑块要求 min < max、step > 0 且值在区间内")
            steps = (field["max"] - field["min"]) / field["step"]
            position = (field["value"] - field["min"]) / field["step"]
            if not math.isfinite(steps) or steps > 1000000 or not math.isfinite(position):
                raise ValueError("滑块最多允许1000000步")
            if not math.isclose(position, round(position), abs_tol=1e-8, rel_tol=0):
                raise ValueError("滑块值必须与 min 和 step 对齐")
        elif kind in ("select", "tabs"):
            values = []
            for option in array(field["options"], "options", 20):
                fields(option, {"value", "label"}, "option")
                values.append(identifier(option["value"], "option.value"))
                text(option["label"], "option.label")
            if len(set(values)) != len(values) or field["value"] not in values:
                raise ValueError("选项值必须唯一且包含当前选中值")
        else:
            raise ValueError("控件只允许 select/toggle/tabs/range")
