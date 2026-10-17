# -*- coding: utf-8 -*-
"""TTS 插件——语音播报文本侧。

工作方式：
- 订阅事件总线：assistant_delta → 句子缓冲切分 → 每会话串行队列合成；
- turn_ended / error → flush_remaining 强制入队；
- 音频就绪时默认只写 stderr（调试用）；可选 `on_audio` 钩子供测试替换。

配置在本插件目录下的 `plugin-config.ini`：`[base]` 是身份与开关，`[ext]` 是 `engine` / `voice` / `max_segment_chars`。
"""
from __future__ import annotations

import hashlib
import queue
import re
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.core import event_name as ev

# ── 引擎层 ──


class TTSProvider:
    """TTS 引擎契约：把文本合成成音频字节流。"""

    name = "base"

    def synthesize(self, text: str, *, voice: Optional[str] = None) -> bytes:
        """将文本合成为音频字节流；无音频产出时返回空字节。"""
        raise NotImplementedError(f"TTSProvider 未实现 synthesize：{type(self).__name__}")

    @property
    def default_voice(self) -> str:
        return ""

    @property
    def available_voices(self) -> List[Dict[str, str]]:
        return []


class ConsoleTTSProvider(TTSProvider):
    """调试引擎：打印文本不发声。"""

    name = "console"

    @property
    def default_voice(self) -> str:
        return "console"

    def synthesize(self, text: str, *, voice: Optional[str] = None) -> bytes:
        print(f"[TTS] {text}", file=sys.stderr, flush=True)
        return b""


class EdgeTTSProvider(TTSProvider):
    """edge-tts 引擎；缺库降级为空合成并提示。"""

    name = "edge"

    VOICES: List[Dict[str, str]] = [
        {"name": "zh-CN-XiaoxiaoNeural", "display": "晓晓（女声-亲切）", "gender": "female"},
        {"name": "zh-CN-XiaoyiNeural", "display": "晓伊（女声-自然）", "gender": "female"},
        {"name": "zh-CN-YunjianNeural", "display": "云健（男声-沉稳）", "gender": "male"},
        {"name": "zh-CN-YunxiNeural", "display": "云希（男声-阳光）", "gender": "male"},
        {"name": "zh-CN-YunyangNeural", "display": "云扬（男声-成熟）", "gender": "male"},
        {"name": "zh-CN-XiaochenNeural", "display": "晓辰（女声-可爱）", "gender": "female"},
        {"name": "zh-CN-XiaohanNeural", "display": "晓涵（女声-温润）", "gender": "female"},
    ]

    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural"):
        self._voice = voice
        self._import_err: Optional[str] = None
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            self._import_err = "edge-tts 未安装。请执行: pip install edge-tts"

    @property
    def default_voice(self) -> str:
        return self._voice

    @property
    def available_voices(self) -> List[Dict[str, str]]:
        return list(self.VOICES)

    def synthesize(self, text: str, *, voice: Optional[str] = None) -> bytes:
        if self._import_err:
            print(f"[EdgeTTS] {self._import_err}", file=sys.stderr, flush=True)
            return b""
        import edge_tts

        v = voice or self._voice
        try:
            communicate = edge_tts.Communicate(text, v)
            chunks: List[bytes] = []
            for chunk in communicate.stream_sync():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    chunks.append(chunk["data"])
            return b"".join(chunks)
        except Exception as exc:
            print(f"[EdgeTTS] 合成失败: {exc}", file=sys.stderr, flush=True)
            return b""


def create_tts_provider(engine: str = "console", voice: Optional[str] = None) -> TTSProvider:
    """引擎工厂：edge → EdgeTTSProvider；其余 → Console。"""
    name = str(engine or "console").strip().lower()
    if name == "edge":
        return EdgeTTSProvider(voice=voice or "zh-CN-XiaoxiaoNeural")
    return ConsoleTTSProvider()


# ── 文本处理（切分与净化） ──

_SENTENCE_END = re.compile(r"[。！？!?;\n]+")

