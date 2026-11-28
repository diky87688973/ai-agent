---
name: evidence-image
description: 把多帧或多项视觉证据拼成一张可内联展示的图：选帧、统一尺寸、3×3 排版、标时刻、落到 %TEMP%。结论依赖多帧像素时用它；单帧直接内联原图。
---

# 证据图

拼图的作用是把时序放进同一张，让读者一次看清状态怎么变。排得整齐但不说明问题的图，等于没给证据。

## 0. 判定

```text
结论依赖单帧        → 直接内联那张图，不拼
结论依赖多帧或场景  → 拼一张，最多 9 格
帧多到 9 格看不清   → 内联视频
纯数值、纯结构      → 不产图，用表格或 text 图
```

## 1. 输入

源图必须是能直接 `Image.open` 的本地文件路径，且是本轮实际产生的：

```text
渲染帧、测试产物、外部截图落盘后的文件、用户给的图
```

拿到的是附件引用而不是路径时，先确认它有没有落盘路径；没有就换一个能产出文件的证据来源，不要拿附件 ID 去拼图。

## 2. 拼图

Pillow 是既有依赖，不需要新增包。

```python
from datetime import datetime
from pathlib import Path
from tempfile import gettempdir

from PIL import Image, ImageDraw, ImageFont

CELL = (480, 360)
COLS = 3
sources = [Path(p) for p in []]  # 按时间顺序填入

def label_font(size=22):
    for name in ("msyh.ttc", "simhei.ttf"):
        try:
            return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)
        except OSError:
            continue
    return ImageFont.load_default()

font = label_font()
rows = (len(sources) + COLS - 1) // COLS
sheet = Image.new("RGB", (CELL[0] * COLS, CELL[1] * rows), (24, 24, 24))
draw = ImageDraw.Draw(sheet)
for index, path in enumerate(sources):
    with Image.open(path) as image:
        frame = image.convert("RGB")
        frame.thumbnail(CELL)
        x = (index % COLS) * CELL[0] + (CELL[0] - frame.width) // 2
        y = (index // COLS) * CELL[1] + (CELL[1] - frame.height) // 2
        sheet.paste(frame, (x, y))
        draw.text(
            ((index % COLS) * CELL[0] + 8, (index // COLS) * CELL[1] + 8),
            path.stem,
            fill=(255, 255, 255),
            font=font,
        )

out = Path(gettempdir()) / f"evidence-{datetime.now():%Y%m%d-%H%M%S}.png"
sheet.save(out)
print(out)
```

字体缺失时 `load_default()` 只画得出 ASCII，标签用英文或序号。

## 3. 校验与交付

```text
1 read_image 看一遍：关键状态可辨、标签不压住内容
2 不可辨 → 减格数、换单帧或换成视频，不硬贴
3 正文写 ![一句说明](<绝对路径>)，同一结论只贴一次
```

## 4. 边界

```text
临时图放 %TEMP%，任务结束删掉自己建的那些
Pillow 读不了 mp4：要视频证据先探测 ffmpeg，缺失就逐帧截图后拼图
生成模型的出图不得充当证据；示意图必须标注
```
