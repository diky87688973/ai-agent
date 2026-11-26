# -*- coding: utf-8 -*-
"""音色设计的维度、措辞与数值参数。

每个选项除了给模型看的英文措辞，还带一组可累加的数值参数：
音高（半音）、语速（倍率）、以及属于 personality 的采样参数。
组合音色 = 把五个维度的增量相加，再夹到安全范围内。

模型本身没有音高与语速参数（文档写明 speed 被忽略），这两项由 `dsp` 在
波形上做，所以这里是真正的量化控制，不是靠描述去猜。

措辞方面的实测结论：英文远强于中文（同一对极端基频差 161 Hz vs 90 Hz），
且指令越长越弱，所以每条只留三到六个词，否定项单列。
"""
from __future__ import annotations

from typing import Dict, List, Mapping

#: 拼接顺序固定，改顺序等于换音色，不允许按调用方意愿重排。
DIMENSION_ORDER = ("gender", "age", "timbre", "persona", "pace", "emotion")

#: 男声档位。选这些值时 age 维度不参与：
#: 同时要求 "a teenage girl" 与 "male voice" 会互相抵消，模型随机偏向一边。
MALE_GENDERS = ("少年", "青年", "中年", "低沉", "暮年")

#: 不产生措辞的维度取值：女声是基准，不需要额外描述。
SILENT_VALUES = {"gender": ("女性",)}

#: 基准参数；集合里没有写到的项就用这里的值。
BASE_PARAMS: Dict[str, float] = {
    "pitch": 0.0,
    "speed": 1.25,
    "gain_db": 0.0,
    "cfg_scale": 3.0,
    "temperature": 0.9,
    "top_k": 50.0,
}

#: 累加项的合法区间；采样参数不累加，取 personality 给的值再夹一次。
PARAM_LIMITS: Dict[str, tuple] = {
    "pitch": (-6.0, 6.0),
    "speed": (1.00, 2.00),
    "gain_db": (-6.0, 6.0),
    "cfg_scale": (1.0, 5.0),
    "temperature": (0.0, 2.0),
    "top_k": (0.0, 100.0),
}

#: 可累加的项；其余按「后写覆盖」处理。
ACCUMULATED = ("pitch", "speed", "gain_db")

