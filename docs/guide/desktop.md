# 桌面入口

根目录的 `agent-gui.exe` 是 Windows 原生启动器，负责找到本机 Python、准备 pywebview、启动 Python 壳；窗口本身由 Python 侧的 pywebview 创建，不包含后端。

```text
agent-gui.exe
  → 查找 python.exe / pythonw.exe
  → python -m agent.gui.bootstrap
  → 确保 WebView2 Runtime
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

默认监听 `127.0.0.1:3156`。固定端口用于保持页面 origin 稳定，`localStorage` 才会跨启动保留；端口被占用时启动失败，不会静默换端口。

`python -m agent.gui.launcher --no-window` 只准备并验证服务，不打开窗口；根目录 `agent-gui.exe` 不解析命令行参数。

## 运行前提

```text
Python 3.10+
系统 WebView2 Runtime
首次运行可联网，用于把 pywebview 安装到用户缓存
```

pywebview 不写入项目目录，位置为：

```text
%LOCALAPPDATA%\ai-agent\pydeps
```

WebView2 缺失时启动器尝试自动安装。macOS / Linux 直接运行 Python 命令，使用对应平台的 WebView。

## 窗口行为

```text
无边框
自绘标题栏
拖动、双击最大化/还原、最大化拖动还原
最小化 / 最大化 / 关闭
四边与四角鼠标缩放
关闭窗口终止 agent-web 子进程
```

自绘标题栏不提供 Windows 边缘分屏；系统边缘分屏只属于原生标题栏。

## 构建启动器

只有修改 `launcher/launcher.cpp` 或图标后才需要重新构建：

```powershell
launcher\build.ps1
```

需要 MSVC Build Tools；产物为根目录 `agent-gui.exe`。不使用 PyInstaller。

## 与源码启动的关系

```text
agent-cli / agent-web / agent-headless  正式命令
agent-gui                               原生启动器 + Python 桌面壳
start.bat / start.sh                    源码 Web 控制台启动
```
