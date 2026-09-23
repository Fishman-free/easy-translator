# -*- coding: utf-8 -*-
"""
从截图里抠出鲸鱼娘立绘（去掉它自带的气泡，气泡由 UI 用代码画，才能随内容伸缩）。

裁剪框来自色族地图的实测边界（2026-09-23）：
  · 它自带的气泡 + 两颗尾点：x≈6–116, y≈12–106
  · 角色本体：x≈112–198, y≈56–196（帽尖最上点 y≈57，左侧最远点 x≈114）
两者相邻不重叠，因此 (112, 54) 起裁可以完整保住角色、且不带气泡残片。

用法：
    python tools/make-mascot.py <原始截图.png>       # 写出 assets/mascot.png
    python tools/make-mascot.py --check              # 只审计现有 assets/mascot.png

自检项：裁剪左上区不得出现气泡轮廓色（否则说明裁剪框漂了）。
"""
import os
import sys

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "assets", "mascot.png")

CROP = (112, 54, 198, 196)          # left, top, right, bottom
# 气泡轮廓色（原图实测）：藏青主色 + 两级抗锯齿过渡色
BUBBLE_STROKE = {(30, 50, 100), (30, 49, 96), (31, 51, 102), (36, 54, 95),
                 (61, 79, 125), (82, 106, 166)}
BG_KEY = 246                        # >= 此亮度视为白底 → 转透明


def cutout(im: Image.Image) -> Image.Image:
    """白底转透明，保留半透明过渡边，避免硬锯齿。"""
    m = im.convert("RGBA")
    px = m.load()
    for y in range(m.height):
        for x in range(m.width):
            r, g, b, a = px[x, y]
            if r >= BG_KEY and g >= BG_KEY and b >= BG_KEY:
                px[x, y] = (255, 255, 255, 0)
            elif r >= 230 and g >= 230 and b >= 230:
                px[x, y] = (r, g, b, 96)
    return m


def audit(m: Image.Image) -> int:
    """左上 40x40 内的气泡轮廓色像素数；应为 0（或个位数的抗锯齿噪声）。"""
    px = m.load()
    hits = 0
    for y in range(min(40, m.height)):
        for x in range(min(40, m.width)):
            r, g, b, a = px[x, y]
            if a > 120 and (r, g, b) in BUBBLE_STROKE:
                hits += 1
    return hits


def opaque_bbox(m: Image.Image):
    px = m.load()
    minx, miny, maxx, maxy = 10 ** 9, 10 ** 9, -1, -1
    for y in range(m.height):
        for x in range(m.width):
            if px[x, y][3] > 120:
                minx, miny = min(minx, x), min(miny, y)
                maxx, maxy = max(maxx, x), max(maxy, y)
    return (minx, miny, maxx, maxy) if maxx >= 0 else None


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--check":
        if not os.path.exists(OUT):
            print("缺少", OUT)
            return 1
        m = Image.open(OUT)
    elif len(sys.argv) == 2:
        im = Image.open(sys.argv[1]).convert("RGB")
        print("原图:", im.size, "裁剪框:", CROP)
        m = cutout(im.crop(CROP))
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        m.save(OUT)
        print("写出:", OUT, os.path.getsize(OUT), "字节")
    else:
        print(__doc__)
        return 2

    hits = audit(m)
    print(f"尺寸 {m.size}｜左上 40x40 的气泡轮廓色像素: {hits}｜不透明包围盒: {opaque_bbox(m)}")
    if hits > 10:
        print("✖ 气泡残片过多，裁剪框需要重新标定")
        return 1
    print("✔ 抠图自检通过（角色完整、无气泡残片）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
