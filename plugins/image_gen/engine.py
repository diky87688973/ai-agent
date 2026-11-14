"""出图插件的本地环境：配置、显卡探测、模型就位判断与命令装配。

配置只有一处来源：插件目录下的 `plugin-config.ini`。运行态只保留宿主注入 data_dir 里的
任务索引（task_id 到结果文件），不另存任何配置副本。
"""

from __future__ import annotations

import configparser
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.core.error_report import report_error

from . import models

CONFIG_NAME = "plugin-config.ini"
OUTPUT_DIRNAME = "output"
TASK_INDEX = "task-index.json"
CONFIG_KEYS = ("model_dir", "runtime_python", "default_model")
TASK_KEEP = 200

_DEFAULTS = {"model_dir": "", "runtime_python": "", "default_model": ""}


def plugin_dir() -> Path:
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return plugin_dir() / CONFIG_NAME


def read_config() -> Dict[str, str]:
    """配置唯一来源：plugin-config.ini。缺文件或缺键即视为未配置。"""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(config_path(), encoding="utf-8")
    values = dict(_DEFAULTS)
    if parser.has_section("config"):
        for key in CONFIG_KEYS:
            raw = (parser["config"].get(key) or "").strip()
            if raw:
                values[key] = raw
    return values


def write_config(**updates: str) -> Dict[str, str]:
    """安装引导把用户确认的目录写回同一份配置；只覆盖传进来的键。"""
    values = read_config()
    for key, raw in updates.items():
        if key in CONFIG_KEYS and str(raw or "").strip():
            values[key] = str(raw).strip()
    parser = configparser.ConfigParser(interpolation=None)
    parser["config"] = values
    path = config_path()
    try:
        with path.open("w", encoding="utf-8") as handle:
            parser.write(handle)
    except OSError as exc:
        report_error("plugin.image_gen.config_write", exc)
        raise
    return values


def detect_gpus() -> List[Dict[str, Any]]:
    try:
        done = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        report_error("plugin.image_gen.nvidia_smi", exc)
        return []
    rows: List[Dict[str, Any]] = []
    for line in (done.stdout or "").strip().splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            rows.append({"name": parts[0], "vram_gb": round(float(parts[1]) / 1024.0, 1)})
        except ValueError as exc:
            report_error("plugin.image_gen.gpu_parse", exc)
            continue
    return rows


def best_vram() -> float:
    return max((row["vram_gb"] for row in detect_gpus()), default=0.0)


def model_dir() -> Optional[Path]:
    raw = read_config()["model_dir"]
    return Path(raw) if raw else None


def model_root() -> Optional[Path]:
    """权重实际所在的根。安装目录下带 models 子目录时以它为根，否则目录即根。"""
    base = model_dir()
    if base is None:
        return None
    nested = base / "models"
    return nested if nested.is_dir() else base


def installed_models(directory: str = "") -> List[str]:
    root = Path(directory) if directory else model_root()
    if root is None:
        return []
    found: List[str] = []
    for item in models.CATALOG:
        markers = item.get("markers") or []
        if markers and all((root / rel).is_file() for rel in markers):
            found.append(item["id"])
    return found


def catalog_for_user() -> List[Dict[str, Any]]:
    """清单附上本机显存与够不够用的结论，供用户决策。"""
    vram = best_vram()
    rows: List[Dict[str, Any]] = []
    for item in models.CATALOG:
        rows.append({
            "id": item["id"],
            "name": item["name"],
            "download_gb": item["download_gb"],
            "vram_gb": item["vram_gb"],
            "mirror": models.MIRROR,
            "auth_required": item["auth_required"],
            "quality": item["quality"],
            "fits_this_machine": vram <= 0 or vram >= float(item["vram_gb"]),
            "note": item["note"],
        })
    return rows


def recommendation() -> str:
    vram = best_vram()
    if vram <= 0:
        return "未探测到 NVIDIA 显卡，本地出图不可用"
    for item in models.CATALOG:
        if not item["auth_required"] and vram >= float(item["vram_gb"]):
            return f"本机显存 {vram}G，推荐 {item['id']}（{item['name']}）"
    return f"本机显存 {vram}G，低于所有可匿名下载模型的建议值"


def output_dir() -> Path:
    root = model_dir()
    if root is None:
        raise ValueError("尚未配置 model_dir，无法确定输出目录")
    target = root / OUTPUT_DIRNAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def runtime_python() -> str:
    raw = read_config()["runtime_python"]
    if not raw or not Path(raw).is_file():
        raise ValueError(
            "runtime_python 未配置或不存在；请把 model_dir 与 runtime_python 写进插件配置")
    return raw


def task_index_path(data_dir: Path) -> Path:
    return Path(data_dir) / TASK_INDEX


def read_task_index(data_dir: Path) -> Dict[str, Any]:
    path = task_index_path(data_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report_error("plugin.image_gen.task_index_read", exc)
        return {}
    return data if isinstance(data, dict) else {}


def lookup_task(data_dir: Path, task_id: str) -> Optional[Dict[str, Any]]:
    entry = read_task_index(data_dir).get(task_id)
    return entry if isinstance(entry, dict) else None


def remember_task(data_dir: Path, task_id: str, batch: str, meta: str, kind: str) -> None:
    """task_id 到结果文件的映射；只保留最近 TASK_KEEP 条，旧条目自动淘汰。"""
    data = read_task_index(data_dir)
    data[task_id] = {"batch": batch, "meta": meta, "kind": kind, "created_at": time.time()}
    if len(data) > TASK_KEEP:
        ordered = sorted(data.items(),
                         key=lambda item: float(item[1].get("created_at") or 0))
        data = dict(ordered[-TASK_KEEP:])
    path = task_index_path(data_dir)
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        report_error("plugin.image_gen.task_index_write", exc)
        raise


def build_generate_argv(model_id: str, prompt: str, out_png: Path, *,
                        width: int, height: int, steps: int, seed: int,
                        negative: str) -> List[str]:
    argv = [
        runtime_python(), "-u", str(plugin_dir() / "runner.py"),
        "--model", model_id,
        "--model-dir", str(model_root() or ""),
        "--prompt", prompt,
        "--out", str(out_png),
        "--width", str(width),
        "--height", str(height),
        "--steps", str(steps),
        "--seed", str(seed),
    ]
    if negative:
        argv += ["--negative", negative]
    return argv


def build_download_argv(model_id: str, directory: str) -> List[str]:
    return [
        runtime_python(), "-u", str(plugin_dir() / "fetcher.py"),
        "--model", model_id,
        "--model-dir", directory,
    ]