DIMENSIONS: List[Dict[str, object]] = [
    {
        "key": "gender",
        "label": "性别声线",
        "options": [
            {"value": "女性", "text": "", "neg": "", "params": {}},
            {"value": "少年", "text": "a young boy's clear voice", "neg": "an adult man",
             "params": {"pitch": -2.0}},
            {"value": "青年", "text": "a young man in his twenties", "neg": "a woman",
             "params": {"pitch": -4.0}},
            {"value": "中年", "text": "a mature man in his forties", "neg": "a woman",
             "params": {"pitch": -5.0}},
            {"value": "低沉", "text": "a man with a deep resonant voice", "neg": "a woman",
             "params": {"pitch": -6.0}},
            {"value": "暮年", "text": "an elderly man with a weathered voice", "neg": "a woman",
             "params": {"pitch": -6.0}},
        ],
    },
    {
        "key": "age",
        "label": "年龄声线",
        "options": [
            {"value": "少女", "text": "a teenage girl's voice", "neg": "an adult woman",
             "params": {"pitch": 2.5}},
            {"value": "年轻女性", "text": "a young woman in her early twenties", "neg": "childish",
             "params": {"pitch": 1.0}},
            {"value": "轻熟", "text": "a woman in her late twenties", "neg": "naive",
             "params": {"pitch": 0.0}},
            {"value": "成熟", "text": "a mature woman in her thirties", "neg": "girlish",
             "params": {"pitch": -1.0}},
            {"value": "长辈", "text": "a middle-aged woman over forty", "neg": "young",
             "params": {"pitch": -2.0}},
        ],
    },
    {
        "key": "timbre",
        "label": "音质质感",
        "options": [
            {"value": "清亮", "text": "bright crisp timbre", "neg": "muffled",
             "params": {"pitch": 0.5}},
            {"value": "温润", "text": "warm and clear timbre", "neg": "shrill",
             "params": {"pitch": 0.0}},
            {"value": "醇厚", "text": "deep chesty timbre", "neg": "thin",
             "params": {"pitch": -1.0}},
            {"value": "微沙", "text": "husky raspy timbre", "neg": "glass-smooth",
             "params": {"pitch": -0.5}},
            {"value": "气声", "text": "very breathy airy voice", "neg": "dry",
             "params": {"pitch": 0.5}},
            {"value": "冷冽", "text": "low, cold, hard timbre", "neg": "warm and sweet",
             "params": {"pitch": -1.0}},
        ],
    },
    {
        "key": "persona",
        "label": "性格气质",
        "options": [
            {"value": "温柔亲切", "text": "warm tender smiling delivery", "neg": "cold",
             "params": {"pitch": 0.0, "speed": -0.10, "cfg_scale": 3.0,
                        "temperature": 0.90, "top_k": 50.0}},
            {"value": "甜美灵动", "text": "bright playful flirty delivery", "neg": "flat",
             "params": {"pitch": 0.5, "speed": 0.05, "cfg_scale": 2.8,
                        "temperature": 0.95, "top_k": 60.0}},
            {"value": "知性稳重", "text": "confident composed clear delivery", "neg": "hesitant",
             "params": {"pitch": 0.0, "speed": 0.00, "cfg_scale": 3.0,
                        "temperature": 0.90, "top_k": 50.0}},
            {"value": "冷艳强势", "text": "commanding forceful icy delivery", "neg": "cutesy",
             "params": {"pitch": -1.0, "speed": -0.05, "cfg_scale": 3.4,
                        "temperature": 0.90, "top_k": 40.0}},
            {"value": "活泼俏皮", "text": "energetic bouncy cheerful delivery", "neg": "stiff",
             "params": {"pitch": 1.0, "speed": 0.25, "cfg_scale": 2.8,
                        "temperature": 1.00, "top_k": 60.0}},
            {"value": "古典端庄", "text": "dignified refined delivery", "neg": "sloppy",
             "params": {"pitch": 0.0, "speed": -0.15, "cfg_scale": 3.2,
                        "temperature": 0.90, "top_k": 45.0}},
            {"value": "慵懒松弛", "text": "relaxed unhurried low-key delivery", "neg": "tense",
             "params": {"pitch": -0.5, "speed": -0.40, "cfg_scale": 3.0,
                        "temperature": 0.90, "top_k": 50.0}},
        ],
    },
    {
        "key": "pace",
        "label": "语速节奏",
        "options": [
            {"value": "舒缓", "text": "slow pace", "neg": "rushed",
             "params": {"speed": -0.30}},
            {"value": "适中", "text": "normal pace", "neg": "dragging",
             "params": {"speed": 0.0}},
            {"value": "轻快", "text": "fast pace", "neg": "sluggish",
             "params": {"speed": 0.20}},
        ],
    },
    {
        "key": "emotion",
        "label": "情绪底色",
        "options": [
            {"value": "平和", "text": "calm emotion", "neg": "excited",
             "params": {}},
            {"value": "温和", "text": "warm emotion", "neg": "indifferent",
             "params": {}},
            {"value": "愉悦", "text": "cheerful emotion", "neg": "gloomy",
             "params": {"pitch": 0.5, "speed": 0.10}},
            {"value": "哀伤", "text": "sorrowful emotion", "neg": "joyful",
             "params": {"pitch": -1.0, "speed": -0.20}},
            {"value": "关切", "text": "caring emotion", "neg": "detached",
             "params": {"speed": 0.10}},
            {"value": "克制", "text": "restrained emotion", "neg": "openly emotional",
             "params": {"speed": -0.05}},
        ],
    },
]

