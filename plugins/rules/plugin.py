# -*- coding: utf-8 -*-
"""Rules 插件：`<项目根>/rules` 下的每个 `.md` 作为一条系统消息注入。

规则目录固定，没有配置项、没有勾选、没有面板 —— 目录里有什么就注入什么，
一个文件对一条系统消息，抬头是 `【用户规则 Rules <相对路径>】`。

注入走 `ctx.add_context_source`：管线每一步组装请求时把本插件产出的文本
刷进上下文的插件段。段名与主体数量（文件数）随注入源一起声明，界面据此
在上下文视图里显示用量。

规则目录与插件目录是两回事：插件代码在 `plugins/rules/`，规则文件在
`<项目根>/rules/`（与 `skills/` 平级）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.config import PROJECT_ROOT
from agent.core.error_report import report_error

__all__ = [
    "INJECT_PREFIX",
    "MAX_RULE_BYTES",
    "RESOURCE_HEAD",
    "RULES_DIR",
    "SEGMENT_LABEL",
    "RulesRuntime",
    "register",
]

#: 系统提示词章节标题（与 Skills 插件同一标题，正文按清单位次合并）。
RESOURCE_HEAD = "## 资源目录"

#: 规则根：工程根下的 `rules/`，与 `skills/` 平级。不提供配置项。
RULES_DIR = PROJECT_ROOT / "rules"

#: 注入抬头：模型靠这一行认出「这是用户立的规矩」，不是对话内容。
INJECT_PREFIX = "【用户规则 Rules {rel}】"

#: 上下文段名（界面那一行显示的字）。
SEGMENT_LABEL = "Rules"

#: 单文件字节上限。超过就跳过该文件，并留一条结构化错误 —— 静默丢规则
#: 比读不出来更难查。
MAX_RULE_BYTES = 200000

#: 只收这一种扩展名：规则是可读的条款，不是脚本或数据。
RULE_SUFFIX = ".md"

#: 段色：让 Rules 段与其它插件段区分开。
SEGMENT_COLOR = "green"


def _hidden(rel: Path) -> bool:
    """路径任一段以 `.` 开头即视为隐藏。"""
    return any(part.startswith(".") for part in rel.parts)


class RulesRuntime:
    """规则目录的只读访问层：扫描、读取、组包。

    只认两件事：根目录与单文件上限。目录不存在时全部操作返回空 ——
    规则是增强项，缺目录不该让装配报错。
    """

    def __init__(self, root: Optional[Any] = None,
                 max_bytes: int = MAX_RULE_BYTES) -> None:
        self.root: Optional[Path] = (
            Path(root).resolve() if root is not None else RULES_DIR.resolve()
        )
        self.max_bytes = int(max_bytes)
        #: 正文缓存：键是 `(路径, mtime_ns, 大小)`。一趟装配会读多次，
        #: 文件一改（mtime/大小变）缓存自动失效。
        self._cache: Dict[Tuple[str, int, int], str] = {}

    @property
    def enabled(self) -> bool:
        """目录存在即启用；不存在就什么都不注入。"""
        return bool(self.root is not None and self.root.is_dir())

    # ── 扫描 ──

    def rule_files(self) -> List[Path]:
        """列出可注入的规则文件：递归、只收 `.md`、跳过隐藏段与 `__pycache__`。

        按相对路径排序：注入顺序稳定，模型看到的条目次序不会每趟乱跳。
        """
        if not self.enabled or self.root is None:
            return []
        out: List[Path] = []
        try:
            for path in sorted(self.root.rglob("*" + RULE_SUFFIX)):
                if not path.is_file():
                    continue
                try:
                    rel = path.relative_to(self.root)
                except ValueError:
                    continue
                if _hidden(rel) or "__pycache__" in rel.parts:
                    continue
                out.append(path)
        except OSError as exc:
            # 扫不动就当作没有规则，但要留痕：目录权限或磁盘问题不该无声无息。
            report_error("rules.scan", exc, root=str(self.root))
            return []
        return out

    def rel_of(self, path: Path) -> str:
        """文件的相对路径（POSIX 风格）；不在根下时退回文件名。"""
        if self.root is None:
            return path.name
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.name

    # ── 读取 ──

    def read_text(self, path: Path) -> str:
        """读一个规则文件的正文（utf-8 容错）；超上限或读不动返回空串。"""
        try:
            info = path.stat()
        except OSError as exc:
            report_error("rules.stat", exc, path=str(path))
            return ""
        if self.max_bytes > 0 and info.st_size > self.max_bytes:
            report_error(
                "rules.too_large",
                f"规则文件超过上限（{info.st_size} > {self.max_bytes} 字节），已跳过",
                path=str(path),
            )
            return ""
        key = (str(path), int(info.st_mtime_ns), int(info.st_size))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            report_error("rules.read", exc, path=str(path))
            return ""
        self._cache[key] = text
        return text

    # ── 组包 ──

    def payloads(self) -> List[Tuple[str, str]]:
        """可注入的规则：`[(相对路径, 正文)]`，空正文的文件不占条目。

        组包与计数共用这一份结果，界面上的「N 个」与真正注入的条数必然一致。
        """
        out: List[Tuple[str, str]] = []
        for path in self.rule_files():
            text = self.read_text(path).strip()
            if not text:
                continue
            out.append((self.rel_of(path), text))
        return out

    def build_system_messages(self, conversation_id: str = "") -> List[str]:
        """每个规则文件一条系统消息：抬头 + 换行 + 正文。

        每个规则文件独立成一条 system 消息；全量注入，不看会话。
        """
        return [
            INJECT_PREFIX.format(rel=rel) + "\n" + text
            for rel, text in self.payloads()
        ]

    def attached_count(self, conversation_id: str = "") -> int:
        """实际注入的规则条数。"""
        return len(self.payloads())


def resource_directory_lines(runtime: "RulesRuntime") -> List[str]:
    """`## 资源目录` 章节里本插件的正文；章节标题由 PromptSections 添加。"""
    suffix = "" if runtime.enabled else "（不存在）"
    return [
        f"- 用户rules: {RULES_DIR}{suffix}",
        "  该目录中规则文件(*.md)会自动注入到上下文，为用户编辑规则时请在该目录下操作，USER_RULES.md为默认用户规则文件",
    ]


def register(ctx: Any) -> List[Callable[[], None]]:
    """插件入口：装配运行时，注册注入源、系统提示词章节与段色。

    三项注册都由 `ctx.add_*` 产出 disposer：插件停用（热开关）时宿主逆序
    撤销，注入与章节一起消失，不需要插件自己做清理。
    """
    runtime = RulesRuntime()
    ctx.set_runtime(runtime)

    return [
        # 上下文注入：一文件一条 system 消息
        ctx.add_context_source(
            runtime.build_system_messages,
            {"label": SEGMENT_LABEL, "count": runtime.attached_count},
        ),
        # 系统提示词章节：与 Skills 插件合并到同一个 `## 资源目录`
        ctx.add_prompt_section(
            RESOURCE_HEAD, lambda _cid: resource_directory_lines(runtime)),
        # 上下文分层里的段外观（界面那一行的颜色）
        ctx.add_ctx_segment_style(label=SEGMENT_LABEL, color=SEGMENT_COLOR),
    ]
