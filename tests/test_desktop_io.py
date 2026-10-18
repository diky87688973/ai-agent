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

from fan_agent_plugins.desktop_io import canvas, keys  # noqa: E402
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
from fan_agent_plugins.desktop_io.ports import Backend, Screenshot  # noqa: E402
from fan_agent_plugins.desktop_io.tools import (  # noqa: E402
    DesktopEyeTool,
    DesktopKeyboardTool,
    DesktopMouseTool,
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
        def call(*args):
            self.calls.append((name,) + args)
            return self._returns.get(name)
        return call


class LiveState:
    def __init__(self, mode: str = "plan") -> None:
        self.mode = mode

    def get_mode(self, _cid: str) -> str:
        return self.mode


def _backend(rect: ScreenRect | None = None, png: bytes | None = None,
             cursor: ScreenPoint | None = None, mixed_scale: bool = False):
    rect = rect or ScreenRect(0, 0, 40, 30)
    screen = Recorder(geometry=ScreenGeometry(rect=rect, mixed_scale=mixed_scale),
                      capture=Screenshot(png or _png(rect.width, rect.height), rect))
    mouse = Recorder(cursor=cursor or ScreenPoint(7, 8))
    keyboard = Recorder()
    return Backend("test", screen, mouse, keyboard), screen, mouse, keyboard


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
            DesktopConfig(eye=False, mouse=False, keyboard=True), backend)
        self.assertEqual([tool.name for tool in only_keyboard], ["desktop_keyboard"])
        all_tools = _PLUGIN.build_tools(DesktopConfig(), backend)
        self.assertEqual([tool.name for tool in all_tools],
                         ["desktop_eye", "desktop_mouse", "desktop_keyboard"])

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
                         ["desktop_eye", "desktop_mouse", "desktop_keyboard"])
        self.assertEqual(disposers, ctx.disposers)
        self.assertEqual(len(disposers), 3)


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