PRESETS: List[Dict[str, object]] = [
    {"id": "qingling", "label": "清亮甜美",
     "dims": {"gender": "女性", "age": "少女", "timbre": "清亮", "persona": "甜美灵动",
              "pace": "轻快", "emotion": "愉悦"},
     "target": {"f0": [340, 395], "centroid": 1600}},
    {"id": "fanyin", "label": "温柔清晰",
     "dims": {"gender": "女性", "age": "年轻女性", "timbre": "温润", "persona": "温柔亲切",
              "pace": "适中", "emotion": "温和"},
     "target": {"f0": [195, 235], "centroid": 2500}},
    {"id": "zhixing", "label": "成熟知性",
     "dims": {"gender": "女性", "age": "成熟", "timbre": "醇厚", "persona": "知性稳重",
              "pace": "舒缓", "emotion": "平和"},
     "target": {"f0": [190, 230], "centroid": 3200}},
    {"id": "yujie", "label": "御姐",
     "dims": {"gender": "女性", "age": "成熟", "timbre": "冷冽", "persona": "冷艳强势",
              "pace": "适中", "emotion": "克制"},
     "target": {"f0": [185, 220], "centroid": 3400}},
    {"id": "ruanmeng", "label": "软萌",
     "dims": {"gender": "女性", "age": "少女", "timbre": "气声", "persona": "甜美灵动",
              "pace": "舒缓", "emotion": "温和"},
     "target": {"f0": [330, 375], "centroid": 2400},
     "seed": 6},
    {"id": "wenyi", "label": "温婉古典",
     "dims": {"gender": "女性", "age": "轻熟", "timbre": "清亮", "persona": "古典端庄",
              "pace": "舒缓", "emotion": "温和"},
     "target": {"f0": [230, 285], "centroid": 2600},
     "seed": 5},
    {"id": "qingleng", "label": "清冷疏离",
     "dims": {"gender": "女性", "age": "年轻女性", "timbre": "冷冽", "persona": "冷艳强势",
              "pace": "适中", "emotion": "克制"},
     "target": {"f0": [195, 235], "centroid": 3100}},
    {"id": "ganlian", "label": "干练职场",
     "dims": {"gender": "女性", "age": "成熟", "timbre": "清亮", "persona": "知性稳重",
              "pace": "轻快", "emotion": "平和"},
     "target": {"f0": [300, 345], "centroid": 2300}},
    {"id": "youya", "label": "优雅端庄",
     "dims": {"gender": "女性", "age": "成熟", "timbre": "醇厚", "persona": "古典端庄",
              "pace": "适中", "emotion": "克制"},
     "target": {"f0": [175, 205], "centroid": 3700}},
    {"id": "huopo", "label": "活泼俏皮",
     "dims": {"gender": "女性", "age": "少女", "timbre": "清亮", "persona": "活泼俏皮",
              "pace": "轻快", "emotion": "愉悦"},
     "target": {"f0": [345, 395], "centroid": 2200}},
    {"id": "shenye", "label": "深夜电台",
     "dims": {"gender": "女性", "age": "轻熟", "timbre": "气声", "persona": "慵懒松弛",
              "pace": "舒缓", "emotion": "温和"},
     "target": {"f0": [190, 225], "centroid": 3700}},
    {"id": "cixiang", "label": "慈祥长辈",
     "dims": {"gender": "女性", "age": "长辈", "timbre": "清亮", "persona": "温柔亲切",
              "pace": "舒缓", "emotion": "愉悦"},
     "target": {"f0": [180, 220], "centroid": 2400},
     "seed": 5},
]


def _option_index() -> Dict[str, Dict[str, Dict[str, object]]]:
    """维度键 → 选项值 → 选项定义。"""
    return {
        str(dim["key"]): {str(opt["value"]): opt for opt in dim["options"]}
        for dim in DIMENSIONS
    }


def _clamped(key: str, value: float) -> float:
    low, high = PARAM_LIMITS[key]
    return float(min(max(value, low), high))


def normalize(dims: Mapping[str, object]) -> Dict[str, str]:
    """校验并归一化维度组合；缺项或取值不在表内一律拒绝，不猜默认。"""
    table = _option_index()
    normalized: Dict[str, str] = {}
    for key in DIMENSION_ORDER:
        raw = str(dims.get(key, "") or "").strip()
        if not raw:
            raise ValueError(f"缺少维度 {key}")
        if raw not in table[key]:
            allowed = "/".join(table[key])
            raise ValueError(f"维度 {key} 只接受 {allowed}，实际 {raw!r}")
        normalized[key] = raw
    return normalized


def _is_male(normalized: Mapping[str, str]) -> bool:
    return normalized.get("gender") in MALE_GENDERS


def compose_params(dims: Mapping[str, object]) -> Dict[str, float]:
    """把各维度的数值参数累加起来，按区间夹紧。

    pitch / speed / gain 逐项相加；cfg_scale / temperature / top_k 由
    personality 决定，后写覆盖，避免多个维度各说一套互相抵消。
    男声档位下 age 不参与：两个维度的音高增量相加会把男声又拉回女声区。
    """
    table = _option_index()
    normalized = normalize(dims)
    skip = {"age"} if _is_male(normalized) else set()
    params = dict(BASE_PARAMS)
    for key in DIMENSION_ORDER:
        if key in skip:
            continue
        option = table[key][normalized[key]]
        for name, raw in (option.get("params") or {}).items():
            if name not in PARAM_LIMITS:
                continue
            value = float(raw)
            if name in ACCUMULATED:
                params[name] = params.get(name, BASE_PARAMS.get(name, 0.0)) + value
            else:
                params[name] = value
    return {name: _clamped(name, value) for name, value in params.items()}


