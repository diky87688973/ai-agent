# -*- coding: utf-8 -*-
"""桌面 IO 插件测试。

覆盖：坐标契约 / 键名归一 / 配置回退与夹取 / 截图加工（缩放、网格、空白）/
三个工具的参数矩阵与结果 / Plan 门控 / 输入锁 / 平台表与后端选择。
"""
from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.core.session_scope import reset_session_scope, set_session_scope  # noqa: E402
from agent.mechanisms.live_state import ModeConflict  # noqa: E402

_PLUGIN_DIR = _ROOT / "plugins"


def _load_plugin_module():
    """按包形态加载插件：子模块的相对导入要能找到父包。"""
    parent = sys.modules.get("fan_agent_plugins")
    if parent is None:
        parent = types.ModuleType("fan_agent_plugins")
        parent.__path__ = [str(_PLUGIN_DIR)]
        sys.modules["fan_agent_plugins"] = parent
    path = _PLUGIN_DIR / "desktop_io" / "plugin.py"
    name = "fan_agent_plugins.desktop_io"
    spec = importlib.util.spec_from_file_location(
        name, str(path), submodule_search_locations=[str(path.parent)])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_PLUGIN = _load_plugin_module()

from fan_agent_plugins.desktop_io import canvas, diff, keys  # noqa: E402
from fan_agent_plugins.desktop_io.backends._unavailable import unavailable_backend  # noqa: E402
from fan_agent_plugins.desktop_io.config import DesktopConfig, load_config  # noqa: E402
from fan_agent_plugins.desktop_io.coords import (  # noqa: E402
    ScreenGeometry,
    ScreenPoint,
    ScreenRect,
)
from fan_agent_plugins.desktop_io.errors import (  # noqa: E402
    DesktopBusy,
    DesktopError,
    DesktopUnavailable,
    ScreenCaptureFailed,
)
from fan_agent_plugins.desktop_io.input_lock import input_guard  # noqa: E402
from fan_agent_plugins.desktop_io.ports import (  # noqa: E402
    Backend,
    Screenshot,
    WindowActivation,
    WindowInfo,
)
from fan_agent_plugins.desktop_io.tools import (  # noqa: E402
    DesktopEyeTool,
    DesktopKeyboardTool,
    DesktopMouseTool,
    DesktopWaitTool,
)


def _png(width: int = 40, height: int = 30, color=(20, 40, 60)) -> bytes:
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


class Recorder:
    """按方法名记录调用并返回预设值，替身不用逐个实现端口。"""

    def __init__(self, **returns) -> None:
        self.calls = []
        self._returns = returns

    def __getattr__(self, name):
        def call(*args, **kwargs):
            # 关键字参数按传入顺序展平到末尾，断言里能直接看出"有没有要置前"。
            self.calls.append((name,) + args + tuple(kwargs.values()))
            return self._returns.get(name)
        return call


class LiveState:
    def __init__(self, mode: str = "plan") -> None:
        self.mode = mode

    def get_mode(self, _cid: str) -> str:
        return self.mode


def _backend(rect: ScreenRect | None = None, png: bytes | None = None,
             cursor: ScreenPoint | None = None, mixed_scale: bool = False,
             windows=None, hit=None):
    rect = rect or ScreenRect(0, 0, 40, 30)
    screen = Recorder(geometry=ScreenGeometry(rect=rect, mixed_scale=mixed_scale),
                      capture=Screenshot(png or _png(rect.width, rect.height), rect))
    mouse = Recorder(cursor=cursor or ScreenPoint(7, 8))
    keyboard = Recorder()
    return Backend("test", screen, mouse, keyboard, windows=windows, hit=hit), \
        screen, mouse, keyboard


def _window_info(hwnd: int = 4242, rect: ScreenRect | None = None,
                 foreground: bool = False) -> WindowInfo:
    rect = rect or ScreenRect(0, 0, 40, 30)
    return WindowInfo(hwnd=hwnd, title="腾讯视频", rect=rect,
                      minimized=False, visible=True, foreground=foreground)


class CoordsTest(unittest.TestCase):
    def test_rect_bounds_and_intersection(self) -> None:
        rect = ScreenRect(10, 10, 20, 20)
        self.assertTrue(rect.contains(ScreenPoint(10, 10)))
        self.assertFalse(rect.contains(ScreenPoint(30, 10)))
        self.assertEqual(rect.intersect(ScreenRect(0, 0, 15, 15)), ScreenRect(10, 10, 5, 5))
        self.assertIsNone(rect.intersect(ScreenRect(50, 50, 1, 1)))

    def test_rect_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            ScreenRect(0, 0, 0, 10)

    def test_geometry_reports_ratio(self) -> None:
        geometry = ScreenGeometry(rect=ScreenRect(0, 0, 100, 100), pixel_ratio=2.0,
                                  dpi="2x", mixed_scale=True)
        self.assertEqual(geometry.to_dict()["pixel_ratio"], 2.0)
        self.assertTrue(geometry.to_dict()["mixed_scale"])
        self.assertEqual(geometry.to_dict()["dpi"], "2x")


class KeysTest(unittest.TestCase):
    def test_aliases_normalize(self) -> None:
        self.assertEqual(keys.canonical("Return"), "enter")
        self.assertEqual(keys.canonical("ESC"), "esc")
        self.assertEqual(keys.canonical("A"), "a")
        self.assertEqual(keys.canonical("minus"), "-")

    def test_unknown_key_names_hint(self) -> None:
        with self.assertRaises(ValueError) as raised:
            keys.canonical("hyper")
        self.assertIn("未知键名", str(raised.exception))
        with self.assertRaises(ValueError):
            keys.canonical("中")

    def test_hotkey_forms(self) -> None:
        self.assertEqual(keys.normalize_hotkey("ctrl+shift+t"), ("ctrl", "shift", "t"))
        self.assertEqual(keys.normalize_hotkey(["alt", "tab"]), ("alt", "tab"))
        self.assertEqual(keys.split_hotkey("ctrl,c"), ["ctrl", "c"])

    def test_hotkey_rejects_bad_shapes(self) -> None:
        for value in ("ctrl", ["ctrl", "shift"], "ctrl++"):
            with self.assertRaises(ValueError):
                keys.normalize_hotkey(value)

    def test_canonical_set_is_coverable(self) -> None:
        self.assertIn("f20", keys.CANONICAL_KEYS)
        self.assertNotIn("f21", keys.CANONICAL_KEYS)


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _write(self, text: str) -> None:
        (self.root / "plugin-config.ini").write_text(text, encoding="utf-8")

    def test_missing_file_uses_defaults(self) -> None:
        self.assertEqual(load_config(self.root), DesktopConfig())

    def test_values_are_read_and_clamped(self) -> None:
        self._write(
            "[ext]\neye = 0\nkeyboard = off\nmax_side = 99999\n"
            "grid_step = 5\nsettle_ms = -3\ntype_interval_ms = 500\n"
        )
        config = load_config(self.root)
        self.assertFalse(config.eye)
        self.assertTrue(config.mouse)
        self.assertFalse(config.keyboard)
        self.assertEqual(config.max_side, 8192)
        self.assertEqual(config.grid_step, 20)
        self.assertEqual(config.settle_ms, 0)
        self.assertEqual(config.type_interval_ms, 200)

    def test_bad_values_fall_back(self) -> None:
        self._write("[ext]\nmax_side = huge\ncursor_mark = maybe\n")
        config = load_config(self.root)
        self.assertEqual(config.max_side, 1600)
        self.assertTrue(config.cursor_mark)


