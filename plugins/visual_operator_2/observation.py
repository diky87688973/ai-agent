# -*- coding: utf-8 -*-
"""视觉观察载荷：把最近帧渲染成模型可读的完整图、标签与校准点。"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from . import render
from .config import VisionConfig


def render_full(frame: Any, max_side: int, config: VisionConfig,
                challenges: Any) -> Tuple[str, Tuple[int, int], Any]:
    """取得一帧完整图的 data URL、尺寸与校准点；按帧缓存。"""
    cache_key = ("full", int(max_side))
    cached = frame.rendered.get(cache_key)
    if isinstance(cached, tuple) and len(cached) == 2:
        return cached[0], cached[1], frame.calibration
    view = render.fit(frame.image, max_side)
    if view is frame.image:
        view = frame.image.copy()
    challenge = challenges.get(frame, view)
    frame.calibration = challenge
    if challenge is not None:
        render.draw_calibration(view, challenge["screen"],
                                frame.image.width, frame.image.height)
    render.draw_marker(view, (
        round(frame.cursor[0] * view.width / frame.image.width),
        round(frame.cursor[1] * view.height / frame.image.height),
    ))
    url = render.data_url(view, config)
    size = (view.width, view.height)
    frame.rendered[cache_key] = (url, size)
    return url, size, challenge


def render_focus(frame: Any, focus: Dict[str, int],
                 config: VisionConfig) -> Optional[Dict[str, Any]]:
    """取得聚焦视图；同一帧、同一聚焦矩形复用缓存。"""
    cache_key = ("focus", tuple(sorted(focus.items())))
    cached = frame.rendered.get(cache_key)
    if isinstance(cached, dict):
        return cached
    view = render.focus_view(frame.image, focus, frame.cursor, config)
    frame.rendered[cache_key] = view
    return view


def _history_views(history: List[Any], config: VisionConfig,
                   challenges: Any) -> Tuple[List[Dict[str, Any]],
                                             List[Dict[str, Any]],
                                             Tuple[int, int], Any]:
    images: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []
    latest = history[-1]
    full_wh = (latest.image.width, latest.image.height)
    challenge = None
    for index, item in enumerate(history):
        is_latest = index == len(history) - 1
        url, item_wh, item_challenge = render_full(
            item, config.image_max_side, config, challenges)
        offset_ms = int((item.captured_at - latest.captured_at) * 1000)
        images.append({
            "label": f"FRAME t={offset_ms}ms" + (" LATEST" if is_latest else ""),
            "url": url,
            "detail": "high" if is_latest else "low",
        })
        rows.append({
            "frame_id": item.frame_id,
            "offset_ms": offset_ms,
            "age_ms": int((time.monotonic() - item.captured_at) * 1000),
        })
        if is_latest:
            full_wh = item_wh
            challenge = item_challenge
    return images, rows, full_wh, challenge


def build_observation(history: List[Any], focus: Optional[Dict[str, int]],
                      config: VisionConfig, challenges: Any, owner: str,
                      last_calibration: Dict[str, Any]) -> Dict[str, Any]:
    frame = history[-1]
    age_ms = int((time.monotonic() - frame.captured_at) * 1000)
    images, frame_rows, full_wh, challenge = _history_views(
        history, config, challenges)
    full_image = images[-1]["url"]
    cursor_x = round(frame.cursor[0] * full_wh[0] / frame.image.width)
    cursor_y = round(frame.cursor[1] * full_wh[1] / frame.image.height)
    offsets = ",".join(str(row["offset_ms"]) for row in frame_rows)
    text = (
        "【系统消息-视觉帧】\n\n"
        "<vision_observation>"
        f"frames={len(frame_rows)};offsets_ms=[{offsets}];"
        "latest_is_last_frame;"
        f"frame_id={frame.frame_id};age_ms={age_ms};"
        f"cursor_model=({cursor_x},{cursor_y});"
        f"image_center=({full_wh[0] // 2},{full_wh[1] // 2});"
        f"original_image_size=({frame.image.width},{frame.image.height});"
        f"compressed_image_size=({full_wh[0]},{full_wh[1]});"
        "coordinate_space=model_image;"
        + ("calibration=C1;check_points=read C1 center from the LATEST frame;"
           if challenge is not None else "")
        + f"owner={owner}"
    )
    focus_data: Dict[str, Any] = {}
    focus_image = ""
    cursor_in_focus = False
    if focus is not None:
        view = render_focus(frame, focus, config)
        if view is not None:
            focus_image = view["url"]
            focus_data = view["focus"]
            cursor_in_focus = view["cursor_in_focus"]
            images.append({"label": view["label"], "url": focus_image,
                           "detail": "high"})
            text += (f";focus_size=({focus_data['image_size'][0]},"
                     f"{focus_data['image_size'][1]})")
    text += "</vision_observation>"
    return {
        "text": text,
        "images": images,
        "frames": frame_rows,
        "full_image": full_image,
        "focus_image": focus_image,
        "frame": frame,
        "frame_id": frame.frame_id,
        "age_ms": age_ms,
        "cursor": {"x": frame.cursor[0], "y": frame.cursor[1]},
        "cursor_in_focus": cursor_in_focus,
        "screen_size": [frame.image.width, frame.image.height],
        "full_size": [full_wh[0], full_wh[1]],
        "full_scale": float(frame.image.width) / float(full_wh[0]),
        "coordinate_space": "model_image",
        "compressed_image_size": [full_wh[0], full_wh[1]],
        "original_image_size": [frame.image.width, frame.image.height],
        "focus": focus_data,
        "calibration": (calibration_points(challenge)
                        if challenge is not None else []),
        "last_calibration": last_calibration,
    }


def calibration_points(challenge: Dict[str, Any]) -> List[Dict[str, int]]:
    from . import calibration
    return calibration.public_points(challenge["screen"])
