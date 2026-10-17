# -*- coding: utf-8 -*-
"""Skills 插件：Skills 库（扫描 / 读取 / 复制）+ `skill_manage` 工具 + 上下文注入。

Skills 走**渐进式披露**：

- 可用 Skills 清单（名字 + 描述）常驻上下文，模型据此判断该用哪个；
- `auto_load/` 目录下 Skills 的正文始终随上下文携带；
- 其余 Skills 的正文**不进上下文**，由模型用 `skill_manage action=read` 按需读取。

没有界面交互，唯一对外可见的是上下文分层里的用量（段名与数量）。

配置在插件自己目录下的 `plugin-config.ini`：`[base]` 是身份与开关，`[ext]` 是 `dir` / `max_file_size`。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.capabilities.plugins import plugin_config_fields
from agent.config import PROJECT_ROOT, load_ini

from .library import SkillManager
from .tools import build as build_tool
from .tools import build_executors

CONFIG_SECTION = "ext"
DEFAULT_MAX_FILE_SIZE = 200000
CONFIG_FILE = "plugin-config.ini"

# 注入前缀：让模型一眼看出这段是 Skills 说明，不是用户对话，也不是知识库素材。
# 抬头在清单/常驻正文里拼（library 出口），这里不再叠一次。
CATALOG_PREFIX = ""
# 常驻抬头带 Skills 名，模型一眼看出这是哪个 Skills 的正文，由 library 逐条拼。
RESIDENT_PREFIX = ""


def _config_path() -> Path:
    """本插件的配置文件：`plugins/skills/plugin-config.ini`。

    配置与本插件同目录：内核的 `config.ini` 只含内核设置。
    """
    return Path(__file__).resolve().parent / CONFIG_FILE


def _load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """读本插件配置的 `[ext]` 节：`dir` / `max_file_size`。

    `dir` 缺失、不存在或不是目录时为 `None`，于是 Skills 库为空、注入为空 ——
    判定失败时静默降级，不报错。相对路径按工程根解析。
    文件不在就用缺省值。
    """
    parser = load_ini(path if path is not None else _config_path())
    values: Dict[str, str] = {}
    if parser.has_section(CONFIG_SECTION):
        values = {k: str(v or "").strip().strip("'\"")
                  for k, v in parser.items(CONFIG_SECTION)}

    root: Optional[Path] = None
    # 环境变量优先：给测试/CI 一个换数据位的口子（与数据根同一套做法）。
    raw_dir = os.environ.get("AI_AGENT_SKILLS_DIR") or values.get("dir") or ""
    if raw_dir:
        candidate = Path(raw_dir)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        try:
            if candidate.is_dir():
                root = candidate.resolve()
        except OSError:
            root = None

    try:
        max_size = int(values.get("max_file_size") or DEFAULT_MAX_FILE_SIZE)
    except (TypeError, ValueError):
        max_size = DEFAULT_MAX_FILE_SIZE
    return {"dir": root, "max_file_size": max_size}


def register(ctx: Any) -> List[Callable[[], None]]:
    """插件入口：装配 Skills 库，注册工具、两条上下文注入与提交执行器。"""
    cfg = _load_config()
    library = SkillManager(cfg["dir"], int(cfg["max_file_size"]))
    base = plugin_config_fields(Path(__file__).resolve().parent)
    style_label = base["name"] or "Skills"

    tool = build_tool(library)
    disposers: List[Callable[[], None]] = [
        ctx.register_tool(tool),
        # 清单：只有名字与描述（渐进式披露第一层）。
        ctx.add_context_source(
            lambda cid, _lib=library: _catalog_parts(_lib),
            {"label": "Skills 清单", "prefix": CATALOG_PREFIX,
             # 取数口按 `fn(conversation_id)` 调用；Skills 清单与会话无关，用闭包吞掉这个参数。
             "count": lambda _cid, _lib=library: len(_lib.list_skills())},
        ),
        # 常驻正文：`auto_load/` 目录下的 Skills（第二层，始终携带）。
        ctx.add_context_source(
            lambda cid, _lib=library: _lib.build_auto_load_messages(),
            {"label": "Skills 常驻", "prefix": RESIDENT_PREFIX,
             # 只数条数：为取长度去把常驻正文全拼一遍是白烧（每次收集都跑）。
             "count": lambda _cid, _lib=library: _lib.auto_load_count()},
        ),
    ]
    # 提交执行器登记到宿主的执行器注册表：`commit_write` 提交时按工具名取。
    disposers.append(
        ctx.add_executor("skill_manage", build_executors(library)["skill_manage"]))
    # 上下文分层外观：无面板，经贡献表交给壳层开屏注册。
    disposers.append(ctx.add_ctx_segment_style(label=style_label, color="plum"))
    # 工具卡视图：开屏脚本，不必挂空面板。
    disposers.append(ctx.add_boot_script("ui/tool-view.js"))
    return disposers


def _catalog_parts(library: SkillManager) -> List[str]:
    """可用 Skills 清单（没有 Skills → 空列表）。

    抬头由 Skills 库拼（`library.CATALOG_HEAD`）—— 清单正文只有一处来源，
    插件这边不再另拼一份，免得两处抬头各写各的。
    """
    return library.build_registry_message_parts()