class CanvasTest(unittest.TestCase):
    def test_scales_and_reports(self) -> None:
        rendered = canvas.render(_png(400, 300), rect=ScreenRect(0, 0, 400, 300),
                                 grid=False, step=100, cursor=None,
                                 cursor_mark=True, max_side=100)
        self.assertEqual((rendered.width, rendered.height), (400, 300))
        self.assertEqual((rendered.sent_width, rendered.sent_height), (100, 75))
        self.assertEqual(rendered.scale, 4.0)
        self.assertTrue(rendered.shrunk)
        self.assertFalse(rendered.blank)

    def test_offset_maps_screen_units_to_sent_pixels(self) -> None:
        # Retina：区域 400 点，图片 800 像素，屏幕坐标 200 落在图片正中。
        self.assertEqual(canvas._offset(0, 200, 400, 800), 400)
        self.assertEqual(canvas._offset(100, 150, 400, 800), 100)

    def test_cursor_mark_follows_screen_extent(self) -> None:
        rendered = canvas.render(_png(800, 600, (255, 255, 255)),
                                 rect=ScreenRect(0, 0, 400, 300), grid=False,
                                 step=100, cursor=ScreenPoint(200, 150),
                                 cursor_mark=True, max_side=0)
        from PIL import Image
        image = Image.open(io.BytesIO(rendered.png))
        self.assertNotEqual(image.getpixel((400, 100)), (255, 255, 255))
        self.assertEqual(image.getpixel((200, 100)), (255, 255, 255))

    def test_grid_and_cursor_change_pixels(self) -> None:
        rect = ScreenRect(100, 200, 400, 300)
        plain = canvas.render(_png(400, 300), rect=rect, grid=False, step=50,
                              cursor=None, cursor_mark=True, max_side=0)
        grid = canvas.render(_png(400, 300), rect=rect, grid=True, step=50,
                             cursor=ScreenPoint(150, 250), cursor_mark=True, max_side=0)
        self.assertNotEqual(plain.png, grid.png)
        self.assertEqual(grid.scale, 1.0)

    def test_blank_and_tiny_images(self) -> None:
        blank = canvas.render(_png(20, 10, (0, 0, 0)), rect=ScreenRect(0, 0, 20, 10),
                              grid=True, step=500, cursor=None,
                              cursor_mark=False, max_side=0)
        self.assertTrue(blank.blank)
        tiny = canvas.render(_png(12, 8), rect=ScreenRect(0, 0, 12, 8),
                             grid=True, step=20, cursor=ScreenPoint(1, 1),
                             cursor_mark=True, max_side=0)
        self.assertEqual((tiny.sent_width, tiny.sent_height), (12, 8))

    def test_bad_png_raises(self) -> None:
        with self.assertRaises(ScreenCaptureFailed):
            canvas.render(b"not a png", rect=ScreenRect(0, 0, 10, 10), grid=False,
                          step=100, cursor=None, cursor_mark=False, max_side=0)


class EyeToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = DesktopConfig(settle_ms=0)

    def test_returns_image_attachment(self) -> None:
        backend, screen, _mouse, _keyboard = _backend()
        result = DesktopEyeTool(backend, self.config).execute({})
        self.assertTrue(result.ok)
        self.assertEqual(result.attachments[0]["mime"], "image/png")
        self.assertTrue(result.attachments[0]["data_base64"])
        self.assertEqual(result.data["capture"], {"x": 0, "y": 0, "width": 40, "height": 30})
        self.assertEqual(result.data["cursor"], {"x": 7, "y": 8})
        self.assertNotIn("note", result.data)
        self.assertIn(("capture", None), screen.calls)

    def test_region_is_clipped_to_screen(self) -> None:
        backend, screen, _mouse, _keyboard = _backend()
        DesktopEyeTool(backend, self.config).execute(
            {"x": -10, "y": 5, "width": 20, "height": 40})
        region = next(call[1] for call in screen.calls if call[0] == "capture")
        self.assertEqual(region, ScreenRect(0, 5, 10, 25))

    def test_region_needs_four_numbers(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        with self.assertRaises(ValueError):
            DesktopEyeTool(backend, self.config).execute({"x": 1, "y": 2, "width": 3})
        with self.assertRaises(ValueError):
            DesktopEyeTool(backend, self.config).execute(
                {"x": -100, "y": -100, "width": 10, "height": 10})

    def test_oversized_region_rejected(self) -> None:
        rect = ScreenRect(0, 0, 7000, 7000)
        backend, _screen, _mouse, _keyboard = _backend(rect=rect)
        with self.assertRaises(ValueError):
            DesktopEyeTool(backend, self.config).execute(
                {"x": 0, "y": 0, "width": 7000, "height": 7000})

    def test_notes_report_shrinking_and_blank(self) -> None:
        rect = ScreenRect(0, 0, 400, 300)
        backend, _screen, _mouse, _keyboard = _backend(rect=rect, png=_png(400, 300))
        result = DesktopEyeTool(backend, self.config).execute({"max_side": 100})
        self.assertIn("缩到 100x75", result.data["note"])
        black, _s, _m, _k = _backend(rect=rect, png=_png(40, 30, (0, 0, 0)))
        blank = DesktopEyeTool(black, self.config).execute({})
        self.assertIn("全黑", blank.data["note"])

    def test_note_reports_mixed_scale(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend(mixed_scale=True)
        result = DesktopEyeTool(backend, self.config).execute({})
        self.assertIn("多屏缩放不一致", result.data["note"])

    def test_grid_switch_is_reported(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        plain = DesktopEyeTool(backend, self.config).execute({"grid": False})
        self.assertNotIn("grid", plain.data)
        gridded = DesktopEyeTool(backend, self.config).execute({"grid": True})
        self.assertEqual(gridded.data["grid"]["step"], 100)

    def test_unknown_argument_rejected(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        with self.assertRaises(ValueError):
            DesktopEyeTool(backend, self.config).execute({"zoom": 2})


class WindowCaptureTest(unittest.TestCase):
    """按窗口取图：走 windows 端口，而不是屏幕端口。"""

    def setUp(self) -> None:
        self.config = DesktopConfig(settle_ms=0)
        rect = ScreenRect(0, 0, 40, 30)
        self.info = _window_info(rect=rect)
        self.windows = Recorder(
            get=self.info,
            find=(self.info,),
            capture=Screenshot(_png(40, 30), rect, source="window"),
        )

    def test_window_title_routes_to_window_port(self) -> None:
        backend, screen, _mouse, _keyboard = _backend(windows=self.windows)
        result = DesktopEyeTool(backend, self.config).execute({"window": "腾讯视频"})
        self.assertEqual(result.data["source"], "window")
        self.assertEqual(result.data["window"]["hwnd"], 4242)
        self.assertIn(("capture", 4242, None, False), self.windows.calls)
        self.assertNotIn("capture", [call[0] for call in screen.calls])

    def test_hwnd_skips_title_lookup(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend(windows=self.windows)
        DesktopEyeTool(backend, self.config).execute({"hwnd": 4242})
        self.assertIn(("get", 4242), self.windows.calls)
        self.assertNotIn("find", [call[0] for call in self.windows.calls])

    def test_region_is_passed_through(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend(windows=self.windows)
        DesktopEyeTool(backend, self.config).execute(
            {"window": "腾讯视频", "x": 1, "y": 2, "width": 10, "height": 12})
        self.assertIn(("capture", 4242, ScreenRect(1, 2, 10, 12), False),
                      self.windows.calls)

    def test_window_and_hwnd_are_exclusive(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend(windows=self.windows)
        with self.assertRaises(ValueError):
            DesktopEyeTool(backend, self.config).execute({"window": "x", "hwnd": 4242})

    def test_missing_window_port_reports_clearly(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        with self.assertRaises(DesktopUnavailable) as raised:
            DesktopEyeTool(backend, self.config).execute({"window": "腾讯视频"})
        self.assertIn("不支持按窗口操作", str(raised.exception))

    def test_no_matching_window(self) -> None:
        empty = Recorder(get=self.info, find=(), capture=None)
        backend, _screen, _mouse, _keyboard = _backend(windows=empty)
        with self.assertRaises(ValueError) as raised:
            DesktopEyeTool(backend, self.config).execute({"window": "不存在的标题"})
        self.assertIn("没有标题包含", str(raised.exception))

    def test_screen_fallback_is_reported(self) -> None:
        fallback = Recorder(
            get=self.info, find=(self.info,),
            capture=Screenshot(_png(40, 30), self.info.rect, source="screen"),
        )
        backend, _screen, _mouse, _keyboard = _backend(windows=fallback)
        result = DesktopEyeTool(backend, self.config).execute({"window": "腾讯视频"})
        self.assertEqual(result.data["source"], "screen")
        self.assertIn("回退为屏幕截图", result.data["note"])

    def test_window_content_has_no_fallback_note(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend(windows=self.windows)
        result = DesktopEyeTool(backend, self.config).execute({"window": "腾讯视频"})
        self.assertNotIn("note", result.data)

    def test_restore_only_does_not_steal_foreground(self) -> None:
        windows = Recorder(
            get=self.info, find=(self.info,),
            capture=Screenshot(_png(40, 30), self.info.rect, source="window",
                               restored=True, activation="none"),
        )
        backend, _screen, _mouse, _keyboard = _backend(windows=windows)
        result = DesktopEyeTool(backend, self.config).execute({"window": "腾讯视频"})
        self.assertTrue(result.data["restored"])
        self.assertNotIn("activated", result.data)
        self.assertIn("未置前", result.data["note"])
        # 恢复后要重取窗口信息，否则回执里的 rect 还是 -32000（title 路径原本不调 get）
        self.assertIn(("get", 4242), windows.calls)

    def test_activate_requested_reports_success(self) -> None:
        windows = Recorder(
            get=self.info, find=(self.info,),
            capture=Screenshot(_png(40, 30), self.info.rect, source="window",
                               restored=True, activation="ok"),
        )
        backend, _screen, _mouse, _keyboard = _backend(windows=windows)
        result = DesktopEyeTool(backend, self.config).execute(
            {"window": "腾讯视频", "activate": True})
        self.assertTrue(result.data["activated"])
        self.assertIn(("capture", 4242, None, True), windows.calls)
        self.assertIn("已恢复并置前", result.data["note"])

    def test_activate_failure_is_reported(self) -> None:
        windows = Recorder(
            get=self.info, find=(self.info,),
            capture=Screenshot(_png(40, 30), self.info.rect, source="window",
                               activation="failed"),
        )
        backend, _screen, _mouse, _keyboard = _backend(windows=windows)
        result = DesktopEyeTool(backend, self.config).execute(
            {"window": "腾讯视频", "activate": True})
        self.assertFalse(result.data["activated"])
        self.assertIn("没抢到前台", result.data["note"])

    def test_activate_rejected_for_plain_screen(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        with self.assertRaises(ValueError) as raised:
            DesktopEyeTool(backend, self.config).execute({"activate": True})
        self.assertIn("只对 window / hwnd 有意义", str(raised.exception))


class WindowActivationTest(unittest.TestCase):
    """手部动作可以带 window / hwnd：先置前，再落点。"""

    def setUp(self) -> None:
        self.config = DesktopConfig(settle_ms=0)
        self.info = _window_info()
        self.active = WindowActivation(window=self.info, active=True, restored=True)

    def test_mouse_activates_before_click(self) -> None:
        windows = Recorder(get=self.info, find=(self.info,), activate=self.active)
        backend, _screen, mouse, _keyboard = _backend(windows=windows)
        result = DesktopMouseTool(backend, self.config).execute(
            {"action": "click", "x": 5, "y": 6, "window": "腾讯视频"})
        self.assertIn(("activate", 4242), windows.calls)
        self.assertIn(("click", ScreenPoint(5, 6), "left", 1), mouse.calls)
        self.assertEqual(result["focus"]["hwnd"], 4242)
        self.assertTrue(result["focus"]["active"])

    def test_keyboard_activates_before_typing(self) -> None:
        windows = Recorder(get=self.info, find=(self.info,), activate=self.active)
        backend, _screen, _mouse, keyboard = _backend(windows=windows)
        result = DesktopKeyboardTool(backend, self.config).execute(
            {"action": "type", "text": "斗破苍穹", "window": "腾讯视频"})
        self.assertIn(("activate", 4242), windows.calls)
        self.assertIn(("type_text", "斗破苍穹", DesktopConfig(settle_ms=0).type_interval_ms),
                      keyboard.calls)
        self.assertEqual(result["focus"]["hwnd"], 4242)

    def test_failed_activation_blocks_input(self) -> None:
        blocked = WindowActivation(window=self.info, active=False, restored=False,
                                   foreground="Cursor")
        windows = Recorder(get=self.info, find=(self.info,), activate=blocked)
        backend, _screen, mouse, keyboard = _backend(windows=windows)
        with self.assertRaises(DesktopError) as raised:
            DesktopKeyboardTool(backend, self.config).execute(
                {"action": "type", "text": "x", "window": "腾讯视频"})
        self.assertIn("没有拿到前台", str(raised.exception))
        self.assertIn("Cursor", str(raised.exception))
        self.assertEqual(keyboard.calls, [])
        with self.assertRaises(DesktopError):
            DesktopMouseTool(backend, self.config).execute(
                {"action": "click", "x": 1, "y": 2, "hwnd": 4242})
        self.assertEqual(mouse.calls, [])

    def test_cursor_query_does_not_activate(self) -> None:
        windows = Recorder(get=self.info, find=(self.info,), activate=self.active)
        backend, _screen, _mouse, _keyboard = _backend(windows=windows)
        DesktopMouseTool(backend, self.config).execute(
            {"action": "cursor", "window": "腾讯视频"})
        self.assertEqual(windows.calls, [])

    def test_activation_reports_matched_when_titles_collide(self) -> None:
        windows = Recorder(get=self.info, find=(self.info, self.info),
                           activate=self.active)
        backend, _screen, _mouse, _keyboard = _backend(windows=windows)
        result = DesktopMouseTool(backend, self.config).execute(
            {"action": "click", "x": 5, "y": 6, "window": "腾讯视频"})
        self.assertEqual(result["focus"]["matched"], 2)


class MouseToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = DesktopConfig(settle_ms=0)
        self.backend, self.screen, self.mouse, self.keyboard = _backend()
        self.tool = DesktopMouseTool(self.backend, self.config)

    def test_move_and_click(self) -> None:
        self.tool.execute({"action": "move", "x": 5, "y": 6})
        self.assertIn(("move", ScreenPoint(5, 6), 0), self.mouse.calls)
        self.tool.execute({"action": "click", "x": 3, "y": 4, "count": 2})
        self.assertIn(("click", ScreenPoint(3, 4), "left", 2), self.mouse.calls)
        self.tool.execute({"action": "click"})
        self.assertIn(("click", None, "left", 1), self.mouse.calls)

    def test_drag_scroll_and_cursor(self) -> None:
        self.tool.execute({"action": "drag", "x": 1, "y": 2, "to_x": 8, "to_y": 9})
        self.assertIn(("drag", ScreenPoint(1, 2), ScreenPoint(8, 9), "left", 300),
                      self.mouse.calls)
        self.tool.execute({"action": "scroll", "amount": -3})
        self.assertIn(("scroll", None, -3, False), self.mouse.calls)
        snapshot = self.tool.execute({"action": "cursor"})
        self.assertEqual(snapshot["cursor"], {"x": 7, "y": 8})
        self.assertEqual(self.mouse.calls[-1], ("cursor",))

    def test_out_of_screen_point_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.tool.execute({"action": "move", "x": 100, "y": 0})

    def test_parameter_matrix(self) -> None:
        bad = [
            {"action": "move", "x": 1},
            {"action": "drag", "x": 1, "y": 2},
            {"action": "scroll", "amount": 0},
            {"action": "scroll", "amount": 99},
            {"action": "move", "x": 1, "y": 2, "count": 2},
            {"action": "move", "x": 1, "y": 2, "button": "side"},
            {"action": "bogus"},
        ]
        for arguments in bad:
            with self.assertRaises(ValueError, msg=str(arguments)):
                self.tool.execute(arguments)

    def test_plan_gate(self) -> None:
        token = set_session_scope("desktop-plan")
        self.addCleanup(reset_session_scope, token)
        tool = DesktopMouseTool(self.backend, self.config, LiveState("plan"))
        self.assertEqual(tool.execute({"action": "cursor"})["action"], "cursor")
        with self.assertRaises(ModeConflict):
            tool.execute({"action": "move", "x": 1, "y": 2})
        allowed = DesktopMouseTool(self.backend, self.config, LiveState("auto"))
        self.assertEqual(allowed.execute({"action": "move", "x": 1, "y": 2})["action"], "move")


class KeyboardToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = DesktopConfig(settle_ms=0)
        self.backend, _screen, _mouse, self.keyboard = _backend()
        self.tool = DesktopKeyboardTool(self.backend, self.config)

    def test_type_key_and_hotkey(self) -> None:
        result = self.tool.execute({"action": "type", "text": "你好 A\n"})
        self.assertEqual(self.keyboard.calls[-1], ("type_text", "你好 A\n", 12))
        self.assertEqual(result["chars"], 5)

        self.tool.execute({"action": "key", "key": "Return", "repeat": 3})
        self.assertEqual(self.keyboard.calls[-1], ("press", "enter", 3))

        self.tool.execute({"action": "hotkey", "keys": "ctrl+shift+t"})
        self.assertEqual(self.keyboard.calls[-1], ("hotkey", ("ctrl", "shift", "t"), 1))

    def test_bad_parameters(self) -> None:
        for arguments in ({"action": "type"},
                          {"action": "key", "key": "hyper"},
                          {"action": "hotkey", "keys": "ctrl"},
                          {"action": "key", "key": "a", "repeat": 99},
                          {"action": "type", "text": "x", "key": "a"}):
            with self.assertRaises(ValueError, msg=str(arguments)):
                self.tool.execute(arguments)

    def test_plan_gate_blocks(self) -> None:
        token = set_session_scope("desktop-plan-keys")
        self.addCleanup(reset_session_scope, token)
        tool = DesktopKeyboardTool(self.backend, self.config, LiveState("plan"))
        with self.assertRaises(ModeConflict):
            tool.execute({"action": "key", "key": "enter"})
        self.assertEqual(self.keyboard.calls, [])


class HoverCaptureTest(unittest.TestCase):
    """悬停取图：移光标与截图必须在同一次调用内完成。"""

    def setUp(self) -> None:
        self.config = DesktopConfig(settle_ms=0, hover_settle_ms=0)
        self.backend, _screen, self.mouse, _keyboard = _backend(
            rect=ScreenRect(0, 0, 800, 700))
        self.tool = DesktopEyeTool(self.backend, self.config)

    def test_hover_moves_cursor_before_capture(self) -> None:
        result = self.tool.execute({"hover": [700, 640]})
        self.assertEqual(self.mouse.calls[0], ("move", ScreenPoint(700, 640), 0))
        self.assertEqual(result.data["hover"], {"x": 700, "y": 640, "settle_ms": 0})

    def test_hover_requires_two_integers(self) -> None:
        for value in ([1], [1, 2, 3], ["a", 2], [True, 2], 5):
            with self.assertRaises(ValueError, msg=str(value)):
                self.tool.execute({"hover": value})

    def test_hover_settle_is_reported_and_clamped(self) -> None:
        result = self.tool.execute({"hover": [1, 2], "hover_settle_ms": 120})
        self.assertEqual(result.data["hover"]["settle_ms"], 120)
        with self.assertRaises(ValueError):
            self.tool.execute({"hover": [1, 2], "hover_settle_ms": 9999})

    def test_hover_outside_the_screen_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.tool.execute({"hover": [1000, 1000]})
        self.assertEqual(self.mouse.calls, [])

    def test_hover_is_blocked_in_plan_mode(self) -> None:
        token = set_session_scope("desktop-hover-plan")
        self.addCleanup(reset_session_scope, token)
        tool = DesktopEyeTool(self.backend, self.config, LiveState("plan"))
        with self.assertRaises(ModeConflict):
            tool.execute({"hover": [1, 2]})
        self.assertEqual(self.mouse.calls, [])
        # 不悬停的普通取图在 Plan 模式下仍然可用。
        self.assertEqual(tool.execute({}).data["source"], "screen")


class WindowHoverTest(unittest.TestCase):
    """窗口悬停：先恢复/置前，再移光标，最后取图。"""

    def test_hover_runs_after_activation_and_before_capture(self) -> None:
        config = DesktopConfig(settle_ms=0, hover_settle_ms=0)
        info = _window_info()
        events = []

        class Probe:
            def get(self, hwnd):
                return info

            def find(self, title):
                return (info,)

            def activate(self, hwnd):
                events.append("activate")
                return WindowActivation(window=info, active=True)

            def capture(self, hwnd, region, *, activate=False, prepare=None):
                events.append("activate-requested" if activate else "no-activate")
                if prepare is not None:
                    prepare()
                events.append("capture")
                return Screenshot(_png(40, 30), info.rect, source="window",
                                  activation="ok" if activate else "none")

        class Mouse:
            def cursor(self):
                return ScreenPoint(7, 8)

            def move(self, point, duration_ms):
                events.append(("move", point))

        screen = Recorder(geometry=ScreenGeometry(rect=info.rect),
                          capture=Screenshot(_png(40, 30), info.rect))
        backend = Backend("test", screen, Mouse(), Recorder(), windows=Probe())
        result = DesktopEyeTool(backend, config).execute(
            {"window": "腾讯视频", "activate": True, "hover": [30, 20]})

        self.assertEqual(events, ["activate-requested", ("move", ScreenPoint(30, 20)),
                                  "capture"])
        self.assertEqual(result.data["window"]["hwnd"], 4242)
        self.assertTrue(result.data["activated"])

    def test_plain_window_capture_does_not_pass_a_prepare_hook(self) -> None:
        config = DesktopConfig(settle_ms=0)
        info = _window_info()
        seen = []

        class Probe:
            def get(self, hwnd):
                return info

            def find(self, title):
                return (info,)

            def capture(self, hwnd, region, *, activate=False, prepare=None):
                seen.append(prepare)
                return Screenshot(_png(40, 30), info.rect, source="window")

        screen = Recorder(geometry=ScreenGeometry(rect=info.rect),
                          capture=Screenshot(_png(40, 30), info.rect))
        backend = Backend("test", screen, Recorder(cursor=ScreenPoint(7, 8)),
                          Recorder(), windows=Probe())
        DesktopEyeTool(backend, config).execute({"window": "腾讯视频"})
        self.assertEqual(seen, [None])


class ShotTest(unittest.TestCase):
    """动作自带回图：点完/打完就在同一次调用里返回图片。"""

    def setUp(self) -> None:
        self.config = DesktopConfig(settle_ms=0)
        self.info = _window_info()
        self.windows = Recorder(
            get=self.info, find=(self.info,),
            activate=WindowActivation(window=self.info, active=True),
            capture=Screenshot(_png(40, 30), self.info.rect, source="window"),
        )

    def test_mouse_shot_returns_image_and_receipt(self) -> None:
        backend, _screen, mouse, _keyboard = _backend(windows=self.windows)
        result = DesktopMouseTool(backend, self.config).execute(
            {"action": "click", "x": 5, "y": 6, "window": "腾讯视频", "shot": True})
        self.assertTrue(result.ok)
        self.assertEqual(result.attachments[0]["mime"], "image/png")
        self.assertEqual(result.data["performed"]["action"], "click")
        self.assertEqual(result.data["window"]["hwnd"], 4242)
        self.assertIn(("click", ScreenPoint(5, 6), "left", 1), mouse.calls)

    def test_mouse_without_shot_returns_plain_dict(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        result = DesktopMouseTool(backend, self.config).execute(
            {"action": "click", "x": 5, "y": 6})
        self.assertIsInstance(result, dict)
        self.assertEqual(result["action"], "click")

    def test_keyboard_shot_returns_image(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend(windows=self.windows)
        result = DesktopKeyboardTool(backend, self.config).execute(
            {"action": "type", "text": "斗破苍穹", "window": "腾讯视频", "shot": True})
        self.assertEqual(result.data["performed"]["chars"], 4)
        self.assertTrue(result.attachments[0]["data_base64"])

    def test_shot_region_is_clipped(self) -> None:
        backend, screen, _mouse, _keyboard = _backend()
        DesktopMouseTool(backend, self.config).execute(
            {"action": "click", "x": 5, "y": 6, "shot": True,
             "shot_region": [-10, -10, 20, 20]})
        self.assertIn(("capture", ScreenRect(0, 0, 10, 10)), screen.calls)

    def test_shot_region_shape_is_validated(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        with self.assertRaises(ValueError):
            DesktopMouseTool(backend, self.config).execute(
                {"action": "click", "x": 5, "y": 6, "shot": True,
                 "shot_region": [1, 2, 3]})

    def test_shot_rejected_for_cursor_query(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        with self.assertRaises(ValueError):
            DesktopMouseTool(backend, self.config).execute(
                {"action": "cursor", "shot": True})


class ClickEvidenceTest(unittest.TestCase):
    """点击回执要能自证：打中了什么、界面动没动。"""

    def setUp(self) -> None:
        self.config = DesktopConfig(settle_ms=0)

    def test_hit_report_is_included(self) -> None:
        hit = Recorder(probe={"hwnd": 99, "class": "Chrome_RenderWidgetHostHWND",
                              "title": "腾讯视频"})
        backend, _screen, _mouse, _keyboard = _backend(hit=hit)
        result = DesktopMouseTool(backend, self.config).execute(
            {"action": "click", "x": 5, "y": 6})
        self.assertEqual(result["hit"]["class"], "Chrome_RenderWidgetHostHWND")
        self.assertIn(("probe", ScreenPoint(5, 6)), hit.calls)

    def test_hit_is_omitted_without_a_hit_port(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        result = DesktopMouseTool(backend, self.config).execute(
            {"action": "click", "x": 5, "y": 6})
        self.assertNotIn("hit", result)

    def test_changed_is_zero_when_nothing_moves(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        result = DesktopMouseTool(backend, self.config).execute(
            {"action": "click", "x": 5, "y": 6})
        self.assertEqual(result["changed"], 0.0)

    def test_changed_is_not_measured_for_move(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        result = DesktopMouseTool(backend, self.config).execute(
            {"action": "move", "x": 5, "y": 6})
        self.assertNotIn("changed", result)
        self.assertNotIn("hit", result)


class DiffTest(unittest.TestCase):
    def test_same_image_has_no_change(self) -> None:
        png = _png(40, 30, (10, 20, 30))
        self.assertEqual(diff.change_ratio(png, png), 0.0)

    def test_different_image_changes(self) -> None:
        before = _png(40, 30, (10, 20, 30))
        after = _png(40, 30, (250, 250, 250))
        self.assertGreater(diff.change_ratio(before, after), 0.9)

    def test_probe_region_follows_the_point_and_clips(self) -> None:
        region = diff.probe_region(ScreenPoint(5, 6), ScreenRect(0, 0, 40, 30))
        self.assertEqual(region, ScreenRect(0, 0, 40, 30))
        inside = diff.probe_region(ScreenPoint(50, 50), ScreenRect(0, 0, 400, 400))
        self.assertEqual(inside, ScreenRect(0, 0, 150, 150))


class _Scripted:
    """按调用顺序返回不同值的替身：等条件需要"先没有、后有了"。"""

    def __init__(self, **functions) -> None:
        self._functions = functions
        self.calls = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name,) + args)
            return self._functions[name](*args, **kwargs)
        return call


class WaitToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = DesktopConfig(settle_ms=0, wait_interval_ms=50)

    def _screen(self, pngs):
        from collections import deque

        queue = deque(pngs)
        geometry = ScreenGeometry(rect=ScreenRect(0, 0, 40, 30))

        def capture(region):
            png = queue.popleft() if len(queue) > 1 else queue[0]
            return Screenshot(png, region or geometry.rect)

        return _Scripted(geometry=lambda: geometry, capture=capture)

    def test_change_satisfies_immediately(self) -> None:
        screen = self._screen([_png(40, 30, (0, 0, 0)), _png(40, 30, (255, 255, 255))])
        backend = Backend("test", screen, Recorder(cursor=ScreenPoint(1, 1)), Recorder())
        result = DesktopWaitTool(backend, self.config).execute(
            {"until": "change", "threshold": 0.1, "timeout_ms": 2000})
        self.assertTrue(result["satisfied"])
        self.assertGreater(result["changed"], 0.9)

    def test_change_times_out_without_raising(self) -> None:
        screen = self._screen([_png(40, 30, (0, 0, 0))])
        backend = Backend("test", screen, Recorder(cursor=ScreenPoint(1, 1)), Recorder())
        result = DesktopWaitTool(backend, self.config).execute(
            {"until": "change", "timeout_ms": 50, "interval_ms": 50})
        self.assertFalse(result["satisfied"])
        self.assertIn("note", result)

    def test_window_appears(self) -> None:
        seen = {"count": 0}

        def find(_title):
            seen["count"] += 1
            return () if seen["count"] == 1 else (_window_info(),)

        windows = _Scripted(find=find)
        backend = Backend("test", Recorder(geometry=ScreenGeometry(
            rect=ScreenRect(0, 0, 40, 30))), Recorder(cursor=ScreenPoint(1, 1)),
            Recorder(), windows=windows)
        result = DesktopWaitTool(backend, self.config).execute(
            {"until": "window_appears", "window": "腾讯视频", "timeout_ms": 2000})
        self.assertTrue(result["satisfied"])
        self.assertEqual(result["window"]["hwnd"], 4242)

    def test_window_disappears_times_out(self) -> None:
        windows = _Scripted(find=lambda _title: (_window_info(),))
        backend = Backend("test", Recorder(geometry=ScreenGeometry(
            rect=ScreenRect(0, 0, 40, 30))), Recorder(cursor=ScreenPoint(1, 1)),
            Recorder(), windows=windows)
        result = DesktopWaitTool(backend, self.config).execute(
            {"until": "window_disappears", "window": "腾讯视频",
             "timeout_ms": 50, "interval_ms": 50})
        self.assertFalse(result["satisfied"])

    def test_window_condition_needs_a_title(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        with self.assertRaises(ValueError):
            DesktopWaitTool(backend, self.config).execute({"until": "window_appears"})

    def test_change_on_a_minimized_window_is_rejected(self) -> None:
        info = WindowInfo(hwnd=7, title="腾讯视频",
                          rect=ScreenRect(-32000, -32000, 160, 28),
                          minimized=True, visible=True)
        windows = _Scripted(get=lambda _hwnd: info, find=lambda _title: (info,))
        backend = Backend("test", Recorder(geometry=ScreenGeometry(
            rect=ScreenRect(0, 0, 40, 30))), Recorder(cursor=ScreenPoint(1, 1)),
            Recorder(), windows=windows)
        with self.assertRaises(ValueError):
            DesktopWaitTool(backend, self.config).execute(
                {"until": "change", "window": "腾讯视频", "timeout_ms": 100})

    def test_bad_parameters(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        tool = DesktopWaitTool(backend, self.config)
        for arguments in ({"until": "eventually"},
                          {"until": "change", "timeout_ms": 10},
                          {"until": "change", "interval_ms": 1},
                          {"until": "change", "threshold": 2},
                          {"until": "change", "threshold": "x"},
                          {"until": "change", "x": 1}):
            with self.assertRaises(ValueError, msg=str(arguments)):
                tool.execute(arguments)

    def test_unknown_argument_rejected(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        with self.assertRaises(ValueError):
            DesktopWaitTool(backend, self.config).execute(
                {"until": "change", "sleep": 1})


class AmbiguityNoteTest(unittest.TestCase):
    """同名窗口：回执必须说清选了谁、还有谁。"""

    def test_matched_windows_are_spelled_out(self) -> None:
        first = _window_info(hwnd=1118188, rect=ScreenRect(189, 38, 1542, 963),
                             foreground=True)
        second = _window_info(hwnd=9376244, rect=ScreenRect(251, 10, 1418, 1020))
        windows = Recorder(
            get=first, find=(first, second),
            capture=Screenshot(_png(40, 30), first.rect, source="window"),
        )
        backend, _screen, _mouse, _keyboard = _backend(windows=windows)
        result = DesktopEyeTool(backend, DesktopConfig(settle_ms=0)).execute(
            {"window": "腾讯视频"})
        self.assertEqual(result.data["window"]["matched"], 2)
        self.assertEqual(result.data["window"]["alternatives"][0]["hwnd"], 9376244)
        note = result.data["note"]
        self.assertIn("2 个", note)
        self.assertIn("前台那个", note)
        self.assertIn("9376244", note)

    def test_single_window_has_no_ambiguity_note(self) -> None:
        info = _window_info(foreground=True)
        windows = Recorder(
            get=info, find=(info,),
            capture=Screenshot(_png(40, 30), info.rect, source="window"),
        )
        backend, _screen, _mouse, _keyboard = _backend(windows=windows)
        result = DesktopEyeTool(backend, DesktopConfig(settle_ms=0)).execute(
            {"window": "腾讯视频"})
        self.assertNotIn("note", result.data)

    def test_hover_on_a_background_window_asks_for_activation(self) -> None:
        info = _window_info(foreground=False)
        windows = Recorder(
            get=info, find=(info,),
            capture=Screenshot(_png(40, 30), info.rect, source="window"),
        )
        backend, _screen, _mouse, _keyboard = _backend(windows=windows)
        result = DesktopEyeTool(
            backend, DesktopConfig(settle_ms=0, hover_settle_ms=0)).execute(
            {"window": "腾讯视频", "hover": [5, 6]})
        self.assertIn("activate=true", result.data["note"])


class ScaleHintTest(unittest.TestCase):
    """缩图必须给出换算示例，避免每次心算比例。"""

    def test_shrunk_image_reports_the_multiplier(self) -> None:
        rect = ScreenRect(0, 0, 400, 300)
        backend, _screen, _mouse, _keyboard = _backend(rect=rect, png=_png(400, 300))
        result = DesktopEyeTool(backend, DesktopConfig(settle_ms=0)).execute(
            {"max_side": 100})
        self.assertIn("× 4", result.data["note"])
        self.assertIn("图上 100,100 对应屏幕 400,400", result.data["note"])
        self.assertEqual(result.data["grid"]["scale"], 4.0)


class IsolationTest(unittest.TestCase):
    def test_input_lock_times_out(self) -> None:
        with input_guard():
            with self.assertRaises(DesktopBusy):
                with input_guard(timeout=0.01):
                    self.fail("应当拿不到第二把锁")

    def test_unavailable_backend_reports(self) -> None:
        backend = unavailable_backend()
        with self.assertRaises(DesktopUnavailable):
            backend.screen.geometry()
        with self.assertRaises(DesktopUnavailable):
            backend.mouse.cursor()
        with self.assertRaises(DesktopUnavailable):
            backend.keyboard.press("enter", 1)


class PluginTest(unittest.TestCase):
    def test_build_tools_honours_switches(self) -> None:
        backend, _screen, _mouse, _keyboard = _backend()
        only_keyboard = _PLUGIN.build_tools(
            DesktopConfig(eye=False, mouse=False, keyboard=True, wait=False), backend)
        self.assertEqual([tool.name for tool in only_keyboard], ["desktop_keyboard"])
        all_tools = _PLUGIN.build_tools(DesktopConfig(), backend)
        self.assertEqual([tool.name for tool in all_tools],
                         ["desktop_eye", "desktop_mouse", "desktop_keyboard",
                          "desktop_wait"])

    def test_register_returns_disposers(self) -> None:
        class Context:
            app = SimpleNamespace(live_state=None)

            def __init__(self) -> None:
                self.tools = []
                self.disposers = []

            def register_tool(self, tool):
                self.tools.append(tool)
                disposer = lambda: None
                self.disposers.append(disposer)
                return disposer

        ctx = Context()
        with mock.patch.object(_PLUGIN, "load_backend",
                               return_value=unavailable_backend()):
            disposers = _PLUGIN.register(ctx)
        self.assertEqual([tool.name for tool in ctx.tools],
                         ["desktop_eye", "desktop_mouse", "desktop_keyboard",
                          "desktop_wait"])
        self.assertEqual(disposers, ctx.disposers)
        self.assertEqual(len(disposers), 4)


def _load_macos_module():
    """用替身 CDLL 加载 macOS 后端：只校验纯表与结构，不加载系统库。"""
    name = "fan_agent_plugins.desktop_io.backends.macos"
    path = _PLUGIN_DIR / "desktop_io" / "backends" / "macos.py"
    with mock.patch("ctypes.CDLL", return_value=mock.MagicMock()):
        spec = importlib.util.spec_from_file_location(name, str(path))
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


@unittest.skipUnless(sys.platform == "win32", "只在 Windows 上校验键码表")
class Win32TableTest(unittest.TestCase):
    def test_key_table_covers_canonical_names(self) -> None:
        from fan_agent_plugins.desktop_io.backends import win32
        missing = [key for key in keys.CANONICAL_KEYS if key not in win32._VK_NAMED]
        self.assertEqual(missing, [])

    def test_utf16_units_and_unknown_key(self) -> None:
        from fan_agent_plugins.desktop_io.backends import win32
        self.assertEqual(win32._utf16_units("a"), (97,))
        self.assertEqual(win32._utf16_units("😀"), (0xD83D, 0xDE00))
        with self.assertRaises(DesktopError):
            win32._virtual_key("hyper")

    def test_scroll_delta_matches_contract(self) -> None:
        from fan_agent_plugins.desktop_io.backends import win32
        mouse = win32.Win32Mouse()
        with mock.patch.object(win32, "_send_mouse") as send:
            mouse.scroll(None, 3, False)
            mouse.scroll(None, 3, True)
        self.assertEqual(send.call_args_list[0].args,
                         (win32.MOUSEEVENTF_WHEEL, (-360) & 0xFFFFFFFF))
        self.assertEqual(send.call_args_list[1].args,
                         (win32.MOUSEEVENTF_HWHEEL, 360))

    def test_uniform_detection_catches_black_frames(self) -> None:
        from fan_agent_plugins.desktop_io.backends import win32
        black = b"\x00\x00\x00\x00" * 64
        self.assertTrue(win32._is_uniform(black))
        varied = black[:4] + b"\x01\x02\x03\x00" + black[8:]
        self.assertFalse(win32._is_uniform(varied))

    def test_crop_bgra_uses_top_down_rows(self) -> None:
        from fan_agent_plugins.desktop_io.backends import win32
        # 3x2，每像素 4 字节，行主序；取右下 2x1 应为第 2 行后两个像素
        pixels = [bytes([row, col, 0, 0]) for row in range(2) for col in range(3)]
        data = b"".join(pixels)
        cropped = win32._crop_bgra(data, 3, 2, 1, 1, 2, 1)
        self.assertEqual(cropped, pixels[4] + pixels[5])

    def test_window_capture_does_not_touch_screen_grab(self) -> None:
        from fan_agent_plugins.desktop_io.backends import win32
        rect = ScreenRect(0, 0, 4, 2)
        with mock.patch.object(win32.user32, "IsWindow", return_value=1), \
                mock.patch.object(win32.user32, "IsIconic", return_value=0), \
                mock.patch.object(win32, "_window_rect", return_value=rect), \
                mock.patch.object(win32, "_print_window",
                                  return_value=b"\x10\x20\x30\x00\x11\x22\x33\x00" * 4), \
                mock.patch.object(win32, "_grab") as grab:
            shot = win32.Win32Windows().capture(1234, None)
        self.assertEqual(shot.source, "window")
        self.assertEqual((shot.rect.width, shot.rect.height), (4, 2))
        grab.assert_not_called()

    def _capture(self, iconic: bool, activate: bool, **patches):
        from fan_agent_plugins.desktop_io.backends import win32
        rect = ScreenRect(0, 0, 4, 2)
        with mock.patch.object(win32.user32, "IsWindow", return_value=1), \
                mock.patch.object(win32.user32, "IsIconic", return_value=int(iconic)), \
                mock.patch.object(win32, "_is_foreground", return_value=False), \
                mock.patch.object(win32, "_window_rect", return_value=rect), \
                mock.patch.object(win32, "_print_window",
                                  return_value=b"\x10\x20\x30\x00\x11\x22\x33\x00" * 4), \
                mock.patch.object(win32, "_restore_without_activation") as restore, \
                mock.patch.object(win32, "_bring_to_front") as front:
            front.return_value = (iconic, True)
            shot = win32.Win32Windows().capture(1234, None, activate=activate)
        return shot, restore, front

    def test_minimized_capture_restores_without_stealing_focus(self) -> None:
        shot, restore, front = self._capture(iconic=True, activate=False)
        restore.assert_called_once_with(1234)
        front.assert_not_called()
        self.assertTrue(shot.restored)
        self.assertEqual(shot.activation, "none")

    def test_activate_uses_foreground_path(self) -> None:
        shot, restore, front = self._capture(iconic=True, activate=True)
        front.assert_called_once_with(1234)
        restore.assert_not_called()
        self.assertTrue(shot.restored)
        self.assertEqual(shot.activation, "ok")

    def test_visible_window_is_left_alone(self) -> None:
        shot, restore, front = self._capture(iconic=False, activate=False)
        restore.assert_not_called()
        front.assert_not_called()
        self.assertFalse(shot.restored)
        self.assertEqual(shot.activation, "none")

    def test_visible_window_activates_only_when_asked(self) -> None:
        shot, restore, front = self._capture(iconic=False, activate=True)
        front.assert_called_once_with(1234)
        restore.assert_not_called()
        self.assertFalse(shot.restored)
        self.assertEqual(shot.activation, "ok")

    def test_find_prefers_foreground_then_z_order(self) -> None:
        """同名窗口：前台优先，其次 Z 序，最后才是面积。

        按面积排序会把盖在画面上的播放层当成主窗：这正是实测会话里
        窗口从 1418x1020 悄悄换成 1542x963 的原因。
        """
        from fan_agent_plugins.desktop_io.backends import win32

        rects = {
            100: ScreenRect(0, 0, 1200, 800),
            200: ScreenRect(0, 0, 1600, 1000),
            300: ScreenRect(0, 0, 800, 600),
        }

        def fake_enum(callback, _data):
            for hwnd in (100, 200, 300):
                callback(hwnd, 0)
            return 1

        with mock.patch.object(win32.user32, "EnumWindows", side_effect=fake_enum), \
                mock.patch.object(win32.user32, "IsWindowVisible", return_value=1), \
                mock.patch.object(win32.user32, "GetWindowLongW", return_value=0), \
                mock.patch.object(win32.user32, "IsIconic", return_value=0), \
                mock.patch.object(win32.user32, "GetForegroundWindow", return_value=300), \
                mock.patch.object(win32, "_window_title", return_value="腾讯视频"), \
                mock.patch.object(win32, "_window_rect",
                                  side_effect=lambda hwnd: rects[hwnd]):
            found = win32.Win32Windows().find("腾讯视频")

        self.assertEqual([info.hwnd for info in found], [300, 100, 200])
        self.assertTrue(found[0].foreground)
        self.assertFalse(found[1].foreground)

    def test_find_without_foreground_falls_back_to_z_order(self) -> None:
        from fan_agent_plugins.desktop_io.backends import win32

        def fake_enum(callback, _data):
            for hwnd in (100, 200):
                callback(hwnd, 0)
            return 1

        with mock.patch.object(win32.user32, "EnumWindows", side_effect=fake_enum), \
                mock.patch.object(win32.user32, "IsWindowVisible", return_value=1), \
                mock.patch.object(win32.user32, "GetWindowLongW", return_value=0), \
                mock.patch.object(win32.user32, "IsIconic", return_value=0), \
                mock.patch.object(win32.user32, "GetForegroundWindow", return_value=0), \
                mock.patch.object(win32, "_window_title", return_value="腾讯视频"), \
                mock.patch.object(win32, "_window_rect",
                                  return_value=ScreenRect(0, 0, 100, 100)):
            found = win32.Win32Windows().find("腾讯视频")

        self.assertEqual([info.hwnd for info in found], [100, 200])

    def test_hit_probe_reports_class_and_root_title(self) -> None:
        from fan_agent_plugins.desktop_io.backends import win32

        with mock.patch.object(win32.user32, "WindowFromPoint", return_value=555), \
                mock.patch.object(win32.user32, "GetAncestor", return_value=777), \
                mock.patch.object(win32, "_window_class",
                                  return_value="Chrome_RenderWidgetHostHWND"), \
                mock.patch.object(win32, "_window_title", return_value="腾讯视频"):
            probe = win32.Win32Hit().probe(ScreenPoint(5, 6))

        self.assertEqual(probe["hwnd"], 555)
        self.assertEqual(probe["root"], 777)
        self.assertEqual(probe["class"], "Chrome_RenderWidgetHostHWND")
        self.assertEqual(probe["title"], "腾讯视频")

    def test_hit_probe_returns_empty_when_nothing_is_there(self) -> None:
        from fan_agent_plugins.desktop_io.backends import win32

        with mock.patch.object(win32.user32, "WindowFromPoint", return_value=0):
            self.assertEqual(win32.Win32Hit().probe(ScreenPoint(5, 6)), {})


class MacOSTableTest(unittest.TestCase):
    """不启动系统库，只校验键码表与结构体拼装。"""

    def test_keycodes_cover_canonical_names(self) -> None:
        module = _load_macos_module()
        missing = [key for key in keys.CANONICAL_KEYS if key not in module._KEYCODES]
        self.assertEqual(missing, [])
        self.assertEqual(module._MODIFIER_FLAGS["cmd"], 1 << 20)

    def test_point_and_unknown_key(self) -> None:
        module = _load_macos_module()
        point = module._point(ScreenPoint(3, 4))
        self.assertEqual((point.x, point.y), (3.0, 4.0))
        with self.assertRaises(DesktopError):
            module._keycode("hyper")

    def test_scroll_delta_matches_contract(self) -> None:
        module = _load_macos_module()
        mouse = module.MacMouse()
        mouse.scroll(None, 3, False)
        module._services.CGEventCreateScrollWheelEvent.assert_called_with(
            None, module.SCROLL_UNIT_LINE, 2, -3, 0)
        mouse.scroll(None, 3, True)
        module._services.CGEventCreateScrollWheelEvent.assert_called_with(
            None, module.SCROLL_UNIT_LINE, 2, 0, 3)


if __name__ == "__main__":
    unittest.main()
