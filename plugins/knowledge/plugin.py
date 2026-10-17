# -*- coding: utf-8 -*-
"""知识库插件。

知识库的一切都在这里：配置判定、路径安全、文件读取、表格解析、勾选状态、
上下文注入与界面。内核不知道"知识库"是什么 —— 它只提供通用的扩展点
（`ctx.add_context_source` / `add_panel` / `add_action` / `add_route` / `data_dir`）
与通用的 INI 读取（`agent.config.load_ini`）。

配置在插件自己目录下的 `plugin-config.ini`：`[base]` 是身份与开关，`[ext]` 是 `dir` / `max_file_size`。

注入走 `ctx.add_context_source`（上下文注入扩展点）：管线每一步组装请求时，
会把注入源产出的文本刷进上下文的「知识库」块。勾选状态落在 `ctx.data_dir`
（`<数据根>/plugin/knowledge/`）—— 插件只看到自己这一层，不需要知道外层目录。

界面由本插件声明：右栏面板 + 它取数的端点 + 输入框下面的动作按钮。
把 `knowledge` 从 `plugins.ini` 里去掉，这些就一起消失。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from agent.capabilities.plugins import plugin_config_fields
from agent.config import PROJECT_ROOT, load_ini

__all__ = [
    "DEFAULT_MAX_FILE_SIZE",
    "KBRuntime",
    "MISSING_OPENPYXL_HINT",
    "TABLE_SUFFIXES",
    "register",
]

#: 未配置 `max_file_size` 时的缺省上限
DEFAULT_MAX_FILE_SIZE = 200000

#: 勾选状态的落盘文件名（放在插件自己的数据目录下）
CHECKED_STATE_FILENAME = "checked_state.json"

#: 注入格式：每个勾选文件独占一条系统消息。模型靠这行标记认出"这是随附资料"。
INJECT_PREFIX = "【知识库：{rel}】"

#: 按表格解析的扩展名（需要 openpyxl）
TABLE_SUFFIXES = (".xlsx", ".xls", ".xlsm")

#: 可收录的文本类扩展名。**知识库只收文本**：非文本文件读出来是替换字符与 NUL，
#: 注进上下文等于白占预算，还会把模型带偏。没有扩展名的文件按文本对待（README 之类）。
TEXT_SUFFIXES = (
    ".md", ".markdown", ".txt", ".text", ".rst", ".log", ".csv", ".tsv",
    ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
    ".html", ".htm", ".css", ".scss", ".less", ".xml", ".sql", ".sh", ".bat", ".ps1",
    ".java", ".kt", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".lua",
    ".properties", ".gradle", ".dockerfile", ".gitignore",
)
#: 无扩展名时也收的常见文件名
TEXT_FILENAMES = ("dockerfile", "makefile", "readme", "license", "changelog")


def parse_extra_suffixes(raw: Any) -> Tuple[str, ...]:
    """解析配置里的自定义扩展名：英文逗号分隔，`txt, ini` 与 `.txt,.ini` 都认。

    规范化成小写带点形式；重复与空项丢掉。写错了不报错 —— 一个拼错的扩展名
    不该让整个知识库不可用。
    """
    out: List[str] = []
    for part in str(raw or "").split(","):
        item = part.strip().strip("'\"").lower()
        if not item:
            continue
        suffix = item if item.startswith(".") else "." + item
        if suffix not in out:
            out.append(suffix)
    return tuple(out)


def is_text_like(name: str, extra: Tuple[str, ...] = ()) -> bool:
    """是否属于可收录的文本类文件（无扩展名按文本对待；`extra` 是配置加的类型）。"""
    low = str(name or "").strip().lower()
    if not low:
        return False
    suffix = Path(low).suffix
    if not suffix:
        return True
    return suffix in TEXT_SUFFIXES or suffix in TABLE_SUFFIXES or suffix in extra

#: 缺 openpyxl 时给出的提示文本（作为提示而非异常，便于模型理解）
MISSING_OPENPYXL_HINT = "（缺少 openpyxl，无法读取 Excel 知识库文件；请先安装 openpyxl）"


def _has_hidden_segment(rel: Path) -> bool:
    """路径任一段以 `.` 开头即视为隐藏。"""
    return any(part.startswith(".") for part in rel.parts)


#: 本插件配置文件的节名（文件在插件自己目录下）
CONFIG_SECTION = "ext"


def _config_path() -> Path:
    """本插件的配置文件：`plugins/knowledge/plugin-config.ini`。

    配置与本插件同目录：内核的 `config.ini` 只含内核设置。
    文件不在就用缺省值（`dir` 为空 → 不提供任何文件）。
    """
    return Path(__file__).resolve().parent / "plugin-config.ini"


def _load_kb_config(path: Optional[Path] = None) -> Dict[str, Any]:
    """读本插件配置的 `[ext]` 节：`dir` / `max_file_size` / `extra_suffixes`。

    `dir` 缺失、不存在或不是目录时返回 `None`，于是 `enabled` 为假、全部操作返回空
    —— 判定失败时静默降级，不报错。相对路径按工程根解析。
    """
    parser = load_ini(path if path is not None else _config_path())
    values: Dict[str, str] = {}
    if parser.has_section(CONFIG_SECTION):
        values = {k: str(v or "").strip().strip("'\"")
                  for k, v in parser.items(CONFIG_SECTION)}

    root: Optional[Path] = None
    raw_dir = values.get("dir") or ""
    if raw_dir:
        candidate = Path(raw_dir)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        try:
            if candidate.is_dir():
                root = candidate.resolve()
        except OSError:
            root = None

    try:
        max_size = int(values.get("max_file_size") or DEFAULT_MAX_FILE_SIZE)
    except (TypeError, ValueError):
        max_size = DEFAULT_MAX_FILE_SIZE
    return {"dir": root, "max_file_size": max_size,
            "extra_suffixes": parse_extra_suffixes(values.get("extra_suffixes"))}


class _KnowledgeFiles:
    """知识库的文件访问层：配置判定、路径安全、校验、读取、列表。

    只认"根目录 + 上限"两件事，不碰会话与注入 —— 那在下面的 `KBRuntime`。
    未配置（`root` 为 None）时全部操作返回空。
    """

    def __init__(self, root: Optional[Any] = None,
                 max_file_size: int = DEFAULT_MAX_FILE_SIZE,
                 extra_suffixes: Any = ()) -> None:
        #: 勾选一变就调它，让装配侧丢掉缓存的收集结果（由 `register()` 接上）。
        self._sources_bump: Any = None
        self.root: Optional[Path] = Path(root).resolve() if root else None
        self.max_file_size = int(max_file_size)
        #: 配置里追加的可收录扩展名（小写带点形式）
        self.extra_suffixes: Tuple[str, ...] = tuple(extra_suffixes or ())
        #: 文件正文缓存：键是 `(路径, mtime_ns, 大小)`，装配一趟会读三次。
        self._read_cache: Dict[Any, str] = {}

    @classmethod
    def from_config(cls, path: Optional[Path] = None,
                    data_dir: Optional[Path] = None) -> "KBRuntime":
        cfg = _load_kb_config(path)
        return KBRuntime(cfg.get("dir"), int(cfg.get("max_file_size") or DEFAULT_MAX_FILE_SIZE),
                         extra_suffixes=cfg.get("extra_suffixes") or (),
                         data_dir=data_dir)

    @property
    def enabled(self) -> bool:
        return self.root is not None

    # ── 路径安全 ──

    def safe_resolve(self, rel: str) -> Optional[Path]:
        """把相对路径解析到根下的真实文件；任何不合规都返回 None。

        拒绝：空值 / 绝对路径 / `..` 越界 / 隐藏段 / 不是文件 / 不存在。
        """
        if not self.enabled or self.root is None:
            return None
        raw = str(rel or "").strip()
        if not raw:
            return None
        if Path(raw).is_absolute():
            return None
        try:
            rel_path = Path(os.path.normpath(raw))
        except (OSError, ValueError):
            return None
        if rel_path.is_absolute() or ".." in rel_path.parts:
            return None
        if _has_hidden_segment(rel_path):
            return None
        try:
            resolved = (self.root / rel_path).resolve()
            resolved.relative_to(self.root)
        except (OSError, ValueError):
            return None
        if not resolved.is_file():
            return None
        return resolved

    # ── 文件校验 ──

    def file_allowed(self, target: Path) -> Tuple[bool, str]:
        """校验单个文件是否可用；返回 (是否允许, 拒绝原因)。"""
        try:
            rel = target.resolve().relative_to(self.root) if self.root else target
        except (OSError, ValueError):
            return False, "越界"
        if _has_hidden_segment(rel):
            return False, "隐藏文件不可用"
        try:
            size = target.stat().st_size
        except OSError:
            return False, "无法读取文件信息"
        if self.max_file_size > 0 and size > self.max_file_size:
            return False, f"文件超过上限（{size} > {self.max_file_size} 字节）"
        if not is_text_like(target.name, self.extra_suffixes):
            return False, "非文本文件不可收录"
        if target.suffix.lower() in TABLE_SUFFIXES:
            try:
                import openpyxl  # noqa: F401
            except ImportError:
                return False, MISSING_OPENPYXL_HINT
        return True, ""

    # ── 文件读取 ──

    def read_text(self, target: Path) -> str:
        """读文件正文：表格转文本（Sheet 头 + 制表符分行），其余按 utf-8 容错解码。

        按 `(路径, mtime, 大小)` 缓存：装配一趟会收集三次，每次勾选文件都全量重读
        纯属白烧磁盘；文件一改（mtime/大小变）缓存自动失效。
        """
        try:
            info = target.stat()
            key = (str(target), info.st_mtime_ns, info.st_size)
        except OSError:
            key = None
        if key is not None:
            hit = self._read_cache.get(key)
            if hit is not None:
                return hit
        if target.suffix.lower() in TABLE_SUFFIXES:
            text = self._read_table(target)
        else:
            try:
                text = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
        if key is not None:
            self._read_cache[key] = text
        return text

    def _read_table(self, target: Path) -> str:
        try:
            import openpyxl
        except ImportError:
            return MISSING_OPENPYXL_HINT
        try:
            book = openpyxl.load_workbook(str(target), read_only=True, data_only=True)
        except Exception:
            # **旁路，刻意吞掉**：一个坏掉的表格只该给出这一行的说明，
            # 不该让整次注入失败（同批其它文件仍然要送出去）。
            return "（无法解析该 Excel 文件）"
        lines: List[str] = []
        try:
            for sheet in book.worksheets:
                lines.append(f"[Sheet: {sheet.title}]")
                for row in sheet.iter_rows(values_only=True):
                    cells = ["" if cell is None else str(cell) for cell in row]
                    while cells and cells[-1] == "":
                        cells.pop()
                    if cells:
                        lines.append("\t".join(cells))
        finally:
            try:
                book.close()
            except Exception:
                # **旁路，刻意吞掉**：关不掉只影响句柄回收，内容已经读完了。
                pass
        return "\n".join(lines)

    # ── 文件列表 ──

    def list_files(self) -> List[Dict[str, Any]]:
        """列出可收录的文件：rglob 递归；排除隐藏段、`__pycache__` 与非文本文件。

        只列能勾的 —— 列出来却勾不了（`file_allowed` 会拒）等于给界面挖坑。
        每项 `{path, name, mtime}`；`path` 为相对根的 POSIX 风格路径。
        未启用时返回空列表（不报错）。
        """
        if not self.enabled or self.root is None:
            return []
        rows: List[Dict[str, Any]] = []
        try:
            for path in sorted(self.root.rglob("*")):
                if not path.is_file():
                    continue
                try:
                    rel = path.relative_to(self.root)
                except ValueError:
                    continue
                if _has_hidden_segment(rel) or "__pycache__" in rel.parts:
                    continue
                if not is_text_like(path.name, self.extra_suffixes):
                    continue
                try:
                    mtime = int(path.stat().st_mtime)
                except OSError:
                    mtime = 0
                rows.append({
                    "path": rel.as_posix(),
                    "name": path.name,
                    "mtime": mtime,
                })
        except OSError:
            return rows
        return rows


class KBRuntime(_KnowledgeFiles):
    """知识库会话状态：文件访问层 + 勾选与注入策略。"""

    def __init__(self, root: Optional[Any] = None,
                 max_file_size: int = DEFAULT_MAX_FILE_SIZE,
                 data_dir: Optional[Path] = None,
                 extra_suffixes: Any = ()) -> None:
        super().__init__(root, max_file_size, extra_suffixes)
        self._data_dir = Path(data_dir) if data_dir is not None else None
        self._lock = threading.Lock()
        #: `{cid: {相对路径, ...}}`；缺失的 cid 视为"没有勾选"。
        self._checked: Dict[str, Set[str]] = {}

    # ── 勾选状态 ──

    def _state_file(self) -> Optional[Path]:
        if self._data_dir is None:
            return None
        return self._data_dir / CHECKED_STATE_FILENAME

    def load_checked(self) -> None:
        """启动时全量读入勾选；文件缺失或损坏时保持空（不报错）。"""
        state_file = self._state_file()
        if state_file is None or not state_file.is_file():
            return
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        with self._lock:
            for cid, paths in data.items():
                if isinstance(paths, list):
                    self._checked[str(cid)] = {str(p) for p in paths}

    def _persist(self) -> None:
        """写回磁盘；写失败静默（勾选是界面偏好，不该让请求失败）。"""
        state_file = self._state_file()
        if state_file is None:
            return
        with self._lock:
            payload = {cid: sorted(v) for cid, v in self._checked.items()}
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            # **旁路，刻意吞掉**：状态文件写不进去只影响下次启动的记忆，
            # 当前会话的勾选仍在内存里、注入照常生效。
            pass

    def get_checked(self, cid: str) -> Set[str]:
        with self._lock:
            return set(self._checked.get(str(cid or "")) or set())

    def set_checked(self, cid: str, rels: List[str]) -> List[str]:
        """全量设置某会话的勾选；逐项校验，空列表清除。返回实际接受的相对路径。"""
        key = str(cid or "")
        accepted: Set[str] = set()
        for rel in rels or []:
            target = self.safe_resolve(str(rel))
            if target is None or not self.file_allowed(target)[0]:
                continue
            if self.root is None:
                continue
            try:
                accepted.add(target.relative_to(self.root).as_posix())
            except ValueError:
                continue
        with self._lock:
            if accepted:
                self._checked[key] = accepted
            else:
                self._checked.pop(key, None)
        self._persist()
        # 勾选是本插件的数据，装配侧缓存看不到它变了 —— 必须显式打个标记，
        # 否则"改了勾选，这一段要等下一轮才生效"。
        bump = self._sources_bump
        if callable(bump):
            bump()
        return sorted(accepted)

    # ── 注入上下文 ──

    def build_system_messages(self, cid: str) -> List[str]:
        """每个勾选文件一条系统消息：标记行 + 文件正文。"""
        if not self.enabled:
            return []
        out: List[str] = []
        for rel in sorted(self.get_checked(cid)):
            target = self.safe_resolve(rel)
            if target is None or not self.file_allowed(target)[0]:
                continue
            try:
                text = self.read_text(target).strip()
            except OSError:
                continue
            if not text:
                continue
            out.append(INJECT_PREFIX.format(rel=rel) + "\n" + text)
        return out

    def attached_count(self, cid: str) -> int:
        """实际会被注入的文件数（勾选、存在、未超限）。"""
        n = 0
        for rel in sorted(self.get_checked(cid)):
            target = self.safe_resolve(rel)
            if target is not None and self.file_allowed(target)[0]:
                n += 1
        return n


def _read_kb_file_text(fpath: Any) -> str:
    """按本插件的规则读一个知识库文件的正文（供测试与外部引用）。"""
    return _KnowledgeFiles().read_text(fpath)


#: 面板 HTML 片段。样式与脚本都是**插件自己的文件**（`ui/` 下），
#: 由壳层经 `_asset` 路由随面板送达，不占壳层的公共资源。
_PANEL_HTML = (
    '<div class="kb-body" id="kbBody">'
    '<div class="kb-loading">📂 加载知识库…</div>'
    "</div>"
)


def register(ctx: Any) -> List[Callable[[], None]]:
    """插件入口：装配运行时，注册注入源、界面贡献与端点。

    知识库**不依赖内核额外的口子**：配置自己读，文件访问是自己的层，
    注入用现成的 `add_context_source`，界面用面板 / 动作 / 端点贡献，
    状态用自己的 `data_dir`。
    """
    cfg = _load_kb_config()
    root = cfg.get("dir") or None
    max_size = int(cfg.get("max_file_size") or DEFAULT_MAX_FILE_SIZE)
    runtime = KBRuntime(root, max_size, data_dir=getattr(ctx, "data_dir", None),
                        extra_suffixes=cfg.get("extra_suffixes") or ())
    runtime.load_checked()
    # 勾选一变就让装配侧丢掉缓存的收集结果：否则"改了勾选要等下一轮才生效"。
    # 出处是宿主的注册表（`ContextSources.bump`），拿不到就退化为"下一轮生效"。
    runtime._sources_bump = getattr(ctx, "bump_context_sources", None)
    ctx.set_runtime(runtime)

    def _meta() -> Any:
        """这一段在上下文分层里的名片：段名、注入前缀、主体数量（勾选文件数）。"""
        return {
            "label": "知识库",
            # 前缀按文件不同（`【知识库：<路径>】`），由本插件在正文里拼好。
            "count": runtime.attached_count,
        }

    disposers: List[Callable[[], None]] = [
        # 上下文注入：管线组装请求时把勾选文件的正文刷进本插件的段落
        ctx.add_context_source(runtime.build_system_messages, _meta()),
    ]

    def _files(query: Dict[str, Any]) -> Any:
        if not runtime.enabled:
            return 200, {"ok": True, "enabled": False, "files": []}
        return 200, {"ok": True, "enabled": True, "files": runtime.list_files()}

    def _checked_get(query: Dict[str, Any]) -> Any:
        cid = str((query or {}).get("conversation_id") or "")
        return 200, {"ok": True, "checked": sorted(runtime.get_checked(cid))}

    def _checked_put(query: Dict[str, Any]) -> Any:
        body = (query or {}).get("body") or {}
        cid = str(body.get("conversation_id") or (query or {}).get("conversation_id") or "")
        if not cid:
            return 400, {"ok": False, "error": "conversation_id required"}
        raw = body.get("checked")
        if not isinstance(raw, list):
            raw = body.get("paths") if isinstance(body.get("paths"), list) else []
        return 200, {"ok": True, "checked": runtime.set_checked(cid, raw)}

    base = plugin_config_fields(Path(__file__).resolve().parent)
    title = base["name"] or "知识库"
    label = f"{base['icon']} {title}".strip() if base["icon"] else title
    disposers.append(ctx.add_panel(
        "kb", title=title, html=_PANEL_HTML,
        script_file="ui/panel.js", css_file="ui/panel.css"))
    disposers.append(ctx.add_action("kb", label=label, title=title))
    disposers.append(ctx.add_ctx_segment_style(label=title, color="blue"))
    disposers.append(ctx.add_route("GET", "files", _files))
    disposers.append(ctx.add_route("GET", "checked", _checked_get))
    disposers.append(ctx.add_route("PUT", "checked", _checked_put))
    return disposers
