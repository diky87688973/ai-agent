"""本地出图工具：模型闸门、用户确认、后台任务与结果回传。

工具只暴露"模型 + 提示词 + 可选参数"，具体加载与采样由 runner 子进程承担；
长耗时的下载与出图一律挂宿主既有的后台任务服务，工具立即返回。
配置唯一来源是插件目录的 `plugin-config.ini`；没有配置就走安装引导。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.capabilities.registry import ToolPlugin
from agent.core.context import SERVICE_BACKGROUND_TASKS
from agent.core.error_report import report_error
from agent.core.session_scope import current_context

from . import engine, models

_ANON = [item["id"] for item in models.CATALOG if not item["auth_required"]]


class ImageGenTool(ToolPlugin):
    name = "image_gen"
    label = "本地出图"
    icon = "🎨"
    parallel_safe = False
    description = (
        "用本地扩散模型出图。出图、下载都是长耗时操作，本工具只负责起后台任务并立即返回，"
        "绝不等待完成；完成后由后台任务通知，再用 action=status 取本地图片路径。\n"
        "任务完成会自动通知，不要用 task_sleep / task_schedule 给自己设唤醒，也不要轮询等待。\n"
        "action 选填，默认 generate。\n"
        "generate：出图。先查本地是否已装模型；没有就返回 needs_setup 并附模型清单（名字、"
        "下载体积、建议显存、镜像源、是否需授权）与本机显卡情况，此时必须与用户确认后才能下载。\n"
        "check：只探测显卡与本地模型，不出图。\n"
        "download：下载模型。必须同时传 confirmed=true 与 model；confirmed 不为 true 时直接拒绝。"
        "model_dir 未配置时先与用户确认目录再传，该目录会写入 plugin-config.ini。"
        "模型仓库需授权的会返回 needs_auth，不准静默换模型，"
        "要与用户确认是否改用可匿名下载的社区量化版。\n"
        "status：凭 task_id 取结果，返回 image_path 即本地图片绝对路径；调用方默认行为是"
        "把该图片内联展示，并在正文里给出这个路径。\n"
        "用户取消或未作答一律视为不下载；未确认时不得调用 download。"
    )
    parameters: Dict[str, Any] = {
        "action": {
            "type": "string",
            "enum": ["generate", "check", "download", "status"],
            "description": "动作，默认 generate",
        },
        "prompt": {"type": "string", "description": "出图提示词，generate 必填"},
        "model": {
            "type": "string",
            "description": "模型 id；省略时用配置里的 default_model，两者都为空则报错",
        },
        "width": {"type": "integer", "minimum": 256, "maximum": 2048, "description": "宽，默认 1024"},
        "height": {"type": "integer", "minimum": 256, "maximum": 2048, "description": "高，默认 768"},
        "steps": {"type": "integer", "minimum": 1, "maximum": 60, "description": "采样步数，默认 20"},
        "seed": {"type": "integer", "minimum": 0, "description": "随机种子，默认 0"},
        "negative": {"type": "string", "description": "反向提示词，仅 SDXL 生效"},
        "task_id": {"type": "string", "description": "status 必填：后台任务 id"},
        "confirmed": {
            "type": "boolean",
            "description": "download 必填：用户已明确同意下载时才传 true",
        },
        "model_dir": {
            "type": "string",
            "description": "download 可选：用户确认的安装目录；已配置过则省略",
        },
    }

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self._data_dir = Path(data_dir) if data_dir else None

    def _runtime_root(self) -> Path:
        """任务索引要用运行态目录；构造期不强制，真正读写时才要求。"""
        if self._data_dir is None:
            raise ValueError("image_gen 未拿到宿主注入的 data_dir，无法记录任务索引")
        return self._data_dir

    def execute(self, arguments: Dict[str, Any]) -> Any:
        action = str(arguments.get("action") or "generate").strip().lower()
        if action == "check":
            return self._check()
        if action == "download":
            return self._download(arguments)
        if action == "status":
            return self._status(arguments)
        if action != "generate":
            raise ValueError(f"未知 action：{action}")
        return self._generate(arguments)

    def _check(self) -> Dict[str, Any]:
        cfg = engine.read_config()
        return {
            "status": "checked",
            "gpu": engine.detect_gpus(),
            "model_dir": cfg["model_dir"],
            "runtime_python": cfg["runtime_python"],
            "default_model": cfg["default_model"],
            "installed": engine.installed_models(),
            "catalog": engine.catalog_for_user(),
            "recommendation": engine.recommendation(),
        }

    def _needs_setup(self, reason: str) -> Dict[str, Any]:
        return {
            "status": "needs_setup",
            "reason": reason,
            "gpu": engine.detect_gpus(),
            "model_dir": engine.read_config()["model_dir"],
            "catalog": engine.catalog_for_user(),
            "recommendation": engine.recommendation(),
            "next": (
                "未配置 model_dir 时进入安装引导：先与用户确认模型与安装目录，"
                "再调用 download 并带 confirmed=true；不要猜测本地路径"
            ),
        }

    def _generate(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        prompt = str(arguments.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("prompt 必填")
        cfg = engine.read_config()
        installed = engine.installed_models()
        if not cfg["model_dir"]:
            return self._needs_setup("尚未配置 model_dir")
        if not installed:
            return self._needs_setup(f"目录 {cfg['model_dir']} 内没有可用扩散模型")
        model_id = str(arguments.get("model") or cfg["default_model"] or "").strip()
        if not model_id:
            raise ValueError(
                "generate 需要 model：参数未传且未配置 default_model；取值见 check 返回的 catalog")
        if model_id not in installed:
            return self._needs_setup(f"模型 {model_id} 未就位；已就位：{', '.join(installed)}")

        width = int(arguments.get("width") or 1024)
        height = int(arguments.get("height") or 768)
        steps = int(arguments.get("steps") or 20)
        seed = int(arguments.get("seed") or 0)
        negative = str(arguments.get("negative") or "")

        out_dir = engine.output_dir()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out_png = out_dir / f"{model_id}_{stamp}_seed{seed}.png"
        argv = engine.build_generate_argv(
            model_id, prompt, out_png, width=width, height=height,
            steps=steps, seed=seed, negative=negative)
        batch, task_id = self._launch(argv, f"出图 {model_id}")
        engine.remember_task(
            self._runtime_root(), task_id, batch, str(out_png) + ".json", "generate")
        return {
            "status": "queued",
            "task_id": task_id,
            "batch": batch,
            "model": model_id,
            "image_path": str(out_png),
            "note": "任务完成会自动通知；收到通知后用 action=status 取最终路径，不要设唤醒或轮询",
        }

    def _download(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if arguments.get("confirmed") is not True:
            return {
                "status": "need_confirm",
                "message": "下载必须先取得用户明确同意，再把 confirmed 传 true",
                "catalog": engine.catalog_for_user(),
                "recommendation": engine.recommendation(),
            }
        model_id = str(arguments.get("model") or "").strip()
        if not model_id:
            raise ValueError("model 必填")
        spec = models.find(model_id)
        if spec["auth_required"]:
            return {
                "status": "needs_auth",
                "model": model_id,
                "message": "该仓库需 HuggingFace 授权，插件无法匿名下载",
                "alternatives": _ANON,
                "next": "与用户确认是否改用可匿名下载的社区量化版",
            }
        directory = str(arguments.get("model_dir") or "").strip()
        if not directory:
            root = engine.model_root()
            directory = str(root) if root is not None else ""
        if not directory:
            return {
                "status": "need_model_dir",
                "message": "请与用户确认安装目录，再把它作为 model_dir 传入",
                "download_gb": spec["download_gb"],
            }
        engine.write_config(model_dir=directory, default_model=model_id)
        argv = engine.build_download_argv(model_id, directory)
        batch, task_id = self._launch(argv, f"下载 {spec['name']}")
        engine.remember_task(self._runtime_root(), task_id, batch, "", "download")
        return {
            "status": "queued",
            "task_id": task_id,
            "batch": batch,
            "model": model_id,
            "model_dir": directory,
            "download_gb": spec["download_gb"],
            "mirror": models.MIRROR,
            "note": "下载完成后用 action=generate 出图；完成会自动通知，不要设唤醒或轮询",
        }

    def _status(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        task_id = str(arguments.get("task_id") or "").strip()
        if not task_id:
            raise ValueError("task_id 必填")
        entry = engine.lookup_task(self._runtime_root(), task_id)
        if entry is None:
            return {"status": "unknown_task", "task_id": task_id}
        meta = Path(entry.get("meta") or "")
        if str(meta) and meta.is_file():
            try:
                payload = json.loads(meta.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                report_error("plugin.image_gen.meta_read", exc)
                payload = None
            if isinstance(payload, dict):
                if payload.get("ok"):
                    return {"status": "done", "task_id": task_id,
                            "image_path": payload.get("image_path"),
                            "elapsed_sec": payload.get("elapsed_sec"),
                            "model": payload.get("model")}
                return {"status": "failed", "task_id": task_id,
                        "error": payload.get("error")}
        state = self._task_state(entry.get("batch") or "", task_id)
        if state == "unavailable":
            return {"status": "unknown_state", "task_id": task_id,
                    "error": "后台任务服务查询失败，已上报；请稍后重试或查任务列表"}
        return {"status": "pending" if state in ("running", "queued", "") else state,
                "task_id": task_id, "batch": entry.get("batch"),
                "note": "尚无结果文件，等完成通知"}

    def _launch(self, argv: List[str], label: str) -> Any:
        turn = current_context()
        manager = turn.service(SERVICE_BACKGROUND_TASKS) if turn is not None else None
        if turn is None or manager is None:
            raise ValueError("出图必须通过会话工具管道调用：后台任务服务不可用")
        created = manager.create(
            turn.conversation_id, argv, str(engine.plugin_dir()), 3600, label)
        if not created.get("ok"):
            raise ValueError(f"后台任务创建失败：{created.get('error')}")
        task = created.get("task") or {}
        return str(task.get("batch") or ""), str(task.get("task_id") or "")

    def _task_state(self, batch: str, task_id: str) -> str:
        turn = current_context()
        manager = turn.service(SERVICE_BACKGROUND_TASKS) if turn is not None else None
        if manager is None or not batch:
            return ""
        try:
            rows = manager.list_tasks(turn.conversation_id, batch, task_id).get("tasks") or []
        except (KeyError, AttributeError, RuntimeError, ValueError) as exc:
            report_error("plugin.image_gen.task_state", exc)
            return "unavailable"
        for row in rows:
            if row.get("task_id") == task_id:
                return str(row.get("status") or "")
        return ""


def make_tool(ctx) -> ImageGenTool:
    return ImageGenTool(ctx.data_dir)
