# -*- coding: utf-8 -*-
"""随机校准点：模型图坐标到屏幕坐标的 32px 复核。"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from . import render

HINT = ("请在当前帧重新读C1在图中的像素点；"
        "强调：xy 与 center_x/center_y 必须直接来自读图像素，严禁自己换算")


def new_points(width: int, height: int,
               cursor: Optional[Tuple[int, int]] = None) -> List[Tuple[int, int]]:
    rng = random.SystemRandom()
    margin_x = max(60, int(width * 0.08))
    margin_y = max(60, int(height * 0.08))
    for _ in range(200):
        point = (rng.randint(margin_x, max(margin_x, width - margin_x)),
                 rng.randint(margin_y, max(margin_y, height - margin_y)))
        if cursor is not None:
            if abs(point[0] - cursor[0]) < 60 and abs(point[1] - cursor[1]) < 60:
                continue
        return [point]
    return [(width // 2, height // 2)]


def challenge_error(points: Optional[List[Dict[str, int]]],
                    expected: List[Tuple[int, int]], center_x: int,
                    center_y: int, image_width: int, image_height: int,
                    tolerance: int = 32) -> str:
    if points is None:
        return ""
    if not isinstance(points, list) or len(points) != 1:
        return "校准失败：check_points 必须是 C1 一个图内坐标；" + HINT
    worst = 0
    for point, (ex, ey) in zip(points, expected):
        if not isinstance(point, dict) or "x" not in point or "y" not in point:
            return "校准失败：check_points 每个点必须是 {x, y}；" + HINT
        mapped = render.full_point_screen(
            image_width, image_height, int(point["x"]), int(point["y"]),
            center_x, center_y, image_width, image_height)
        worst = max(worst, abs(mapped["screen"]["x"] - ex),
                    abs(mapped["screen"]["y"] - ey))
    if worst > tolerance:
        return f"校准失败，误差 {worst}px，超过 {tolerance}px；" + HINT
    return ""


def model_error(points: Optional[List[Dict[str, int]]],
                expected: List[Tuple[int, int]], tolerance: int = 32) -> str:
    if points is None:
        return ""
    if not isinstance(points, list) or len(points) != 1:
        return "校准失败：check_points 必须是 C1 一个图内坐标；" + HINT
    worst = 0
    for point, (ex, ey) in zip(points, expected):
        if not isinstance(point, dict) or "x" not in point or "y" not in point:
            return "校准失败：check_points 每个点必须是 {x, y}；" + HINT
        worst = max(worst, abs(int(point["x"]) - ex), abs(int(point["y"]) - ey))
    if worst > tolerance:
        return f"校准失败，误差 {worst}px，超过 {tolerance}px；" + HINT
    return ""


class ChallengeStore:
    """每帧随机校准点缓存；动作通过后立即消费。"""

    def __init__(self, tolerance: int = 32, enabled: bool = True) -> None:
        self._items: Dict[str, Dict[str, object]] = {}
        self.tolerance = max(0, int(tolerance))
        self.enabled = bool(enabled)

    def clear(self) -> None:
        self._items.clear()

    def __contains__(self, frame_id: str) -> bool:
        return frame_id in self._items

    def __getitem__(self, frame_id: str) -> Dict[str, object]:
        return self._items[frame_id]

    def get(self, frame, full) -> Dict[str, object] | None:
        if not self.enabled:
            return None
        challenge = self._items.get(frame.frame_id)
        if challenge is not None:
            return challenge
        points = new_points(frame.image.width, frame.image.height, frame.cursor)
        model = [
            (round(x * full.width / frame.image.width),
             round(y * full.height / frame.image.height))
            for x, y in points
        ]
        challenge = {"screen": points, "model": model}
        self._items[frame.frame_id] = challenge
        while len(self._items) > 8:
            self._items.pop(next(iter(self._items)))
        return challenge

    def consume(self, frame_id: str) -> None:
        self._items.pop(frame_id, None)

    def error(self, points, frame_id: str, center_x: int, center_y: int,
              image_width: int, image_height: int,
              model_only: bool = False) -> str:
        if not self.enabled or points is None:
            return ""
        challenge = self._items.get(frame_id)
        if challenge is None:
            return "校准失败：当前帧没有随机校准点；" + HINT
        if model_only:
            return model_error(
                points, challenge["model"], self.tolerance)
        return challenge_error(
            points, challenge["screen"], center_x, center_y,
            image_width, image_height, self.tolerance)

    def report(self, points, frame_id: str, center_x: int, center_y: int,
               image_width: int, image_height: int,
               model_only: bool = False) -> dict:
        if not self.enabled or not isinstance(points, list) or len(points) != 1:
            return {}
        challenge = self._items.get(frame_id)
        if challenge is None:
            return {}
        rows = []
        for index, point in enumerate(points):
            if not isinstance(point, dict) or "x" not in point or "y" not in point:
                continue
            expected = challenge["screen"][index]
            row = {"label": f"C{index + 1}", "real": {
                "x": int(expected[0]), "y": int(expected[1])},
                "model": {"x": int(point["x"]), "y": int(point["y"])}}
            if not model_only:
                mapped = render.full_point_screen(
                    image_width, image_height, int(point["x"]), int(point["y"]),
                    center_x, center_y, image_width, image_height)
                row["screen"] = mapped["screen"]
                row["delta"] = {
                    "x": mapped["screen"]["x"] - int(expected[0]),
                    "y": mapped["screen"]["y"] - int(expected[1]),
                }
            else:
                expected_model = challenge["model"][index]
                row["delta"] = {
                    "x": int(point["x"]) - int(expected_model[0]),
                    "y": int(point["y"]) - int(expected_model[1]),
                }
            rows.append(row)
        worst = max((abs(item.get("delta", {}).get("x", 0)) for item in rows),
                    default=0)
        worst = max(worst, max((abs(item.get("delta", {}).get("y", 0))
                                for item in rows), default=0))
        return {"accepted": worst <= self.tolerance, "worst": worst,
                "points": rows}


def public_points(points) -> list:
    return [{"label": f"C{index}", "x": int(x), "y": int(y)}
            for index, (x, y) in enumerate(points, 1)]
