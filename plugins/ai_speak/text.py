# -*- coding: utf-8 -*-
"""AI说话的文本规范、切分与合成前净化。

三个出口都是纯函数：

- `split_message(msg, max_chars)`：校验并切段；
- `to_speech_text(text)`：把段转成送给 edge-tts 的文本；
- `MessageValidationError`：校验失败的结构化异常。

切段边界由标点决定；引号/括号内部的标点不切分。数字之间的 `.`、`,`、`:`
分别是小数点、千分位与时间分隔，不当作边界。
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Tuple

MAX_MESSAGE_CHARS = 512
DEFAULT_MAX_SEGMENT_CHARS = 128

_CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF))
_CN_OPENERS = {"“": "”", "‘": "’", "（": "）", "《": "》", "「": "」"}
_CN_CLOSERS = {"”": "“", "’": "‘", "）": "（", "》": "《", "」": "「"}
_EN_OPENERS = {"(": ")"}
_EN_CLOSERS = {'"': '"', ")": "("}
_OPENERS = set(_CN_OPENERS) | set(_EN_OPENERS) | {"'", '"'}
_CLOSERS = set(_CN_CLOSERS) | set(_EN_CLOSERS) | {"'", '"'}
_BOUNDARY_CN = set("，。？！；、：")
_BOUNDARY_EN = set(".,?!;:")
_MATH = set("+-*/×÷＋－＊／")
_PERCENT = set("%％")
_SPACES = set(" \u3000")
#: 文件名与路径里最常见、也念得出来的符号。
#: 说文件名不该比说英文单词更难 —— 后者本来就允许 `-` 与 `'`。
_PATH_CHARS = set("_.\\/")
_START_CLOSERS = _CLOSERS - {'"', "'"}
_TRAILING_OPENERS = {"“", "‘", "（", "(", "「"}

_OPEN_CLOSER = {
    "“": "”",
    "‘": "’",
    "（": "）",
    "《": "》",
    "「": "」",
    '"': '"',
    "(": ")",
    "'": "'",
}


class MessageValidationError(ValueError):
    """`msg` 不符合说话规范；带稳定的错误码与位置（1-based）。"""

    def __init__(self, message: str, *, position: int = 0,
                 code: str = "invalid_message") -> None:
        self.code = code
        self.position = int(position)
        super().__init__(message)


def _fail(message: str, position: int, code: str = "invalid_message") -> None:
    suffix = f"（位置 {position}）" if position > 0 else ""
    raise MessageValidationError(message + suffix, position=position, code=code)


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(start <= code <= end for start, end in _CJK_RANGES)


def _is_ascii_letter(ch: str) -> bool:
    return ("A" <= ch <= "Z") or ("a" <= ch <= "z")


def _is_ascii_digit(ch: str) -> bool:
    return "0" <= ch <= "9"


def _is_ascii_alnum(ch: str) -> bool:
    return _is_ascii_letter(ch) or _is_ascii_digit(ch)


def _is_space(ch: str) -> bool:
    return ch in _SPACES


def _is_boundary(ch: str) -> bool:
    return ch in _BOUNDARY_CN or ch in _BOUNDARY_EN


def _is_operand(ch: str) -> bool:
    return (
        _is_ascii_alnum(ch)
        or _is_cjk(ch)
        or ch in _CLOSERS
        or ch in _PERCENT
    )


def _prev_nonspace(text: str, index: int) -> Optional[int]:
    cursor = index - 1
    while cursor >= 0 and _is_space(text[cursor]):
        cursor -= 1
    return cursor if cursor >= 0 else None


def _next_nonspace(text: str, index: int) -> Optional[int]:
    cursor = index + 1
    while cursor < len(text) and _is_space(text[cursor]):
        cursor += 1
    return cursor if cursor < len(text) else None


def _numeric_separator(text: str, index: int) -> bool:
    """数字内部的 `.` `,` `:` 不是分句边界。"""
    ch = text[index]
    if ch not in ".,:":
        return False
    if index == 0 or index + 1 >= len(text):
        return False
    return _is_ascii_digit(text[index - 1]) and _is_ascii_digit(text[index + 1])


def _path_char(ch: str) -> bool:
    """文件名内部的字符：字母、数字、下划线、连字符。"""
    return _is_ascii_alnum(ch) or ch in "_-"


def _extension_dot(text: str, index: int) -> bool:
    """文件名的点不是分句边界：`USER_RULES.md`、`a/b.py` 要整体念出来。

    判定收紧到「点前是名字字符、点后是 1–5 个字母且不再接名字字符」——
    扩展名长度有界，避免把 `end. Next` 这类正常句号也吞掉。
    """
    if text[index] != ".":
        return False
    if index == 0 or not _path_char(text[index - 1]):
        return False
    cursor = index + 1
    letters = 0
    while cursor < len(text) and _is_ascii_letter(text[cursor]):
        cursor += 1
        letters += 1
    if not 1 <= letters <= 5:
        return False
    return cursor >= len(text) or not _path_char(text[cursor])


def _allowed_char(ch: str) -> bool:
    """字符合法性：只拦破坏结构的控制字符，其余一律放行。

    不在这一层拦“念不出来”的符号：模型天生想用各种引号、箭头、emoji，
    在这一层逐个列举只会不断漏（书名号就是漏进来的那一个）。
    不发音的符号交给 `to_speech_text` 在合成前统一清掉。

    控制字符必须拦：换行与制表符会改变切段后各段的拼接含义，
    它们不是“念不出来”，而是“结构不成立”。
    """
    if _is_space(ch):
        return True
    return unicodedata.category(ch)[0] != "C"


#: 报错时给模型看的允许字符一览。
#: 只说“这个字符不行”等于让它反复试；说清零了就不存在须要试的东西。
_ALLOWED_SUMMARY = (
    "除换行、制表符等控制字符外均可；引号括号需成对；"
    "不发音的符号（各种引号、箭头、emoji 等）会在合成前自动移除，不必删。"
)


def _describe_char(ch: str) -> str:
    """不可见字符用可读名字，避免报错里出现一个看不见的字符。"""
    if ch == "\n":
        return "换行"
    if ch == "\t":
        return "制表符"
    if ch == "\r":
        return "回车"
    return ch


def _scan_structure(text: str) -> List[int]:
    """校验字符、配对与数字上下文，返回边界终点列表。"""
    stack: List[Tuple[str, int]] = []
    boundaries: List[int] = []

    def add_boundary(index: int) -> None:
        end = index + 1
        if boundaries and boundaries[-1] == index:
            boundaries[-1] = end
        else:
            boundaries.append(end)

    for index, ch in enumerate(text):
        if not _allowed_char(ch):
            _fail(
                f"不允许的字符「{_describe_char(ch)}」；{_ALLOWED_SUMMARY}",
                index + 1,
                "invalid_char",
            )

        if ch == '"':
            if stack and stack[-1][0] == '"':
                stack.pop()
            else:
                if index + 1 < len(text) and text[index + 1] == '"':
                    _fail("空的英文双引号", index + 1, "empty_pair")
                stack.append(('"', index))
            continue

        if ch in _CN_OPENERS or ch in _EN_OPENERS:
            closer = _OPEN_CLOSER[ch]
            if index + 1 < len(text) and text[index + 1] == closer:
                _fail(f"空的引号或括号「{ch}{closer}」", index + 1, "empty_pair")
            stack.append((closer, index))
            continue

        if ch == "'":
            prev_letter = index > 0 and _is_ascii_letter(text[index - 1])
            next_letter = index + 1 < len(text) and _is_ascii_letter(text[index + 1])
            if prev_letter and next_letter:
                continue
            if stack and stack[-1][0] == "'":
                stack.pop()
            else:
                if index + 1 < len(text) and text[index + 1] == "'":
                    _fail("空的单引号", index + 1, "empty_pair")
                stack.append(("'", index))
            continue

        if ch in _CN_CLOSERS or ch in _EN_CLOSERS:
            if not stack or stack[-1][0] != ch:
                _fail(f"「{ch}」没有对应的开符号", index + 1, "unmatched_close")
            stack.pop()
            continue

        if _is_boundary(ch) and not stack:
            if not _numeric_separator(text, index) and not _extension_dot(text, index):
                add_boundary(index)

    if stack:
        closer, opener_index = stack[-1]
        _fail(f"「{text[opener_index]}」没有对应的「{closer}」",
              opener_index + 1, "unmatched_open")

    _validate_structure_edges(text, boundaries)
    return boundaries


def _validate_structure_edges(text: str, boundaries: List[int]) -> None:
    """校验首尾边界与结束标点，必要时补最后一个边界。"""
    if not text:
        _fail("msg 不能为空", 0, "empty")

    if text[0] in _BOUNDARY_CN or text[0] in _BOUNDARY_EN or text[0] in _START_CLOSERS:
        _fail("msg 不能以边界标点或闭引号/闭括号开头", 1, "leading_boundary")
    if text[-1] in _TRAILING_OPENERS:
        _fail("msg 不能以开引号/开括号结尾", len(text), "trailing_opener")

    cursor = len(text) - 1
    while cursor >= 0 and text[cursor] in _CLOSERS:
        cursor -= 1
    if cursor < 0 or not _is_boundary(text[cursor]):
        _fail("msg 必须以边界标点结尾", len(text), "missing_end")
    if not boundaries or boundaries[-1] < len(text):
        if boundaries and boundaries[-1] == cursor + 1:
            boundaries[-1] = len(text)
        else:
            boundaries.append(len(text))
    return boundaries


def _check_math_and_percent(text: str) -> None:
    for index, ch in enumerate(text):
        if ch in _PERCENT:
            previous = _prev_nonspace(text, index)
            if previous is None or not _is_ascii_digit(text[previous]):
                _fail(f"百分号「{ch}」前面必须是数字", index + 1, "invalid_percent")
            continue

        if ch not in _MATH:
            continue

        if index > 0 and text[index - 1] in _MATH:
            _fail(f"四则符号「{ch}」不能连续出现", index + 1, "repeated_math")

        previous = _prev_nonspace(text, index)
        following = _next_nonspace(text, index)
        prev_ch = text[previous] if previous is not None else ""
        next_ch = text[following] if following is not None else ""

        if ch in "-－":
            if (index > 0 and index + 1 < len(text)
                    and _is_ascii_alnum(text[index - 1])
                    and _is_ascii_alnum(text[index + 1])):
                continue
            if following is not None and _is_ascii_digit(next_ch):
                continue
            if previous is not None and following is not None \
                    and _is_operand(prev_ch) and _is_operand(next_ch):
                continue
            _fail(f"减号「{ch}」缺少操作数", index + 1, "invalid_math")
            continue

        if previous is None or following is None \
                or not _is_operand(prev_ch) or not _is_operand(next_ch):
            _fail(f"四则符号「{ch}」左右必须有操作数", index + 1, "invalid_math")


def split_message(msg: object, max_chars: int) -> Tuple[str, ...]:
    """校验 `msg` 并切成不超过 `max_chars` 的段。

    `max_chars` 是配置值，不在这里设上限；小于 1 视为调用方错误。
    """
    limit = int(max_chars)
    if limit < 1:
        raise ValueError("max_segment_chars 必须 >= 1")
    raw = str(msg or "")
    if len(raw) > MAX_MESSAGE_CHARS:
        _fail(f"msg 超过 {MAX_MESSAGE_CHARS} 字", MAX_MESSAGE_CHARS + 1, "too_long")
    text = raw.strip()
    if not text:
        _fail("msg 不能为空", 0, "empty")

    boundaries = _scan_structure(text)
    _check_math_and_percent(text)

    pieces: List[str] = []
    start = 0
    for end in boundaries:
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        start = end
    tail = text[start:].strip()
    if tail:
        _fail("msg 必须以边界标点结尾", len(text), "missing_end")
    if not pieces:
        _fail("msg 不能为空", 0, "empty")

    for number, piece in enumerate(pieces, 1):
        if len(piece) > limit:
            _fail(
                f"第 {number} 个分句 {len(piece)} 字，超过上限 {limit} 字",
                len(text),
                "segment_too_long",
            )

    segments: List[str] = []
    current = ""
    for piece in pieces:
        candidate = _join(current, piece)
        if current and len(candidate) > limit:
            segments.append(current)
            current = piece
        else:
            current = candidate
    if current:
        segments.append(current)
    return tuple(segments)


def _join(current: str, piece: str) -> str:
    if not current:
        return piece
    if _is_ascii_alnum(current[-1]) or _is_ascii_alnum(piece[0]):
        return f"{current} {piece}"
    return current + piece


def _chinese_integer(value: int) -> str:
    digits = "零一二三四五六七八九"
    if value < 0:
        return "负" + _chinese_integer(-value)
    if value == 0:
        return "零"
    if value >= 100000000:
        high, low = divmod(value, 100000000)
        out = _chinese_integer(high) + "亿"
        if low:
            if low < 10000000:
                out += "零"
            out += _chinese_integer(low)
        return out
    if value >= 10000:
        high, low = divmod(value, 10000)
        out = _chinese_integer(high) + "万"
        if low:
            if low < 1000:
                out += "零"
            out += _chinese_integer(low)
        return out

    out = ""
    zero = False
    for base, unit in ((1000, "千"), (100, "百"), (10, "十"), (1, "")):
        digit = value // base
        value %= base
        if digit:
            if zero and out:
                out += "零"
            zero = False
            if not (base == 10 and digit == 1 and not out):
                out += digits[digit]
            out += unit
        elif out:
            zero = True
    return out


def _chinese_number(raw: str) -> str:
    text = str(raw or "").replace(",", "").strip()
    if "." in text:
        integer, fraction = text.split(".", 1)
        return _chinese_integer(int(integer or "0")) + "点" + "".join(
            "零一二三四五六七八九"[int(ch)] for ch in fraction if ch.isdigit()
        )
    return _chinese_integer(int(text or "0"))


def _percent_replacement(match: "re.Match[str]") -> str:
    number = _chinese_number(match.group(1))
    if number == "一百":
        number = "百"
    return "百分之" + number


_MATH_WORDS = {
    "+": "加", "＋": "加",
    "-": "减", "－": "减",
    "*": "乘", "＊": "乘", "×": "乘",
    "/": "除以", "／": "除以", "÷": "除以",
}
_DATE_RE = re.compile(r"\b\d{4}[-－]\d{1,2}(?:[-－]\d{1,2})?\b")
_MATH_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([+\-*/×÷＋－＊／])\s*(\d[\d,]*(?:\.\d+)?)")
_NEGATIVE_RE = re.compile(r"(?<![0-9A-Za-z])[-－](\d[\d,]*(?:\.\d+)?)")
_PERCENT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*[%％]")


def _math_replacement(match: "re.Match[str]") -> str:
    left = _chinese_number(match.group(1))
    op = _MATH_WORDS.get(match.group(2), match.group(2))
    right = _chinese_number(match.group(3))
    return f"{left}{op}{right}"


def _negative_replacement(match: "re.Match[str]") -> str:
    return "负" + _chinese_number(match.group(1))


#: 合成前保留的标点：分句边界与文件名符号。
#: 撇号留着是为了 don't 这类词内撇号；成对的引号已在前面删掉。
_SPEAKABLE_PUNCT = set("，。？！；、：.,?!;:") | set("_.\\/-") | {"'"}


def _is_speakable(ch: str) -> bool:
    """这个字符念得出来吗。字母与数字一律保留（含全角），标点只留清单内的。"""
    if ch in _SPEAKABLE_PUNCT or ch in _SPACES:
        return True
    return unicodedata.category(ch)[0] in ("L", "N")


def to_speech_text(text: str) -> str:
    """把一段话转成送给引擎的文本：去掉不发音符号，百分比与四则转中文读法。

    清洗用“保留可发音字符”而不是“逐个删掉已知符号”：后者每遇到一种新引号
    就漏一次（书名号就是这样一路留到引擎的）。这里只保证一件事——
    留下的每一个字符都有声音。
    """
    source = str(text or "")
    source = re.sub(r'[“”‘’（）"()]', "", source)
    source = re.sub(r"(?<![A-Za-z])'|'(?![A-Za-z])", "", source)

    protected: List[str] = []

    def hold_date(match: "re.Match[str]") -> str:
        protected.append(match.group(0))
        return f"\x00{len(protected) - 1}\x00"

    source = _DATE_RE.sub(hold_date, source)
    source = _PERCENT_RE.sub(_percent_replacement, source)
    source = _MATH_RE.sub(_math_replacement, source)
    source = _NEGATIVE_RE.sub(_negative_replacement, source)
    source = re.sub(r"(?<=\d),(?=\d)", "", source)
    source = re.sub(r"[ \u3000]+", " ", source).strip()

    for index, value in enumerate(protected):
        source = source.replace(f"\x00{index}\x00", value)
    spoken = "".join(ch for ch in source if _is_speakable(ch))
    return re.sub(r"[ \u3000]+", " ", spoken).strip()
