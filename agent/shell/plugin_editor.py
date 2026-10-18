# -*- coding: utf-8 -*-
"""插件配置的可编辑区域：`[base]` 由宿主维护，设置页只读写插件自己的节。

插件配置的元数据（`id` / `name` / `desc` / `icon` / `version` / `enable`）写在
`[base]`。它是插件声明与装载开关，设置页既不该展示也不该回写 —— 一次误编辑
就能让插件改名、失联或无法装载。

可编辑区域按插件形态取：

- 声明了 `settings-schema.json` 的插件（多模型）：按 schema 把 `[model:*]` 等
  节渲染成结构化表单，保存时只替换这些节；
- 只有 `[ext]` 的插件（知识库 / Skills / 语音）：正文即 `[ext]` 的内容，
  节头不展示；
- 其余情形（没有 `[ext]`、也没声明 schema）：除 `[base]` 外的节都算插件自己的，
  多节时保留节头，否则无法区分多个条目。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from agent.shell.ini_sections import (
    append_section,
    newline,
    replace_sections,
    section_at,
    section_body,
    section_names,
)

BASE = "base"
SCHEMA_FILE = "settings-schema.json"
KEY_RE = re.compile(r"^(\s*)([A-Za-z0-9_-]+)(\s*=\s*)(.*)$")
NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
SECTION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_:-]*")
_FIELD_KINDS = ("text", "secret", "number", "bool", "enum")


def load_schema(folder: Path) -> Optional[Dict[str, Any]]:
    """读插件目录下的结构化表单声明；缺失或结构不完整返回 None。

    坏 schema 不阻断设置页：退回文本编辑，插件仍可配置。
    """
    path = Path(folder) / SCHEMA_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        # 读不出或不是合法 JSON 就是没声明，设置页退回文本编辑。
        return None
    if not isinstance(data, dict) or str(data.get("kind") or "") != "sections":
        return None
    prefix = str(data.get("section_prefix") or "").strip()
    identity = data.get("identity")
    raw_fields = data.get("fields")
    if not prefix or not isinstance(identity, dict) or not isinstance(raw_fields, list):
        return None
    id_key = str(identity.get("key") or "").strip()
    if not id_key:
        return None
    fields: List[Dict[str, Any]] = []
    for item in raw_fields:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        kind = str(item.get("kind") or "text").strip()
        label = str(item.get("label") or key).strip()
        if not key or kind not in _FIELD_KINDS:
            continue
        field = {
            "key": key,
            "kind": kind,
            "label": label,
            "hint": str(item.get("hint") or ""),
            "placeholder": str(item.get("placeholder") or ""),
            "default": str(item.get("default") or ""),
        }
        if kind == "enum":
            options = [
                {"value": str(opt.get("value") or ""), "label": str(opt.get("label") or opt.get("value") or "")}
                for opt in (item.get("options") or [])
                if isinstance(opt, dict) and str(opt.get("value") or "").strip()
            ]
            if not options:
                continue
            field["options"] = options
        if item.get("min") is not None:
            try:
                field["min"] = int(item["min"])
            except (TypeError, ValueError):
                # 边界写坏了只是少一条校验，字段本身仍要能编辑。
                pass
        show_if = item.get("show_if")
        if isinstance(show_if, dict) and str(show_if.get("key") or "").strip():
            field["show_if"] = {
                "key": str(show_if.get("key")).strip(),
                "equals": str(show_if.get("equals") or ""),
            }
        fields.append(field)
    if not fields:
        return None
    return {
        "kind": "sections",
        "title": str(data.get("title") or "配置"),
        "section_prefix": prefix,
        "add_label": str(data.get("add_label") or "添加"),
        "empty_text": str(data.get("empty_text") or ""),
        "identity": {
            "key": id_key,
            "label": str(identity.get("label") or id_key),
            "hint": str(identity.get("hint") or ""),
        },
        "fields": fields,
    }


def build_editor(text: str, folder: Path) -> Dict[str, Any]:
    """把插件配置文本转成设置页可渲染的编辑视图。"""
    schema = load_schema(folder)
    if schema:
        return {
            "kind": "sections",
            "schema": schema,
            "groups": _mask_secrets(parse_groups(text, schema), schema),
        }
    sections = text_sections(text)
    show_headers = len(sections) > 1
    return {
        "kind": "text",
        "text": render_text(text, sections, show_headers=show_headers),
        "sections": sections,
        "show_headers": show_headers,
    }


def text_sections(text: str) -> List[str]:
    """文本编辑器负责的节：有 `[ext]` 就只认它，否则除 `[base]` 外的全部。

    只有 `[base]` 的配置还没有插件自己的节，编辑器按 `[ext]` 新建。
    """
    names = section_names(text)
    ext = [name for name in names if name.lower() == "ext"]
    if ext:
        return ext
    rest = [name for name in names if name.lower() != BASE]
    return rest or ["ext"]


def render_text(text: str, sections: Iterable[str], *, show_headers: bool) -> str:
    """把若干节的正文拼成一段可编辑文本；单节模式不输出节头。"""
    lines = text.splitlines(keepends=True)
    blocks: List[str] = []
    for name in sections:
        body = section_body(lines, name)
        if body is None:
            continue
        body = _trim_blank(body)
        if show_headers:
            blocks.append(f"[{name}]\n" + "".join(_lf(line) for line in body))
        else:
            blocks.append("".join(_lf(line) for line in body))
    if not blocks:
        return ""
    return "\n\n".join(block.rstrip("\n") for block in blocks) + "\n"


def _mask_secrets(groups: List[Dict[str, Any]], schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """密钥字段只回显"有没有配过"：明文不出接口，保存时留空表示不改。

    与宿主设置页的 `secret` 控件同一套契约；文本编辑模式不做这件事 ——
    那里用户看到的就是整份配置，掩码会让他保存时把密钥覆盖成星号。
    """
    secret_keys = [str(item["key"]).lower() for item in schema["fields"]
                   if item["kind"] == "secret"]
    if not secret_keys:
        return groups
    masked: List[Dict[str, Any]] = []
    for group in groups:
        values = dict(group.get("values") or {})
        configured: Dict[str, bool] = {}
        for key in secret_keys:
            configured[key] = bool(str(values.get(key) or "").strip())
            values[key] = ""
        item = dict(group)
        item["values"] = values
        item["configured"] = configured
        masked.append(item)
    return masked


def parse_groups(text: str, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """按 schema 读节 → 结构化分组。

    注释跟着它下面那个键走（`comments`），保存时原样写回；第一个键之前的
    注释进 `notes`。不做这件事的话，从表单点一次保存就会把用户在节里写的
    说明全都抹掉 —— 结构化的代价不能是"注释静默消失"。
    """
    prefix = str(schema["section_prefix"])
    fields = {str(item["key"]).lower() for item in schema["fields"]}
    identity = str(schema["identity"]["key"]).lower()
    lines = text.splitlines(keepends=True)
    groups: List[Dict[str, Any]] = []
    for name in section_names(text):
        if not name.startswith(prefix):
            continue
        group_id = name[len(prefix):].strip()
        if not NAME_RE.fullmatch(group_id):
            continue
        body = section_body(lines, name) or []
        values: Dict[str, str] = {}
        notes: List[str] = []
        comments: Dict[str, List[str]] = {}
        extras: List[str] = []
        pending: List[str] = []
        seen_key = False
        for raw in body:
            line = raw.rstrip("\r\n")
            stripped = line.strip()
            if not stripped or stripped[0] in ";#":
                (pending if seen_key else notes).append(line)
                continue
            matched = KEY_RE.match(line)
            if matched is None:
                continue
            seen_key = True
            key = matched.group(2)
            low = key.lower()
            if low == identity:
                pending = []
                continue
            if low in fields:
                values[low] = matched.group(4).strip()
                if pending:
                    comments[low] = list(pending)
            else:
                extras.extend(x for x in pending if x.strip())
                extras.append(stripped)
            pending = []
        # 末尾注释与最后一个键无关，但要留住：并进 extras 的尾部。
        extras.extend(x for x in pending if x.strip())
        groups.append({
            "id": group_id,
            "notes": "\n".join(notes).strip("\n"),
            "values": values,
            "comments": comments,
            "extras": extras,
        })
    return groups


def merge_text(text: str, submitted: str, sections: Iterable[str]) -> Tuple[Optional[str], str]:
    """文本编辑器保存：替换/删除这些节，`[base]` 与其它节逐字节保留。

    返回 `(新文本, "")`；校验失败返回 `(None, 原因)`。
    """
    allowed = list(sections)
    single = len(allowed) == 1
    parsed, error = _parse_submitted(submitted, allowed, single)
    if error:
        return None, error
    result = _merge_parsed(text, parsed, allowed)
    return result, ""


def merge_groups(text: str, groups: Any, schema: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """结构化表单保存：按 schema 重写 `[model:*]` 等节。

    密钥字段留空 = 保留文件里原来的值：界面拿到的是掩码（空串），
    回写空串会把密钥清掉，下一次请求才在网关那里报鉴权失败。
    """
    if not isinstance(groups, list) or not groups:
        return None, "至少保留一条配置"
    prefix = str(schema["section_prefix"])
    lines = text.splitlines(keepends=True)
    existing = [name for name in section_names(text) if name.startswith(prefix)]
    previous: Dict[str, Tuple[Dict[str, str], List[str]]] = {}
    for name in existing:
        body = section_body(lines, name) or []
        previous[name[len(prefix):].strip().lower()] = _scan_section(body, schema)
    parsed: List[Tuple[str, List[str]]] = []
    seen: set = set()
    for index, group in enumerate(groups, start=1):
        if not isinstance(group, dict):
            return None, "配置项格式不对"
        group_id = str(group.get("id") or "").strip()
        if not group_id:
            return None, f"第 {index} 条的 ID 不能为空"
        if not NAME_RE.fullmatch(group_id):
            return None, f"第 {index} 条的 ID 只能包含字母、数字、下划线与短横"
        low = group_id.lower()
        if low in seen:
            return None, f"ID 重复：{group_id}"
        seen.add(low)
        values = group.get("values")
        if not isinstance(values, dict):
            return None, f"{group_id} 的配置项格式不对"
        old_values, old_extras = previous.get(low, ({}, []))
        body, error = _group_body(group, schema, values, old_extras, old_values)
        if error:
            return None, f"{group_id}：{error}"
        parsed.append((prefix + group_id, body))
    result = _merge_parsed(text, parsed, existing)
    return result, ""


def _group_body(group: Dict[str, Any], schema: Dict[str, Any],
                submitted: Dict[str, Any],
                extras: List[str], previous: Dict[str, str]) -> Tuple[List[str], str]:
    values = submitted
    fields = list(schema["fields"])
    by_key = {str(item["key"]): item for item in fields}
    for key in values:
        if str(key) not in by_key:
            return [], f"未知配置项 {key}"
    body: List[str] = []
    notes = str(group.get("notes") or "").strip()
    if notes:
        body.extend(notes.splitlines())
    comments = group.get("comments") if isinstance(group.get("comments"), dict) else {}
    effective = {
        str(field["key"]): str(values.get(str(field["key"])) or field.get("default") or "")
        for field in fields
    }
    for field in fields:
        key = str(field["key"])
        if not _visible(field, effective):
            continue
        value = str(values.get(key) or "").strip()
        kind = str(field["kind"])
        if kind == "secret" and not value:
            # 掩码字段留空 = 不改。没有旧值时就不写这个键（不写空串）。
            value = str(previous.get(key.lower()) or "").strip()
        if kind == "bool":
            body.extend(_comment_lines(comments.get(key.lower())))
            body.append(f"{key} = {_bool_text(value, field)}")
            continue
        if not value:
            value = str(field.get("default") or "")
        if not value:
            continue
        if "\n" in value or "\r" in value:
            return [], f"{field['label']}不能换行"
        if kind == "enum":
            allowed = [str(opt["value"]) for opt in field.get("options") or []]
            if value not in allowed:
                return [], f"{field['label']}不在可选范围内"
        elif kind == "number":
            try:
                number = int(value)
            except (TypeError, ValueError):
                return [], f"{field['label']}要填整数"
            floor = field.get("min")
            if floor is not None and number < int(floor):
                return [], f"{field['label']}不能小于 {floor}"
            value = str(number)
        body.extend(_comment_lines(comments.get(key.lower())))
        body.append(f"{key} = {value}")
    body.extend(extras)
    return body, ""


def _comment_lines(lines: Any) -> List[str]:
    """键前面那几行注释（空行丢掉，避免重复保存越攒越空）。"""
    if not isinstance(lines, list):
        return []
    return [str(line) for line in lines if str(line).strip()]


def _bool_text(value: str, field: Dict[str, Any]) -> str:
    text = str(value or "").strip().lower()
    if not text:
        text = str(field.get("default") or "").strip().lower()
    return "0" if text in ("0", "false", "off", "no", "") else "1"


def _visible(field: Dict[str, Any], values: Dict[str, str]) -> bool:
    condition = field.get("show_if")
    if not isinstance(condition, dict):
        return True
    return str(values.get(str(condition.get("key")) or "") or "") == str(condition.get("equals") or "")


def _scan_section(body: List[str], schema: Dict[str, Any]) -> Tuple[Dict[str, str], List[str]]:
    """读一节：schema 内的键进 `values`，其余键原样留在 `extras`。

    `id` 是节名，正文里不出现，目录解析也不把它当配置项。
    """
    known = {str(item["key"]).lower() for item in schema["fields"]}
    identity = str(schema["identity"]["key"]).lower()
    values: Dict[str, str] = {}
    extras: List[str] = []
    for raw in body:
        line = raw.rstrip("\r\n")
        stripped = line.strip()
        if not stripped or stripped[0] in ";#":
            continue
        matched = KEY_RE.match(line)
        if matched is None:
            continue
        key = matched.group(2).lower()
        if key == identity:
            continue
        if key in known:
            values[key] = matched.group(4).strip()
        else:
            extras.append(stripped)
    return values, extras


def _parse_submitted(submitted: str, allowed: List[str],
                     single: bool) -> Tuple[List[Tuple[str, List[str]]], str]:
    text = str(submitted or "")
    if "\x00" in text:
        return [], "配置内容不合法"
    if single:
        name = allowed[0]
        for line in text.splitlines():
            if section_at(line) is not None:
                return [], "这一项只填键值，节头由系统维护"
        return [(name, text.splitlines())], ""
    lines = text.splitlines()
    parsed: List[Tuple[str, List[str]]] = []
    current: Optional[str] = None
    body: List[str] = []
    seen: set = set()
    for line in lines:
        name = section_at(line)
        if name is not None:
            if current is not None:
                parsed.append((current, body))
            if name.lower() == BASE:
                return [], "`[base]` 由系统维护，不能在这里修改"
            if not SECTION_RE.fullmatch(name):
                return [], f"节名不合法：{name}"
            low = name.lower()
            if low in seen:
                return [], f"节重复：{name}"
            seen.add(low)
            current = name
            body = []
            continue
        if current is None:
            if line.strip():
                return [], "内容要以 [节名] 开头"
            continue
        body.append(line)
    if current is not None:
        parsed.append((current, body))
    if not parsed:
        return [], "配置内容为空"
    return parsed, ""


def _merge_parsed(text: str, parsed: List[Tuple[str, List[str]]],
                  allowed: List[str]) -> str:
    nl = newline(text) if text else "\n"
    existing = {name.lower(): name for name in section_names(text)}
    replaced: List[Tuple[str, List[str]]] = []
    added: List[Tuple[str, List[str]]] = []
    for name, body in parsed:
        real = existing.get(name.lower())
        if real is not None:
            replaced.append((real, body))
        else:
            added.append((name, body))
    removed = [
        existing[name.lower()] for name in allowed
        if name.lower() not in {item[0].lower() for item in parsed}
    ]
    result = replace_sections(text, replaced, remove=removed)
    for name, body in added:
        result = append_section(result, name, body)
    if not result.endswith(("\n", "\r")) and result:
        result += nl
    return result


def _trim_blank(lines: List[str]) -> List[str]:
    start, end = 0, len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _lf(line: str) -> str:
    return str(line).rstrip("\r\n") + "\n"
