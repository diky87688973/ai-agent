# -*- coding: utf-8 -*-
"""Skills 插件：Skills 库（扫描 / 读取）+ `skills` 工具 + 上下文注入。

Skills 走渐进式披露：

- 可用 Skills 清单（名字 + 描述）常驻上下文，模型据此判断该用哪个；
- `auto_load/` 目录下 Skills 的正文始终随上下文携带；
- 其余 Skills 的正文不进上下文，由模型用 `skills action=read` 按需读取。

没有界面交互，唯一对外可见的是上下文分层里的用量（段名与数量）。

配置在插件自己目录下的 `plugin-config.ini`：`[config]` 是 `dir` / `max_file_size`；身份在 `plugin-meta.json`，开关在 `plugins.ini`。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.capabilities.plugins import plugin_config_fields
from agent.config import PROJECT_ROOT, load_ini

from .library import SkillManager
from .tools import build as build_tool

CONFIG_SECTION = "config"
DEFAULT_MAX_FILE_SIZE = 200000
CONFIG_FILE = "plugin-config.ini"
#: 随代码发布的内置 Skills 根；用户外置目录由 [config] dir 指定。
BUILTIN_SKILLS_DIR = PROJECT_ROOT / "skills"

# 注入前缀：让模型一眼看出这段是 Skills 说明，不是用户对话，也不是知识库素材。
# 抬头在清单/常驻正文里拼（library 出口），这里不再叠一次。
CATALOG_PREFIX = ""
# 常驻抬头带 Skills 名，模型一眼看出这是哪个 Skills 的正文，由 library 逐条拼。
RESIDENT_PREFIX = ""
RESOURCE_HEAD = "## 资源目录"


def _config_path() -> Path:
    """本插件的配置文件：`plugins/skills/plugin-config.ini`。

    配置与本插件同目录：内核的 `config.ini` 只含内核设置。
    """
    return Path(__file__).resolve().parent / CONFIG_FILE


def _load_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """读本插件配置的 `[config]` 节：`dir` / `max_file_size`。

    `dir` 是用户外置 Skills 根；未配置时为 `None`。路径存在与否都保留，
    由库里决定能否读取/写入。相对路径按工程根解析。
    """
    parser = load_ini(path if path is not None else _config_path())
    values: Dict[str, str] = {}
    if parser.has_section(CONFIG_SECTION):
        values = {k: str(v or "").strip().strip("'\"")
                  for k, v in parser.items(CONFIG_SECTION)}

    root: Optional[Path] = None
    # 环境变量优先：为测试与 CI 提供独立的外部 Skills 目录入口。
    raw_dir = os.environ.get("AI_AGENT_SKILLS_DIR") or values.get("dir") or ""
    if raw_dir:
        candidate = Path(raw_dir)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        try:
            root = candidate.resolve()
        except OSError:
            root = candidate.absolute()

    try:
        max_size = int(values.get("max_file_size") or DEFAULT_MAX_FILE_SIZE)
    except (TypeError, ValueError):
        max_size = DEFAULT_MAX_FILE_SIZE
    return {"dir": root, "max_file_size": max_size}


def register(ctx: Any) -> List[Callable[[], None]]:
    """插件入口：装配 Skills 库，注册工具、系统提示词章节与提交执行器。"""
    cfg = _load_config()
    library = SkillManager(cfg["dir"], int(cfg["max_file_size"]),
                           builtin_dir=BUILTIN_SKILLS_DIR)
    base = plugin_config_fields(Path(__file__).resolve().parent)
    style_label = base["name"] or "Skills"

    tool = build_tool(library)
    disposers: List[Callable[[], None]] = [
        ctx.register_tool(tool),
        # 资源目录：写入系统提示词章节；Rules 插件后续向同一章节追加自己的行。
        ctx.add_prompt_section(
            RESOURCE_HEAD,
            lambda cid, _lib=library: _resource_directory_lines(_lib),
        ),
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
             # 只数条数：为取长度去把常驻正文全拼一遍是重复开销（每次收集都跑）。
             "count": lambda _cid, _lib=library: _lib.auto_load_count()},
        ),
    ]
    # 上下文分层外观：无面板，经贡献表交给壳层开屏注册。
    disposers.append(ctx.add_ctx_segment_style(label=style_label, color="plum"))
    # 工具卡视图：开屏脚本，不必挂空面板。
    disposers.append(ctx.add_boot_script("ui/tool-view.js"))
    return disposers


def _resource_directory_lines(library: SkillManager) -> List[str]:
    """资源目录正文行；章节标题由 PromptSections 统一添加。"""
    builtin = library.builtin_dir or BUILTIN_SKILLS_DIR
    lines = [f"- 内置skills: {builtin}"]
    external = library.external_dir
    if external and external.is_dir():
        lines.append(f"- 外置skills: {external}")
    elif external:
        lines.append(f"- 外置skills: {external}（不存在）")
    else:
        lines.extend([
            "- 外置skills: 未配置",
            "  外置skills目录为用户skills目录，当前未配置外置skills目录，必要时提醒用户在\"Skills\"插件中配置dir即可",
        ])
    return lines


def _catalog_parts(library: SkillManager) -> List[str]:
    """可用 Skills 清单（没有 Skills → 空列表）。

    抬头由 Skills 库拼（`library.CATALOG_HEAD`）—— 清单正文只有一处来源，
    插件这边不再另拼一份，免得两处抬头各写各的。
    """
    return library.build_registry_message_parts()
