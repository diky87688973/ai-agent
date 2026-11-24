"""文件查看器声明的版本、匹配提示与优先级冲突校验。"""
from __future__ import annotations

import re

PREFIX = "app/shell/web-ui/file-viewers/"


def validate_file_viewers(config) -> None:
    claims = set()
    for path in config.paths():
        if not path.startswith(PREFIX):
            continue
        spec = config.spec(path)
        props = spec.props
        extensions = props.get("extensions", ())
        if spec.kind != "ui-control" or props.get("version") != 1 or not extensions:
            raise ValueError(f"文件查看器契约无效：{path}")
        for suffix in extensions:
            key = (suffix, spec.order if spec.order is not None else 0)
            if not isinstance(suffix, str) or not re.fullmatch(r"\.[a-z0-9]{1,16}", suffix) or key in claims:
                raise ValueError(f"文件查看器后缀无效或优先级冲突：{path}")
            claims.add(key)
