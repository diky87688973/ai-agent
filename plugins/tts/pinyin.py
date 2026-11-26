# -*- coding: utf-8 -*-
"""Edge TTS 的多音字辅助：把易误判的字改写成带声调拼音。

这是引擎适配细节而非说词逻辑：只有 Edge 需要，本地模型自己读得准。
因此归属 tts 插件，由 provider 按 `needs_pinyin_hints` 决定是否调用。
"""
from __future__ import annotations

import re
from typing import List

#: “行”读 háng 的短语；这些“行”读 xíng，先占位保护。
_HANG_EXCEPTIONS = re.compile(
    r"一行人(?:员|等)?|一行\s*(?:\d+|[一二三四五六七八九十百千万零两几数众余多若干俩个Nn]+)\s*人"
)
#: 数字 + 行，按行号/行数读 háng。
_HANG_AFTER_NUMBER = re.compile(
    r"(?P<number>\d+(?:\.\d+)?|[一二三四五六七八九十百千万零两]+)\s*行"
)
#: 行 + 数字，按行号读 háng。
_HANG_BEFORE_NUMBER = re.compile(
    r"行\s*(?P<number>\d+|[一二三四五六七八九十百千万零两]+)"
)
#: 「数行」按行数读 háng；后接「为」时是「函数行为」这类词，保持原读。
_HANG_AFTER_COUNT = re.compile(r"数行(?!为)")
#: 「重」读 zhòng 的词。
#: 「重 + 动词」表示再做一次，是开放集，列不完；读 zhòng 的是封闭集，可以列全。
#: 因此这里只列 zhòng，其余「重」一律按 chóng 处理。
_ZHONG_EXCEPTIONS = re.compile(
    r"重要|重点|重视|重大|重心|重任|重担|重责|重头戏|重金|重奖|重罚|重创"
    r"|重压|重兵|重镇|重地|重灾区|重工业|重武器|重利|重义|重男轻女|重色轻友"
    r"|重量|体重|净重|毛重|皮重|超重|失重|减重|载重|承重|自重|负重|比重|加重"
    r"|起重|配重|荷重"
    r"|严重|沉重|浓重|笨重|繁重|稳重|厚重|凝重|深重|惨重|着重|偏重"
    r"|尊重|器重|看重|珍重|保重|借重|倚重"
    r"|(?:很|好|太|真|挺|极|最|更|较|非常)重"
)


def apply(text: str) -> str:
    """用带声调的拼音校准 Edge TTS 容易误判的多音字。"""
    held: List[str] = []

    def hold(match: "re.Match[str]") -> str:
        held.append(match.group(0))
        return f"\x00{len(held) - 1}\x00"

    source = (text.replace("换行", "换 háng ")
              .replace("折行", "折 háng ")
              .replace("行内", " háng 内")
              .replace("运行", "运 xíng"))
    source = _HANG_EXCEPTIONS.sub(hold, source)
    source = _ZHONG_EXCEPTIONS.sub(hold, source)
    source = source.replace("重", " chóng ")
    source = _HANG_AFTER_COUNT.sub("数 háng ", source)
    source = _HANG_AFTER_NUMBER.sub(lambda m: f"{m.group('number')} háng ", source)
    source = _HANG_BEFORE_NUMBER.sub(lambda m: f" háng {m.group('number')}", source)
    for index, value in enumerate(held):
        source = source.replace(f"\x00{index}\x00", value)
    source = re.sub(r"[ \t]+", " ", source)
    source = re.sub(r" +([，。？！；、：.,?!;:])", r"\1", source)
    source = re.sub(r"([，。？！；、：.,?!;:])\s+", r"\1", source)
    return source.strip()
