[English](desktop.md) | **中文**

# 桌面入口

根目录的 `agent-gui.exe` 是 Windows 原生启动器，负责定位本机 Python、确保 WebView2 Runtime、准备 pywebview、启动 Python 壳；窗口本身由 Python 侧的 pywebview 创建，不包含后端。

```text
agent-gui.exe
  → 查找 python.exe / pythonw.exe
  → 确保 WebView2 Runtime
  → python -m agent.gui.bootstrap
  → pythonw -m agent.gui.launcher
  → 启动 agent-web 子进程，打开无边框窗口
```

## 运行

Windows 直接双击：

```text
agent-gui.exe
```

源码方式：

```bash
python -m agent.gui.launcher
```

默认监听 `127.0.0.1:3156`。固定端口用于保持页面 origin 稳定，`localStorage` 才能跨启动保留；若端口被旧 AI Agent 进程占用，启动器会强制结束旧进程并重启服务；其他程序占用端口时仍启动失败，不会静默改用其他端口。

`python -m agent.gui.launcher --no-window` 启动并验证服务后立即停止，不打开窗口；根目录 `agent-gui.exe` 不解析命令行参数。

## 运行前提

```text
Python 3.10+
系统 WebView2 Runtime
首次运行可能需要联网，用于把 pywebview 安装到用户缓存
```

pywebview 不写入项目目录，在 Windows 上的位置为：

```text
%LOCALAPPDATA%\ai-agent\pydeps
```

WebView2 缺失时启动器尝试自动安装。macOS / Linux 需先安装 pywebview，再直接运行 Python 命令，使用对应平台的 WebView。

## 窗口行为

```text
无边框
自绘标题栏
拖动、双击最大化/还原、最大化拖动还原
Windows 拖到屏幕顶边松手最大化
最小化 / 最大化 / 关闭
四边与四角鼠标缩放
关闭窗口终止 agent-web 子进程
```

Windows 窗口保留原生最小化能力，任务栏图标支持激活与最小化。GUI 宿主在窗口显示及页面加载时补齐 `WS_MINIMIZEBOX` 和 `WS_SYSMENU`，不添加系统标题栏或缩放边框，也不模拟任务栏点击。

Windows 标题栏拖动到鼠标所在屏幕工作区顶边 8 个原生像素内松手时最大化；顶部任务栏区域也可触发。最终移动完成后才执行最大化，并保留双击还原与最大化拖动还原。屏幕查询或移动失败时不触发贴顶最大化，错误留痕。此行为通过桌面窗口桥接提供，不增加系统边框；左右边缘分屏未提供。macOS / Linux 不启用贴顶判断。

## 构建启动器

只有修改 `launcher/launcher.cpp` 或图标后才需要重新构建：

```powershell
launcher\build.ps1
```

需要 MSVC Build Tools；产物为根目录 `agent-gui.exe`。不使用 PyInstaller。

## 与源码启动的关系

```text
agent-cli / agent-web / agent-headless  正式命令
agent-gui.exe                           原生启动器 + Python 桌面壳
start.bat / start.sh                    源码 Web 界面启动
```
