# -*- coding: utf-8 -*-
"""注释文案检查：注释只解释代码，不留"工程过程"文案与对读者的叮嘱。

## 为什么需要这条检查

注释里混进"谁说的 / 哪一轮发现的 / 当时怎么错的"这类叙述，有两个问题：

1. 对读者无信息量：读代码需要的是"这里为什么这样写、改动它会坏什么"，
   而不是某次调试的经过；
2. 不会自己消失：这类文案随对话产生，不清理就一直在。

同一条理由适用于对读者讲话：注释与配置模板都不是讲话的地方 ——
"不写在这里""模板见 X""注意：…"既不解释代码，也不描述配置项本身。

人工清理只能覆盖已有文件；这条检查把判据固定下来，新增的也一并覆盖。

## 判据（只查这几类，避免误报）

| 类别 | 命中形态 |
|---|---|
| 引用用户原话 | 转述用户的话，含具体日期或"拍板 / 要求 / 反馈"之类动词 |
| 实测/复审叙述 | 以"实测"起头的调试结论、带轮次的复审叙述 |
| 纠错史 | 以"曾经 / 原先 / 原来 / 此前 / 历史上 / 早期"交代旧行为有错 |
| 对读者讲话 | "别把它…"、"请你自己…"这类写给读者的叮嘱 |
| 叮嘱与指路 | "不写在这里"/"放在别处"/"见 X"/"参见"/"注意："这类指使读者去别处看 |
| 自我指涉 | "我当时…"、"作者本来…"这类写代码时的心理活动 |
| 设计辩护 | "为什么不…？因为…"、"之所以…"、"这是有意的" |
| 版本口吻 | "第一版"、"目前暂"、"后续再"、"将来"、"下一步" |
| 遗留备忘 | `TODO` / `FIXME` / `XXX` / "待办" / "回头补" |
| 元叙述 | "本文件…"、"这段注释说明…"、"下文会…"、"读者应…" |
| 方案对比 | "这样比 A 好"、"相比 X 的做法"、"不用 A 而用 B" |
| 改动叙述 | "以前是…"、"这次改成…"、"原本用…" |
| 排版标记 | 注释里的 Markdown 加粗（`**…**`）——注释不渲染，星号会原样留下 |

## 查哪些文件

`.py`（`agent/` `scripts/` `tests/` `plugins/`）与配置文件、界面资产、文档：
`.ini` `.toml` `.js` `.css` `.html` `.md`。

配置模板与 JS 注释同样是对外文案：只查 `.py` 会漏掉
`plugins/*/plugin-config.ini` 里的"不写在这里""模板见…"。

## 刻意不查的（工程约定，删了会坏）

- `LOCAL-CHANGE D23` —— UI 改动登记标记，`check_ui_js.py` 要读；
- `# noqa: E402` 等工具指令；
- 测试文件里的 `实测：…` 若描述的是被测行为本身
  （例如"实测 `?last_event_id=0` 回放后 `stream.seq=12`"），
  那是用例的预期依据，不是过程叙述。所以本检查对 tests/ 放宽：
  只查"引用用户原话 / 对读者讲话 / 自我指涉"三类。
- 文档（`.md`）里的"见 [x.md](…)"是交叉引用，属文档本职，不查。

用法：python scripts/check_comment_style.py
退出码：0 = 干净；1 = 命中。
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: 全仓所有 .py 都查这三类（与"是不是测试"无关，任何文件里都成立）
UNIVERSAL = {
    "引用用户原话": re.compile(
        r"用户\s*(?:\d{4}-\d{2}-\d{2}\s*)?(?:明确|指出|要求|定|说过|纠正|拍板|截图|反馈)"
    ),
    "对读者讲话": re.compile(r"(?:别当|别把它|不要当成|请自己|请你)"),
    "自我指涉": re.compile(r"(?:我|作者)(?:当时|本来|之前|误|以为)"),
}

#: 生产代码与配置、界面资产额外查这两类（测试里的"实测：…"常是用例依据，故放宽）
PRODUCTION_ONLY = {
    "实测/复审叙述": re.compile(
        r"实测[踩到发现验证：:]|实测（|第[一二三四五六七八九十]+轮复审|复审代理|复审实测"
    ),
    "纠错史": re.compile(
        r"(?:曾经|原先|原来|此前|历史上|早期)[^。\n]{0,40}"
        r"(?:是错的|错|坏|挂|失效|丢|不准|不对)"
    ),
    # 叮嘱与指路：把读者指使去别处，或对读者下叮嘱 / 下指令。既不解释代码，
    # 也不描述配置项本身 —— 判据只看"是不是在跟读者说话"。
    # 对读者下指令：告诉读者该/不该做什么，而不是描述代码会怎样。
    #   × "内核的 `config.ini` 里不放插件设置"（指使读者去别处看）
    #   × "不要往返回值里塞数据"（命令读者）
    #   √ "不持有上下文对象，不 import 别的模块"（陈述代码的约束）
    #   √ "同一文件的两个写者必须串行，否则…丢行"（陈述 + 后果）
    #
    # 判据只收明确的指令形态，不收"必须与…一致"这类陈述 ——
    # 收太宽会把技术要求也报出来，CI 常红之后就没人看这条检查了。
    # `别(?!的)`：`别` 后跟 `的` 是"另外的"（"别的模块"），不是祈使。
    # 反问式设计辩护：注释在跟读者论证"为什么这么设计"，而不是解释代码。
    #   × "为什么不全量带？因为…"
    #   × "为什么要单独一段？…"
    # `为什么不能 X：<平台/API 原因>` 是约束说明，不算辩护；只有后面不接原因的
    # 才当反问论证报出来。
    "设计辩护": re.compile(
        r"为什么(?:不|要|得|会|是|用)(?![^。\n]{0,40}[：:])|为何(?:不|要)|之所以|"
        r"这是有意的|有意为之|这里有意|故意这么"
    ),
    # 版本与档位口吻：本工程没有第二版，也没有分阶段路线。
    #   × "第一版先这样"  × "目前暂"  × "后续再"  × "v1 不做"
    "版本口吻": re.compile(
        r"第一版|第二版|上一版|v\d+(?:\.\d+)?\s*(?:里|中|先|暂)|"
        r"目前暂|暂时(?:先|只)|后续(?:再|补|加|做)|下一步(?:再|做|加)|"
        r"将来(?:再|做|加)|以后(?:再|补|加)|待(?:日后|以后)"
    ),
    # 给自己留的备忘：不解释代码，只是提醒以后做。
    "遗留备忘": re.compile(r"\bTODO\b|\bFIXME\b|\bXXX\b|待办|回头(?:补|再|改)|以后要"),
    # 元叙述：讲这份文件/这段注释本身怎么读，而不是讲代码。
    #   × "本文档分三节"  × "这段注释说明…"  × "本文件含密钥"（在讲文件本身的管理）
    # `本文件` 会吃到"读取文本文件"这类业务名词，所以要求它后面跟的是元动作。
    "元叙述": re.compile(
        # `上下文里` 会被 `下文(?:会|将|里)` 吃到，所以前面加边界；`本文件会/内/里`
        # 也多是普通表述（"本文件会用到…"），只认明确的元动作。
        r"本文档|本注释|这段注释|这段说明|(?<![上\u4e00-\u9fff])下文(?:会|将)|"
        r"上文(?:说过|提到)|读者(?:可以|应)|"
        # `本文件顶部/上方` 是在指代码位置，属解释代码；`本文件共/含/只…` 是在讲文件本身。
        r"本文件(?:共|分|含|只|仅|之外|管理|的(?:说明|判据|职责))"
    ),
    # 方案对比：把没选的方案也写进注释，属设计讨论。
    #   × "这样比 A 好"  × "相比 X 的做法"  × "A 不行所以用 B"
    "方案对比": re.compile(
        r"这样比|相比(?:之?下|.{0,8}的做法)|比.{2,12}更好|"
        r"而不(?:是|采用|用).{0,16}(?:做法|方案|方式)|"
        r"(?:之所以)?不(?:用|采用).{2,14}(?:而|才)(?:用|改)"
    ),
    # 改动叙述：交代"以前是怎么写的、这次改成什么"，属过程叙述。
    "改动叙述": re.compile(
        r"(?:以前|原先|原本|本来|旧版|原实现|原代码|改动前|改之前)[^。\n]{0,30}"
        r"(?:是|用|写法|实现|版本|这样|如此)|"
        r"(?:这次|本次|现在)(?:改|换|挪|拆|合并|去掉|删掉)(?:成|为|到|了)"
    ),
    "对读者下指令": re.compile(
        r"不写在这里|不放在?这里|不写进|不放进|不放(?:内核|壳层|公共|别处)|"
        r"不放[\u4e00-\u9fff]{0,6}设置|"
        r"放在?各自?目录|由自己管|自己管自己|"
        r"模板见|详见|参见|见上文|见下文|"
        r"注意[：:]|请注意|请务必|切记|别忘了|"
        r"(?:^|[。；;，,：:、\s])(?:不要|别(?!的))"
        r"(?:往|把|用|写|加|删|改|传|编|猜|绕|动|覆盖|顺手|假装|复制|引用|"
        r"再|直接|自己|落到|落在|放到|混|留|放|指)"
    ),
    # 排版标记：注释与配置模板不渲染 Markdown，加粗语法只会留下字面的星号。
    #   × "# 这里**必须**先读"   √ "# 这里必须先读"
    # 只认成对的 `**…**`（可跨行，文档串里的强调常折行）；代码里的解包
    # （`{**a, **b}`）、幂运算与 glob 不在注释区，扫不到。
    "排版标记": re.compile(r"\*\*[^*]{1,80}?\*\*"),
}

#: 非 .py 的受检文本文件（配置模板、界面资产、文档）
TEXT_SUFFIXES = (".ini", ".toml", ".js", ".css", ".html", ".md")
#: 文档里的"见 [x](y)"是交叉引用，属文档本职
DOC_SUFFIXES = (".md",)
#: 压缩过的第三方资产不查
TEXT_SKIP_NAMES = ("highlight.min.js",)

#: 给模型的提示词：那里的祈使句是在指导模型做事，属产品文案，不按注释判据查。
#: （其余文件里主语是读者的祈使句由本检查报出。）
PROMPT_FILES = (
    ROOT / "agent/shell/prompts.py",
    ROOT / "agent/shell/chat.py",
)

#: 生产代码目录（这些目录下的 .py 全查）
PRODUCTION_DIRS = ("agent", "scripts")
#: 插件与配置模板目录（同样是要给人看的文案）
EXTRA_DIRS = ("plugins",)
SKIP_PARTS = ("retired", "__pycache__")
#: 本文件自身要排除：它的说明里必须引用这些坏模式（当例子），否则讲不清判据。
SELF = Path(__file__).resolve()


def _docstring_spans(tree: ast.AST) -> list[tuple[int, str]]:
    """挑出真正的文档串，返回 [(起始行, 文本)]。

    只有模块 / 类 / 函数的首条语句才是文档串（由 AST 给出，不靠猜）。
    赋值给常量的三引号串不是文档串 —— 模块级 `_PROMPT` 是给模型的提示词，
    那是在指导模型做事，属产品文案；按 token 猜会把这类全算进来。
    """
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            out.append((first.lineno, first.value.value))
    return out


def scan_text(text: str, suffix: str,
              patterns: dict[str, re.Pattern[str]]) -> list[tuple[int, str, str]]:
    """返回 [(行号, 类别, 该行)]；`text` 是文件全文，`suffix` 决定解析方式。

    `.py` 用 `tokenize` 取注释、用 `ast` 取文档串（见 `_docstring_spans`）。
    普通字符串与赋值用的三引号串不算 —— 异常里的"必须 > 0"是给用户/模型的
    错误文案，模块级 `_PROMPT` 常量是给模型的提示词，两者都不是对读者讲话；
    按行匹配会把这类全捞进来。

    非 `.py`（`.ini`/`.js`/…）没有 parser，按行首标记取注释。
    """
    out: list[tuple[int, str, str]] = []
    if suffix == ".py":
        try:
            toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return out
        for tok in toks:
            if tok.type == tokenize.COMMENT:
                for name, pat in patterns.items():
                    if pat.search(tok.string):
                        out.append((tok.start[0], name, tok.string.strip()))
                        break
        try:
            docs = _docstring_spans(ast.parse(text))
        except SyntaxError:
            docs = []
        for lineno, body in docs:
            for off, sub in enumerate(body.splitlines()):
                for name, pat in patterns.items():
                    if name == "排版标记":
                        continue
                    if pat.search(sub):
                        out.append((lineno + off, name, sub.strip()))
                        break
            # 排版标记允许跨行：文档串里的强调常在折行处断成两段。
            marker = patterns.get("排版标记")
            if marker is not None:
                for m in marker.finditer(body):
                    off = body.count("\n", 0, m.start())
                    out.append((lineno + off, "排版标记", m.group(0)))
        return out

    for lineno, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s.startswith(("#", ";", "//", "*", "/*")):
            continue
        for name, pat in patterns.items():
            if pat.search(s):
                out.append((lineno, name, s))
                break
    return out


def _scan(path: Path, patterns: dict[str, re.Pattern[str]]) -> list[tuple[int, str, str]]:
    """读文件后交给 `scan_text`；读不到按"无命中"处理（可见的读失败由调用方别的检查管）。"""
    out: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return out
    return scan_text(text, path.suffix, patterns)


def main() -> int:
    hits: list[tuple[Path, int, str, str]] = []
    for base in PRODUCTION_DIRS + EXTRA_DIRS:
        root = ROOT / base
        if not root.is_dir():
            continue
        for py in sorted(root.rglob("*.py")):
            if any(part in py.parts for part in SKIP_PARTS):
                continue
            if py.resolve() == SELF or py.resolve() in PROMPT_FILES:
                continue
            pats = {**UNIVERSAL, **PRODUCTION_ONLY}
            for lineno, name, line in _scan(py, pats):
                hits.append((py, lineno, name, line))

    tests = ROOT / "tests"
    if tests.is_dir():
        for py in sorted(tests.rglob("*.py")):
            if py.resolve() == SELF:
                continue
            for lineno, name, line in _scan(py, UNIVERSAL):
                hits.append((py, lineno, name, line))

    # 配置模板、界面资产与文档：同样是对外文案
    for f in sorted(ROOT.rglob("*")):
        if not f.is_file() or any(part in f.parts for part in SKIP_PARTS):
            continue
        if f.name in TEXT_SKIP_NAMES or f.resolve() == SELF:
            continue
        if f.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if "data" in f.relative_to(ROOT).parts:
            continue
        pats = dict(PRODUCTION_ONLY)
        if f.suffix.lower() in DOC_SUFFIXES:
            # 文档里的交叉引用是本职，只留"叮嘱"里最硬的两条
            pats = {"对读者讲话": UNIVERSAL["对读者讲话"],
                    "自我指涉": UNIVERSAL["自我指涉"]}
        for lineno, name, line in _scan(f, pats):
            if name == "叮嘱与指路" and "见 [" in line:
                continue
            hits.append((f, lineno, name, line))

    print("注释文案检查：注释只解释代码，不留工程过程文案")
    if not hits:
        print("✅ 未发现过程叙述类文案")
        return 0

    print(f"\n发现 {len(hits)} 处：")
    by_kind: dict[str, int] = {}
    for _py, _lineno, name, _line in hits:
        by_kind[name] = by_kind.get(name, 0) + 1
    for name, count in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        print(f"  {name}：{count}")
    print()
    for py, lineno, name, line in hits[:40]:
        rel = py.relative_to(ROOT)
        print(f"  [{name}] {rel}:{lineno}")
        print(f"      {line[:110]}")
    if len(hits) > 40:
        print(f"  …另有 {len(hits) - 40} 处")
    print(
        "\n改法：删掉「谁说的 / 哪一轮发现的 / 当时怎么错的」，"
        "留下「这里为什么这样写、改动它会坏什么」。"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
