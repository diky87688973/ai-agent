# -*- coding: utf-8 -*-
"""模型请求的对话与图片准备。"""
from __future__ import annotations

from typing import Any, Dict, List

from agent.core.image_embed import strip_attachment_meta, strip_old_images


def prepare_dialogue(dialogue: Any, image_turns: int,
                      image_max: int) -> List[Dict[str, Any]]:
    """对话 → 请求用对话：按配置剥掉窗口外的图。

    默认保留最近 1 轮最多 8 张：截图工具每步一张大图，历史全带会先撞上游
    请求体上限。把两个上限都设成负数可关闭剥离，但请求体会随会话增长。

    压缩请求与模型请求走同一函数：压缩器声明前缀与随后请求逐字节相同，
    该声明只在两边用同一套剥图参数时成立。
    """
    prepared, _stripped = strip_old_images(dialogue, keep_turns=image_turns,
                                           max_images=image_max)
    return strip_attachment_meta(prepared)
