# -*- coding: utf-8 -*-
"""音色实验室：把维度组合变成试听音频，满意后注册成固定音色。

试听与参考音色用同一句样板、同一套采样参数，差异只来自维度本身。
注册走服务端 `/v1/voices`，维度组合写进它的 metadata，以后可还原当初怎么配。
"""
from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Mapping

import numpy as np

from agent.common.tts_contract import TTSEngineUnavailable, TTSRequest, TTSResult

from . import schema

_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_VOICE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_TIMEOUT_S = 180.0


def _measure(audio: bytes, sample_rate: int) -> Dict[str, float]:
    """算一次生成的关键指标：基频中位数、频谱质心、时长。

    产品流程不用它，留给测试与诊断：音色是否落在定位区间靠这三个值判定。
    """
    data = np.frombuffer(audio, dtype="<i2").astype(np.float32)
    seconds = data.size / float(sample_rate)
    window = 960
    frames = data[: (data.size // window) * window].reshape(-1, window)
    if frames.size == 0:
        return {"f0": 0.0, "centroid": 0.0, "seconds": seconds}
    energy = np.sqrt((frames ** 2).mean(axis=1))
    picked = frames[energy >= np.percentile(energy, 60)][:80] if frames.shape[0] else frames
    f0s: List[float] = []
    centroids: List[float] = []
    low_lag = int(sample_rate / 400)
    high_lag = int(sample_rate / 60)
    for frame in picked:
        centered = frame - frame.mean()
        corr = np.correlate(centered, centered, mode="full")[centered.size - 1:]
        if high_lag < corr.size:
            lag = low_lag + int(np.argmax(corr[low_lag:high_lag]))
            if corr[lag] > 0.3 * corr[0]:
                f0s.append(sample_rate / lag)
        spec = np.abs(np.fft.rfft(centered * np.hanning(centered.size)))
        freqs = np.fft.rfftfreq(centered.size, 1.0 / sample_rate)
        if spec.sum() > 0:
            centroids.append(float((spec * freqs).sum() / spec.sum()))
    return {
        "f0": float(np.median(f0s)) if f0s else 0.0,
        "centroid": float(np.mean(centroids)) if centroids else 0.0,
        "seconds": seconds,
    }


class VoiceLabError(ValueError):
    """音色操作失败；消息面向使用者，可直接展示。"""


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(int(sample_rate))
        writer.writeframes(pcm)
    return buffer.getvalue()


class VoiceLab:
    """一个本地引擎上的音色工作台。"""

    def __init__(self, config: Any, supervisor: Any, provider: Any) -> None:
        self._config = config
        self._supervisor = supervisor
        self._provider = provider

    # ── 试听 ──────────────────────────────────────────────

    def preview(self, dims: Mapping[str, object], seed: int = 0) -> TTSResult:
        """按维度组合合成一句样板。

        必须带 design=True：不给参考音色，模型才会按指令真的造一个新音色。
        波形一律不做处理：重采样变调会挪走共振峰、手写变速会切碎语音，
        两样都试过，听感都崩。音高走指令，语速走播放器。

        seed 为 0 时按该组合对应的预设种子取，保证“听到的”就是“存下来的”。
        """
        params = schema.compose_params(dims)
        return self._provider.synthesize(TTSRequest(
            text=schema.SAMPLE_TEXT,
            instruction=schema.compose(dims),
            voice_id="",
            design=True,
            seed=seed or schema.seed_for(dims),
            cfg_scale=params["cfg_scale"],
            temperature=params["temperature"],
            top_k=int(params["top_k"]),
            timeout_s=_TIMEOUT_S,
        ))

    # ── 保存 ──────────────────────────────────────────────

    def save(self, dims: Mapping[str, object], voice_id: str) -> Dict[str, Any]:
        """把当前组合固化成命名音色。"""
        name = str(voice_id or "").strip()
        if not _VOICE_ID_RE.match(name):
            raise VoiceLabError(
                "音色 id 只允许小写字母开头，后接小写字母、数字、下划线或短横线，最长 64")
        description = schema.describe(dims)
        normalized = schema.normalize(dims)
        params = schema.compose_params(dims)

        result = self.preview(dims)
        wav = _pcm_to_wav(result.audio, result.sample_rate)
        base = self._supervisor.ensure_ready()
        metadata: Dict[str, str] = dict(normalized)
        metadata.update({name: f"{value:g}" for name, value in params.items()})
        payload = self._post_voice(base, name, wav, description, metadata)
        return {
            "id": name,
            "description": description,
            "dims": normalized,
            "params": params,
            "seconds": round(len(result.audio) / 2 / max(1, result.sample_rate), 2),
            "voice": payload,
        }

    # ── 查询与删除 ────────────────────────────────────────

    def list_voices(self) -> List[Dict[str, Any]]:
        base = self._supervisor.ensure_ready()
        rows = self._get_json(base, "/v1/voices")
        if not isinstance(rows, list):
            return []
        return [
            {
                "id": str(row.get("id") or ""),
                "seconds": float(row.get("seconds") or 0.0),
                "saved": bool(row.get("saved")),
                "description": str(row.get("description") or ""),
                "dims": dict(row.get("metadata") or {}),
            }
            for row in rows
            if isinstance(row, dict) and row.get("id")
        ]

    def delete_voice(self, voice_id: str) -> Dict[str, Any]:
        """删内存与磁盘两处。

        服务端 DELETE 只清内存并保留 `.breeze`，下次启动会把它读回来，
        所以磁盘文件必须自己删，否则「删了又回来」。
        """
        name = str(voice_id or "").strip()
        if not _VOICE_ID_RE.match(name):
            raise VoiceLabError(f"非法音色 id：{voice_id!r}")
        base = self._supervisor.ensure_ready()
        dropped = False
        req = urllib.request.Request(f"{base}/v1/voices/{name}", method="DELETE")
        try:
            with _NO_PROXY.open(req, timeout=_TIMEOUT_S) as resp:
                resp.read()
            dropped = True
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise VoiceLabError(f"删除音色失败：HTTP {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise TTSEngineUnavailable(f"无法连接本地合成服务：{exc}") from exc

        removed_file = False
        path = self._voices_dir() / f"{name}.breeze"
        if path.is_file():
            try:
                path.unlink()
                removed_file = True
            except OSError as exc:
                raise VoiceLabError(f"音色文件删除失败：{exc}") from exc
        return {"id": name, "dropped": dropped, "removed_file": removed_file}

    # ── 当前音色 ──────────────────────────────────────────

    def set_current(self, voice_id: str) -> Dict[str, Any]:
        """把配置里的 voice_id 改成指定值；重载插件后生效。"""
        name = str(voice_id or "").strip()
        if not _VOICE_ID_RE.match(name):
            raise VoiceLabError(f"非法音色 id：{voice_id!r}")
        known = {row["id"] for row in self.list_voices()}
        if name not in known:
            raise VoiceLabError(f"音色 {name!r} 不存在，先保存再启用")
        from .config import config_path

        path = config_path()
        text = path.read_text(encoding="utf-8")
        pattern = re.compile(r"^(?P<lead>\s*voice_id\s*=\s*).*$", re.MULTILINE)
        if not pattern.search(text):
            raise VoiceLabError("配置文件里没有 voice_id 键，无法写入")
        updated = pattern.sub(lambda m: m.group("lead") + name, text, count=1)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
        # 同步运行态：provider 手里是装配期的 voice_id快照，
        # 只改文件的话新音色要等重载插件才生效。
        self._provider.set_voice_id(name)
        return {"voice_id": name, "reload_required": False}

    # ── 内部 ──────────────────────────────────────────────

    def _voices_dir(self) -> Path:
        root = str(getattr(self._config, "model_dir", "") or "").strip()
        return Path(root) / "voices"

    def _post_voice(self, base: str, name: str, wav: bytes,
                    description: str, dims: Mapping[str, str]) -> Dict[str, Any]:
        boundary = "----ttsvoiceboundary"
        body = b""
        body += ("--" + boundary + "\r\n").encode()
        body += (b'Content-Disposition: form-data; name="ref_audio"; '
                 b'filename="ref.wav"\r\nContent-Type: audio/wav\r\n\r\n')
        body += wav + b"\r\n"
        fields = (
            ("ref_text", schema.SAMPLE_TEXT),
            ("name", name),
            ("description", description),
            ("metadata", json.dumps(dims, ensure_ascii=False)),
        )
        for field, value in fields:
            body += ("--" + boundary + "\r\n").encode()
            body += (f'Content-Disposition: form-data; name="{field}"\r\n\r\n').encode("utf-8")
            body += value.encode("utf-8") + b"\r\n"
        body += ("--" + boundary + "--\r\n").encode()
        req = urllib.request.Request(
            base + "/v1/voices", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with _NO_PROXY.open(req, timeout=_TIMEOUT_S) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except OSError:
                detail = ""
            raise VoiceLabError(
                f"注册音色被拒绝（HTTP {exc.code}）：{detail}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise TTSEngineUnavailable(f"无法连接本地合成服务：{exc}") from exc
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _get_json(self, base: str, path: str) -> Any:
        req = urllib.request.Request(base + path)
        try:
            with _NO_PROXY.open(req, timeout=_TIMEOUT_S) as resp:
                raw = resp.read()
        except (urllib.error.URLError, OSError) as exc:
            raise TTSEngineUnavailable(f"无法连接本地合成服务：{exc}") from exc
        try:
            return json.loads(raw or b"[]")
        except ValueError as exc:
            raise VoiceLabError(f"服务返回无法解析：{exc}") from exc
