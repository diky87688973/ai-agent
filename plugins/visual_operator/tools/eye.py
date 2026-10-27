# -*- coding: utf-8 -*-
"""`desktop_eye`：截屏、叠网格、把图片作为附件交给模型。"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict, Optional

from agent.capabilities.registry import ToolPlugin
from agent.core.tool_call import ToolResult

from ..capture_store import CaptureStore
from ..config import DesktopConfig
from ..coords import ScreenPoint
from ..guard import reject_in_plan
from ..ports import Backend
from ._capture import capture_payload, request_from_arguments
from ._params import as_bool, as_int, reject_unknown, require_range

_FIELDS = ("x", "y", "width", "height", "grid", "grid_step", "grid_unit", "max_side",
           "window", "hwnd", "activate", "annotate", "hover", "hover_path",
           "hover_settle_ms", "hover_approach_ms", "hover_wiggle")


class DesktopEyeTool(ToolPlugin):
    """截取桌面并附上图片。"""

    name = "desktop_eye"
    label = "看屏"
    icon = "👁"
    description = (
        "已知多步流程优先用 desktop_act，减少 eye/mouse 往返；本工具只取当前需要的一帧。"
        "看屏并附坐标网格。精确点击协议：先取局部区域（x/y/width/height），"
        "max_side=0，grid_step=20，量外框必须用 annotated 标注图；"
        "禁止用 raw 图量边框。再用 capture_id + space=image 把矩形交给 click_region。"
        "整屏/缩放图只用于定位大概位置，不要直接用来点击小目标。"
        "截取桌面并作为图片直接查看（不是 OCR）。支持整屏、区域与指定窗口。"
        "给 window（标题片段）或 hwnd 时取该窗口自身内容，目标被别的窗口盖住也能看到；"
        "窗口若已最小化会先恢复再取图，回执标 restored。"
        "activate=false（默认）只恢复不置前，不改变用户正在用的窗口；"
        "需要把窗口亮到前台时给 activate=true。"
        "要给悬停才出现的控件拍照（视频控制条、下拉菜单、提示气泡），"
        "用 hover=[x,y]：同一次调用内先移光标、等界面展开、再截图。"
        "默认会连续移动并在落点做几次 1–2px 微移动（hover_wiggle），"
        "因为播放器只认连续的 mousemove，瞬移后静止会被当成鼠标没动；"
        "要更接近真实轨迹可给 hover_path 中间点。"
        "回执的 hover.hit 会说明光标下是哪一层窗口；"
        "若它与这次取图的窗口不是同一个，note 会直接指出该改用哪个 hwnd——"
        "播放器画面常是独立顶层窗口，按标题取的却是它上面的详情页壳。"
        "不给 window / hwnd 而给了 hover 时，直接取光标那一层窗口的原尺寸内容，"
        "既不会被遮挡，也不会因为整屏缩放而看不清控件上的字。"
        "分开调用「先移鼠标、再截图」在多数播放器与网页上都会失败——"
        "控件的自动隐藏通常只有 2–3 秒，撑不过一次模型往返。"
        "不给窗口则取屏幕合成结果（会包含遮挡物）。"
        "默认每张图都带坐标辅助线：光标位置是黑色描边、白色分隔的亮绿短十字、"
        "小圆环和黑底或黑色描边的 CURSOR 标签；短十字只画在光标附近，不铺满全图，"
        "中心留空，落点像素本身不被盖住。小区域的标签只写坐标，省略 CURSOR "
        "前缀；短边小于 90 的区域完全不画标签，坐标从回执 cursor 读取。"
        "网格主线是红色粗线，细线是蓝色，刻度数字在边缘。"
        "这些线不是截图里的界面元素，是读坐标的参照；先读 CURSOR 标签和绿十字，"
        "再用网格定位，回执的 cursor 给出同一坐标。图片压缩后辅助线和标签仍保留；"
        "仍看不清时缩小取图区域、把 grid_step 调到 20–40，或提高 max_side。"
        "要同时看标注图和干净原图时给 annotate=both：同一张图先回标注图、再回"
        "无辅助线原图；annotate=raw 只回原图，默认 annotated 只回标注图。"
        "量尺寸/坐标时用 annotated + grid_step=20 的图，不要用 raw；"
        "raw 只用于确认内容，边框不能靠肉眼估。"
        "回执带 capture_id；要按图内坐标点击时，先让这张图的网格用图内像素"
        "（grid_unit=image），再把 capture_id 与图内 x/y 交给 desktop_mouse"
        "（space=image）。默认网格仍是屏幕坐标；两种坐标不要混用。"
        "整屏截图不要直接用来估 5px 级控件；局部取图、max_side=0、grid_step=20 才是精确点击路径。"
    )
    parameters = {
        "x": {"type": "integer", "description": "区域左上角 x（屏幕坐标）；与 y/width/height 同时给出"},
        "y": {"type": "integer", "description": "区域左上角 y（屏幕坐标）"},
        "width": {"type": "integer", "description": "区域宽度（屏幕坐标）"},
        "height": {"type": "integer", "description": "区域高度（屏幕坐标）"},
        "window": {"type": "string", "description": "窗口标题片段；取该窗口自身内容，遮挡不影响"},
        "hwnd": {"type": "integer", "description": "窗口句柄；与 window 二选一，hwnd 更精确"},
        "activate": {"type": "boolean",
                     "description": "取图前是否把窗口带到前台（默认 false：只恢复不置前，不打断当前操作）"},
        "hover": {"type": "array", "items": {"type": "integer"}, "minItems": 2,
                  "maxItems": 2,
                  "description": "取图前把光标移到这里 [x, y]（屏幕坐标），用来展开悬停控件"},
        "hover_path": {"type": "array", "items": {"type": "array",
                                                  "items": {"type": "integer"},
                                                  "minItems": 2, "maxItems": 2},
                       "description": "到 hover 之前先经过的中间点 [[x, y], ...]，最多 4 个；"
                                      "用它模拟真实移动轨迹，唤醒只认连续 mousemove 的播放器控件"},
        "hover_settle_ms": {"type": "integer",
                            "description": "移完光标等界面展开的毫秒数 0–5000；缺省取插件配置"},
        "hover_approach_ms": {"type": "integer",
                              "description": "移动到落点用多少毫秒 0–2000（默认 120）；"
                                             "0 = 一次跳变。"},
        "hover_wiggle": {"type": "boolean",
                         "description": "到达后是否在落点附近做几次 1–2px 微移动（默认 true）；"
                                        "播放器控制条通常需要它才会出现。微动结束会回到落点"},
        "grid": {"type": "boolean", "description": "叠加坐标网格与刻度（默认 true）"},
        "grid_step": {"type": "integer",
                      "description": "网格间距（屏幕坐标）20–500；缺省取插件配置。"
                                     "整屏用于定位；精确点击局部时给 20"},
        "grid_unit": {"type": "string", "enum": ["screen", "image"],
                      "description": "网格刻度单位：screen 屏幕坐标（默认）/ image 图内像素。"
                                     "图内像素配合 capture_id 交给 desktop_mouse"},
        "max_side": {"type": "integer",
                     "description": "长边缩到不超过该像素；0 = 不缩放；"
                                    "精确点击局部时用 0，避免缩放误差"},
        "annotate": {"type": "string", "enum": ["annotated", "raw", "both"],
                     "description": "annotated 只回标注图（默认）/ raw 只回原图 / "
                                    "both 先回标注图再回原图"},
    }

    def __init__(self, backend: Backend, config: DesktopConfig,
                 live_state: Any = None,
                 captures: Optional[CaptureStore] = None) -> None:
        self._backend = backend
        self._config = config
        self._live_state = live_state
        self._captures = captures

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, set(_FIELDS), action=self.name)
        hover = _hover_point(arguments)
        hover_path = _hover_path(arguments)
        if hover_path and hover is None:
            raise ValueError("hover_path 必须与 hover 一起给：hover 是终点")
        if hover is not None:
            # 悬停会移动真实光标：它已经不属于"只读看屏"，Plan 模式必须拦住。
            reject_in_plan(self._live_state, "桌面悬停取图")
            bounds = self._backend.screen.geometry().rect
            for waypoint in hover_path:
                if not bounds.contains(waypoint):
                    raise ValueError(
                        f"hover_path 的点 {waypoint.to_dict()} 不在屏幕 {bounds.to_dict()} 内")
        request = request_from_arguments(self._backend, self._config, arguments)
        # 小目标（剧集卡片、播放器按钮）用更细的网格才能把坐标读准；
        # 这是纯视觉精度，不引入任何文字识别。
        request = dataclasses.replace(
            request,
            grid_step=require_range(
                as_int(arguments, "grid_step", self._config.grid_step),
                "grid_step", 20, 500),
        )
        if hover is not None:
            settle = require_range(
                as_int(arguments, "hover_settle_ms", self._config.hover_settle_ms),
                "hover_settle_ms", 0, 5000)
            approach = require_range(
                as_int(arguments, "hover_approach_ms", self._config.hover_approach_ms),
                "hover_approach_ms", 0, 2000)
            wiggle = as_bool(arguments, "hover_wiggle", self._config.hover_wiggle)
            request = dataclasses.replace(
                request, hover=hover, hover_path=hover_path,
                hover_settle_ms=settle, hover_approach_ms=approach,
                hover_wiggle=wiggle)

        summary, attachments = capture_payload(
            self._backend, self._config, request, captures=self._captures)
        return ToolResult.attach(summary, attachments)


def _hover_point(arguments: Dict[str, Any]) -> Optional[ScreenPoint]:
    """读 hover=[x, y]；形态不对就报错，不做坐标猜测。"""
    value = arguments.get("hover")
    if value is None:
        return None
    return _as_point(value, "hover")


def _hover_path(arguments: Dict[str, Any]) -> tuple:
    """读 hover_path=[[x, y], ...]；只收终点之前的中间点。"""
    value = arguments.get("hover_path")
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 4:
        raise ValueError("hover_path 要给 1–4 个中间点，每个点是 [x, y]")
    return tuple(_as_point(item, "hover_path") for item in value)


def _as_point(value: Any, name: str) -> ScreenPoint:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} 要给两个整数 [x, y]（屏幕坐标）")
    x, y = value
    for axis, number in (("x", x), ("y", y)):
        if isinstance(number, bool) or not isinstance(number, int):
            raise ValueError(f"{name} 的 {axis} 必须是整数，实际 {number!r}")
    return ScreenPoint(int(x), int(y))
