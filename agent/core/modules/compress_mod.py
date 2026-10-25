# -*- coding: utf-8 -*-
"""压缩模块：上下文预算与压缩。"""
from __future__ import annotations

from typing import Any, Iterator

from agent.core.error_report import report_error
from agent.core.event_name import COMPRESS_ENDED, COMPRESS_STARTED, CONTEXT_COMPACTED
from agent.core.image_embed import KEEP_IMAGE_TURNS, MAX_EMBED_IMAGES
from agent.core.module import ModuleBase
from agent.core.modules.assemble import assemble_with
from agent.core.modules.dialogue import prepare_dialogue
from agent.core.modules.mode_note import resolve_runtime_note
from agent.core.outcome import Outcome
from agent.core.ports import Ports


class CompressModule(ModuleBase):
    """上下文预算与压缩：把循环里的三处检查收拢成一个模块。

    从不要求续行：压缩是准备动作，不产生"该跑模型了"的意图。
    压缩器缺省或出错一律放行——压缩是增强项，绝不阻断回合。
    """

    name = "compress"
    requires = ("context", "compactor")

    def __init__(self, *, context: Any = None, compactor: Any = None,
                 mode_note: Any = "", image_turns: int = KEEP_IMAGE_TURNS,
                 image_max: int = MAX_EMBED_IMAGES) -> None:
        self.context_pass = context
        self._compactor = compactor
        #: 执行模式说明 —— 摘要复用前缀时要照平常请求补在末尾。
        #: 与 `ModelModule` 各持一份：两个模块各自组装各自的请求，互相不读对方状态。
        self._mode_note = mode_note
        #: 图片口径必须与 `ModelModule` 一致：压缩器声明的"前缀与随后请求逐字节相同"
        #: 只有在两边用同一套剥图参数时才成立。
        self._image_turns = int(image_turns)
        self._image_max = int(image_max)

    def _covered_end(self) -> int:
        """已覆盖前缀长度（压缩器维护）；没有压缩器就是 0。"""
        value = getattr(self._compactor, "covered_end", 0)
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def execute(self, ports: Ports) -> Iterator[Any]:
        if self.context_pass is None and self._compactor is None:
            # 没装压缩能力：仍发终态（`skipped`），监听者据此知道"这轮没压"，
            # 而不是以为"事件丢了"。
            yield ports.emit(COMPRESS_ENDED, compacted=False, skipped=True)
            return Outcome.ok()
        from time import perf_counter
        started = perf_counter()
        runtime_note = resolve_runtime_note(self._mode_note)
        # 发给模型的请求序列：必须成对（`derive_request_messages`
        # 会为悬空的 tool_calls 补说明性占位，否则模型 API 硬拒绝 400）。
        # 请求序列取自 derive_request_messages()；derive_messages() 保留悬空——那是日志的忠实折叠，会保留悬空。
        dialogue = prepare_dialogue(ports.log.derive_request_messages(),
                                     self._image_turns, self._image_max)
        # 工具定义照平常请求取同一份：摘要复用前缀时它是前缀的一部分，
        # 少一项或换一份就整段缓存作废。
        schemas = ports.tool_port.schemas() if getattr(ports, "tool_port", None) is not None else []
        yield ports.emit(COMPRESS_STARTED, messages=len(dialogue))
        report: Any = None
        if self._compactor is not None:
            try:
                # 压缩走同一条装配入口：头部 + 对话（+ 尾部仅执行模式，随后剔除）。
                # 压缩器拿到的这份与随后模型请求的前缀是同一份装配结果。
                whole = assemble_with(self.context_pass, dialogue, runtime_note,
                                       self._covered_end())
                report = self._compactor.ensure_before_append(
                    self.context_pass, dialogue, pending=None, tools=schemas,
                    mode_note=runtime_note, assembled=whole)
            except Exception as exc:
                # 压缩异常 → 放行，不阻断回合；但必须留痕：静默吞掉会让
                # "压缩从未生效"看起来像"没超阈值"，排查时会往完全错的方向找。
                report = None
                report_error("core.compress", exc)
        elif self.context_pass is not None:
            # 没有压缩能力：至少把对话装进上下文，后续模块才看得到。
            assemble_with(self.context_pass, dialogue, runtime_note, 0)
        compacted = isinstance(report, dict) and bool(report)
        if compacted:
            yield ports.emit(CONTEXT_COMPACTED, **report)
        yield ports.emit(COMPRESS_ENDED, compacted=compacted,
                         elapsed_ms=int((perf_counter() - started) * 1000))
        return Outcome.ok()        # ← 控制信号经 StopIteration.value 传出；缺 return 时该值为 None