_SYMBOL_MAP: Dict[str, str] = {
    "→": "转为", "←": "从", "↑": "上", "↓": "下",
    "±": "正负", "×": "乘", "÷": "除",
    "℃": "摄氏度",
    "≠": "不等于", "=": "等于",
}

_OP_MAP: Dict[str, str] = {"+": "加", "-": "减", "*": "乘", "/": "除"}


def chunk_text_for_tts(text: str, max_len: int) -> List[str]:
    """按句末切分；单段超长再硬切。"""
    t = str(text or "").strip()
    if not t:
        return []
    parts: List[str] = []
    buf = t
    while buf:
        m = _SENTENCE_END.search(buf)
        if m:
            piece = buf[: m.end()].strip()
            buf = buf[m.end():].lstrip()
        elif len(buf) > max_len:
            piece = buf[:max_len].strip()
            buf = buf[max_len:].lstrip()
        else:
            parts.append(buf)
            break
        if piece and len(piece) >= 2:
            if len(piece) <= max_len:
                parts.append(piece)
            else:
                for i in range(0, len(piece), max_len):
                    sub = piece[i: i + max_len].strip()
                    if sub and len(sub) >= 2:
                        parts.append(sub)
    return parts


def prepare_for_tts(text: str) -> str:
    """文本配音预处理：符号 / 运算符 / 百分号 / 小数；保留标点。"""
    t = str(text or "")
    for k, v in _SYMBOL_MAP.items():
        t = t.replace(k, v)

    def _op_repl(m):
        return m.group(1) + _OP_MAP.get(m.group(2), m.group(2)) + m.group(3)

    t = re.sub(r"(\d+)\s*([+\-*/])\s*(\d+)", _op_repl, t)
    t = re.sub(r"([\d.]+)％", lambda m: "百分之" + m.group(1), t)
    t = re.sub(r"([\d.]+)%", lambda m: "百分之" + m.group(1), t)

    def _dec_repl(m):
        cn = "零一二三四五六七八九"
        return m.group(1) + "点" + "".join(cn[int(d)] for d in m.group(2))

    return re.sub(r"(\d+)\.(\d+)", _dec_repl, t)


def sanitize_for_tts(text: str) -> str:
    """送合成前的完全净化：去转义 / 白名单 / 合并空格。"""
    t = prepare_for_tts(text)
    t = re.sub(r"\\[a-z]", "", t)
    t = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _segment_ok(text: str) -> bool:
    """段过滤器：长度 ≥2 或含中文/字母。"""
    t = str(text or "").strip()
    if not t:
        return False
    if len(t) >= 2:
        return True
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", t))


# ── 音色 ──

TTS_VOICES: List[str] = [
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-XiaoyiNeural",
    "zh-CN-YunjianNeural",
    "zh-CN-YunxiNeural",
    "zh-CN-YunyangNeural",
    "zh-CN-XiaochenNeural",
    "zh-CN-XiaohanNeural",
]


def voice_for(cid: str, name: str = "") -> str:
    """音色分配：无来源 → 晓晓；否则 md5(cid|name) 哈希取模。"""
    if not cid and not name:
        return TTS_VOICES[0]
    raw = f"{cid or ''}|{name or ''}"
    idx = int(hashlib.md5(raw.encode("utf-8")).hexdigest(), 16) % len(TTS_VOICES)
    return TTS_VOICES[idx]


# ── 运行时（缓冲 / 队列） ──

_SYNTHESIZE_TIMEOUT = 15


def _parse_item(item: Any) -> Tuple[str, Optional[str], str]:
    if isinstance(item, str):
        return item, None, ""
    if isinstance(item, (list, tuple)):
        if len(item) >= 3:
            text, voice, dbg = item[:3]
            return str(text or ""), voice, str(dbg or "")
        if len(item) >= 2:
            text, voice = item[:2]
            return str(text or ""), voice, ""
    return str(item or ""), None, ""


