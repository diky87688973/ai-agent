"""一次调用式出图：加载权重、采样、存图后退出；由插件以 runtime_python 启动。

FLUX 走社区量化 GGUF + 独立文本编码器，VAE 必须关掉 quant_conv 系列层
（FLUX 的 ae 不含这两层，diffusers 默认新建会把解码结果搅成噪声）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import models

TRANSFORMER_CONFIG = {
    "_class_name": "FluxTransformer2DModel",
    "attention_head_dim": 128,
    "axes_dims_rope": [16, 56, 56],
    "guidance_embeds": True,
    "in_channels": 64,
    "joint_attention_dim": 4096,
    "num_attention_heads": 24,
    "num_layers": 19,
    "num_single_layers": 38,
    "out_channels": 64,
    "patch_size": 1,
    "pooled_projection_dim": 768,
}

VAE_CONFIG = {
    "_class_name": "AutoencoderKL",
    "in_channels": 3,
    "out_channels": 3,
    "down_block_types": [
        "DownEncoderBlock2D", "DownEncoderBlock2D",
        "DownEncoderBlock2D", "DownEncoderBlock2D",
    ],
    "up_block_types": [
        "UpDecoderBlock2D", "UpDecoderBlock2D",
        "UpDecoderBlock2D", "UpDecoderBlock2D",
    ],
    "block_out_channels": [128, 256, 512, 512],
    "layers_per_block": 2,
    "latent_channels": 16,
    "norm_num_groups": 32,
    "sample_size": 1024,
    "scaling_factor": 0.3611,
    "shift_factor": 0.1159,
    "use_quant_conv": False,
    "use_post_quant_conv": False,
}

CLIP_CONFIG = {
    "vocab_size": 49408,
    "hidden_size": 768,
    "intermediate_size": 3072,
    "num_hidden_layers": 12,
    "num_attention_heads": 12,
    "max_position_embeddings": 77,
    "hidden_act": "quick_gelu",
    "layer_norm_eps": 1e-5,
    "projection_dim": 768,
    "bos_token_id": 49406,
    "eos_token_id": 49407,
    "pad_token_id": 49407,
}


def _write_config_dir(root: Path, name: str, cfg: dict) -> str:
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _fill(module, weights: Path, dtype) -> int:
    from safetensors import safe_open

    filled = 0
    with safe_open(str(weights), framework="pt", device="cpu") as handle:
        for key in handle.keys():
            try:
                param = module.get_parameter(key)
            except AttributeError:
                print("skip-unmapped", key, file=sys.stderr, flush=True)
                continue
            tensor = handle.get_tensor(key)
            if tensor.dtype != dtype:
                tensor = tensor.to(dtype)
            param.data.copy_(tensor)
            filled += 1
    return filled


def _run_flux(root: Path, gguf: Path, args) -> None:
    from diffusers import (
        AutoencoderKL,
        FlowMatchEulerDiscreteScheduler,
        FluxPipeline,
        FluxTransformer2DModel,
        GGUFQuantizationConfig,
    )
    from diffusers.loaders.single_file_utils import convert_ldm_vae_checkpoint
    from safetensors.torch import load_file
    from transformers import (
        CLIPTextConfig,
        CLIPTextModel,
        CLIPTokenizer,
        T5Config,
        T5EncoderModel,
        T5TokenizerFast,
    )

    transformer = FluxTransformer2DModel.from_single_file(
        str(gguf),
        config=_write_config_dir(root, "cfg-transformer", TRANSFORMER_CONFIG),
        quantization_config=GGUFQuantizationConfig(compute_dtype=torch.bfloat16),
        torch_dtype=torch.bfloat16,
    )

    vae = AutoencoderKL(**{k: v for k, v in VAE_CONFIG.items() if not k.startswith("_")})
    state = convert_ldm_vae_checkpoint(load_file(str(root / "vae" / "ae.safetensors")), vae.config)
    vae.load_state_dict(state, strict=False)
    vae = vae.to(torch.bfloat16).eval()

    clip = CLIPTextModel(CLIPTextConfig(**CLIP_CONFIG))
    _fill(clip, root / "text_encoders" / "clip_l.safetensors", torch.bfloat16)
    clip = clip.to(torch.bfloat16).eval()

    t5 = T5EncoderModel(T5Config.from_pretrained(str(root / "t5")))
    _fill(t5, root / "text_encoders" / "t5xxl_fp16.safetensors", torch.bfloat16)
    t5 = t5.to(torch.bfloat16).eval()

    shift = 1.0 if "schnell" in gguf.name else 3.0
    pipe = FluxPipeline(
        scheduler=FlowMatchEulerDiscreteScheduler(shift=shift),
        vae=vae,
        text_encoder=clip,
        tokenizer=CLIPTokenizer.from_pretrained(str(root / "clip")),
        text_encoder_2=t5,
        tokenizer_2=T5TokenizerFast.from_pretrained(str(root / "t5")),
        transformer=transformer,
    )
    pipe.set_progress_bar_config(disable=True)

    device = torch.device("cuda")
    pipe.text_encoder.to(device)
    pipe.text_encoder_2.to(device)
    with torch.no_grad():
        embeds, pooled, _ = pipe.encode_prompt(
            prompt=args.prompt, prompt_2=None, device=device,
            num_images_per_prompt=1, max_sequence_length=512)
    pipe.text_encoder.to("cpu")
    pipe.text_encoder_2.to("cpu")
    pipe.transformer.to(device)
    pipe.vae.to(device)
    torch.cuda.empty_cache()

    generator = torch.Generator("cpu").manual_seed(args.seed)
    image = pipe(
        prompt_embeds=embeds.to(device),
        pooled_prompt_embeds=pooled.to(device),
        width=args.width,
        height=args.height,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance,
        generator=generator,
    ).images[0]
    image.save(args.out)


def _vram_gb() -> float:
    """本机最大显存（GB）；读不到返回 0，由调用方决定是否跳过校验。"""
    try:
        done = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        print("vram-probe-failed", type(exc).__name__, exc, file=sys.stderr, flush=True)
        return 0.0
    values = []
    for line in (done.stdout or "").strip().splitlines():
        try:
            values.append(float(line.strip()) / 1024.0)
        except ValueError as exc:
            print("vram-parse-failed", line.strip(), type(exc).__name__,
                  file=sys.stderr, flush=True)
    return max(values, default=0.0)


def _run_flux_official(root: Path, args) -> None:
    from diffusers import FluxPipeline

    pipe = FluxPipeline.from_pretrained(str(root / "flux1-dev"), torch_dtype=torch.bfloat16)
    pipe.enable_model_cpu_offload()
    pipe.set_progress_bar_config(disable=True)
    generator = torch.Generator("cpu").manual_seed(args.seed)
    image = pipe(
        prompt=args.prompt,
        width=args.width,
        height=args.height,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance,
        generator=generator,
    ).images[0]
    image.save(args.out)


def _run_sdxl(root: Path, args) -> None:
    from diffusers import StableDiffusionXLPipeline

    pipe = StableDiffusionXLPipeline.from_pretrained(
        str(root / "sdxl"), torch_dtype=torch.bfloat16, use_safetensors=True)
    pipe.to("cuda")
    pipe.set_progress_bar_config(disable=True)
    generator = torch.Generator("cpu").manual_seed(args.seed)
    image = pipe(
        prompt=args.prompt,
        negative_prompt=args.negative or None,
        width=args.width,
        height=args.height,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance,
        generator=generator,
    ).images[0]
    image.save(args.out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--steps", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--guidance", type=float, default=3.5)
    ap.add_argument("--negative", default="")
    args = ap.parse_args()

    root = Path(args.model_dir)
    started = time.time()
    result = {"ok": False, "model": args.model, "prompt": args.prompt,
              "width": args.width, "height": args.height, "steps": args.steps,
              "seed": args.seed}
    try:
        spec = models.find(args.model)
        vram = _vram_gb()
        if vram and vram < float(spec["vram_gb"]):
            raise RuntimeError(
                f"显存不足：{args.model} 建议 {spec['vram_gb']}G，本机 {vram}G")
        if args.model == "flux-dev-official":
            _run_flux_official(root, args)
        elif args.model.startswith("flux"):
            name = ("flux1-dev-Q4_K_S.gguf" if args.model == "flux-dev-q4"
                    else "flux1-schnell-Q4_K_S.gguf")
            gguf = root / "gguf" / name
            if not gguf.is_file():
                raise FileNotFoundError(f"缺少主模型：{gguf}")
            if "schnell" in args.model:
                args.steps = min(args.steps, 8)
                args.guidance = 0.0
            _run_flux(root, gguf, args)
        elif args.model == "sdxl-base":
            _run_sdxl(root, args)
        else:
            raise ValueError(f"不支持的模型：{args.model}")
        result.update({"ok": True, "image_path": str(Path(args.out).resolve()),
                       "elapsed_sec": round(time.time() - started, 1),
                       "steps": args.steps, "guidance": args.guidance})
        print("SAVED", args.out, flush=True)
    except Exception as exc:
        result.update({"error": f"{type(exc).__name__}: {exc}"})
        print("ERROR", result["error"], file=sys.stderr, flush=True)
    finally:
        meta = Path(str(args.out) + ".json")
        try:
            meta.parent.mkdir(parents=True, exist_ok=True)
            meta.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        except OSError as exc:
            print("META_WRITE_FAILED", type(exc).__name__, exc,
                  file=sys.stderr, flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
