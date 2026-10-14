# -*- coding: utf-8 -*-
"""技能库：扫描 / 元数据解析 / 读取 / 复制计划（技能插件内部）。

范围：不做 LLM 元数据生成、不做缺 frontmatter 自动写回、
不携带 side_usage / notifications（无旁支模型；静默写文件违反写盘纪律）。
复制采用「计划（预览）→ 执行（提交）」两段式，配合 id 制门控。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

CATALOG_HEAD = "【Skills清单】"


class SkillMeta:
    """单个技能元数据。"""

    __slots__ = ("name", "description", "file_path", "is_auto_load")

    def __init__(self, name: str, description: str, file_path: Path, is_auto_load: bool = False) -> None:
        self.name = str(name or "").strip()
        self.description = str(description or "").strip()
        self.file_path = file_path
        self.is_auto_load = bool(is_auto_load)


class SkillManager:
    """技能库：扫描目录、缓存元数据与正文、mtime 增量重扫。"""

    def __init__(self, skills_dir: Optional[Path], max_file_size: int = 200000) -> None:
        self.skills_dir = Path(skills_dir) if skills_dir else None
        self.max_file_size = int(max_file_size)
        self.skills: List[SkillMeta] = []
        self._content_cache: Dict[str, str] = {}
        self._last_mtimes: Dict[str, float] = {}
        if self.skills_dir and self.skills_dir.is_dir():
            self._scan()
            # 首次扫描后就把 mtime 记下来：不记的话下面每次 `_check_rescan`
            # 都会判成"变了"再扫一遍（首次加载后紧接着的重扫纯属白做）。
            self._last_mtimes = self._current_mtimes()

    # ── 隐藏目录过滤 ────────────────────────────────────

    @staticmethod
    def _should_skip(file_path: Path) -> bool:
        for part in file_path.parts:
            if part.startswith(".") and part != ".":
                return True
        return False

    # ── 动态检测 / 扫描 ────────────────────────────────

    def auto_load_count(self) -> int:
        """常驻技能条数（不拼正文）。"""
        self._check_rescan()
        return sum(1 for s in self.skills if s.is_auto_load)

    def _current_mtimes(self) -> Dict[str, float]:
        """当前全部技能文件的 mtime 表（键是绝对路径）。"""
        out: Dict[str, float] = {}
        if not self.skills_dir or not self.skills_dir.is_dir():
            return out
        for md_file in self.skills_dir.rglob("*.md"):
            if not md_file.is_file() or self._should_skip(md_file):
                continue
            try:
                out[str(md_file.resolve())] = md_file.stat().st_mtime
            except OSError:
                continue
        return out

    def _check_rescan(self) -> None:
        """mtime 检测新增 / 变更 / 删除；有变化则清缓存重扫。

        界面/工具改完技能文件后，下一次收集就能看到（这里每次都核对 mtime）。
        """
        if not self.skills_dir or not self.skills_dir.is_dir():
            return
        current = self._current_mtimes()
        changed = current != self._last_mtimes
        if not changed:
            return
        self._last_mtimes = current
        self.skills.clear()
        self._content_cache.clear()
        self._scan()

    def _force_rescan(self) -> None:
        """清空缓存全量重扫（复制落盘后调用）。"""
        self.skills.clear()
        self._content_cache.clear()
        self._scan()
        self._last_mtimes = self._current_mtimes()

    def _scan(self) -> None:
        """扫描 skills_dir 下全部 .md（auto_load 子目录标记；隐藏目录跳过）。"""
        if not self.skills_dir or not self.skills_dir.is_dir():
            return
        seen: Set[str] = set()
        auto_dir = self.skills_dir / "auto_load"

        def _rel_key(md: Path) -> str:
            try:
                return str(md.relative_to(self.skills_dir)).replace("\\", "/").lower()
            except ValueError:
                return md.name.lower()

        def _collect_one(md_file: Path, is_auto_load: bool) -> None:
            key = _rel_key(md_file)
            if key in seen:
                return
            seen.add(key)
            rel_name = str(md_file.relative_to(self.skills_dir)).replace("\\", "/")
            if rel_name.lower().endswith(".md"):
                rel_name = rel_name[:-3]
            _, desc = self._parse_meta(md_file)
            self.skills.append(SkillMeta(rel_name, desc, md_file, is_auto_load=is_auto_load))

        if auto_dir.is_dir():
            for md_file in sorted(auto_dir.rglob("*.md")):
                if md_file.is_file() and not self._should_skip(md_file):
                    _collect_one(md_file, is_auto_load=True)

        skip_prefix = auto_dir.resolve() if auto_dir.is_dir() else None
        for md_file in sorted(self.skills_dir.rglob("*.md")):
            if not md_file.is_file() or self._should_skip(md_file):
                continue
            if skip_prefix and skip_prefix in md_file.resolve().parents:
                continue
            _collect_one(md_file, is_auto_load=False)

    # ── frontmatter 解析 ───────────────────────────────

    @staticmethod
    def _strip_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
        """解析首部 --- 分隔的简版 YAML frontmatter（key: value 逐行）。"""
        meta: Dict[str, str] = {}
        lines = text.strip().splitlines()
        if not lines:
            return meta, text
        if not lines[0].strip().startswith("---"):
            return meta, text
        end = -1
        for i in range(1, len(lines)):
            if lines[i].strip().startswith("---"):
                end = i
                break
        if end < 1:
            return meta, text
        for line in lines[1:end]:
            s = line.strip()
            if ":" in s:
                key, _, val = s.partition(":")
                meta[key.strip().lower()] = val.strip()
        body = "\n".join(lines[end + 1:]).strip()
        return meta, body

    def _parse_meta(self, file_path: Path) -> Tuple[str, str]:
        try:
            text = file_path.read_text(encoding="utf-8")
        except OSError:
            return file_path.stem, ""
        meta, _ = self._strip_frontmatter(text)
        name = str(meta.get("name") or "").strip() or file_path.stem
        desc = str(meta.get("description") or "").strip()
        return name, desc

    # ── 公开 API ───────────────────────────────────────

    def list_skills(self) -> List[Dict[str, Any]]:
        """列出普通技能（auto_load 常驻技能不列入，供上下文注入用）。"""
        self._check_rescan()
        return [
            {"name": s.name, "description": s.description, "auto_load": s.is_auto_load}
            for s in self.skills
            if not s.is_auto_load
        ]

    def list_skill_names(self) -> List[str]:
        """全部技能 name 列表（供错误提示）。"""
        return [s.name for s in self.skills]

    def get_skill_meta(self, name: str) -> Optional[SkillMeta]:
        """按 name 取元数据（精确 → 纯文件名 stem）。"""
        self._check_rescan()
        key = str(name or "").strip()
        if not key:
            return None
        for s in self.skills:
            if s.name == key:
                return s
        for s in self.skills:
            if Path(s.name).stem == key:
                return s
        return None

    def get_skill(self, name: str) -> Optional[str]:
        """按 name 取正文（精确 → 忽略大小写 → stem 且父目录为根）。"""
        self._check_rescan()
        key = str(name or "").strip()
        if not key:
            return None
        for s in self.skills:
            if s.name == key:
                return self._read_content(s)
        key_lower = key.lower()
        for s in self.skills:
            if s.name.lower() == key_lower:
                return self._read_content(s)
        if "/" not in key and "\\" not in key:
            stem_matches = [
                s
                for s in self.skills
                if s.file_path.stem.lower() == key_lower and s.file_path.parent == self.skills_dir
            ]
            if len(stem_matches) == 1:
                return self._read_content(stem_matches[0])
        return None

    def build_registry_message(self) -> str:
        """构建**可用技能清单**（一条 system 消息，注入上下文前端）。

        渐进式披露的第一层：清单里只有名字与描述，正文按需用 `skill_manage`
        读取。模型据此知道"有哪些技能、什么时候该用"，而不必把所有正文塞进请求。
        没有普通技能 → 空串（不注入空清单）。
        """
        parts = self.build_registry_message_parts()
        return parts[0] if parts else ""

    def build_registry_message_parts(self) -> List[str]:
        """清单的**消息列表形态**（没有技能 → 空列表）。

        注入源按 `List[str]` 收内容，这里给它列表；单条内容与
        `build_registry_message()` 完全一致。
        """
        items = self.list_skills()
        if not items:
            return []
        lines = [CATALOG_HEAD,
                 "需要用某个技能时，先用 skill_manage 读取它的正文再照做。"]
        for s in items:
            desc = str(s.get("description") or "").strip() or "（无描述）"
            lines.append(f"- {s.get('name')}: {desc}")
        return ["\n".join(lines)]

    def build_auto_load_messages(self) -> List[str]:
        """构建 `auto_load/` 目录下技能的**常驻正文**（每条一条 system 消息）。

        渐进式披露的第二层：这些技能始终随上下文携带，不必模型主动读取。
        正文为空的不注入。
        """
        self._check_rescan()
        out: List[str] = []
        for s in self.skills:
            if not s.is_auto_load:
                continue
            content = self._read_content(s)
            if content.strip():
                out.append(f"【Skills 技能 {s.name}】\n{content}")
        return out

    def _read_content(self, meta: SkillMeta) -> str:
        if meta.name in self._content_cache:
            return self._content_cache[meta.name]
        try:
            text = meta.file_path.read_text(encoding="utf-8")
        except OSError:
            return ""
        if len(text.encode("utf-8")) > self.max_file_size:
            text = text[: self.max_file_size // 2] + "\n\n...(文件过大，已截断)"
        _, body = self._strip_frontmatter(text)
        content = body.strip()
        self._content_cache[meta.name] = content
        return content

    # ── 复制（两段式：计划 → 执行）──────────────────────

    def plan_copy(self, source: Path, subdir: str = "") -> Dict[str, Any]:
        """复制计划（预览，不落盘）：解析源与目标、列出将复制文件与冲突。"""
        if not self.skills_dir:
            raise ValueError("skills 目录未配置")
        sub = str(subdir or "").strip().strip("/")
        if source.is_file():
            target_dir = (self.skills_dir / sub) if sub else self.skills_dir
            dest = target_dir / source.name
            return {
                "mode": "file",
                "source": str(source),
                "target_dir": str(target_dir),
                "files": [source.name],
                "conflicts": [str(dest)] if dest.exists() else [],
                "skipped": 0,
            }
        if not source.is_dir():
            raise FileNotFoundError(f"源路径不存在: {source}")
        src = (source / sub) if sub else source
        if not src.is_dir():
            raise FileNotFoundError(f"子目录不存在: {src}")
        target_dir = (self.skills_dir / sub) if sub else self.skills_dir
        files: List[str] = []
        skipped = 0
        for f in sorted(src.iterdir()):
            if not f.is_file() or f.suffix != ".md":
                skipped += 1
                continue
            files.append(f.name)
        conflicts = [str(target_dir / name) for name in files if (target_dir / name).exists()]
        return {
            "mode": "dir",
            "source": str(src),
            "target_dir": str(target_dir),
            "files": files,
            "conflicts": conflicts,
            "skipped": skipped,
        }

    def execute_copy(self, source: Path, subdir: str = "") -> Dict[str, Any]:
        """执行复制（提交）：仅 .md 文件；返回 copied / skipped / errors / path。"""
        plan = self.plan_copy(source, subdir)
        target_dir = Path(plan["target_dir"])
        target_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        errors: List[str] = []
        if plan["mode"] == "file":
            try:
                shutil.copy2(str(source), str(target_dir / source.name))
                copied = 1
            except Exception as exc:
                errors.append(str(exc))
            dest_path = str(target_dir / source.name)
        else:
            src_dir = Path(plan["source"])
            for f in sorted(src_dir.iterdir()):
                if not f.is_file() or f.suffix != ".md":
                    continue
                try:
                    shutil.copy2(str(f), str(target_dir / f.name))
                    copied += 1
                except Exception as exc:
                    errors.append(f"{f.name}: {exc}")
            dest_path = str(target_dir)
        self._force_rescan()
        return {"copied": copied, "skipped": plan["skipped"], "errors": errors, "path": dest_path}
