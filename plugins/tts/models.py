# -*- coding: utf-8 -*-
"""可用模型清单与安装位置约定。

安装根目录由用户指定，目录下固定两件东西：模型文件与推理程序目录。
清单只登记实测可用的一项，避免把未验证的量化等级当成选择给出去。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping

#: 推理程序在安装根下的固定目录名。
ENGINE_DIR = "breeze-tts-2-cpp"
SERVER_EXE = "breeze-server.exe"


@dataclass(frozen=True)
class ModelSpec:
    """一项可安装的模型。"""

    id: str
    filename: str
    size_bytes: int
    sha256: str
    label: str
    note: str


#: `sha256` 是本机转换并量化后的实测值，用于确认"是不是同一份产物"；
#: 它不是官方发布校验和，因此引导安装时不作为下载校验依据。
MODELS: Mapping[str, ModelSpec] = {
    "breeze-tts-2-q4k": ModelSpec(
        id="breeze-tts-2-q4k",
        filename="breeze-tts-2-q4k-cpp.gguf",
        size_bytes=2538909376,
        sha256="483418fbbb438f5f1c08dbe2b017e42db0f1d126765cd3f772d8622a30a4915c",
        label="Breeze TTS 2 · Q4_K（实测可用）",
        note="约 2.36 GiB，常驻显存约 3.8 GiB，首帧 150~350 ms，支持情感与语速指令",
    ),
}


def default_model_id() -> str:
    return next(iter(MODELS))


def model_path(root: Path, model_id: str) -> Path:
    """模型文件在安装根下的位置。"""
    spec = MODELS.get(str(model_id or "").strip())
    if spec is None:
        raise KeyError(f"未登记的模型：{model_id!r}")
    return Path(root) / spec.filename


def server_executable(root: Path) -> Path:
    """推理程序在安装根下的位置。"""
    return Path(root) / ENGINE_DIR / SERVER_EXE


def installed(root: Path, model_id: str) -> bool:
    """模型与推理程序是否都已就位。"""
    if not str(root or "").strip():
        return False
    try:
        model = model_path(root, model_id)
    except KeyError:
        return False
    return model.is_file() and server_executable(root).is_file()


def describe(root: Path, model_id: str) -> Dict[str, object]:
    """给引导流程用的安装说明；路径一律给出绝对位置。"""
    base = Path(root) if str(root or "").strip() else None
    spec = MODELS.get(str(model_id or "").strip())
    return {
        "model_id": model_id,
        "label": spec.label if spec else "",
        "note": spec.note if spec else "",
        "model_dir": str(base) if base else "",
        "model_path": str(model_path(base, model_id)) if base and spec else "",
        "engine_dir": str(Path(base) / ENGINE_DIR) if base else "",
        "server_path": str(server_executable(base)) if base else "",
        "size_bytes": spec.size_bytes if spec else 0,
        "sha256": spec.sha256 if spec else "",
    }
