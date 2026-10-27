**English** | [中文](desktop.zh.md)

# Desktop entry

`agent-gui.exe` in the project root is the native Windows launcher. It locates the local Python installation, ensures the WebView2 Runtime, prepares pywebview, and starts the Python shell. The window itself is created by pywebview on the Python side and contains no backend.

```text
agent-gui.exe
  → locate python.exe / pythonw.exe
  → ensure the WebView2 Runtime
  → python -m agent.gui.bootstrap
  → pythonw -m agent.gui.launcher
  → start the agent-web subprocess and open a frameless window
```

## Running

On Windows, double-click:

```text
agent-gui.exe
```

From source:

```bash
python -m agent.gui.launcher
```

The default listener is `127.0.0.1:3156`. The fixed port keeps the page origin stable so that `localStorage` persists across launches. If the port is in use, startup fails; the launcher does not silently switch to another port.

`python -m agent.gui.launcher --no-window` starts and validates the service, then stops it without opening a window. The root `agent-gui.exe` does not parse command-line arguments.

## Prerequisites

```text
Python 3.10+
System WebView2 Runtime
Network access may be required on first run to install pywebview into the user cache
```

pywebview is not written to the project directory; on Windows it is installed at:

```text
%LOCALAPPDATA%\ai-agent\pydeps
```

If WebView2 is missing, the launcher attempts an automatic installation. On macOS and Linux, install pywebview first, then run the Python command directly; the platform WebView is used.

## Window behavior

```text
Frameless
Custom-drawn title bar
Drag to move; double-click to maximize/restore; dragging a maximized window restores it
Minimize / maximize / close
Resize with the mouse from any edge or corner
Closing the window terminates the agent-web subprocess
```

The custom-drawn title bar does not provide Windows edge snapping; system edge snapping belongs to the native title bar.

## Building the launcher

Rebuild only after changing `launcher/launcher.cpp` or the icon:

```powershell
launcher\build.ps1
```

MSVC Build Tools are required. The output is `agent-gui.exe` in the project root. PyInstaller is not used.

## Relationship to source startup

```text
agent-cli / agent-web / agent-headless  Official commands
agent-gui.exe                           Native launcher + Python desktop shell
start.bat / start.sh                    Source Web console startup
```
