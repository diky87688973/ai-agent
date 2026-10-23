$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
if (!(Test-Path $vswhere)) { throw "vswhere.exe not found" }
$vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$vs) { throw "MSVC build tools not found" }
$vcvars = Join-Path $vs "VC\Auxiliary\Build\vcvars64.bat"
$launcher = Join-Path $PSScriptRoot "launcher.cpp"
$resource = Join-Path $PSScriptRoot "launcher.rc"
$out = Join-Path $root "agent-gui.exe"
$quotedVc = '"' + $vcvars + '"'
$cmd = "$quotedVc && cd /d `"$PSScriptRoot`" && rc /nologo /fo launcher.res launcher.rc && " +
       "cl /nologo /O2 /MT /std:c++17 /EHsc /DUNICODE /D_UNICODE /utf-8 launcher.cpp launcher.res " +
       "/link /SUBSYSTEM:WINDOWS /OUT:`"$out`" user32.lib shell32.lib urlmon.lib ole32.lib wintrust.lib"
cmd /c $cmd
if ($LASTEXITCODE -ne 0) { throw "build failed: $LASTEXITCODE" }
Get-Item $out | Select-Object FullName, Length
