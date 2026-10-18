#!/usr/bin/env bash
# AI Agent 启动脚本（Linux / macOS）
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "============================================"
echo "  AI Agent"
echo "============================================"
echo

# ── 1. 检查 Python ──────────────────────────────
PY=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
    echo "[错误] 未找到 python3 命令。"
    echo "       请安装 Python 3.10 或更高版本: https://www.python.org/downloads/"
    echo
    exit 1
fi
echo "[1/3] $($PY --version 2>&1)"

# ── 2. 检查依赖 ────────────────────────────────
if $PY -c "import openpyxl, PIL" >/dev/null 2>&1; then
    echo "[2/3] 依赖已就绪"
else
    echo "[2/3] 缺少依赖，正在安装..."
    if ! $PY -m pip install -e .; then
        echo
        echo "[错误] 依赖安装失败。请检查网络后重试:"
        echo "       $PY -m pip install -e ."
        echo
        exit 1
    fi
fi

# ── 3. 检查配置文件 ────────────────────────────
if [ ! -f config.ini ]; then
    [ -f config.ini.example ] && cp config.ini.example config.ini
    echo
    echo "============================================"
    echo "  需要填写模型 API Key"
    echo "============================================"
    echo
    echo "  已生成配置文件: $ROOT/config.ini"
    echo
    echo "  请填写:"
    echo
    echo "      [model_reasoning]"
    echo "      api_key = 你的 API Key"
    echo
    exit 1
fi

if ! $PY -c "import sys;sys.path.insert(0,'.');from agent.config import get_model_reasoning as g;sys.exit(0 if g().get('api_key') else 1)" >/dev/null 2>&1; then
    echo
    echo "============================================"
    echo "  模型 API Key 未填写"
    echo "============================================"
    echo
    echo "  配置文件: $ROOT/config.ini"
    echo
    echo "  请填写:"
    echo
    echo "      [model_reasoning]"
    echo "      api_key = 你的 API Key"
    echo
    exit 1
fi

echo "[3/3] 配置已就绪"
echo
echo "============================================"
echo "  服务地址:  http://127.0.0.1:8765/"
echo "  停止服务:  Ctrl+C"
echo "============================================"
echo

exec $PY -m agent.entry.web --host 127.0.0.1 --port 8765
