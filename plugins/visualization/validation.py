"""组件文档的唯一输入边界；返回独立 JSON 快照。"""
from __future__ import annotations

import json
import math
import re

from .validation_extra import validate_extra

KINDS = ("proportion", "tasks", "mermaid", "flow", "progress", "bar", "line", "donut",
         "timeline", "gantt", "waterfall", "controls", "table")
MAX_BYTES = 65536


def fields(value: object, expected: set[str], path: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{path} 必须且只能包含：{', '.join(sorted(expected))}")
    return value


def text(value: object, path: str, limit: int = 160) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{path} 必须是 1–{limit} 字的非空文本")
    return value


def number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{path} 必须是有限数值")
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or abs(value) > 1e100:
        raise ValueError(f"{path} 必须是绝对值不超过 1e100 的有限数值")
    return value


def array(value: object, path: str, maximum: int, minimum: int = 1) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{path} 必须是 {minimum}–{maximum} 项的数组")
    return value


def identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise ValueError(f"{path} 必须是 1–64 位字母、数字、下划线或短横线")
    return value


def flow(data: dict) -> None:
    fields(data, {"nodes", "edges"}, "data")
    nodes = array(data["nodes"], "nodes", 60)
    ids = set()
    for node in nodes:
        fields(node, {"id", "label"}, "node")
        key = identifier(node["id"], "node.id")
        if key in ids:
            raise ValueError(f"重复节点：{key}")
        ids.add(key)
        text(node["label"], "node.label")
    for edge in array(data["edges"], "edges", 120, 0):
        fields(edge, {"source", "target"}, "edge")
        identifier(edge["source"], "edge.source")
        identifier(edge["target"], "edge.target")
        if edge["source"] not in ids or edge["target"] not in ids:
            raise ValueError("edge 的 source/target 必须引用已声明的节点")


def items(data: dict, kind: str) -> None:
    fields(data, {"items"}, "data")
    values = []
    for item in array(data["items"], "items", 100, 0):
        fields(item, {"label", "value", "total"} if kind == "progress"
               else {"label", "value"}, "item")
        text(item["label"], "item.label")
        value = number(item["value"], "item.value")
        values.append(value)
        if kind == "progress":
            total = number(item["total"], "item.total")
            if total <= 0 or not 0 <= value <= total:
                raise ValueError("进度要求 total > 0 且 0 ≤ value ≤ total")
        elif kind in ("proportion", "donut") and value < 0:
            raise ValueError("比例值不能为负")
    if values and kind in ("proportion", "donut") and (not math.isfinite(sum(values)) or sum(values) <= 0):
        raise ValueError("比例总量必须是大于 0 的有限数值")


def line(data: dict) -> None:
    fields(data, {"labels", "series"}, "data")
    labels = array(data["labels"], "labels", 200)
    for label in labels:
        text(label, "labels[]")
    for series in array(data["series"], "series", 8):
        fields(series, {"label", "values"}, "series")
        text(series["label"], "series.label")
        values = array(series["values"], "series.values", 200)
        if len(values) != len(labels):
            raise ValueError("series.values 长度必须与 labels 一致")
        for value in values:
            number(value, "series.values[]")


def table(data: dict) -> None:
    fields(data, {"columns", "rows"}, "data")
    keys = set()
    for column in array(data["columns"], "columns", 20):
        fields(column, {"key", "label"}, "column")
        key = identifier(column["key"], "column.key")
        if key in keys:
            raise ValueError(f"重复列：{key}")
        keys.add(key)
        text(column["label"], "column.label")
    for row in array(data["rows"], "rows", 500, 0):
        fields(row, keys, "row")
        for value in row.values():
            if value is None or isinstance(value, bool):
                continue
            if isinstance(value, str):
                if len(value) > 1000:
                    raise ValueError("表格单元格最多 1000 字")
            else:
                number(value, "cell")


def validate_document(value: object) -> dict:
    doc = fields(value, {"panel_id", "revision", "operation", "kind", "title", "summary", "data"}, "document")
    identifier(doc["panel_id"], "panel_id")
    if type(doc["revision"]) is not int or not 1 <= doc["revision"] <= 1000000:
        raise ValueError("revision 必须是 1–1000000 的整数")
    if doc["operation"] not in ("upsert", "remove"):
        raise ValueError("operation 必须是 upsert 或 remove")
    kind = doc["kind"]
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("不支持的组件类型")
    text(doc["title"], "title", 120)
    text(doc["summary"], "summary", 2000)
    try:
        encoded = json.dumps(doc, ensure_ascii=False, allow_nan=False)
        size = len(encoded.encode("utf-8"))
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("组件文档必须是有效 JSON") from exc
    if size > MAX_BYTES:
        raise ValueError("组件文档不能超过 64 KiB")
    if doc["operation"] == "remove":
        fields(doc["data"], set(), "data")
    elif kind in ("progress", "proportion", "donut", "bar"):
        items(doc["data"], kind)
    elif kind in ("flow", "line", "table"):
        {"flow": flow, "line": line, "table": table}[kind](doc["data"])
    else:
        validate_extra(kind, doc["data"], fields, array, text, number, identifier)
    return json.loads(encoded)
