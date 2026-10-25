# -*- coding: utf-8 -*-
"""开发者工具：导出某个会话的真实请求上下文；不注册为模型工具。"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402
from agent.config import default_data_root  # noqa: E402
from agent.mechanisms.session_store import SessionStore  # noqa: E402
from agent.shell.context_dump import build_snapshot, render_text  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dump_context.py",
        description="导出某个会话的真实请求上下文（只读，不调用模型）",
    )
    parser.add_argument("--cid", required=True, help="会话 ID")
    parser.add_argument("--out", default="-", help="输出文件；默认 stdout")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--include-tools", action="store_true", help="JSON 中带完整工具 schema")
    parser.add_argument("--data-root", default="", help="数据根；默认使用工程配置")
    parser.add_argument("--plugins-dir", default="", help="插件根；默认使用工程配置")
    parser.add_argument("--plugins-path", default="", help="插件清单；默认使用工程配置")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.data_root:
        os.environ["AI_AGENT_DATA_ROOT"] = str(Path(args.data_root).resolve())
    data_root = Path(args.data_root).resolve() if args.data_root else default_data_root()
    app = build_app(
        store=SessionStore(data_root),
        plugins_dir=Path(args.plugins_dir).resolve() if args.plugins_dir else None,
        plugins_path=Path(args.plugins_path).resolve() if args.plugins_path else None,
    )
    try:
        snapshot = build_snapshot(app, args.cid, include_tools=args.include_tools)
        text = (json.dumps(snapshot, ensure_ascii=False, indent=2)
                if args.format == "json" else render_text(snapshot))
        if args.out == "-":
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8")
            print(text, end="")
        else:
            Path(args.out).write_text(text, encoding="utf-8")
    except Exception as exc:
        print(f"dump_context: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        app.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
