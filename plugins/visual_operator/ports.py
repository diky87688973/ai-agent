# -*- coding: utf-8 -*-
"""桌面后端的三条端口与数据结构。

工具只依赖这些协议；平台实现放在 `backends/` 下，按平台选择。
坐标一律是工具契约里的屏幕坐标（Windows 物理像素，macOS 显示点），
后端直接以该坐标系投递输入。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Sequence

from .coords import ScreenGeometry, ScreenPoint, ScreenRect
from .locate import LocatorPort


@dataclass(frozen=True)
class Screenshot:
    """一张原始截图：PNG 字节与它覆盖的屏幕矩形。

    `source` 标明这张图是怎么来的：
      - `screen`：屏幕合成结果（GDI/DXGI 一类），可能含遮挡物；
      - `window`：目标窗口自身重绘（PrintWindow），遮挡不影响内容。
    调用侧据此判断「看到的是不是目标窗口」。

    `restored` 表示取图前窗口原本最小化、已被恢复；`activation` 记录置前的结果：
      - `none`：没请求置前（默认），恢复窗口但不动前台；
      - `ok`：请求置前且成功；
      - `failed`：请求置前但没抢到，`foreground` 为假。
    `foreground` 是取图那一刻目标是否真的在前台。
    """

    png: bytes
    rect: ScreenRect
    source: str = "screen"
    restored: bool = False
    foreground: bool = False
    activation: str = "none"


@dataclass(frozen=True)
class WindowInfo:
    """一个顶层窗口：句柄、标题、屏幕矩形与状态。

    `foreground` 只在「按标题找窗口」时才有意义：同名窗口不止一个时，
    调用侧要能说清选中的这个是不是用户眼前那个。
    """

    hwnd: int
    title: str
    rect: ScreenRect
    minimized: bool
    visible: bool
    foreground: bool = False

    def to_dict(self) -> dict:
        return {
            "hwnd": self.hwnd,
            "title": self.title,
            "rect": self.rect.to_dict(),
            "minimized": self.minimized,
            "visible": self.visible,
            "foreground": self.foreground,
        }


@dataclass(frozen=True)
class WindowActivation:
    """一次激活尝试的结果。

    抢不到前台不算失败：`active` 如实写结果，`foreground` 写实际拿了前台的窗口，
    调用侧据此决定是继续还是换路径；句柄失效才报错。
    """

    window: WindowInfo
    active: bool
    restored: bool = False
    foreground: str = ""

    def to_dict(self) -> dict:
        data = {
            "hwnd": self.window.hwnd,
            "title": self.window.title,
            "rect": self.window.rect.to_dict(),
            "active": self.active,
            "restored": self.restored,
        }
        if self.foreground:
            data["foreground"] = self.foreground
        return data


@dataclass(frozen=True)
class FocusInfo:
    """当前拥有键盘焦点的控件/窗口。"""

    hwnd: int
    title: str
    class_name: str
    rect: ScreenRect

    def to_dict(self) -> dict:
        return {"hwnd": self.hwnd, "title": self.title,
                "class": self.class_name, "rect": self.rect.to_dict()}


class FocusPort(Protocol):
    """返回当前键盘焦点。没有该能力的平台不提供此端口。"""

    def focused(self) -> FocusInfo:
        ...


class ScreenPort(Protocol):
    """截屏与屏幕几何。"""

    def geometry(self) -> ScreenGeometry:
        """当前虚拟桌面的矩形与比例。"""
        ...

    def capture(self, region: Optional[ScreenRect]) -> Screenshot:
        """截取区域；`region` 为 None 时截取整屏。"""
        ...


class WindowPort(Protocol):
    """按窗口取图：先找窗口，再取它自己的内容，不依赖它是否在前台。

    可选能力：`list_visible()` 返回当前可见顶层窗口。提供了它，鼠标动作才能
    在前后对比窗口层（`window_changed.opened` / `closed`）；没有则只对比落点窗口。
    """

    def get(self, hwnd: int) -> WindowInfo:
        """按句柄取窗口信息；句柄失效时报错。"""
        ...

    def find(self, title_contains: str) -> Sequence[WindowInfo]:
        """标题包含 `title_contains` 的可见顶层窗口。

        同名窗口不止一个时按「前台 → Z 序 → 面积」排序，第 0 个就是调用侧
        默认要操作的那个；其余候选只用于回执说明。
        """
        ...

    def activate(self, hwnd: int) -> WindowActivation:
        """把窗口带到前台，等价于人点任务栏：最小化先恢复，再抢前台。

        抢不到前台时返回 `active=False`，不抛错；句柄失效才抛错。
        """
        ...

    def capture(self, hwnd: int, region: Optional[ScreenRect],
                *, activate: bool = False,
                prepare: Optional[Callable[[], None]] = None) -> Screenshot:
        """取窗口内容；`region` 是屏幕坐标，超出窗口的部分会被裁掉。

        `activate=False`（默认）只恢复不置前：最小化的窗口会被恢复并重绘，
        但当前前台窗口保持不变；`activate=True` 则恢复并置前，等价于点任务栏。
        `prepare` 在窗口已恢复/置前、真正取图之前调用：悬停取图靠它保证
        「控件已经能看见」和「截图发生在悬停之后」同时成立。
        """
        ...


class MousePort(Protocol):
    """鼠标动作；坐标是屏幕像素。"""

    def cursor(self) -> ScreenPoint:
        ...

    def move(self, point: ScreenPoint, duration_ms: int) -> None:
        ...

    def click(self, point: Optional[ScreenPoint], button: str, count: int) -> None:
        ...

    def drag(self, start: ScreenPoint, end: ScreenPoint, button: str,
             duration_ms: int) -> None:
        ...

    def scroll(self, point: Optional[ScreenPoint], amount: int, horizontal: bool) -> None:
        ...


class KeyboardPort(Protocol):
    """键盘动作；键名是 `keys.py` 的规范名。"""

    def type_text(self, text: str, interval_ms: int) -> None:
        ...

    def press(self, key: str, repeat: int) -> None:
        ...

    def hotkey(self, keys: Sequence[str], repeat: int) -> None:
        ...


class HitPort(Protocol):
    """落点探测：这个屏幕坐标下面是哪个窗口 / 哪类控件。

    只做「谁在这一层」，不做语义识别：拿不到时返回空字典，
    调用侧据此省略 `hit`，而不是把"没探测到"写成"点在空白处"。
    """

    def probe(self, point: ScreenPoint) -> dict:
        """坐标下的窗口句柄、类名与所属顶层窗口标题。"""
        ...


@dataclass(frozen=True)
class Backend:
    """一套可用的后端；平台不支持时换成三个只会报错的端口。

    `windows` 可以为 None：只支持整屏截图的平台不提供按窗口取图。
    `hit` 可以为 None：不提供落点探测的平台不返回 `hit`。
    """

    platform: str
    screen: ScreenPort
    mouse: MousePort
    keyboard: KeyboardPort
    windows: Optional[WindowPort] = None
    hit: Optional[HitPort] = None
    locator: Optional[LocatorPort] = None
    focus: Optional[FocusPort] = None
