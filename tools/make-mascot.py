# -*- coding: utf-8 -*-
"""
从截图里抠出鲸鱼娘立绘（去掉她自带的气泡；气泡由 UI 用代码画，才能随内容伸缩）。

**抠图方法：按连通性，不按颜色。**
她的帽子/围裙/衣领是白色的，与背景同色 —— 早先按「接近白色→透明」抠，
把她整块白色衣服当背景抠掉了（表现为头像和身体缺洞）。正确做法：
  ① 「亮」像素（接近白）视为候选背景，从图片四边灌水连通 → 这些才是真背景；
  ② 被轮廓包住的白（她的帽子/围裙）连不到外面，**保留**；
  ③ 前景取「包含右下角」的连通块 = 她本人（它自带的气泡与尾点是另外的连通块，自动排除）；
  ④ 轮廓内的封闭空洞填实，保证剪影完整。

用法：
    python tools/make-mascot.py <原始截图.png>       # 写出 assets/mascot.png
    python tools/make-mascot.py --check              # 只审计现有 assets/mascot.png

自检（缺一不可）：
  · 头部带、身体带都要有足够的不透明像素（证明头像与身体都抠进来了）
  · 不得混入气泡轮廓色（证明没把她的气泡一起抠进来）
  · 轮廓内无封闭空洞
"""
import os
import sys

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "assets", "mascot.png")

LIGHT = 244                      # >= 此亮度视为「候选背景/白」
# 气泡轮廓色（原图实测）：藏青主色 + 两级抗锯齿过渡色
BUBBLE_STROKE = {(30, 50, 100), (30, 49, 96), (31, 51, 102), (36, 54, 95),
                 (61, 79, 125), (82, 106, 166)}


def _flood(mask, seeds, w, h):
    """在布尔图上四邻域灌水，返回可达集合。"""
    seen = set()
    stack = [s for s in seeds if mask[s[1]][s[0]] and s not in seen]
    for s in stack:
        seen.add(s)
    while stack:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] and (nx, ny) not in seen:
                seen.add((nx, ny))
                stack.append((nx, ny))
    return seen


def extract_character(im: Image.Image, zone=None, seed=None):
    """→ (裁剪图 RGBA, 说明字典)。剪影已填洞，白衣服不会再被抠掉。

    **不要用矩形裁剪框**：她左半边（耳朵/头发/袍角，最远到 x≈68）与她自带的气泡、
    尾点只隔着背景间隙 —— 矩形框要么把她切掉、要么把气泡带进来。正确做法是
    「取含右下角的连通块」：气泡弧线与两颗尾点是各自独立的连通块，自动排除。
    zone 参数仅用于实验性调试。
    """
    if zone:
        im = im.crop(zone)
    w, h = im.size
    px = im.load()
    light = [[(px[x, y][0] >= LIGHT and px[x, y][1] >= LIGHT and px[x, y][2] >= LIGHT)
              for x in range(w)] for y in range(h)]

    border = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + \
             [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    bg = _flood(light, border, w, h)                    # 真背景：从四边连通得到的白

    if seed is None:
        seed = (w - 2, h - 2)                           # 右下角 = 她的衣服
        for r in range(8):
            cand = (w - 2 - r, h - 2 - r)
            if cand not in bg:
                seed = cand
                break

    fg = [[(x, y) not in bg for x in range(w)] for y in range(h)]
    her = _flood(fg, [seed], w, h)                      # 只含角色区里与右下角连通的部分

    xs = [p[0] for p in her]
    ys = [p[1] for p in her]
    box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)

    # —— 填洞：轮廓内的封闭白（她的帽子/围裙）必须算作她的一部分 ——
    # 注意：her 是「本图坐标」，下面的掩码也是本图坐标，别再混用
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    outside = _flood([[(x + x0, y + y0) not in her for x in range(bw)] for y in range(bh)],
                     [(x, 0) for x in range(bw)] + [(x, bh - 1) for x in range(bw)] +
                     [(0, y) for y in range(bh)] + [(bw - 1, y) for y in range(bh)], bw, bh)
    solid = set()
    for y in range(bh):
        for x in range(bw):
            if (x + x0, y + y0) in her or (x, y) not in outside:
                solid.add((x + x0, y + y0))

    art = im.crop(box).convert("RGBA")
    apx = art.load()
    for y in range(art.height):
        for x in range(art.width):
            if (x + x0, y + y0) in solid:
                r, g, b, _a = apx[x, y]
                apx[x, y] = (r, g, b, 255)
            else:
                apx[x, y] = (0, 0, 0, 0)

    # 边缘 1px 羽化：原图在画框右/下把人切开了（切口是硬边深色），而她自然轮廓那侧
    # 是浅色抗锯齿边 —— 两边观感会「颜色不一样」。把 alpha 羽化一层，硬切边就融进白底。
    from PIL import ImageFilter
    alpha = art.split()[3].filter(ImageFilter.GaussianBlur(0.6))
    art.putalpha(alpha)
    info = {"box": box, "size": art.size, "seed": seed, "opaque": len(solid),
            "zone": zone}
    # 她的嘴部位置（肤色区中心）→ 供 UI 把对话气泡的尾巴对准她的嘴
    sx = sy = sn = 0
    for (x, y) in solid:
        r, g, b = im.getpixel((x, y))[:3]
        if r > 235 and 215 < g < 250 and 205 < b < 245 and r > b + 8:
            sx += x
            sy += y
            sn += 1
    info["mouth"] = (round((sx / sn) - box[0], 1), round((sy / sn) - box[1], 1)) if sn > 20 else None
    info["skin_px"] = sn
    return art, info


