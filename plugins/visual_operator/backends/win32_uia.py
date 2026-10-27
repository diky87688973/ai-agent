# -*- coding: utf-8 -*-
"""Windows UIA 文本定位：通过系统 PowerShell 的 UIAutomationClient 查询控件树。

只做定位；不点击、不输入、不截图。点击与输入仍由鼠标、键盘工具执行。
查询通过 `-Command -` 从 stdin 送入，查询参数用 base64 编码，避免命令行拼接。
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
from typing import Any, Dict, List, Optional, Sequence

from ..coords import ScreenPoint, ScreenRect
from ..errors import DesktopError, DesktopUnavailable
from ..locate import LocatorMatch

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$raw = $env:DSH_UIA_QUERY
$q = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($raw.Trim())) | ConvertFrom-Json
$root = if ($q.hwnd) {
    [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$q.hwnd)
} else {
    [System.Windows.Automation.AutomationElement]::RootElement
}
if ($null -eq $root) { throw 'UIA root unavailable' }
$scope = [System.Windows.Automation.TreeScope]::Descendants
if ($q.match -eq 'exact') {
    $cond = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::NameProperty, [string]$q.text)
} else {
    $cond = [System.Windows.Automation.Condition]::TrueCondition
}
$all = $root.FindAll($scope, $cond)
$needle = ([string]$q.text).ToLowerInvariant()
$rows = @()
for ($i = 0; $i -lt $all.Count -and $rows.Count -lt [int]$q.limit; $i++) {
    $el = $all.Item($i)
    if ($null -eq $el) { continue }
    $name = [string]$el.Current.Name
    $match = $false
    if ($q.match -eq 'exact') { $match = $true }
    elseif ($q.match -eq 'regex') {
        try { $match = [regex]::IsMatch($name, [string]$q.text) } catch { $match = $false }
    } else { $match = $name.ToLowerInvariant().Contains($needle) }
    if (-not $match) { continue }
    $r = $el.Current.BoundingRectangle
    if ($r.IsEmpty) { continue }
    $point = $null
    try { $point = $el.GetClickablePoint() } catch { $point = $null }
    $rows += [ordered]@{
        name = $name
        control_type = [string]$el.Current.ControlType.ProgrammaticName
        rect = [ordered]@{ x = [double]$r.X; y = [double]$r.Y;
                           width = [double]$r.Width; height = [double]$r.Height }
        clickable = if ($point) { [ordered]@{ x = [double]$point.X; y = [double]$point.Y } } else { $null }
    }
}
ConvertTo-Json -InputObject @($rows) -Compress -Depth 6
"""

_FIND_LIMIT = 50


class WindowsUiaLocator:
    """Windows UIA 定位端口。"""

    def __init__(self, executable: str = "powershell.exe", timeout_ms: int = 10000) -> None:
        self._executable = executable
        self._timeout_ms = int(timeout_ms)

    def find(self, hwnd: Optional[int], text: str, match: str,
             limit: int) -> Sequence[LocatorMatch]:
        if not text.strip():
            raise ValueError("text 不能为空")
        if match not in ("contains", "exact", "regex"):
            raise ValueError("match 只接受 contains / exact / regex")
        limit = max(1, min(_FIND_LIMIT, int(limit)))
        query = json.dumps({
            "hwnd": int(hwnd) if hwnd else None,
            "text": text,
            "match": match,
            "limit": limit,
        }, ensure_ascii=False).encode("utf-8")
        encoded = base64.b64encode(query).decode("ascii")
        env = os.environ.copy()
        env["DSH_UIA_QUERY"] = encoded
        try:
            completed = subprocess.run(
                [self._executable, "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-Command", _SCRIPT],
                text=True, encoding="utf-8", errors="replace",
                capture_output=True, env=env,
                timeout=self._timeout_ms / 1000.0,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError as exc:
            raise DesktopUnavailable("找不到 PowerShell，UIA 定位不可用") from exc
        except subprocess.TimeoutExpired as exc:
            raise DesktopUnavailable("UIA 定位超时") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise DesktopError(f"UIA 查询失败：{detail[-300:] or 'PowerShell 返回非零'}")
        rows = self._parse(completed.stdout)
        return [self._match(row) for row in rows]

    @staticmethod
    def _parse(output: str) -> List[Dict[str, Any]]:
        lines = [line.strip() for line in str(output or "").splitlines() if line.strip()]
        if not lines:
            raise DesktopError("UIA 查询没有返回结果")
        try:
            value = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise DesktopError("UIA 查询返回的不是 JSON") from exc
        if isinstance(value, dict):
            value = [value]
        if not isinstance(value, list):
            raise DesktopError("UIA 查询返回格式不对")
        return [row for row in value if isinstance(row, dict)]

    @staticmethod
    def _match(row: Dict[str, Any]) -> LocatorMatch:
        rect = row.get("rect") or {}
        try:
            square = ScreenRect(int(round(float(rect["x"]))),
                                int(round(float(rect["y"]))),
                                max(1, int(round(float(rect["width"])))),
                                max(1, int(round(float(rect["height"])))))
        except (KeyError, TypeError, ValueError) as exc:
            raise DesktopError("UIA 返回的控件矩形无效") from exc
        point = row.get("clickable") or {}
        clickable = None
        try:
            if point:
                clickable = ScreenPoint(int(round(float(point["x"]))),
                                        int(round(float(point["y"]))))
        except (KeyError, TypeError, ValueError):
            clickable = None
        return LocatorMatch(
            name=str(row.get("name") or ""),
            control_type=str(row.get("control_type") or ""),
            rect=square,
            clickable=clickable,
        )