class TTSRuntime:
    """TTS 运行时：配置 / 引擎 / 每会话句子缓冲与串行队列 / 开关。"""

    def __init__(
        self,
        config: Dict[str, str],
        on_audio: Optional[Callable[..., None]] = None,
        provider: Optional[TTSProvider] = None,
    ) -> None:
        self._config = dict(config or {})
        self._on_audio = on_audio
        self._provider = provider
        self._provider_lock = threading.Lock()
        self._buffers: Dict[str, str] = {}
        self._last_voice: Dict[str, Tuple[Optional[str], str]] = {}
        self._buffers_lock = threading.Lock()
        self._queues: Dict[str, queue.Queue] = {}
        self._queues_lock = threading.Lock()

    # ── 配置 ──

    def _cfg(self, key: str, default: str = "") -> str:
        return str(self._config.get(key) or default).strip()

    def max_segment_chars(self) -> int:
        try:
            n = int(self._cfg("max_segment_chars") or "240")
        except ValueError:
            n = 240
        return max(40, min(n, 2000))

    def engine_name(self) -> str:
        return self._cfg("engine", "console").lower() or "console"

    # ── 引擎（延迟初始化） ──

    def provider(self) -> TTSProvider:
        if self._provider is None:
            with self._provider_lock:
                if self._provider is None:
                    voice = self._cfg("voice") or None
                    self._provider = create_tts_provider(self.engine_name(), voice=voice)
        return self._provider

    # ── 句子缓冲 ──

    # ── 句子缓冲 ──

    def feed(self, cid: str, delta: str, voice: Optional[str] = None, dbg_sender: str = "") -> None:
        """喂入文本增量：整句（或超长段）切分后入串行队列。"""
        cid = str(cid or "")
        if not delta or not cid:
            return
        max_len = self.max_segment_chars()
        texts: List[str] = []
        with self._buffers_lock:
            self._last_voice[cid] = (voice, dbg_sender or "")
            buf = self._buffers.get(cid, "") + str(delta)
            while buf:
                m = _SENTENCE_END.search(buf)
                if m:
                    sentence = buf[: m.end()]
                    buf = buf[m.end():]
                    texts.extend(chunk_text_for_tts(sentence, max_len))
                    continue
                if len(buf) >= max_len:
                    texts.extend(chunk_text_for_tts(buf[:max_len], max_len))
                    buf = buf[max_len:]
                    continue
                break
            self._buffers[cid] = buf
        for t in texts:
            t = t.strip()
            if _segment_ok(t):
                self._get_queue(cid).put((t, voice, dbg_sender or ""))

    def flush(self, cid: str) -> None:
        """回合收尾：清空缓冲并强制入队。"""
        cid = str(cid or "")
        with self._buffers_lock:
            voice, dbg = self._last_voice.get(cid, (None, ""))
            remaining = self._buffers.pop(cid, "")
        if remaining:
            for t in chunk_text_for_tts(remaining.strip(), self.max_segment_chars()):
                if _segment_ok(t):
                    self._get_queue(cid).put((t, voice, dbg))

    # ── 队列与合成 ──

    def _get_queue(self, cid: str) -> queue.Queue:
        with self._queues_lock:
            q = self._queues.get(cid)
            if q is None:
                q = queue.Queue()
                self._queues[cid] = q
                threading.Thread(target=self._consume, args=(cid,), daemon=True).start()
            return q

    def _consume(self, cid: str) -> None:
        q = self._queues.get(cid)
        if q is None:
            return
        while True:
            try:
                item = q.get()
            except Exception:
                break
            if item is None:
                break
            text, voice, dbg = _parse_item(item)
            if not str(text or "").strip():
                continue
            try:
                self._synthesize_and_emit(cid, text, voice, dbg)
            except Exception as exc:
                print(f"[TTS] 合成失败 cid={cid}: {exc}", file=sys.stderr, flush=True)
        with self._queues_lock:
            self._queues.pop(cid, None)

    def _synthesize_and_emit(self, cid: str, text: str, voice: Optional[str], dbg: str) -> None:
        spoken = prepare_for_tts(text)  # 展示文本（保留标点，供 UI 对齐）
        clean = sanitize_for_tts(text)
        if not clean:
            return
        provider = self.provider()
        result: List[bytes] = []
        errors: List[Exception] = []

        def _synth() -> None:
            try:
                result.append(provider.synthesize(clean, voice=voice))
            except Exception as exc:
                errors.append(exc)

        t = threading.Thread(target=_synth, daemon=True)
        t.start()
        t.join(timeout=_SYNTHESIZE_TIMEOUT)
        if t.is_alive():
            print(f"[TTS] 合成超时({_SYNTHESIZE_TIMEOUT}s)，跳过: {clean[:40]}...", file=sys.stderr, flush=True)
            return
        if errors:
            print(f"[TTS] 合成失败: {errors[0]}", file=sys.stderr, flush=True)
            return
        audio = result[0] if result else b""
        if audio:
            self._emit_audio(cid, audio, spoken, voice or TTS_VOICES[0], dbg)

    def _emit_audio(self, cid: str, audio: bytes, text: str, voice: str, dbg: str) -> None:
        """音频就绪：有 `on_audio` 则回调，否则只写 stderr。"""
        if self._on_audio is not None:
            self._on_audio(cid=cid, audio=audio, text=text, voice=voice, dbg=dbg)
            return
        print(
            f"[TTS] 音频就绪 cid={cid} bytes={len(audio)} voice={voice} text={text[:40]}...",
            file=sys.stderr,
            flush=True,
        )

    def dispose(self) -> None:
        """卸载：唤醒全部消费线程退出。"""
        with self._queues_lock:
            queues = list(self._queues.values())
        for q in queues:
            try:
                q.put(None)
            except Exception:
                pass


