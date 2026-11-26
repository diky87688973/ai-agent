# -*- coding: utf-8 -*-
"""合成引擎的唯一注册点：按配置装配实现，上层不直接引用具体 provider。

新增引擎只改这里：加一个分支、加一个模块，其余调用方不动。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent.common.tts_contract import TTSEngineUnavailable, TTSProvider

from . import models, pinyin
from .breeze_provider import BreezeProvider
from .config import TTSConfig
from .edge_provider import EdgeProvider
from .supervisor import ServerSupervisor
from .voice_lab import VoiceLab


def create_supervisor(config: TTSConfig) -> Optional[ServerSupervisor]:
    """按配置构造本地服务的进程管理；未配置安装目录时返回 None。"""
    root = str(config.model_dir or "").strip()
    if not root:
        return None
    base = Path(root)
    return ServerSupervisor(
        exe=models.server_executable(base),
        model=models.model_path(base, config.default_model),
        port=config.server_port,
        startup_timeout=config.startup_timeout,
        idle_timeout=config.idle_timeout,
        voices_dir=base / "voices",
    )


def create_voice_lab(config: TTSConfig, provider: TTSProvider) -> Optional[VoiceLab]:
    """只有本地引擎有参考音色概念；网络引擎没有音色库，返回 None。

    工作台复用 provider 已有的进程管理，否则会起第二套服务进程，
    两边各自拉一份模型、各自回收，显存与状态都对不上。
    """
    if not isinstance(provider, BreezeProvider):
        return None
    return VoiceLab(config, provider.supervisor, provider)


def create_provider(config: TTSConfig) -> TTSProvider:
    """按 `engine` 装配一个 provider。"""
    if config.engine == "edge":
        return EdgeProvider(voice=config.edge_voice, pinyin=pinyin)

    supervisor = create_supervisor(config)
    if supervisor is None:
        raise TTSEngineUnavailable(
            "本地引擎需要配置 model_dir（模型与推理程序的安装目录）")
    return BreezeProvider(
        supervisor=supervisor,
        voice_desc=config.voice_desc,
        emotion=config.emotion,
        cfg_scale=config.cfg_scale,
        voice_id=config.voice_id,
        temperature=config.temperature,
        top_k=config.top_k,
    )
