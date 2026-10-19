#!/usr/bin/env bash
# AI Agent 启动脚本（Linux / macOS）
set -u

SOURCE="${BASH_SOURCE[0]:-$0}"
ROOT="$(cd "$(dirname "$SOURCE")" && pwd)"
cd "$ROOT"

echo "============================================"
echo "  AI Agent"
echo "============================================"
echo

# ── 1. 找一个可用的 Python 3.10+ ───────────────
PY=""
for cand in python3.13 python3.12 python3.14 python3.11 python3.10 python3.15 python3 python; do
    if ! command -v "$cand" >/dev/null 2>&1; then
        continue
    fi
    if "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "[错误] 没有找到 Python 3.10 或更高版本。"
    echo
    echo "  macOS:"
    echo "    brew install python"
    echo "    或从 https://www.python.org/downloads/ 安装"
    echo
    echo "  Linux:"
    echo "    用发行版的包管理器安装 python3（3.10+）"
    echo
    echo "  安装后重新运行: ./start.sh"
    exit 1
fi

echo "[1/4] Python: $("$PY" --version 2>&1)  ($PY)"

# ── 2. 确保 pip 可用（不要依赖裸 pip 命令）──────
if ! "$PY" -m pip --version >/dev/null 2>&1; then
    echo "[2/4] pip 未就绪，尝试用 Python 自带的 ensurepip 安装..."
    if ! "$PY" -m ensurepip --upgrade; then
        echo
        echo "[错误] 无法安装 pip。请重装 Python 3.10+ 后重试。"
        exit 1
    fi
fi
echo "[2/4] pip: $("$PY" -m pip --version 2>&1 | head -n 1)"

# ── 3. 依赖（缺什么用 python -m pip 装什么）────
if ! "$PY" -c "import openpyxl, PIL" >/dev/null 2>&1; then
    echo "[3/4] 缺少运行依赖，正在安装..."
    if ! "$PY" -m pip install -e . -c constraints.txt; then
        echo
        echo "[错误] 依赖安装失败。请检查网络后手动执行:"
        echo "       $PY -m pip install -e . -c constraints.txt"
        exit 1
    fi
else
    echo "[3/4] 运行依赖已就绪"
fi

# edge-tts 是可选能力：失败只提示，不阻断启动。
if ! "$PY" -c "import edge_tts" >/dev/null 2>&1; then
    echo "[3/4] 安装语音合成依赖（可选）..."
    if ! "$PY" -m pip install -e ".[tts]" -c constraints.txt; then
        echo "[提示] edge-tts 未安装，AI说话会不可用；不影响其它功能。"
    fi
fi

# ── 4. 配置交给浏览器向导，不再用命令行卡住启动 ──
if [ ! -f config.ini ] && [ -f config.ini.example ]; then
    cp config.ini.example config.ini
    echo "[4/4] 已生成 config.ini；首次启动请在浏览器向导里填写模型。"
else
    echo "[4/4] 配置检查交给浏览器向导"
fi
echo

echo "============================================"
echo "  服务地址:  http://127.0.0.1:8765/"
echo "  首次设置:  http://127.0.0.1:8765/setup"
echo "  停止服务:  Ctrl+C"
echo "============================================"
echo

exec "$PY" -m agent.entry.web --host 127.0.0.1 --port 8765 --open
