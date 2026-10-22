# -*- coding: utf-8 -*-
"""上下文注入源与插件段落。"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

from agent.core.error_report import report_error


@dataclass(frozen=True)
class SourceMeta:
    """插件段落的描述：段 key 与段名。

    `key` 是前端认的字段名，也进 `context_layout.segments[].key`，
    所以与插件名一致；宿主不解释它的含义。
    """

    key: str = ""
    label: str = ""
    plugin: str = ""
    # 注入前缀：告诉模型这段是什么（如 `【知识库：a.md】`、`【Skills 清单】`）。
    # 前缀由来源给，宿主不替它拼 —— 拼错了模型会把它当对话内容。
    prefix: str = ""
    # 主体数量的取数口 `fn(conversation_id) -> int`（插件自报，如"勾选了几个文件"、
    # "清单里列了几个 Skills"）；不给时按消息条数算。
    count: Optional[Callable[[str], int]] = None
    # 插件在清单（`plugins.ini`）里的位次。插件段之间的组装顺序按它排 ——
    # 清单靠前的插件，它的段也靠前。应用级来源（非插件）没有位次，排在最后。
    plugin_rank: Optional[int] = None


@dataclass(frozen=True)
class PluginSegments:
    """插件贡献的段落：段落表 + 各段主体数量。

    `items` 是 `[(段 key, 段名, 正文)]`，顺序即装配顺序；
    `counts` 是按位置对应的主体数量（同一个插件可以声明多段，按 key 存会互相覆盖）；
    """

    items: Tuple[Tuple[str, str, str], ...] = ()
    counts: Tuple[int, ...] = ()

    def __post_init__(self) -> None:
        """入口即冻结：调用方传 list 也落成 tuple（B1）。

        冻结对象却留着可变容器，等于只锁了门框：外部改一下原列表，
        装配顺序与数量就跟着变。这里逐项复制成元组，之后任何人都改不到。
        正文元素保持原样（可能已经是 `list[str]`，由装配侧再展开）。
        """
        frozen: List[Tuple[str, str, str]] = []
        for item in self.items:
            parts = tuple(item)
            if len(parts) != 3:
                raise ValueError(
                    f"PluginSegments 每项须为 (key, 段名, 正文)，收到 {parts!r}"
                )
            frozen.append((parts[0], parts[1], parts[2]))
        object.__setattr__(self, "items", tuple(frozen))
        object.__setattr__(self, "counts", tuple(int(c) for c in self.counts))


def slug(text: str) -> str:
    """把任意名字压成可用作段 key 的形状（只留字母数字与 `_`、`-`）。"""
    out = "".join(ch if (ch.isalnum() or ch in "_-") else "_" for ch in str(text or ""))
    return out.strip("_") or "source"


class ContextSources:
    """上下文注入源注册表（扩展点）。

    每个来源贡献一段 `system` 文本，并自带段名（`SourceMeta`）：
    段 key 是插件名（前端按它找插件注册的渲染钩子），段名与主体数量由插件给。

    宿主不认识任何具体插件 —— 知识库、Skills 清单都只是"某个插件注册的一段"；
    来源函数是 `fn(conversation_id) -> List[str]`（文本列表，每条独立成消息）。
    `collect` 按注册顺序串接，单个来源异常被隔离（记录 stderr），不影响其他来源。
    """

    def __init__(self) -> None:
        self._sources: List[Tuple[str, str, Callable[[str], List[str]], Any, str, str]] = []
        self._lock = threading.Lock()
        #: 内容版本号：注册变化或来源自身的数据变化（例如勾选集合变了）时 +1。
        #: 装配侧据此判断缓存的收集结果还能不能用 —— 光看"有没有注册新来源"
        #: 判不出"同一个来源的数据换了"。
        self._version = 0

    @property
    def version(self) -> int:
        return int(self._version)

    def bump(self) -> None:
        """标记来源内容已变（勾选集合、磁盘文件等），让装配侧丢掉缓存重收集。"""
        with self._lock:
            self._version += 1

    def add(self, fn: Callable[[str], List[str]],
            meta: Optional["SourceMeta"] = None) -> Callable[[], None]:
        """注册一段注入源；返回幂等 disposer。

        `meta` 不给时按来源函数名兜底成一段段名等于 key 的来源。
        """
        if not callable(fn):
            raise ValueError("上下文来源必须可调用")
        info = meta if isinstance(meta, SourceMeta) else SourceMeta()
        key = info.key or slug(getattr(fn, "__name__", "") or "source")
        return self._register(self._sources,
                              (key, info.label or key, fn, info.count, info.prefix,
                               info.plugin_rank))

    def _register(self, bucket: List[Any], item: Any) -> Callable[[], None]:
        with self._lock:
            bucket.append(item)
            self._version += 1

        def _dispose() -> None:
            with self._lock:
                if item in bucket:
                    bucket.remove(item)
                    # 卸下来源也是内容变化。不打版本号的话，本趟还没作废的快照
                    # 会继续带着已经卸掉的那一段。
                    self._version += 1

        return _dispose

    def collect_segments(self, conversation_id: str) -> "PluginSegments":
        """收集注入源，返回 `PluginSegments`（异常隔离）。

        `items` 是 `[(段 key, 段名, 正文)]`；`counts` 按位置对应 `items` ——
        同一个插件可以注册多个来源，它们共用段 key，按 key 存会互相覆盖。
        数量由来源自报，没有自报口的按消息条数算。
        """
        with self._lock:
            sources = list(self._sources)
        # 插件段按插件清单位次排：清单靠前的插件排在前面；
        # 没有位次的（应用级来源）排最后。稳定排序，同位次保持注册序。
        sources.sort(key=lambda s: (s[5] is None, s[5] if s[5] is not None else 0))
        items: List[Tuple[str, str, str]] = []
        counts: List[int] = []
        for key, label, fn, reported, prefix, _order in sources:
            texts = self._gather(fn, conversation_id)
            if texts is None:
                # 来源异常已隔离：不占位（占位会假装插件正常只是没内容）。
                continue
            amount = None
            if callable(reported):
                try:
                    amount = max(0, int(reported(conversation_id)))
                except Exception as exc:
                    report_error(
                        "context.source_count",
                        exc,
                        conversation_id=conversation_id,
                        source=key,
                    )
                    amount = None
            if not texts:
                # 空段仍占位：上下文示意图要看见已装载但尚未注入内容的插件
                # （例如知识库未勾选）。正文空串，装配进模型时会被跳过。
                items.append((key, label, ""))
                counts.append(amount if amount is not None else 0)
                continue
            for i, text in enumerate(texts):
                # 前缀在收集时统一加上：插件只管正文，前缀由它自己声明。
                items.append((key, label, f"{prefix}{text}" if prefix else text))
                # 一个来源给多条正文时只有第一条带自报数量，其余按条数算。
                counts.append(amount if i == 0 and amount is not None else 1)
        # 不变量：数量与正文逐条对齐。少了数量，管线那边会把别人的数量贴到
        # 自己的段上（按位置取值）；错位是静默的，只在浮层上表现为数字离谱。
        while len(counts) < len(items):
            counts.append(1)
        return PluginSegments(items=tuple(items), counts=tuple(counts))

    @staticmethod
    def _gather(
        fn: Callable[[str], List[str]], conversation_id: str,
    ) -> Optional[List[str]]:
        """收集一个来源。异常 → `None`（隔离、不占位）；正常无正文 → `[]`（占空段）。"""
        try:
            parts = fn(conversation_id)
        except Exception as exc:
            report_error(
                "context.source",
                exc,
                conversation_id=conversation_id,
            )
            return None
        out: List[str] = []
        for text in parts or []:
            t = str(text or "").strip()
            if t:
                out.append(t)
        return out


