# -*- coding: utf-8 -*-
"""步卡标题里的版本时刻：`file_undo` 卡片显示"文件 to HH:MM:SS"。

`mod_id` 的形状是 `<路径哈希>:YYYYMMDD_HHMMSS_mmm_序号_随机`
（见 `file_safety._version_dir_name`）。前端从这个串里取 `HHMMSS` 换成可读时刻。

**不能靠数段数取** —— 名字里增删一段（例如为了同毫秒定序而加序号）就会取错位置，
卡片上显示的会变成序号（`to 0000`）而不是时刻。这里把形状钉死：
前端正则与后端生成的目录名必须对得上。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.mechanisms.file_safety import _version_dir_name  # noqa: E402
from agent.shell.ui_bundle import read_ui_js  # noqa: E402

#: 前端取时刻用的正则（与主脚本 `const mv=/…/` 保持一致）
_FRONT_RE = re.compile(r"_(\d{6})_\d{3}_\d{4}_[0-9a-z]+$")


def _extract_ts(mid: str) -> str:
    m = _FRONT_RE.search(mid)
    if not m:
        return ""
    t = m.group(1)
    return f"{t[:2]}:{t[2:4]}:{t[4:6]}"


class VersionStampTest(unittest.TestCase):
    def test_frontend_regex_matches_backend_directory_names(self) -> None:
        """后端现造的版本目录名必须被前端正则命中，且取到的是**时间**那一段。"""
        for _ in range(5):
            name = _version_dir_name()
            mid = f"a1b2c3d4e5f60718:{name}"
            ts = _extract_ts(mid)
            with self.subTest(name=name):
                self.assertRegex(ts, r"^\d{2}:\d{2}:\d{2}$")
                # 目录名第二段就是 HHMMSS，必须与取出来的一致
                hhmmss = name.split("_")[1]
                self.assertEqual(ts, f"{hhmmss[:2]}:{hhmmss[2:4]}:{hhmmss[4:6]}")

    def test_frontend_has_two_unescaped_stamp_regexes(self) -> None:
        """前端两处取时刻（建标题 / 补文件段）正则同形，且不得写成 `\\\\d`。"""
        src = read_ui_js()
        self.assertNotIn("slice(-2,-1)", src, msg="仍有按段数取时间戳的旧写法")
        found = 0
        for i, line in enumerate(src.splitlines(), 1):
            if "mv=/" not in line:
                continue
            found += 1
            with self.subTest(line=i):
                seg = line[line.index("mv=/"):line.index("mv=/") + 60]
                chars = list(seg)
                for k, ch in enumerate(chars):
                    if ch == "\\" and k + 1 < len(chars) and chars[k + 1] == "\\":
                        self.fail(f"第 {i} 行正则被多转义了一层：{seg}")
                self.assertIn(r"_(\d{6})_\d{3}_\d{4}_[0-9a-z]+$", seg)
        self.assertEqual(found, 2, msg=f"取版本时刻的地方应有两处，实测 {found} 处")

    def test_node_agrees_with_python(self) -> None:
        """把 JS 那段真跑一遍，结果与 Python 侧一致（防止只改了注释没改代码）。"""
        node = shutil.which("node")
        if node is None:
            self.skipTest("node 不在 PATH 上")
        names = [_version_dir_name() for _ in range(3)]
        mids = [f"hash{i}:{n}" for i, n in enumerate(names)]
        script = f"""
const mids = {json.dumps(mids)};
const out = mids.map(mid => {{
  let ts = "";
  const mv = /_(\\d{{6}})_\\d{{3}}_\\d{{4}}_[0-9a-z]+$/.exec(mid);
  if (mv) ts = mv[1].slice(0,2) + ":" + mv[1].slice(2,4) + ":" + mv[1].slice(4,6);
  return ts;
}});
process.stdout.write(JSON.stringify(out));
"""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "probe.js"
            p.write_text(script, encoding="utf-8")
            r = subprocess.run([node, str(p)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, msg=r.stderr[:300])
        self.assertEqual(json.loads(r.stdout), [_extract_ts(m) for m in mids])

    def test_unparseable_ids_are_empty(self) -> None:
        for bad in ("", "hash:", "hash:乱的名字", "hash:20261013_2102_657_af07"):
            with self.subTest(bad=bad):
                self.assertEqual(_extract_ts(bad), "")


if __name__ == "__main__":
    unittest.main()
