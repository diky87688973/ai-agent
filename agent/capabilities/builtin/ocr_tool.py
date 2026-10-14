# -*- coding: utf-8 -*-
"""OCR 工具：image_ocr——pytesseract / easyocr（可选依赖，缺依赖结构化降级）。

引擎选择 auto / pytesseract / easyocr；region="x,y,w,h" 局部识别；
缺依赖抛 MissingDependency（安装提示随 data 透传）。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.capabilities.registry import ToolPlugin


class MissingDependency(RuntimeError):
    """可选 OCR 依赖缺失：安装提示随 data 透传。"""

    def __init__(
        self,
        message: str,
        install_command: str,
        estimated_time: str = "",
        security_notes: Optional[List[str]] = None,
    ) -> None:
        super().__init__(message)
        self.data = {
            "type": "MissingDependency",
            "message": message,
            "dependencies": {
                "install_command": install_command,
                "estimated_time": estimated_time,
                "security_notes": security_notes or [],
            },
        }


class OcrError(RuntimeError):
    """OCR 识别失败。"""


def _available(module: str) -> bool:
    """探测可选依赖是否可导入（find_spec 不触发重量级 import）。"""
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


class ImageOcrTool(ToolPlugin):
    """图片 OCR。"""

    name = "image_ocr"
    label = "识别图片文字"
    icon = "🖼"
    description = "对图片做 OCR（pytesseract / easyocr，可选依赖）；支持区域裁剪；缺依赖时给出安装提示。"
    parameters = {
        "path": {"type": "string", "description": "图片文件路径"},
        "lang": {"type": "string", "description": "语言包（默认 chi_sim+eng）"},
        "region": {"type": "string", "description": "裁剪区域 x,y,w,h 逗号分隔整数（可选）"},
        "engine": {"type": "string", "description": "auto / pytesseract / easyocr（默认 auto）"},
    }

    @staticmethod
    def _detect_engine(prefer: Optional[str]) -> str:
        has_tess = _available("pytesseract")
        if prefer == "pytesseract" and has_tess:
            return "pytesseract"
        if prefer == "easyocr" and _available("easyocr"):
            return "easyocr"
        if has_tess:
            return "pytesseract"
        if _available("easyocr"):
            return "easyocr"
        return "none"

    @staticmethod
    def _ocr_pytesseract(image_path: Path, lang: str, region: Optional[Tuple[int, int, int, int]]) -> Dict[str, Any]:
        import pytesseract as pt
        from PIL import Image

        img = Image.open(image_path)
        if region:
            x, y, w, h = region
            img = img.crop((x, y, x + w, y + h))
        try:
            data = pt.image_to_data(img, lang=lang, output_type=pt.Output.DICT)
        except Exception as e:
            raise OcrError(f"Tesseract 识别失败: {e}")

        words_with_pos: List[Dict[str, Any]] = []
        for i in range(len(data["text"])):
            txt = (data["text"][i] or "").strip()
            if not txt:
                continue
            words_with_pos.append(
                {
                    "text": txt,
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "w": data["width"][i],
                    "h": data["height"][i],
                    "confidence": data["conf"][i],
                }
            )
        line_map: Dict[int, List[Dict[str, Any]]] = {}
        for w in words_with_pos:
            line_map.setdefault(w["y"] // 5, []).append(w)
        text_lines: List[Dict[str, Any]] = []
        for row in sorted(line_map):
            line_map[row].sort(key=lambda x: x["x"])
            txt = " ".join(w["text"] for w in line_map[row])
            if txt.strip():
                text_lines.append({"text": txt.strip(), "words": line_map[row]})
        full_text = "\n".join(t["text"] for t in text_lines)
        return {
            "engine": "pytesseract",
            "full_text": full_text,
            "lines": text_lines,
            "words": words_with_pos,
        }

    @staticmethod
    def _ocr_easyocr(image_path: Path, lang: str, region: Optional[Tuple[int, int, int, int]]) -> Dict[str, Any]:
        import easyocr as _eo

        _lang_map = {"chi_sim": "ch_sim", "chi_tra": "ch_tra", "eng": "en", "en": "en"}
        lang_list: List[str] = []
        for p in lang.replace("+", ",").split(","):
            p = p.strip()
            if p:
                lang_list.append(_lang_map.get(p, p))
        if not lang_list:
            lang_list = ["ch_sim", "en"]
        try:
            reader = _eo.Reader(lang_list, gpu=False)
        except Exception as e:
            raise OcrError(f"easyocr reader 初始化失败: {e}")
        try:
            results = reader.readtext(str(image_path))
        except Exception as e:
            raise OcrError(f"easyocr 识别失败: {e}")

        if region:
            rx, ry, rw, rh = region
            filtered = []
            for bbox, txt, conf in results:
                cx = (bbox[0][0] + bbox[2][0]) / 2
                cy = (bbox[0][1] + bbox[2][1]) / 2
                if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
                    filtered.append((bbox, txt, conf))
            results = filtered

        words: List[Dict[str, Any]] = []
        for bbox, txt, conf in results:
            x0 = int(min(p[0] for p in bbox))
            y0 = int(min(p[1] for p in bbox))
            x1 = int(max(p[0] for p in bbox))
            y1 = int(max(p[1] for p in bbox))
            words.append(
                {
                    "text": txt,
                    "x": x0,
                    "y": y0,
                    "w": x1 - x0,
                    "h": y1 - y0,
                    "confidence": round(conf, 3),
                }
            )
        full_text = "\n".join(w["text"] for w in words)
        return {"engine": "easyocr", "full_text": full_text, "words": words}

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise ValueError("缺少 path（图片文件路径）")
        src = Path(raw_path)
        if not src.is_file():
            raise FileNotFoundError(f"图片不存在: {src}")

        region_tuple: Optional[Tuple[int, int, int, int]] = None
        region_raw = arguments.get("region")
        if region_raw is not None and str(region_raw).strip() != "":
            try:
                parts = [int(x.strip()) for x in str(region_raw).split(",")]
            except (TypeError, ValueError):
                raise ValueError("region 须为 x,y,w,h 四个整数")
            if len(parts) != 4:
                raise ValueError("region 须为 x,y,w,h 四个整数")
            region_tuple = (parts[0], parts[1], parts[2], parts[3])

        lang = str(arguments.get("lang") or "chi_sim+eng")
        engine = str(arguments.get("engine") or "auto").strip().lower()
        preferred = None if engine == "auto" else engine
        active = self._detect_engine(preferred)
        if active == "none":
            raise MissingDependency(
                "未检测到 OCR 引擎，请安装 pytesseract（含 Tesseract 可执行文件）或 easyocr",
                install_command="pip install pytesseract Pillow  # 或 pip install easyocr",
                estimated_time="easyocr 首次安装约 2–5 分钟（含模型）",
                security_notes=["easyocr 依赖链可能在编译时触发杀软误报，需按需加白名单"],
            )
        if active == "pytesseract":
            if not _available("PIL"):
                raise MissingDependency(
                    "pytesseract 需要 Pillow：pip install Pillow",
                    install_command="pip install Pillow",
                )
            return self._ocr_pytesseract(src, lang, region_tuple)
        if active == "easyocr":
            return self._ocr_easyocr(src, lang, region_tuple)
        raise OcrError(f"未知引擎: {active}")


def build_plugins() -> List[ToolPlugin]:
    """构造本组工具（image_ocr）。"""
    return [ImageOcrTool()]
