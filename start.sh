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
# 多模型插件可以独立提供模型与凭据；有它就不强制内核 config.ini 的密钥。
if [ -f "plugins/multi_model/plugin-config.ini" ]; then
    echo "[3/3] 插件模型配置已就绪"
else
    if [ ! -f config.ini ]; then
        [ -f config.ini.example ] && cp config.ini.example config.ini
        echo
        echo "============================================"
        echo "  需要填写模型 API Key"
        echo "============================================"
        echo
        echo "  已生成配置文件: $ROOT/config.ini"
        echo
        echo "  请填写 [model_reasoning] 下的 api_base_url / api_key。"
        echo
        if command -v open >/dev/null 2>&1; then
            open -e "$ROOT/config.ini" >/dev/null 2>&1 || true
        fi
        exit 1
    fi

    if ! "$PY" - "$ROOT/config.ini" <<'PY'
import sys

from agent.config import get_model_reasoning

try:
    config = get_model_reasoning(sys.argv[1])
except Exception as exc:
    print(f"[错误] 无法读取配置: {type(exc).__name__}: {exc}", file=sys.stderr)
    raise SystemExit(2)
missing = [name for name in ("api_base_url", "api_key")
           if not config.get(name) or config.get(name) == "sk-请替换"]
if missing:
    print("[错误] [model_reasoning] 缺少或仍是占位值: " + ", ".join(missing),
          file=sys.stderr)
    raise SystemExit(1)
PY
    then
        echo
        echo "============================================"
        echo "  模型配置未就绪"
        echo "============================================"
        echo
        echo "  配置文件: $ROOT/config.ini"
        echo
        echo "  确认改的是这个文件，并且 [model_reasoning] 下 api_base_url、"
        echo "  api_key 都有值；已填写仍失败时看上一行的具体错误。"
        echo
        if command -v open >/dev/null 2>&1; then
            open -e "$ROOT/config.ini" >/dev/null 2>&1 || true
        fi
        exit 1
    fi

    echo "[3/3] 配置已就绪"
fi
echo
echo "============================================"
echo "  服务地址:  http://127.0.0.1:8765/"
echo "  停止服务:  Ctrl+C"
echo "============================================"
echo

exec $PY -m agent.entry.web --host 127.0.0.1 --port 8765
