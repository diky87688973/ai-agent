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

from agent.config import PROJECT_ROOT, load_ini

from .library import SkillManager
from .tools import build as build_tool

CONFIG_SECTION = "config"
DEFAULT_MAX_FILE_SIZE = 200000
CONFIG_FILE = "plugin-config.ini"
#: 随代码发布的内置 Skills 根；用户外置目录由 [config] dir 指定。
BUILTIN_SKILLS_DIR = PROJECT_ROOT / "skills"


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


def make_runtime(ctx: Any) -> SkillManager:
    """装配期构造 Skills 库：外置目录 + 单文件上限 + 内置目录。"""
    cfg = _load_config()
    return SkillManager(cfg["dir"], int(cfg["max_file_size"]),
                        builtin_dir=BUILTIN_SKILLS_DIR)


def make_tool(ctx: Any, runtime: SkillManager) -> Any:
    """`skills` 工具：读写都交给库，工具自身只做参数转发。"""
    return build_tool(runtime)


def make_catalog_source(ctx: Any, runtime: SkillManager) -> Callable[..., Any]:
    """清单注入源：只有名字与描述（渐进式披露第一层）。"""
    def source(cid: str) -> Any:
        return _catalog_parts(runtime)
    return source


def make_resident_source(ctx: Any, runtime: SkillManager) -> Callable[..., Any]:
    """常驻正文注入源：`auto_load/` 下的 Skills（第二层，始终携带）。"""
    def source(cid: str) -> Any:
        return runtime.build_auto_load_messages()
    return source


def make_prompt_section(ctx: Any, runtime: SkillManager) -> Callable[[str], List[str]]:
    """`## 资源目录` 章节里本插件的正文行。"""
    def section(cid: str) -> List[str]:
        return _resource_directory_lines(runtime)
    return section


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
