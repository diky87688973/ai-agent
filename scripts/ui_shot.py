# -*- coding: utf-8 -*-
"""界面自测：开无头 Chrome → 打开指定会话 → 报告关键样式 → 截图。

用法::

    python scripts/ui_shot.py <conversation_id|-> <输出.png> [--theme dark|light] [--wait 6000]

`-` 表示不打开会话，只看空页面（顶栏与输入区）。
需要本机装了 Chrome；只用标准库（CDP 走 WebSocket）。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)

STYLE_PROBE = """(function(){
  function cs(sel, props){ var el=document.querySelector(sel); if(!el) return null;
    var s=getComputedStyle(el), o={}; props.forEach(function(p){ o[p]=s.getPropertyValue(p); }); return o; }
  var P=['background-color','color','font-family','font-size','line-height'];
  return JSON.stringify({
    theme: document.documentElement.getAttribute('data-ui-theme'),
    body: cs('body', P),
    answer: cs('.b.a', P),
    code: cs('.b.a code', P),
    card: cs('.card', P),
    tag: cs('.tag', P)
  });
})()"""


def find_chrome() -> str:
    for p in CHROME_CANDIDATES:
        if Path(p).exists():
            return p
    raise SystemExit("没找到 Chrome / Edge")


class Ws:
    """极简 WebSocket 客户端：只发文本帧、收文本帧。"""

    def __init__(self, url: str) -> None:
        from urllib.parse import urlparse

        u = urlparse(url)
        self.sock = socket.create_connection((u.hostname or "127.0.0.1", u.port or 80), timeout=20)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self._buf = buf.split(b"\r\n\r\n", 1)[1]
        self._id = 0
        self._handlers = []

    def send(self, obj: dict) -> None:
        payload = json.dumps(obj).encode()
        mask = os.urandom(4)
        n = len(payload)
        if n < 126:
            header = bytes([0x81, 0x80 | n])
        elif n < 65536:
            header = bytes([0x81, 0xFE]) + struct.pack(">H", n)
        else:
            header = bytes([0x81, 0xFF]) + struct.pack(">Q", n)
        masked = bytes(payload[i] ^ mask[i % 4] for i in range(n))
        self.sock.sendall(header + mask + masked)

    def _pump(self) -> None:
        self._buf += self.sock.recv(65536)
        while len(self._buf) >= 2:
            b1 = self._buf[1]
            n = b1 & 0x7F
            off = 2
            if n == 126:
                if len(self._buf) < 4:
                    return
                n = struct.unpack(">H", self._buf[2:4])[0]
                off = 4
            elif n == 127:
                if len(self._buf) < 10:
                    return
                n = struct.unpack(">Q", self._buf[2:10])[0]
                off = 10
            if len(self._buf) < off + n:
                return
            raw = self._buf[off:off + n]
            self._buf = self._buf[off + n:]
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError as exc:
                print(f"[scripts.ui_shot.Ws._pump] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                continue
            for fn in list(self._handlers):
                fn(msg)

    def call(self, method: str, params: dict | None = None, timeout: float = 25.0) -> dict:
        self._id += 1
        my = self._id
        box: dict = {}

        def _on(msg: dict) -> None:
            if msg.get("id") == my:
                box.update(msg)

        self._handlers.append(_on)
        self.send({"id": my, "method": method, "params": params or {}})
        deadline = time.time() + timeout
        while not box and time.time() < deadline:
            self._pump()
        return box

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError as exc:
            print(f"[scripts.ui_shot.Ws.close] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ui_shot.py", description="界面自测截图")
    ap.add_argument("conversation_id", help="会话 id；`-` 表示不打开会话")
    ap.add_argument("out", help="输出 PNG 路径")
    ap.add_argument("--url", default="http://127.0.0.1:8765/", help="页面地址")
    ap.add_argument("--theme", default="", choices=("", "dark", "light"), help="先切主题再截")
    ap.add_argument("--wait", type=int, default=6000, help="打开会话后等待毫秒数")
    ap.add_argument("--scale", type=float, default=2.0, help="设备像素比；1 = 1:1 不放大")
    ap.add_argument("--clip", default="", help="只截一块：x,y,w,h（CSS 像素）")
    args = ap.parse_args(list(argv) if argv is not None else None)

    port = 9400 + (int.from_bytes(os.urandom(2), "big") % 200)
    profile = Path(tempfile.mkdtemp(prefix="uishot_"))
    chrome = subprocess.Popen(
        [find_chrome(), "--headless=new", "--disable-gpu", "--no-first-run",
         f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--window-size=1500,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ver = None
        for _ in range(80):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as r:
                    ver = json.loads(r.read().decode())
                break
            except Exception as exc:
                print(f"[scripts.ui_shot.main] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                time.sleep(0.3)
        if not ver:
            print("DevTools 未就绪", file=sys.stderr)
            return 1
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
            tabs = json.loads(r.read().decode())
        page = next(t for t in tabs if t.get("type") == "page")
        ws = Ws(page["webSocketDebuggerUrl"])
        ws.call("Page.enable")
        ws.call("Runtime.enable")
        ws.call("Emulation.setDeviceMetricsOverride",
                {"width": 1500, "height": 1000, "deviceScaleFactor": args.scale,
                 "mobile": False})
        ws.call("Page.navigate", {"url": args.url})
        time.sleep(5)
        if args.theme:
            ws.call("Runtime.evaluate", {
                "expression": f"try{{localStorage.setItem('aiAgent.uiTheme',{json.dumps(args.theme)})}}catch(e){{}}"
                              ";location.reload()"})
            time.sleep(4.5)
        if args.conversation_id and args.conversation_id != "-":
            ws.call("Runtime.evaluate", {
                "expression": f"openConversationFromMenu({json.dumps(args.conversation_id)},\"ui-shot\")"})
            time.sleep(max(0, args.wait) / 1000.0)
        res = ws.call("Runtime.evaluate", {"expression": STYLE_PROBE, "returnByValue": True})
        value = (((res.get("result") or {}).get("result") or {}).get("value"))
        if value:
            print("STYLE = " + value)
        params: dict = {"format": "png"}
        if args.clip:
            x, y, w, h = (float(v) for v in args.clip.split(","))
            params["clip"] = {"x": x, "y": y, "width": w, "height": h, "scale": 1}
            params["captureBeyondViewport"] = True
        shot = ws.call("Page.captureScreenshot", params)
        data = ((shot.get("result") or {}).get("data"))
        if not data:
            print("截图失败: " + json.dumps(shot)[:200], file=sys.stderr)
            return 1
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(data))
        digest = hashlib.sha256(out.read_bytes()).hexdigest()[:12]
        print(f"SHOT = {out}  {out.stat().st_size} 字节  sha256:{digest}")
        ws.close()
        return 0
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=5)
        except subprocess.TimeoutExpired:
            chrome.kill()


if __name__ == "__main__":
    raise SystemExit(main())
