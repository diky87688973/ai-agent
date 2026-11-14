"""可下载扩散模型清单：下载体积、显存需求、镜像源与授权要求。

`files` 是下载器逐个取回的文件（仓库 / 文件名 / 目标子目录）；
`markers` 是判断该模型在本地是否就位的相对路径。
"""

from __future__ import annotations

from typing import Any, Dict, List

MIRROR = "https://hf-mirror.com"

_FLUX_TEXT = [
    ("comfyanonymous/flux_text_encoders", "t5xxl_fp16.safetensors", "text_encoders"),
    ("comfyanonymous/flux_text_encoders", "clip_l.safetensors", "text_encoders"),
    ("camenduru/FLUX.1-dev", "ae.safetensors", "vae"),
]

_CLIP_TOKENIZER = [
    ("openai/clip-vit-large-patch14", "config.json", "clip"),
    ("openai/clip-vit-large-patch14", "tokenizer_config.json", "clip"),
    ("openai/clip-vit-large-patch14", "special_tokens_map.json", "clip"),
    ("openai/clip-vit-large-patch14", "vocab.json", "clip"),
    ("openai/clip-vit-large-patch14", "merges.txt", "clip"),
]

_T5_TOKENIZER = [
    ("google/t5-v1_1-xxl", "config.json", "t5"),
    ("google/t5-v1_1-xxl", "special_tokens_map.json", "t5"),
    ("google/t5-v1_1-xxl", "tokenizer_config.json", "t5"),
    ("google/t5-v1_1-xxl", "spiece.model", "t5"),
]

_SDXL = "stabilityai/stable-diffusion-xl-base-1.0"

_SDXL_FILES = [
    (_SDXL, "model_index.json", "sdxl"),
    (_SDXL, "scheduler/scheduler_config.json", "sdxl"),
    (_SDXL, "text_encoder/config.json", "sdxl"),
    (_SDXL, "text_encoder/model.safetensors", "sdxl"),
    (_SDXL, "text_encoder_2/config.json", "sdxl"),
    (_SDXL, "text_encoder_2/model.safetensors", "sdxl"),
    (_SDXL, "tokenizer/merges.txt", "sdxl"),
    (_SDXL, "tokenizer/special_tokens_map.json", "sdxl"),
    (_SDXL, "tokenizer/tokenizer_config.json", "sdxl"),
    (_SDXL, "tokenizer/vocab.json", "sdxl"),
    (_SDXL, "tokenizer_2/merges.txt", "sdxl"),
    (_SDXL, "tokenizer_2/special_tokens_map.json", "sdxl"),
    (_SDXL, "tokenizer_2/tokenizer_config.json", "sdxl"),
    (_SDXL, "tokenizer_2/vocab.json", "sdxl"),
    (_SDXL, "tokenizer_2/spiece.model", "sdxl"),
    (_SDXL, "unet/config.json", "sdxl"),
    (_SDXL, "unet/diffusion_pytorch_model.safetensors", "sdxl"),
    (_SDXL, "vae/config.json", "sdxl"),
    (_SDXL, "vae/diffusion_pytorch_model.safetensors", "sdxl"),
]

CATALOG: List[Dict[str, Any]] = [
    {
        "id": "flux-dev-q4",
        "name": "FLUX.1-dev Q4_K_S（社区量化）",
        "quality": "最高",
        "download_gb": 16.0,
        "vram_gb": 12,
        "auth_required": False,
        "note": "主模型 6.34G + T5 9.12G + VAE 0.31G + CLIP 0.23G",
        "files": [
            ("city96/FLUX.1-dev-gguf", "flux1-dev-Q4_K_S.gguf", "gguf"),
            *_FLUX_TEXT,
            *_CLIP_TOKENIZER,
            *_T5_TOKENIZER,
        ],
        "markers": [
            "gguf/flux1-dev-Q4_K_S.gguf",
            "text_encoders/t5xxl_fp16.safetensors",
            "text_encoders/clip_l.safetensors",
            "vae/ae.safetensors",
            "clip/vocab.json",
            "t5/spiece.model",
        ],
    },
    {
        "id": "flux-schnell-q4",
        "name": "FLUX.1-schnell Q4_K_S（社区量化，4 步出图）",
        "quality": "高，速度快",
        "download_gb": 16.0,
        "vram_gb": 12,
        "auth_required": False,
        "note": "主模型 6.32G + T5 9.12G + VAE 0.31G + CLIP 0.23G",
        "files": [
            ("city96/FLUX.1-schnell-gguf", "flux1-schnell-Q4_K_S.gguf", "gguf"),
            *_FLUX_TEXT,
            *_CLIP_TOKENIZER,
            *_T5_TOKENIZER,
        ],
        "markers": [
            "gguf/flux1-schnell-Q4_K_S.gguf",
            "text_encoders/t5xxl_fp16.safetensors",
            "text_encoders/clip_l.safetensors",
            "vae/ae.safetensors",
            "clip/vocab.json",
            "t5/spiece.model",
        ],
    },
    {
        "id": "flux-dev-official",
        "name": "FLUX.1-dev 官方 fp16",
        "quality": "最高，无量化损失",
        "download_gb": 33.0,
        "vram_gb": 24,
        "auth_required": True,
        "note": "官方仓库为 gated，需 HuggingFace 账号授权与 token；本机 16G 显存通常不足",
        "files": [],
        "markers": [
            "flux1-dev/transformer/config.json",
            "flux1-dev/text_encoder_2/config.json",
            "flux1-dev/vae/config.json",
        ],
    },
    {
        "id": "sdxl-base",
        "name": "SDXL base 1.0 fp16",
        "quality": "稳定，生态最全",
        "download_gb": 7.0,
        "vram_gb": 8,
        "auth_required": False,
        "note": "官方原生权重，无量化，diffusers 直接加载",
        "files": _SDXL_FILES,
        "markers": [
            "sdxl/model_index.json",
            "sdxl/unet/diffusion_pytorch_model.safetensors",
            "sdxl/vae/diffusion_pytorch_model.safetensors",
        ],
    },
]


def find(model_id: str) -> Dict[str, Any]:
    for item in CATALOG:
        if item["id"] == model_id:
            return item
    raise ValueError(
        f"未知模型：{model_id}；可选：{', '.join(item['id'] for item in CATALOG)}")
