# -*- coding: utf-8 -*-
"""视觉操作 2.0 全局运行态。

视觉资源全局唯一：采集线程、帧队列、眼睛开关、owner 会话、授权都由本模块持有。
插件只把观察交给上下文钩子，不把状态复制到宿主。
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageStat

from agent.core.error_report import report_error

from . import backend, render
from .config import VisionConfig
from .consent import CONSENT_OPTIONS, CONSENT_TITLE

CaptureFn = Callable[[], Image.Image]
CursorFn = Callable[[], Tuple[int, int]]

@dataclass(slots=True)
class Frame:
    frame_id: str
    image: Image.Image
    cursor: Tuple[int, int]
    captured_at: float
    generation: int


@dataclass(slots=True)
class PendingConsent:
    request_id: str
    conversation_id: str
    call_id: str


class VisionRuntime:
    """全局视觉资源与会话 owner。"""
    def __init__(
        self,
        config: VisionConfig,
        *,
        publish: Optional[Callable[[str, Dict[str, Any]], int]] = None,
        capture: Optional[CaptureFn] = None,
        cursor: Optional[CursorFn] = None,
        wake: Optional[Callable[[str], None]] = None,
        input_monitor: Any = None,
        control_badge: Any = None,
    ) -> None:
        self.config = config
        self._publish = publish
        self._wake_model = wake
        self._input_monitor = input_monitor
        self._control_badge = control_badge
        self._capture = capture or backend.capture_screen
        self._cursor = cursor or backend.cursor_position
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._frames: deque[Frame] = deque(maxlen=config.queue_size)
        self._owner = ""
        self._eyes_open = False
        self._takeover = False
        self._generation = 0
        self._focus: Optional[Dict[str, int]] = None
        self._pending: Optional[PendingConsent] = None
        self._grants: Dict[str, Dict[str, Any]] = {}
        self._last_diff = 0.0
        self._last_wake = 0.0
        self._closed = False
    # ── 授权 ──────────────────────────────────────────────
    def request_open(self, conversation_id: str, call_id: str) -> Dict[str, Any]:
        cid = str(conversation_id or "").strip()
        if not cid:
            return {"ok": False, "error": "缺少 conversation_id"}
        with self._lock:
            if self._owner and self._owner != cid:
                return {"ok": False, "error": "眼睛正被其他会话使用"}
            if self._eyes_open and self._owner == cid:
                return {"ok": False, "error": "眼睛已经打开"}
            if self._pending is not None:
                if self._pending.conversation_id != cid:
                    return {"ok": False, "error": "其他会话有未完成的授权请求"}
                return {
                    "ok": True,
                    "request_id": self._pending.request_id,
                    "title": CONSENT_TITLE,
                    "options": list(CONSENT_OPTIONS),
                    "reused": True,
                }
            request = PendingConsent(
                request_id="consent_req_" + uuid.uuid4().hex,
                conversation_id=cid,
                call_id=str(call_id or ""),
            )
            self._pending = request
            return {
                "ok": True,
                "request_id": request.request_id,
                "title": CONSENT_TITLE,
                "options": list(CONSENT_OPTIONS),
                "reused": False,
            }
    def pending(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            req = self._pending
            if req is None or req.conversation_id != str(conversation_id or ""):
                return None
            return {
                "conversation_id": req.conversation_id,
                "request_id": req.request_id,
                "title": CONSENT_TITLE,
                "options": list(CONSENT_OPTIONS),
                "call_id": req.call_id,
            }
    def confirm(self, conversation_id: str, request_id: str, choice: str) -> Dict[str, Any]:
        cid = str(conversation_id or "").strip()
        rid = str(request_id or "").strip()
        decision = str(choice or "").strip().lower()
        if decision not in ("agree", "reject"):
            return {"ok": False, "error": "choice 只能是 agree 或 reject"}
        with self._lock:
            req = self._pending
            if req is None or req.request_id != rid or req.conversation_id != cid:
                return {"ok": False, "error": "没有匹配的授权请求"}
            if self._owner and self._owner != cid:
                return {"ok": False, "error": "眼睛正被其他会话使用"}
            self._pending = None
            if decision == "reject":
                return {"ok": True, "decision": "reject", "consent_id": "",
                        "call_id": req.call_id}
            self._owner = cid
            consent_id = "consent_" + uuid.uuid4().hex
            self._grants[consent_id] = {
                "conversation_id": cid,
                "purpose": "eye_open",
                "request_id": rid,
                "consumed": False,
            }
            return {
                "ok": True,
                "decision": "agree",
                "consent_id": consent_id,
                "call_id": req.call_id,
            }
    def start(self, conversation_id: str, consent_id: str) -> Dict[str, Any]:
        cid = str(conversation_id or "").strip()
        ident = str(consent_id or "").strip()
        with self._lock:
            if self._owner and self._owner != cid:
                return {"ok": False, "error": "眼睛正被其他会话使用"}
            grant = self._grants.get(ident)
            if not isinstance(grant, dict):
                return {"ok": False, "error": "授权凭证不存在"}
            if grant.get("consumed"):
                return {"ok": False, "error": "授权凭证已使用"}
            if str(grant.get("conversation_id") or "") != cid:
                return {"ok": False, "error": "授权凭证不属于当前会话"}
            grant["consumed"] = True
            self._owner = cid
            self._eyes_open = True
            self._takeover = False
            self._generation += 1
            self._frames.clear()
            try:
                before = self._cursor()
                image = self._capture()
                after = self._cursor()
                self._remember_frame(image, before if before == after else after,
                                     self._generation)
                if self._input_monitor is not None:
                    if not self._input_monitor.start():
                        raise RuntimeError("用户输入接管钩子安装失败")
                if self._control_badge is not None:
                    self._control_badge.show()
            except (OSError, ValueError, RuntimeError) as exc:
                self._eyes_open = False
                self._owner = ""
                self._generation += 1
                if self._control_badge is not None:
                    self._control_badge.hide()
                report_error("plugins.visual_operator_2.initial_capture", exc)
                return {"ok": False, "error": str(exc)}
            if not self._eyes_open:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            self._start_capture_locked()
            self._wake.set()
        self._emit("eye_opened", {"conversation_id": cid})
        return {
            "ok": True,
            "eyes_open": True,
            "owner_conversation_id": cid,
            "observation_note": "下一轮上下文尾部会注入完整图和聚焦图",
        }
    def _stop_monitor(self) -> None:
        monitor = self._input_monitor
        if monitor is None:
            return
        try:
            monitor.stop()
        except Exception as exc:
            report_error("plugins.visual_operator_2.input_monitor.stop", exc)
    def user_takeover(self) -> None:
        backend.release_left()
        with self._lock:
            if not self._eyes_open:
                return
            cid = self._owner
            self._takeover = True
            self._eyes_open = False
            self._owner = ""
            self._generation += 1
            self._frames.clear()
            self._grants.clear()
            self._pending = None
            self._focus = None
        if self._control_badge is not None:
            self._control_badge.hide()
        self._emit("eye_closed", {
            "conversation_id": cid,
            "reason": "user_takeover",
        })
        self._emit("control_returned", {
            "conversation_id": cid,
        })
    def stop(self, conversation_id: str) -> Dict[str, Any]:
        cid = str(conversation_id or "").strip()
        with self._lock:
            if self._takeover:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            if self._owner and self._owner != cid:
                return {"ok": False, "error": "眼睛属于其他会话"}
            if not self._eyes_open and not self._owner:
                return {"ok": True, "eyes_open": False}
            self._eyes_open = False
            self._owner = ""
            self._takeover = False
            self._generation += 1
            self._frames.clear()
            self._grants.clear()
            self._pending = None
            self._focus = None
        self._stop_monitor()
        if self._control_badge is not None:
            self._control_badge.hide()
        self._emit("eye_closed", {"conversation_id": cid})
        return {"ok": True, "eyes_open": False}
    def revoke(self, conversation_id: str) -> Dict[str, Any]:
        return self.stop(conversation_id)
    def status(self, conversation_id: str) -> Dict[str, Any]:
        with self._lock:
            owner = self._owner
            return {
                "ok": True,
                "conversation_id": str(conversation_id or ""),
                "owner_conversation_id": owner,
                "eyes_open": bool(self._eyes_open and owner == str(conversation_id or "")),
                "consent_valid": bool(self._grants),
                "user_takeover": bool(self._takeover),
            }
    # ── 观察与动作 ────────────────────────────────────────
    def observe(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._eyes_open or self._owner != str(conversation_id or ""):
                return None
            if not self._frames:
                return None
            frame = self._frames[-1]
            full = frame.image.copy()
            render.draw_marker(full, frame.cursor)
            age_ms = int((time.monotonic() - frame.captured_at) * 1000)
            full_image = render.data_url(full, self.config)
            full_scale = float(frame.image.width) / float(full.width)
            text = (
                "<vision_observation>"
                f"frame_id={frame.frame_id};age_ms={age_ms};"
                f"cursor=({frame.cursor[0]},{frame.cursor[1]});"
                f"screen_size=({frame.image.width},{frame.image.height});"
                f"original_image_size=({frame.image.width},{frame.image.height});"
                f"compressed_image_size=({full.width},{full.height});"
                f"coordinate_space=model_image;"
                f"owner={self._owner}"
                "</vision_observation>"
            )
            return {
                "text": text,
                "images": ["FULL FRAME", full_image],
                "full_image": full_image,
                "focus_image": "",
                "frame": frame,
                "frame_id": frame.frame_id,
                "age_ms": age_ms,
                "cursor": {"x": frame.cursor[0], "y": frame.cursor[1]},
                "cursor_in_focus": False,
                "screen_size": [frame.image.width, frame.image.height],
                "full_size": [full.width, full.height],
                "full_scale": full_scale,
                "coordinate_space": "model_image",
                "compressed_image_size": [full.width, full.height],
                "original_image_size": [frame.image.width, frame.image.height],
                "focus": {},
            }
    def publish_observation(self, observation: Dict[str, Any]) -> None:
        """把即将交给模型的那一帧同步推给前端；不写入会话历史。"""
        if self._publish is None:
            return
        frame = observation.get("frame")
        if not isinstance(frame, Frame):
            return
        self._publish("vision_frame", {
            "conversation_id": self._owner,
            "frame_id": observation["frame_id"],
            "source": "model_input",
            "age_ms": observation["age_ms"],
            "cursor": observation["cursor"],
            "cursor_in_focus": observation["cursor_in_focus"],
            "screen_size": observation["screen_size"],
            "full_size": observation["full_size"],
            "full_scale": observation["full_scale"],
            "coordinate_space": observation["coordinate_space"],
            "focus": observation["focus"],
            "full_image": observation["full_image"],
            "focus_image": observation["focus_image"],
        })
    def focus(self, conversation_id: str,
              region: Optional[Dict[str, Any]], center_cursor: bool) -> Dict[str, Any]:
        with self._lock:
            if self._takeover:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            if not self._eyes_open or self._owner != str(conversation_id or ""):
                return {"ok": False, "error": "眼睛未打开或不属于当前会话"}
            if region is None:
                self._focus = None
            else:
                try:
                    rect = {
                        "x": int(region["x"]),
                        "y": int(region["y"]),
                        "width": int(region["width"]),
                        "height": int(region["height"]),
                    }
                except (KeyError, TypeError, ValueError):
                    return {"ok": False, "error": "region 必须是 x/y/width/height"}
                if not self._frames:
                    return {"ok": False, "error": "当前没有观察帧"}
                clipped = render.clip_focus(rect, self._frames[-1].image.size)
                if clipped is None:
                    return {"ok": False, "error": "聚焦区域超出屏幕或小于 64×64"}
                self._focus = clipped
            before = self._cursor()
            centered = False
            if center_cursor and self._focus is not None:
                rect = self._focus
                backend.set_cursor(rect["x"] + rect["width"] // 2,
                                   rect["y"] + rect["height"] // 2)
                centered = True
            after = self._cursor()
            self._wake.set()
            result = {
                "ok": True,
                "focus": self._focus,
                "cursor_before": {"x": before[0], "y": before[1]},
                "cursor_after": {"x": after[0], "y": after[1]},
                "centered": centered,
            }
        result["observation_frame_id"] = self._capture_after_action(conversation_id) or ""
        return result
    def move(self, conversation_id: str, dx: int, dy: int) -> Dict[str, Any]:
        with self._lock:
            if self._takeover:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            if not self._eyes_open or self._owner != str(conversation_id or ""):
                return {"ok": False, "error": "眼睛未打开或不属于当前会话"}
            if not self._frames:
                return {"ok": False, "error": "当前没有观察帧"}
            origin = self._frames[-1].cursor
            target_x = origin[0] + int(dx)
            target_y = origin[1] + int(dy)
            before = self._cursor()
            if (target_x, target_y) == before:
                return {"ok": True, "moved": False, "no_op": True}
            moved = backend.move_cursor(
                target_x, target_y,
                self.config.move_duration_ms,
                should_stop=lambda: self._takeover or not self._eyes_open)
            if not moved:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            after = self._cursor()
            self._wake.set()
            result = {
                "ok": True,
                "cursor_before": {"x": before[0], "y": before[1]},
                "cursor_after": {"x": after[0], "y": after[1]},
            }
        result["observation_frame_id"] = self._capture_after_action(
            conversation_id, self.config.move_settle_ms) or ""
        result["observation_note"] = "移动后立即抓取的完整图和聚焦图"
        return result
    def move_point(self, conversation_id: str, x: int, y: int,
                   width: int, height: int, image_width: int,
                   image_height: int) -> Dict[str, Any]:
        with self._lock:
            if self._takeover:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            if not self._eyes_open or self._owner != str(conversation_id or ""):
                return {"ok": False, "error": "眼睛未打开或不属于当前会话"}
            if not self._frames:
                return {"ok": False, "error": "当前没有观察帧"}
            if width <= 0 or height <= 0:
                return {"ok": False, "error": "width/height 必须大于 0"}
            if image_width <= 0 or image_height <= 0:
                return {"ok": False, "error": "image_width/image_height 必须大于 0"}
            frame = self._frames[-1]
            mapped = render.full_point_screen(
                frame.image.width, frame.image.height,
                x, y, width, height, image_width, image_height)
            screen_x = mapped["screen"]["x"]
            screen_y = mapped["screen"]["y"]
            before = self._cursor()
            if (screen_x, screen_y) == before:
                return {"ok": True, "moved": False, "no_op": True}
            moved = backend.move_cursor(
                screen_x, screen_y,
                self.config.move_duration_ms,
                should_stop=lambda: self._takeover or not self._eyes_open)
            if not moved:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            after = self._cursor()
            self._wake.set()
            result = {
                "ok": True,
                "coordinate_space": "model_image",
                "model_point": {"x": int(x), "y": int(y)},
                "model_image_size": [int(width), int(height)],
                "original_image_size": [int(image_width), int(image_height)],
                "screen_size": mapped["screen_size"],
                "scale": mapped["scale"],
                "target_screen": mapped["screen"],
                "cursor_before": {"x": before[0], "y": before[1]},
                "cursor_after": {"x": after[0], "y": after[1]},
            }
        result["observation_frame_id"] = self._capture_after_action(
            conversation_id, self.config.move_settle_ms) or ""
        result["observation_note"] = "移动后立即抓取的完整图和聚焦图"
        return result
    def move_focus(self, conversation_id: str, x: int, y: int,
                   width: int, height: int, image_width: int,
                   image_height: int) -> Dict[str, Any]:
        with self._lock:
            if self._takeover:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            if not self._eyes_open or self._owner != str(conversation_id or ""):
                return {"ok": False, "error": "眼睛未打开或不属于当前会话"}
            if not self._frames:
                return {"ok": False, "error": "当前没有观察帧"}
            if width <= 0 or height <= 0:
                return {"ok": False, "error": "width/height 必须大于 0"}
            if image_width <= 0 or image_height <= 0:
                return {"ok": False, "error": "image_width/image_height 必须大于 0"}
            frame = self._frames[-1]
            focus = render.resolve_focus(frame, self._focus,
                                     self.config.focus_width,
                                     self.config.focus_height)
            screen_x = round(focus["x"] + int(x) * focus["width"] / float(width))
            screen_y = round(focus["y"] + int(y) * focus["height"] / float(height))
            if not (0 <= screen_x < frame.image.width and 0 <= screen_y < frame.image.height):
                return {"ok": False, "error": "聚焦图目标落在屏幕外"}
            before = self._cursor()
            if (screen_x, screen_y) == before:
                return {"ok": True, "moved": False, "no_op": True}
            moved = backend.move_cursor(
                screen_x, screen_y, self.config.move_duration_ms,
                should_stop=lambda: self._takeover or not self._eyes_open)
            if not moved:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            after = self._cursor()
            self._wake.set()
            result = {
                "ok": True,
                "coordinate_space": "focus_image",
                "model_point": {"x": int(x), "y": int(y)},
                "model_image_size": [int(width), int(height)],
                "original_image_size": [int(image_width), int(image_height)],
                "focus": focus,
                "target_screen": {"x": screen_x, "y": screen_y},
                "cursor_before": {"x": before[0], "y": before[1]},
                "cursor_after": {"x": after[0], "y": after[1]},
            }
        result["observation_frame_id"] = self._capture_after_action(
            conversation_id, self.config.move_settle_ms) or ""
        result["observation_note"] = "移动后立即抓取的完整图和聚焦图"
        return result
    def click(self, conversation_id: str, button: str = "left",
              count: int = 1, interval_ms: int = 72) -> Dict[str, Any]:
        interval = int(interval_ms)
        if interval < 72:
            return {"ok": False, "error": "interval_ms 不能小于 72"}
        clicks_count = max(1, min(10, int(count)))
        clicks: List[Dict[str, Any]] = []
        with self._lock:
            if self._takeover:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            if not self._eyes_open or self._owner != str(conversation_id or ""):
                return {"ok": False, "error": "眼睛未打开或不属于当前会话"}
            before = self._cursor()
        try:
            for index in range(clicks_count):
                with self._lock:
                    if self._takeover:
                        return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权",
                                "clicks": clicks}
                    if not self._eyes_open or self._owner != str(conversation_id or ""):
                        return {"ok": False, "error": "眼睛未打开或不属于当前会话",
                                "clicks": clicks}
                backend.click(button, 1)
                clicks.append({"index": index + 1})
                if index + 1 < clicks_count:
                    time.sleep(interval / 1000.0)
        except (OSError, ValueError, RuntimeError) as exc:
            return {"ok": False, "error": str(exc), "clicks": clicks}
        after = self._cursor()
        post_frame = self._capture_after_action(conversation_id)
        self._wake.set()
        return {
            "ok": True,
            "cursor_before": {"x": before[0], "y": before[1]},
            "cursor_after": {"x": after[0], "y": after[1]},
            "clicks": len(clicks),
            "interval_ms": interval,
            "observation_frame_id": post_frame or "",
            "observation_note": "下一次模型请求尾部带动作后的完整图和聚焦图",
            "settle_ms": self.config.settle_ms,
        }
    def click_sequence(self, conversation_id: str, points: List[Dict[str, int]],
                       width: int, height: int, image_width: int,
                       image_height: int, interval_ms: int = 72,
                       count: int = 1) -> Dict[str, Any]:
        with self._lock:
            if self._takeover:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            if not self._eyes_open or self._owner != str(conversation_id or ""):
                return {"ok": False, "error": "眼睛未打开或不属于当前会话"}
            if not self._frames:
                return {"ok": False, "error": "当前没有观察帧"}
            if not points:
                return {"ok": False, "error": "points 不能为空"}
            if width <= 0 or height <= 0 or image_width <= 0 or image_height <= 0:
                return {"ok": False, "error": "width/height/image_width/image_height 必须大于 0"}
            frame = self._frames[-1]
            targets = []
            for point in points:
                mapped = render.full_point_screen(
                    frame.image.width, frame.image.height,
                    int(point["x"]), int(point["y"]),
                    width, height, image_width, image_height)
                targets.append({
                    "model_point": {"x": int(point["x"]), "y": int(point["y"])},
                    "target_screen": mapped["screen"],
                })
        interval = int(interval_ms)
        if interval < 72:
            return {"ok": False, "error": "interval_ms 不能小于 72", "clicks": []}
        interval = min(1000, interval)
        per_point = max(1, min(3, int(count)))
        clicks: List[Dict[str, Any]] = []
        previous_screen = None
        try:
            for index, target in enumerate(targets):
                screen = target["target_screen"]
                if screen != previous_screen:
                    with self._lock:
                        if self._takeover:
                            return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权",
                                    "clicks": clicks}
                    moved = backend.move_cursor(
                        screen["x"], screen["y"], self.config.move_duration_ms,
                        should_stop=lambda: self._takeover or not self._eyes_open)
                    if not moved:
                        return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权",
                                "clicks": clicks}
                for click_index in range(per_point):
                    with self._lock:
                        if self._takeover:
                            return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权",
                                    "clicks": clicks}
                        if not self._eyes_open or self._owner != str(conversation_id or ""):
                            return {"ok": False, "error": "眼睛未打开或不属于当前会话",
                                    "clicks": clicks}
                    backend.click("left", 1)
                    if click_index + 1 < per_point:
                        time.sleep(interval / 1000.0)
                clicks.append({**target, "moved": screen != previous_screen})
                previous_screen = screen
                if index < len(targets) - 1:
                    time.sleep(interval / 1000.0)
        except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
            return {"ok": False, "error": str(exc), "clicks": clicks}
        post_frame = self._capture_after_action(conversation_id)
        self._wake.set()
        return {
            "ok": True,
            "coordinate_space": "model_image",
            "model_image_size": [int(width), int(height)],
            "original_image_size": [int(image_width), int(image_height)],
            "clicks": clicks,
            "interval_ms": interval,
            "count": per_point,
            "observation_frame_id": post_frame or "",
            "observation_note": "下一次模型请求尾部带动作后的完整图和聚焦图",
        }
    def key(self, conversation_id: str, keys: List[str]) -> Dict[str, Any]:
        with self._lock:
            if self._takeover:
                return {"ok": False, "error": "用户已接管电脑，请重新申请视觉授权"}
            if not self._eyes_open or self._owner != str(conversation_id or ""):
                return {"ok": False, "error": "眼睛未打开或不属于当前会话"}
            try:
                backend.press_keys(keys)
            except (OSError, ValueError, RuntimeError) as exc:
                return {"ok": False, "error": str(exc)}
        self._wake.set()
        return {"ok": True, "keys": list(keys)}
    # ── 采集 ──────────────────────────────────────────────
    def _start_capture_locked(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._capture_loop, name="visual-operator-2-capture", daemon=True)
        self._thread.start()
    def _capture_loop(self) -> None:
        interval = 1.0 / max(0.2, float(self.config.fps))
        while not self._stop.is_set():
            self._wake.wait(interval)
            self._wake.clear()
            if self._stop.is_set():
                return
            try:
                with self._lock:
                    if not self._eyes_open:
                        continue
                    generation = self._generation
                before = self._cursor()
                image = self._capture()
                after = self._cursor()
                with self._lock:
                    if not self._eyes_open or generation != self._generation:
                        continue
                    self._remember_frame(image, before if before == after else after,
                                         generation)
            except Exception as exc:
                report_error("plugins.visual_operator_2.capture", exc)
                continue
    def _capture_after_action(self, conversation_id: str,
                              delay_ms: Optional[int] = None) -> Optional[str]:
        delay = self.config.settle_ms if delay_ms is None else delay_ms
        settle = max(0, int(delay)) / 1000.0
        if settle > 0:
            time.sleep(settle)
        with self._lock:
            if (self._takeover or not self._eyes_open
                    or self._owner != str(conversation_id or "")):
                return None
            generation = self._generation
        try:
            before = self._cursor()
            image = self._capture()
            after = self._cursor()
        except (OSError, ValueError, RuntimeError) as exc:
            report_error("plugins.visual_operator_2.action_capture", exc)
            return None
        with self._lock:
            if (self._takeover or not self._eyes_open
                    or self._owner != str(conversation_id or "")
                    or generation != self._generation):
                return None
            self._remember_frame(image, before if before == after else after,
                                 generation)
            return self._frames[-1].frame_id if self._frames else None
    def _remember_frame(self, image: Image.Image, cursor: Tuple[int, int],
                        generation: int) -> None:
        frame = Frame(
            frame_id="f-" + uuid.uuid4().hex[:12],
            image=image,
            cursor=(int(cursor[0]), int(cursor[1])),
            captured_at=time.monotonic(),
            generation=generation,
        )
        previous = self._frames[-1] if self._frames else None
        self._frames.append(frame)
        if previous is not None:
            try:
                diff = ImageChops.difference(previous.image, image).convert("L")
                self._last_diff = float(ImageStat.Stat(diff).mean[0]) / 255.0
            except (ValueError, OSError):
                self._last_diff = 0.0
            if self._last_diff > 0.02:
                self._emit("vision_change", {
                    "conversation_id": self._owner,
                    "frame_id": frame.frame_id,
                    "diff_ratio": round(self._last_diff, 4),
                })
                now = time.monotonic()
                if self._wake_model is not None and now - self._last_wake >= 1.0:
                    self._last_wake = now
                    threading.Thread(
                        target=self._wake_owner,
                        args=(self._owner,),
                        daemon=True,
                    ).start()
    def _wake_owner(self, conversation_id: str) -> None:
        callback = self._wake_model
        if callback is None:
            return
        try:
            callback(str(conversation_id or ""))
        except Exception as exc:
            report_error("plugins.visual_operator_2.wake", exc)
    def _emit(self, event: str, payload: Dict[str, Any]) -> None:
        if self._publish is None:
            return
        try:
            self._publish(event, payload)
        except Exception as exc:
            report_error("plugins.visual_operator_2.publish", exc)
            return
    def close(self) -> None:
        backend.release_left()
        self._closed = True
        self._stop.set()
        self._wake.set()
        with self._lock:
            self._eyes_open = False
            self._owner = ""
            self._takeover = False
            self._frames.clear()
            self._grants.clear()
            self._pending = None
        self._stop_monitor()
        if self._control_badge is not None:
            self._control_badge.close()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)


def _contains(rect: Dict[str, int], point: Tuple[int, int]) -> bool:
    x, y = point
    return (rect["x"] <= x < rect["x"] + rect["width"]
            and rect["y"] <= y < rect["y"] + rect["height"])



__all__ = ["Frame", "VisionRuntime"]