def describe_params(params: Mapping[str, float]) -> str:
    """把参数渲染成一行可读摘要，给界面与日志用。"""
    return (f"音高 {params['pitch']:+.1f} 半音 / 语速 x{params['speed']:.2f} / "
            f"cfg {params['cfg_scale']:.1f} / temp {params['temperature']:.2f} / "
            f"top_k {params['top_k']:.0f}")


def _pitch_words(pitch: float, male: bool = False) -> str:
    """把音高参数翻译成模型能听懂的音高描述。

    不用重采样改音高：那会把共振峰整体挪走（+4 半音 = 上移 26%），
    声音会变成花栗鼠或慢放怪声，听感直接崩掉。

    中音档也要明写 female：不写的时候模型会飘到中性或偏低的地方，
    实测 wenyi 因此掉到 220 Hz，听成男声。男声反向同理，档位必须写死性别。
    """
    if male:
        if pitch >= -2.5:
            return "slightly high-pitched young male voice"
        if pitch >= -4.5:
            return "medium-pitched young male voice"
        if pitch >= -5.5:
            return "slightly low-pitched mature male voice"
        return "deep low-pitched male voice"
    if pitch >= 3.0:
        return "high-pitched youthful female voice"
    if pitch >= 1.5:
        return "slightly high-pitched female voice"
    if pitch <= -3.0:
        return "deep low-pitched female voice"
    if pitch <= -1.5:
        return "slightly low-pitched female voice"
    return "medium-pitched female voice"


def compose(dims: Mapping[str, object]) -> str:
    """把维度组合成一条英文指令：音高档 + 各维度措辞 + 能量句 + 否定项。"""
    table = _option_index()
    normalized = normalize(dims)
    male = _is_male(normalized)
    params = compose_params(dims)
    skip = {"age"} if male else set()
    parts = []
    avoid = []
    for key in DIMENSION_ORDER:
        option = table[key][normalized[key]]
        text = str(option["text"])
        # 女声是基准，不额外描述；男声档位下年龄措辞会与性别冲突，一律不拼。
        if text and key not in skip:
            parts.append(text)
        neg = str(option.get("neg") or "")
        if neg:
            avoid.append(neg)
    pitch_word = _pitch_words(params["pitch"], male)
    if pitch_word:
        parts.insert(0, pitch_word)
    # 不能写 "speak with energy"：那句会让模型转成播报腔（实测 wenyi 被听成广播员）。
    # 也不能不写能量：不写时响度只 -25~-40 dB、基频起伏 22~48，像有气无力。
    # 所以明确要求“像真人说话、不要像念新闻”。
    return (f"must be {', '.join(parts)}. sound like a real person talking with natural "
            f"liveliness, not reading the news. definitely not {avoid}.")


def describe(dims: Mapping[str, object]) -> str:
    """给界面看的中文描述；英文指令只进模型。

    男声档位下年龄不参与拼装，描述里也不列，否则会出现「少年，少女」这种自相矛盾的组合。
    """
    normalized = normalize(dims)
    skip = {"age"} if _is_male(normalized) else set()
    return "，".join(normalized[key] for key in DIMENSION_ORDER if key not in skip)


def seed_for(dims: Mapping[str, object]) -> int:
    """返回该组合对应的预设种子；不是预设组合就返回 0（服务端默认 42）。

    试听与保存必须用同一个种子：同一句指令换 seed 就是另一个音色，
    否则用户听到的与存下来的不是一个声音。
    """
    normalized = normalize(dims)
    for preset in PRESETS:
        if normalize(preset["dims"]) == normalized:
            return int(preset.get("seed") or 0)
    return 0


def options_payload() -> Dict[str, object]:
    """给界面的完整选项：维度、预设、样板句与基准参数。"""
    return {
        "dimensions": DIMENSIONS,
        "order": list(DIMENSION_ORDER),
        "presets": PRESETS,
        "sample_text": SAMPLE_TEXT,
        "base_params": BASE_PARAMS,
        "param_limits": {k: list(v) for k, v in PARAM_LIMITS.items()},
    }


#: 试听与参考音色共用同一句样板，保证音色之间的差异只来自参数本身。
SAMPLE_TEXT = "陛下，这件事臣妾已经办好了，请您放心。"