# ── 插件入口（事件订阅） ──

_RUNTIMES: Dict[str, TTSRuntime] = {}


def get_runtime(name: str = "tts") -> Optional[TTSRuntime]:
    """获取已加载插件的运行时（测试与壳层接入用）。"""
    return _RUNTIMES.get(name)


def _config_path() -> Path:
    """本插件的配置文件：`plugins/tts/plugin-config.ini`。

    配置与本插件同目录：内核的 `config.ini` 只含内核设置。
    """
    return Path(__file__).resolve().parent / "plugin-config.ini"


def _load_tts_config() -> Dict[str, str]:
    """读取本插件配置的 `[ext]` 节（缺失返回空 dict）。"""
    try:
        from agent.config import load_ini

        parser = load_ini(_config_path())
        if parser.has_section("ext"):
            return {k: str(v).strip().strip("'\"") for k, v in parser.items("ext")}
    except Exception:
        pass
    return {}


def _make_delta_handler(runtime: TTSRuntime) -> Callable[[Any], None]:
    def _handler(event: Any) -> None:
        data = getattr(event, "data", None) or {}
        cid = str(data.get("conversation_id") or "")
        text = str(data.get("text") or "")
        if cid and text:
            runtime.feed(cid, text, voice=voice_for("", ""))

    return _handler


def _make_flush_handler(runtime: TTSRuntime) -> Callable[[Any], None]:
    def _handler(event: Any) -> None:
        data = getattr(event, "data", None) or {}
        cid = str(data.get("conversation_id") or "")
        if cid:
            runtime.flush(cid)

    return _handler


def register(ctx: Any) -> List[Callable[[], None]]:
    """插件入口：装配运行时并订阅事件总线（返回 disposer 列表）。"""
    runtime = TTSRuntime(_load_tts_config())
    # 登记给宿主（动态模块名下壳层 import 不到同一份实例）。
    ctx.set_runtime(runtime)
    _RUNTIMES[ctx.name] = runtime
    disposers: List[Callable[[], None]] = [
        ctx.subscribe(ev.ASSISTANT_DELTA, _make_delta_handler(runtime)),
        ctx.subscribe(ev.TURN_ENDED, _make_flush_handler(runtime)),
        ctx.subscribe(ev.ERROR, _make_flush_handler(runtime)),
    ]

    def _cleanup() -> None:
        _RUNTIMES.pop(ctx.name, None)
        runtime.dispose()

    disposers.append(_cleanup)
    return disposers