def audit(m: Image.Image):
    """自检：头/身两带都要有内容；不得混入气泡轮廓色；剪影不得有洞。"""
    w, h = m.size
    px = m.load()

    def band(y0, y1):
        return sum(1 for y in range(max(0, y0), min(h, y1)) for x in range(w) if px[x, y][3] > 120)

    head, body = band(0, int(h * 0.35)), band(int(h * 0.55), h)
    bubble = sum(1 for y in range(h) for x in range(w)
                 if px[x, y][3] > 120 and (px[x, y][0], px[x, y][1], px[x, y][2]) in BUBBLE_STROKE)
    # 剪影内是否还有空洞：轮廓内 alpha=0 的像素个数
    holes = sum(1 for y in range(1, h - 1) for x in range(1, w - 1)
                if px[x, y][3] == 0 and all(px[x + dx, y + dy][3] > 0 for dx, dy in
                                            ((1, 0), (-1, 0), (0, 1), (0, -1))))
    return head, body, bubble, holes


def make_preview(art: Image.Image, path: str):
    """3x 预览（白底与浅灰底各一份并排），供目视检查抠图是否完整。"""
    big = art.resize((art.width * 3, art.height * 3), Image.NEAREST)
    pad = 16
    canvas = Image.new("RGB", (big.width * 2 + pad * 3, big.height + pad * 2), (226, 230, 238))
    for i, bg in enumerate(((255, 255, 255), (238, 241, 246))):
        tile = Image.new("RGB", big.size, bg)
        tile.paste(big, (0, 0), big)
        canvas.paste(tile, (pad + i * (big.width + pad), pad))
    canvas.save(path)
    return path


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--check":
        if not os.path.exists(OUT):
            print("缺少", OUT)
            return 1
        art = Image.open(OUT)
        info = {"box": "-", "size": art.size, "seed": "-", "opaque": "-"}
    elif len(sys.argv) == 2:
        im = Image.open(sys.argv[1]).convert("RGB")
        print("原图:", im.size)
        art, info = extract_character(im)
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        art.save(OUT)
        prev = make_preview(art, os.path.join(REPO, "docs", "mascot-preview.png"))
        print("剪影框:", info["box"], "→ 尺寸", info["size"], "不透明像素", info["opaque"])
        print("嘴部位置（相对剪影左上）:", info.get("mouth"), "肤色像素", info.get("skin_px"))
        print("写出:", OUT, os.path.getsize(OUT), "字节｜预览:", prev)
    else:
        print(__doc__)
        return 2

    head, body, bubble, holes = audit(art)
    w, h = art.size
    print(f"自检：头部带不透明 {head}px（{head * 100 // (w * max(1, int(h * 0.35)))}%）"
          f"｜身体带 {body}px（{body * 100 // (w * max(1, h - int(h * 0.55)))}%）"
          f"｜气泡轮廓色 {bubble}px｜剪影内空洞 {holes}px")

    ok = True
    if head < w * 3:
        print("  ✖ 头部带几乎全空 —— 头像没抠进来")
        ok = False
    if body < w * 3:
        print("  ✖ 身体带几乎全空 —— 身体没抠进来")
        ok = False
    if bubble > 10:
        print("  ✖ 混入了她自带的气泡轮廓")
        ok = False
    if holes > 0:
        print("  ✖ 剪影内还有空洞（白衣服被误抠）")
        ok = False
    print("✔ 抠图自检通过（头身俱全、无气泡残片、剪影无洞）" if ok else "✖ 自检未通过")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
