# -*- coding: utf-8 -*-
"""截图取图与加工的唯一入口。

`desktop_eye` 与手部动作的 `shot` 走同一份实现：区域裁剪、按窗口取图、
缩放、网格、回执与提示文案只有一处。两份实现迟早会分叉，
而"图上的坐标能不能直接填回 desktop_mouse"正是最不能分叉的地方。
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from agent.core.session_scope import current_session_id

from .. import canvas
from ..capture_store import CaptureStore
from ..config import DesktopConfig
from ..coords import ScreenPoint, ScreenRect
from ..errors import DesktopError
from ..ports import Backend, WindowInfo
from ._params import as_bool, as_int, has, require_range
from ._windows import MAX_CANDIDATES, alternatives, window_candidates

#: 单张截图的像素上限。整屏超过它时给区域参数；这不是内存保护，
#: 而是让错误停在调用侧，不把几百 MB 的位图搬进内存再报错。
MAX_CAPTURE_PIXELS = 40_000_000

REGION_FIELDS = ("x", "y", "width", "height")


@dataclass(frozen=True)
class CaptureRequest:
    """一次取图的完整意图：看哪、多大、怎么画。"""

    window: Optional[str] = None
    hwnd: Optional[int] = None
    region: Optional[ScreenRect] = None
    grid: bool = True
    max_side: int = 0
    activate: bool = False
    #: `annotated` 只回标注图；`raw` 只回原图；`both` 先标注图后原图。
    annotate: str = "annotated"
    #: 取图前把光标移到这里，用来展开悬停控件；None 表示不动光标。
    hover: Optional[ScreenPoint] = None
    hover_settle_ms: int = 0
    #: 中间路径点：先经过它们再到 hover，产生连续的移动轨迹。
    hover_path: Tuple[ScreenPoint, ...] = ()
    #: 每一段移动的时长；0 表示每个点一次跳变。
    hover_approach_ms: int = 0
    #: 到达后是否在落点附近做几次 1–2px 微移动。
    hover_wiggle: bool = False
    #: 网格间距（屏幕坐标）；None 取插件配置。小目标用更细的网格定位。
    grid_step: Optional[int] = None
    #: 网格刻度单位：screen 屏幕坐标 / image 图内像素坐标。
    grid_unit: str = "screen"
    #: 回执里额外并入的字段（`shot` 用它标出"这是哪个动作之后的图"）。
    extra: Dict[str, Any] = field(default_factory=dict)


def request_from_arguments(backend: Backend, config: DesktopConfig,
                           arguments: Dict[str, Any], *,
                           activate_default: bool = False) -> CaptureRequest:
    """从 `desktop_eye` 的参数构造请求；区域由 x/y/width/height 给出。"""
    bounds = backend.screen.geometry().rect
    window = _text(arguments, "window")
    hwnd = _hwnd(arguments)
    if window is not None and hwnd is not None:
        raise ValueError("window 与 hwnd 二选一，不要同时给")
    return CaptureRequest(
        window=window,
        hwnd=hwnd,
        region=region_from_arguments(arguments, bounds),
        grid=as_bool(arguments, "grid", True),
        max_side=require_range(
            as_int(arguments, "max_side", config.max_side), "max_side", 0, 8192),
        activate=as_bool(arguments, "activate", activate_default),
        annotate=_annotate(arguments),
        grid_unit=_grid_unit(arguments),
    )


def _annotate(arguments: Dict[str, Any]) -> str:
    """标注图模式：annotated / raw / both；未知值直接拒绝。"""
    value = str(arguments.get("annotate") or "annotated").strip().lower()
    if value not in ("annotated", "raw", "both"):
        raise ValueError(
            f"annotate 只能是 annotated / raw / both，实际 {arguments.get('annotate')!r}"
        )
    return value


def _grid_unit(arguments: Dict[str, Any]) -> str:
    """网格刻度单位；未知值直接拒绝，不做猜测。"""
    value = str(arguments.get("grid_unit") or "screen").strip().lower()
    if value not in ("screen", "image"):
        raise ValueError(f"grid_unit 只能是 screen 或 image，实际 {arguments.get('grid_unit')!r}")
    return value


def region_from_arguments(arguments: Dict[str, Any],
                          bounds: ScreenRect) -> Optional[ScreenRect]:
    """读 x / y / width / height；四个一起给，缺一个就报错。"""
    given = [key for key in REGION_FIELDS if has(arguments, key)]
    if not given:
        return None
    if len(given) < 4:
        raise ValueError(
            "区域要 x / y / width / height 四个参数一起给；整屏时四个都省略"
        )
    requested = ScreenRect(
        as_int(arguments, "x") or 0,
        as_int(arguments, "y") or 0,
        as_int(arguments, "width") or 0,
        as_int(arguments, "height") or 0,
    )
    clamped = requested.intersect(bounds)
    if clamped is None:
        raise ValueError(f"区域与屏幕没有交集；屏幕是 {bounds.to_dict()}")
    return clamped


def capture_payload(backend: Backend, config: DesktopConfig,
                    request: CaptureRequest, *,
                    captures: Optional[CaptureStore] = None,
                    session_id: Optional[str] = None,
                    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """取图、加工并组装回执；返回 (data, 图片附件列表)。"""
    geometry = backend.screen.geometry()
    if request.hover is not None and not geometry.rect.contains(request.hover):
        raise ValueError(
            f"hover 坐标 {request.hover.to_dict()} 不在屏幕 {geometry.rect.to_dict()} 内"
        )
    selector = {"window": request.window} if request.window else {"hwnd": request.hwnd}
    candidates, matched = window_candidates(backend, selector)
    target: Optional[WindowInfo] = candidates[0] if candidates else None
    region = request.region

    # 光标下面那层是谁：先粗探一次，用来决定"没给窗口时该拍哪个窗口"。
    # 回执里的 hover.hit 会在悬停与置前都完成后再探一次，避免把动作前的
    # 遮挡关系当成结果。
    initial_probe: Optional[Dict[str, Any]] = None
    if request.hover is not None and backend.hit is not None:
        initial_probe = backend.hit.probe(request.hover)

    if request.activate and not (request.window or request.hwnd):
        raise ValueError("activate 只对 window / hwnd 有意义；整屏取图不涉及窗口")

    auto_target = False
    if target is None and region is None and request.hover is not None \
            and backend.windows is not None:
        landed = (initial_probe or {}).get("root") or (initial_probe or {}).get("hwnd")
        if landed:
            # 只想看悬停控件时按光标那层取窗口内容：原尺寸、无遮挡、无整屏缩放。
            try:
                target = backend.windows.get(int(landed))
                auto_target = True
            except Exception:
                target = None

    if target is None:
        _hover(request, backend)
        planned = region or geometry.rect
        _check_area(planned.width * planned.height)
        screenshot = backend.screen.capture(region)
    else:
        # 悬停要在窗口恢复/置前之后、取图之前发生：两个条件缺一个，
        # 拍到的都是"还没展开"或"别的窗口上展开"的画面。
        prepare = ((lambda: _hover(request, backend))
                   if request.hover is not None else None)
        capture_options = {"activate": request.activate}
        if prepare is not None:
            capture_options["prepare"] = prepare
        screenshot = backend.windows.capture(target.hwnd, region, **capture_options)
        if screenshot.restored:
            # 恢复前的矩形是 (-32000,...)，拿它当回执会误导调用侧；重新读一次。
            target = backend.windows.get(target.hwnd)

    _check_area(screenshot.rect.width * screenshot.rect.height)
    cursor = backend.mouse.cursor()
    step = request.grid_step or config.grid_step
    annotated = request.annotate in ("annotated", "both")
    rendered = canvas.render(
        screenshot.png,
        rect=screenshot.rect,
        grid=request.grid if annotated else False,
        step=step,
        cursor=cursor if annotated else None,
        cursor_mark=config.cursor_mark if annotated else False,
        max_side=request.max_side,
        grid_unit=request.grid_unit,
    )
    raw_rendered = None
    if request.annotate == "both":
        raw_rendered = canvas.render(
            screenshot.png,
            rect=screenshot.rect,
            grid=False,
            step=step,
            cursor=None,
            cursor_mark=False,
            max_side=request.max_side,
            grid_unit=request.grid_unit,
        )

    def image_info(item: canvas.Rendered) -> Dict[str, Any]:
        return {
            "width": item.width,
            "height": item.height,
            "sent_width": item.sent_width,
            "sent_height": item.sent_height,
            "scale": item.scale,
            "bytes": len(item.png),
        }

    summary: Dict[str, Any] = {
        "platform": backend.platform,
        "screen": geometry.rect.to_dict(),
        "capture": screenshot.rect.to_dict(),
        "source": screenshot.source,
        "annotate": request.annotate,
        "image": image_info(rendered),
        "image_to_screen": {
            "scale_x": round(screenshot.rect.width / rendered.sent_width, 6),
            "scale_y": round(screenshot.rect.height / rendered.sent_height, 6),
            "ox": screenshot.rect.x,
            "oy": screenshot.rect.y,
        },
        "dpi": geometry.dpi or "unknown",
    }
    if raw_rendered is not None:
        summary["raw_image"] = image_info(raw_rendered)
        summary["attachment_order"] = ["annotated", "raw"]
    elif request.annotate == "raw":
        summary["attachment_order"] = ["raw"]
    else:
        summary["attachment_order"] = ["annotated"]
    if captures is not None:
        ref = captures.put(
            session_id if session_id is not None else current_session_id(),
            screenshot.rect,
            rendered.sent_width,
            rendered.sent_height,
            hwnd=target.hwnd if target is not None else None,
            title=target.title if target is not None else "",
        )
        summary["capture_id"] = ref.capture_id
    if target is not None:
        summary["window"] = target.to_dict()
        if auto_target:
            summary["window"]["auto"] = "hover.hit"
        if matched > 1:
            summary["window"]["matched"] = matched
            summary["window"]["alternatives"] = alternatives(candidates)
        if screenshot.restored:
            summary["restored"] = True
        if request.activate:
            summary["activated"] = screenshot.activation == "ok"
    if cursor is not None:
        summary["cursor"] = cursor.to_dict()
    hover_hit: Optional[Dict[str, Any]] = None
    if request.hover is not None:
        # 悬停与置前都已完成：这里探到的是"拍这张图时"光标下的真实窗口。
        # 它必须和"拍了哪个窗口"一起回执：两者常常不是同一个
        # （播放器画面是独立顶层窗口，截图拍的却是它上面的详情页壳）。
        hover_hit = backend.hit.probe(request.hover) if backend.hit is not None else None
        hover_data: Dict[str, Any] = {
            "x": request.hover.x,
            "y": request.hover.y,
            "settle_ms": request.hover_settle_ms,
            "approach_ms": request.hover_approach_ms,
            "wiggle": request.hover_wiggle,
        }
        if request.hover_path:
            hover_data["path"] = [point.to_dict() for point in request.hover_path]
        if hover_hit:
            hover_data["hit"] = hover_hit
        summary["hover"] = hover_data
    if request.grid and annotated:
        summary["grid"] = {
            "step": step,
            "unit": request.grid_unit,
            "scale": rendered.scale,
        }
    note = build_note(
        rendered, geometry.mixed_scale, step,
        source=screenshot.source, windowed=target is not None,
        restored=screenshot.restored, activation=screenshot.activation,
        matched=matched, candidates=candidates, target=target,
        hovered=request.hover is not None, foreground=screenshot.foreground,
        hover_hit=hover_hit, auto_target=auto_target,
    )
    if note:
        summary["note"] = note
    summary.update(request.extra)

    attachments = [{
        "mime": "image/png",
        "data_base64": base64.b64encode(rendered.png).decode("ascii"),
    }]
    if raw_rendered is not None:
        attachments.append({
            "mime": "image/png",
            "data_base64": base64.b64encode(raw_rendered.png).decode("ascii"),
        })
    return summary, attachments


def build_note(rendered: Any, mixed_scale: bool, step: int, *,
               source: str = "screen", windowed: bool = False,
               restored: bool = False, activation: str = "none",
               matched: int = 0, candidates: Sequence[WindowInfo] = (),
               target: Optional[WindowInfo] = None,
               hovered: bool = False, foreground: bool = False,
               hover_hit: Optional[Dict[str, Any]] = None,
               auto_target: bool = False) -> str:
    """拼回执里的人话提示：只写模型据此能改动作的事实。"""
    parts = []
    if restored and activation == "ok":
        parts.append("窗口原为最小化，已恢复并置前（与点任务栏等效）才取到内容")
    elif restored and activation == "failed":
        parts.append("窗口原为最小化，已恢复但没抢到前台；内容取自窗口自身重绘，"
                     "接下来要输入时请重新激活该窗口")
    elif restored:
        parts.append("窗口原为最小化，已恢复（未置前，当前前台窗口保持不变）才取到内容")
    elif activation == "failed":
        parts.append("请求置前但没抢到前台；内容仍取自窗口自身重绘")
    if windowed and source == "screen":
        parts.append("窗口内容取不到（可能仍在最小化或尚未重绘），已回退为屏幕截图，可能包含遮挡物")
    if matched > 1 and target is not None:
        parts.append(_ambiguity_note(matched, candidates, target))
    if hovered and windowed and not foreground:
        parts.append("窗口不在前台，hover 可能落在遮挡它的窗口上；"
                     "要让悬停生效请给 activate=true")
    if hovered:
        mismatch = _hover_mismatch(hover_hit, target, windowed=windowed)
        if mismatch:
            parts.append(mismatch)
    if auto_target and target is not None:
        parts.append(
            f"未指定窗口，已按 hover 落点取 hwnd={target.hwnd} 自身内容"
            "（原尺寸、无遮挡）；要看整屏再显式给区域或 window")
    if rendered.shrunk:
        parts.append(
            f"图片已从 {rendered.width}x{rendered.height} 缩到 "
            f"{rendered.sent_width}x{rendered.sent_height}；"
            f"网格刻度（每 {step} 屏幕坐标）仍是原坐标，可直接用于 desktop_mouse"
        )
        parts.append(_scale_hint(rendered))
    if rendered.blank:
        parts.append("画面全黑：可能处于锁屏、UAC 安全桌面或受保护内容")
    if mixed_scale:
        parts.append("多屏缩放不一致，副屏坐标可能有偏差")
    return "；".join(parts)


def _ambiguity_note(matched: int, candidates: Sequence[WindowInfo],
                    target: WindowInfo) -> str:
    """同名窗口不止一个时，把"选了谁、还有谁"说全。

    只给一个 `matched: 2` 等于让模型自己猜：它猜不到另一个窗口是
    播放层还是隐藏辅助窗，于是要么反复重试，要么改用整屏（比例尺也变了）。
    """
    picked = "前台那个" if target.foreground else "最靠前的那个"
    others = "、".join(
        f"hwnd={info.hwnd}（{info.rect.width}x{info.rect.height}）"
        for info in tuple(candidates)[1:1 + MAX_CANDIDATES]
    )
    tail = f"；其余：{others}，要换目标就显式给 hwnd" if others else ""
    return f"标题包含同一片段的可见窗口有 {matched} 个，已选{picked} hwnd={target.hwnd}{tail}"


def _scale_hint(rendered: Any) -> str:
    """给一次换算示例：模型少做一次心算，就少一次点偏。"""
    scale = rendered.scale
    if scale <= 1.0:
        return ""
    sample_x, sample_y = 100, 100
    return (f"换算：图上像素 × {scale:g} = 屏幕坐标，"
            f"例如图上 {sample_x},{sample_y} 对应屏幕 "
            f"{round(sample_x * scale)},{round(sample_y * scale)}")


def _hover(request: CaptureRequest, backend: Backend) -> None:
    """把光标移到指定位置并等界面展开。

    这是"移鼠标 + 截图"能成立的前提：悬停控件普遍 2–3 秒自动收起，
    而两次工具调用之间隔着一次模型往返（实测 2–8 秒），分两步必然错过。

    移动不是一次瞬移：先走完 `hover_path` 的中间点，再用 `hover_approach_ms`
    连续移到落点，最后（可选）在 1–2px 内来回几次。播放器与网页的自动隐藏
    控件靠连续的 `WM_MOUSEMOVE` 判断"鼠标在动"，一次跳变后静止会被当成没动。
    微动结束必须收回落点；目标窗口抢光标时直接报错，不把偏移后的坐标当落点。
    """
    if request.hover is None:
        return
    for waypoint in request.hover_path:
        backend.mouse.move(waypoint, request.hover_approach_ms)
    backend.mouse.move(request.hover, request.hover_approach_ms)
    if request.hover_wiggle:
        _wiggle(request.hover, backend)
        _return_to(request.hover, backend)
    if request.hover_settle_ms > 0:
        time.sleep(request.hover_settle_ms / 1000.0)


def _return_to(point: ScreenPoint, backend: Backend) -> None:
    """微动后把真实光标收回落点；窗口若抢光标则明确失败。"""
    actual = backend.mouse.cursor()
    for _attempt in range(3):
        if actual == point:
            return
        backend.mouse.move(point, 0)
        time.sleep(0.01)
        actual = backend.mouse.cursor()
    raise DesktopError(
        f"hover 微动后光标未能回到落点 {point.to_dict()}，实际 {actual.to_dict()}"
    )


def _wiggle(point: ScreenPoint, backend: Backend) -> None:
    """在落点附近做几次亚像素级的位移，再回到落点。

    位移必须是真实的光标移动（`SetCursorPos` 会投递 `WM_MOUSEMOVE`），
    不能只是改回执里的数字；否则播放器依然认为鼠标没动。
    """
    for dx, dy in ((1, 0), (-1, 1), (1, -1), (-1, 0)):
        backend.mouse.move(ScreenPoint(point.x + dx, point.y + dy), 0)
    backend.mouse.move(point, 0)


def _hover_mismatch(hover_hit: Optional[Dict[str, Any]],
                    target: Optional[WindowInfo], *, windowed: bool) -> str:
    """光标所在层与取图窗口不是同一个时，把这件事说清楚。

    这是"控制条唤不出来"最常见的真相：播放器画面是独立顶层窗口，
    而按标题取图选中的是承载详情页的另一个窗口。控制条即使出现，
    也不会出现在这张图里；换 y 坐标重试多少次都一样。
    """
    if not hover_hit:
        return ""
    root = hover_hit.get("root") or hover_hit.get("hwnd")
    if not root:
        return ""
    if not windowed or target is None:
        return ""
    if int(root) == int(target.hwnd):
        return ""
    title = hover_hit.get("title") or ""
    label = f"「{title}」" if title else ""
    return (
        f"光标落在 hwnd={root}{label}，与这次取图的窗口 hwnd={target.hwnd}"
        f"「{target.title}」不是同一个；悬停展开的控件属于光标那层，"
        f"要拍它请改用 hwnd={root}"
    )


def _check_area(pixels: int) -> None:
    if pixels > MAX_CAPTURE_PIXELS:
        raise ValueError(
            f"截图区域 {pixels} 像素超过上限 {MAX_CAPTURE_PIXELS}；"
            "给一个更小的区域，或先缩放屏幕"
        )


def _text(arguments: Dict[str, Any], key: str) -> Optional[str]:
    value = arguments.get(key)
    if value is None or value == "":
        return None
    return str(value)


def _hwnd(arguments: Dict[str, Any]) -> Optional[int]:
    if not has(arguments, "hwnd"):
        return None
    return as_int(arguments, "hwnd", 0)
