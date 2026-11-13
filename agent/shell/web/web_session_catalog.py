"""HTTP projection of indexed session navigation."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any

from agent.core.error_report import report_error
from agent.mechanisms.session_catalog import PAGE_SIZE, SessionCatalog
from agent.mechanisms.session_store import is_valid_conversation_id
from agent.shell.timefmt import date_group

CATALOG_URL = "/api/chat/session-catalog"
_PROJECT_ID = re.compile(r"[0-9a-f]{32}")
_SECTIONS = frozenset(("recent", "pinned", "projects", "project"))


def _cursor(raw: str, section: str) -> tuple:
    if not raw:
        if section == "projects":
            return "", ""
        return 2**63 - 1, "\uffff"
    if len(raw) > 256:
        raise ValueError("分页位置无效")
    value = json.loads(raw)
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("分页位置无效")
    key, ident = value
    if section == "projects":
        if not isinstance(key, str) or not isinstance(ident, str) or not _PROJECT_ID.fullmatch(ident):
            raise ValueError("分页位置无效")
    elif (not isinstance(ident, str) or ident != ident.strip() or
          not is_valid_conversation_id(ident) or type(key) is not int or not 0 <= key < 2**63):
        raise ValueError("分页位置无效")
    return key, ident


def _read(catalog: SessionCatalog, query: dict[str, str]) -> tuple[int, dict]:
    section = query.get("section", "recent")
    project = query.get("project", "")
    if section not in _SECTIONS or (section == "project" and not _PROJECT_ID.fullmatch(project)):
        raise ValueError("会话分组无效")
    cursor = _cursor(query.get("before", ""), section)
    rows = catalog.page(section, cursor, project)
    page = rows[:PAGE_SIZE]
    more = len(rows) > PAGE_SIZE
    next_before = None
    if more:
        last = page[-1]
        if section == "projects":
            next_before = [last["name"], last["id"]]
        else:
            next_before = [last["cursor_key"] if section != "project" else 0, last["cid"]]
    now = time.time()
    if section != "projects":
        page = [{
            "id": row["cid"], "title": row["title"], "project": row["project"],
            "pinned": row["pinned"] is not None, "activity": row["activity"] / 1e9,
            "date_group": date_group(row["activity"] / 1e9, now),
        } for row in page]
    state = catalog.state
    return 200, {"ok": True, "items": page, "next_before": next_before,
                 "preparing": state == "preparing",
                 "warning": "会话目录更新失败，请重试" if state == "error" else ""}


def _write(catalog: SessionCatalog, body: dict[str, Any]) -> tuple[int, dict]:
    if not isinstance(body, dict):
        raise ValueError("请求格式无效")
    operation = body.get("operation")
    project = body.get("project", "")
    if not isinstance(project, str):
        raise ValueError("项目无效")
    if operation in ("create", "rename", "delete"):
        if operation != "create" and not _PROJECT_ID.fullmatch(project):
            raise ValueError("项目无效")
        name = body.get("name", "")
        if operation != "delete":
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60 or any(ord(c) < 32 for c in name):
                raise ValueError("请输入 1–60 个字符的项目名称")
            name = name.strip()
        project = catalog.change_project(operation, project, name)
        return 200, {"ok": True, "project": project, "name": name}
    cid = body.get("conversation_id")
    if not isinstance(cid, str) or cid != cid.strip() or not is_valid_conversation_id(cid):
        raise ValueError("会话无效")
    if operation == "move" and (project == "" or _PROJECT_ID.fullmatch(project)):
        catalog.organize(cid, "project", project or None)
    elif operation == "pin" and isinstance(body.get("pinned"), bool):
        catalog.organize(cid, "pinned", body["pinned"])
    else:
        raise ValueError("会话操作无效")
    return 200, {"ok": True}


def session_catalog_response(catalog: SessionCatalog | None, query: dict[str, str],
                             body: dict[str, Any] | None = None) -> tuple[int, dict]:
    if catalog is None:
        return 503, {"ok": False, "error": "会话目录不可用"}
    catalog.start()
    if not catalog.initialized.is_set():
        return 503, {"ok": False, "preparing": catalog.state == "preparing",
                     "error": "正在整理会话列表" if catalog.state == "preparing" else "会话目录暂不可用"}
    try:
        return _read(catalog, query) if body is None else _write(catalog, body)
    except ValueError as exc:
        return 400, {"ok": False, "error": str(exc) or "请求格式无效"}
    except LookupError as exc:
        return 404, {"ok": False, "error": str(exc)}
    except sqlite3.IntegrityError:
        return 409, {"ok": False, "error": "项目名称已存在"}
    except (OSError, sqlite3.Error) as exc:
        report_error("web_session_catalog", exc)
        return 503, {"ok": False, "error": "会话目录暂不可用，请重试"}
