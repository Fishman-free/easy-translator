# -*- coding: utf-8 -*-
"""屏幕取词：UIA（Windows 辅助功能）为主，视觉模型 OCR 为兜底。

实测（2026-09-23，Windows 11 + Python 3.14 + uiautomation 2.0.29）：
  · `TextPattern.RangeFromPoint(x, y)` + `ExpandToEnclosingUnit(TextUnit.Word)`
    能精确取到光标下那个英文单词，浏览器、记事本、Word、Electron 系应用都支持；
  · 词下方偏一点（约 6px）也能取到 —— 与浏览器扩展的行盒容差一致；
  · 取不到的情形（图片、游戏、自绘 UI）交给视觉模型 OCR 兜底；两者都没有则静默。
"""
from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.request

from PIL import Image, ImageDraw

from .lookup import extract_word_at, is_english_word, is_letter_like, CJK

try:
    import uiautomation as auto
except Exception:                     # 未装依赖时仍可只用 OCR 兜底
    auto = None

TEXTUNIT_WORD = 2                     # IUIAutomation TextUnit_Word

# UIA 走树单次要 ~500ms（实测 513ms），而守护每轮轮询都要调一次——驻留 2 秒 = 十几轮，
# 光这一项就吃掉 2 秒以上。按 12px 网格缓存一小段时间，驻留期间的轮询变成内存命中。
_UIA_CACHE: dict = {}
_UIA_TTL = 1.5


def word_at_point_uia(x: int, y: int):
    """（带网格缓存）落点 → (单词, 是否看到文字)。"""
    key = (int(x) // 12, int(y) // 12)
    now = time.time()
    hit = _UIA_CACHE.get(key)
    if hit is not None and now - hit[0] < _UIA_TTL:
        globals()["_LAST_UIA_REASON"] = hit[3] + "（缓存）"
        return hit[1], hit[2]
    word, saw = _word_at_point_uia_uncached(x, y)
    if len(_UIA_CACHE) > 512:
        _UIA_CACHE.clear()
    _UIA_CACHE[key] = (now, word, saw, globals().get("_LAST_UIA_REASON", ""))
    return word, saw


_LAST_UIA_REASON = ""          # 最近一次 UIA 判定的原因（只写进轨迹日志，便于定位）


def _word_at_point_uia_uncached(x: int, y: int):
    """落点 → (单词, 是否看到文字)。

    第二个返回值很关键：辅助功能说「这里有文字，但不是英文」时，
    必须就此静默（中文上不弹窗的产品铁律）；只有「根本没有文字」才轮到 OCR 兜底。
    """
    if auto is None:
        return None, False
    global _LAST_UIA_REASON
    _LAST_UIA_REASON = ""
    try:
        ctrl = auto.ControlFromPoint(int(x), int(y))
    except Exception:
        return None, False
    if ctrl is None:
        _LAST_UIA_REASON = "光标处没有控件"
        return None, False

    node = ctrl
    for _ in range(24):
        if node is None:
            break
        try:
            pattern = node.GetTextPattern()
        except Exception:
            pattern = None
        if pattern is not None:
            try:
                rng = pattern.RangeFromPoint(int(x), int(y))
                if rng is None:
                    return None, False
                rng.ExpandToEnclosingUnit(TEXTUNIT_WORD)
                got = (rng.GetText(64) or "").strip()
            except Exception:
                return None, False
            if not got:
                return None, False
            # ① 先判定这段文字到底在不在光标底下 —— 这是「虚空索敌」的唯一闸门。
            #   ExpandToEnclosingUnit 会把落点扩展成「邻近的词」；图片/画布/带缩放变换的
            #   容器（PDF 阅读器、Electron）尤其会给出「在别处」的文字。
            #   **拿不到矩形 = 无法验证**：此时绝不能信这个词（否则光标停在一片空白上也会
            #   弹出一个远处的词），一律交给 OCR 按像素读（它有自己的墨迹/形状/位置闸门）。
            try:
                rects = rng.GetBoundingRectangles()
            except Exception:
                rects = None
            if not rects:
                _LAST_UIA_REASON = "拿不到文字矩形→转OCR"
                return None, False
            inside_rect = None
            for r in rects:
                if (r.left - 4 <= x <= r.right + 4 and
                        r.top - 4 <= y <= r.bottom + 4):
                    inside_rect = r
                    break
            if inside_rect is None:
                gap = min(max(max(r.left - x, x - r.right),
                              max(r.top - y, y - r.bottom)) for r in rects)
                if gap > 24:              # 不是紧贴的词缝 → 文字在别处 → 交 OCR
                    _LAST_UIA_REASON = f"文字在别处(距{gap:.0f}px)→转OCR"
                    return None, False
                _LAST_UIA_REASON = "词缝空白→静默"
                return None, True         # 词缝空白：按铁律静默
            # 矩形确实包含光标，但大得像整个容器（有些控件返回的是容器矩形而不是词的）
            # → 词未必在光标下，仍不可信 → 交 OCR
            if (inside_rect.right - inside_rect.left) > 600 or \
               (inside_rect.bottom - inside_rect.top) > 200:
                _LAST_UIA_REASON = (
                    f"矩形像容器({int(inside_rect.right - inside_rect.left)}x"
                    f"{int(inside_rect.bottom - inside_rect.top)})→转OCR")
                return None, False
            # 取回来的可能是「词 + 尾随空格」甚至标点，统一过取词闸门
            found = extract_word_at(got, 0)
            if found["word"]:
                return found["word"], True
            for cand in _tokenize(got):
                if is_english_word(cand):
                    _LAST_UIA_REASON = "命中英文词:" + cand[:24]
                    return cand, True
            for ch in got:                 # 希腊字母 / 花体·双线体等变体字母：内置表有读音
                if is_letter_like(ch):
                    _LAST_UIA_REASON = "命中数学/希腊字母:" + ch
                    return ch, True
            # 剩下的情况：这段文字确实在光标下，但它不是英文/希腊字母/数学变体。
            #   · 含中文 → 按产品铁律静默（中文上绝不弹窗）；
            #   · 其它（数字、符号、箭头、空白…）→ 报「这里没文字」，交给 OCR 按像素再试
            #     （数学符号 PDF 就靠这一步；OCR 读到中文会返回 null，依旧静默）
            if CJK.search(got):
                _LAST_UIA_REASON = "光标下是中文→静默"
                return None, True
            _LAST_UIA_REASON = "光标下非英文（数字/符号）→转OCR"
            return None, False
        try:
            node = node.GetParentControl()
        except Exception:
            return None, False
    _LAST_UIA_REASON = "往上找不到 TextPattern"
    return None, False


def _tokenize(s: str):
    out, cur = [], []
    for ch in s or "":
        if ch.isalpha() or ch in "'-\u2019":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


# 视觉取词的提示词（抽成模块常量：回归测试复用同一份原文，避免测试与生产漂移）
OCR_PROMPT = ("图中有一个红色圆圈，圆圈只是鼠标位置的标记（它不是字符，不要把它读成 X 或 ○）。\n"
              "重要：**只有当圆圈正好圈住一个字母时才输出它**；如果圈住的是线条、边框、表格线、\n"
              "图标、色块、空白或什么都没有 → 输出 {\"word\":null}。\n"
              "注意：公式、图表、表格、截图里的**英文单词**照常读出来（如 Fraction、Exponent、Bias）；\n"
              "但圈住的是纯符号（+ − × ÷ = ± 括号、上下标、孤立的数字）→ {\"word\":null}。\n"
              "确认是字母后，按下面规则只输出一个 JSON，不要解释：\n"
              "- 圈住的是英文字母 → 输出它所在的**完整英文单词**，并**保持原样大小写**"
              "（IEEE、NPU、SEI 不要改成小写）：{\"word\":\"word\"}\n"
              "- 圈住的是一个孤立的单个字母（数学变量，如 F X n，也可能写成花体 ℱ ℒ 𝒩）"
              "→ 输出这个字母本身：{\"word\":\"F\"}\n"
              "- 圈住的是希腊字母 → 原样输出该字母（如 Ω α λ β）：{\"word\":\"Ω\"}\n"
              "- 圈住的是花体/双线体/哥特体字母（如 ℒ ℝ 𝔼 𝒩 𝔤 𝓛 ℱ）→ 原样输出该字符：{\"word\":\"ℒ\"}\n"
              "- 圈住的是中文/数字/标点/空白/什么都没有 → {\"word\":null}")


def _grab_png(x: int, y: int, w: int = 140, h: int = 56) -> bytes | None:
    """截取光标附近一小块（要小：块大了会把邻行的英文也收进来，误判成\"指到的词\"）。"""
    try:
        from PIL import ImageGrab
    except Exception:
        return None
    try:
        img = ImageGrab.grab(bbox=(x - w // 2, y - h // 2, x + w // 2, y + h // 2), all_screens=True)
    except Exception:
        return None
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


_OCR_CACHE: dict = {}          # (格, ) → (时间戳, 单词或 None)：短期去重
_POS_SPOT = None               # (x, y, word)：识别成功的位置（光标没移开就复用）
_FAIL_SPOT = None              # (x, y)：识别失败的位置（光标没移开就不重试）
# 游戏守护标记（可选，环境变量 ET_GAMING_FLAG 指定）：文件存在时不发起 OCR，
# 避免把本地视觉模型重新拉回显存（打游戏时抢显存会卡）。
GAMING_FLAG = os.environ.get("ET_GAMING_FLAG")


def _has_ink(img, half_w: int = 12, half_h: int = 14) -> bool:
    """光标**正下方**那一小块里，有没有**像字母**的笔迹。

    三层判定，逐层收紧：
      ① 位置：只看 ±12×±14 像素（150% 缩放下约半个字符宽）——窗口开大（曾用 ±26×±20，
         约一个字符宽）会出现「大范围索敌」：光标落在字缝或公式空白里也算有笔迹，
         然后模型从宽截图里挑个字符读出来。
      ② 数量：至少 6 个暗像素采样点——纯空白直接判空、不问模型（省 1-2 秒，也杜绝幻觉）。
      ③ **形状**：细而长且横贯/纵贯窗口的（边框 / 表格线 / 下划线）、包围盒超过 44px 的
         （图标 / 色块）、或把包围盒填满的（纯色块 / 照片纹理）→ 判空。

    「笔迹」是**相对底色**判定的：底色优先取裁剪图**外圈**（光标窗口之外的背景），
    与底色差 >40 的像素才算笔迹 —— 这样**浅底深字**和**深底浅字**（暗色主题）都成立，
    **红字也照样算笔迹**（判定必须在「还没画红圈」的原图上做，否则红字会被当成锚点滤掉）。
    整窗同色时：与底色明显不同 → 是大字笔画把窗口盖满了，算有笔迹；与底色一样 → 空白。

    剩下的是不是「字母」由视觉模型按提示词确认（线条/图标/中文/标点/空白一律输出 null）。"""
    try:
        px = img.load()
        w, h = img.size
        cx, cy = w // 2, h // 2
        x0, x1 = max(0, cx - half_w), min(w, cx + half_w)
        y0, y1 = max(0, cy - half_h), min(h, cy + half_h)
        samples = []
        for yy in range(y0, y1, 2):        # 隔行隔列采样，够用且快
            for xx in range(x0, x1, 2):
                samples.append((xx, yy, px[xx, yy][:3]))
        if len(samples) < 12:
            return True
        # 参照底色**不能**只取光标窗口自己的中位色：大字号（公式/幻灯片/截图放大）的笔画
        # 比 ±12×±14 这个窗口还粗，窗口里整块都是字色，「和自己比」永远差 0 →
        # 误判「没有笔迹」（用户报「截屏/公式里的红字识别不了」，根因就在这）。
        # 所以底色改从裁剪图**外圈**取（光标窗口之外，通常是纸面/背景）。
        border = []
        for xx in range(2, w - 2, 4):
            for yy in (2, 4, h - 5, h - 3):
                border.append(px[xx, yy][:3])

        def med(vals):
            v = sorted(vals)
            return v[len(v) // 2] if v else 0

        ref = border if len(border) >= 24 else [s[2] for s in samples]
        # 底色 = 外圈各通道中位数（RGB 三通道分别取，**不能用亮度**：黄字在白底上亮度
        # 几乎相同 → 会误判「没有笔迹」，荧光标注/黄标题这类全漏）
        bgc = (med([c[0] for c in ref]), med([c[1] for c in ref]), med([c[2] for c in ref]))

        def far(c3):
            return max(abs(c3[0] - bgc[0]), abs(c3[1] - bgc[1]), abs(c3[2] - bgc[2])) > 40

        ink = [s for s in samples if far(s[2])]      # 与（外圈）底色色差 >40 才算笔迹
        if len(ink) < 6:
            # 整窗同色：若它和外圈底色明显不同 → 是「大字笔画把窗口整个盖住」，算有笔迹；
            # 若它和外圈底色一样（各通道都近）→ 真的空白（或纯色区域），判空。
            winc = (med([s[2][0] for s in samples]), med([s[2][1] for s in samples]),
                    med([s[2][2] for s in samples]))
            if len(border) >= 24 and far(winc):
                ink = samples
            else:
                return False               # ② 空白（或纯色区域）
        xs = [s[0] for s in ink]
        ys = [s[1] for s in ink]
        bw, bh = max(xs) - min(xs), max(ys) - min(ys)
        if bw > 44 or bh > 44:
            return False                   # ③ 太大：图标 / 色块 / 超大标题
        span_w, span_h = (x1 - x0) - 6, (y1 - y0) - 6
        if min(bw, bh) <= 6 and (bw >= span_w or bh >= span_h):
            return False                   # ③ 细而长且横贯/纵贯窗口 → 边框、表格线、下划线
        # 曾经这里还有一条「把包围盒填满 → 判色块」：已删除 —— 大字号（公式/截图放大）
        # 的笔画本来就可能把光标窗口填满，那条判据会让用户的红字大字永远判空。
        # 真色块交给模型判空（提示词里「色块 → null」），代价只是多一次推理。
        return True                        # 剩下的是不是「字母」交给模型判定
    except Exception:
        return True                        # 判不了就不拦


def _line_height(img) -> int:
    """光标所在**那一行文字的高度**（从中心行向上下扩展，遇到空白行就停）。

    用途：判断该不该放大裁剪。正文小字（~24px）用 140×56 正合适；但 PDF/幻灯片里的
    公式大字可能有 50px+，一个词就有 200px 宽 —— 固定 140 宽会把词从中间切断，
    实测只能读到 Bra / tion / ent 这种碎片（用户报的「公式里翻译不了」就是这个）。
    """
    try:
        rgb = img.convert("RGB")
        w, h = rgb.size
        px = rgb.load()
        step = max(1, w // 60)
    except Exception:
        return 0

    def med(vals):
        v = sorted(vals)
        return v[len(v) // 2] if v else 0

    # 底色 = 全图各通道中位数（RGB 分别取 —— 用亮度会让黄字失去行高）
    cols = [[px[xx, yy][:3] for xx in range(0, w, step)] for yy in range(0, h, 2)]
    flat = [c for row in cols for c in row]
    bgc = (med([c[0] for c in flat]), med([c[1] for c in flat]), med([c[2] for c in flat]))

    def far(c3):
        return max(abs(c3[0] - bgc[0]), abs(c3[1] - bgc[1]), abs(c3[2] - bgc[2])) > 40

    def has_row(y):
        n = 0
        for xx in range(0, w, step):
            if far(px[xx, y]):
                n += 1
                if n >= 2:
                    return True
        return False

    mid = h // 2
    if not (has_row(mid) or has_row(mid - 2) or has_row(mid + 2)):
        return 0                       # 光标那一行就是空白 → 不算文字行
    y0 = mid
    while y0 > 0 and has_row(y0 - 1):
        y0 -= 1
    y1 = mid
    while y1 < h - 1 and has_row(y1 + 1):
        y1 += 1
    return y1 - y0 + 1


def _same_spot(x: int, y: int, spot, radius: int = 20) -> bool:
    """光标是否还在上次那个「地方」（半径 20px ≈ 一个字宽）。"""
    return bool(spot) and abs(x - spot[0]) <= radius and abs(y - spot[1]) <= radius


def _screen_rect():
    """虚拟桌面范围（多显示器也正确），用于把裁剪框夹在屏幕内。"""
    try:
        import ctypes
        u = ctypes.windll.user32
        return (u.GetSystemMetrics(76), u.GetSystemMetrics(77),
                u.GetSystemMetrics(76) + u.GetSystemMetrics(78),
                u.GetSystemMetrics(77) + u.GetSystemMetrics(79))
    except Exception:
        return (0, 0, 1920, 1080)


def _grab_rect(rect):
    """按屏幕矩形截图（自动夹在屏幕内）；返回 (图, 该矩形实际左上的屏幕坐标)。"""
    try:
        from PIL import ImageGrab
    except Exception:
        return None, None
    x0, y0, x1, y1 = _screen_rect()
    rx0, ry0 = max(x0, rect[0]), max(y0, rect[1])
    rx1, ry1 = min(x1, rect[2]), min(y1, rect[3])
    if rx1 - rx0 < 4 or ry1 - ry0 < 4:
        return None, None
    try:
        img = ImageGrab.grab(bbox=(rx0, ry0, rx1, ry1), all_screens=True).convert("RGB")
    except Exception:
        return None, None
    return img, (rx0, ry0)


def _word_crop_png(x: int, y: int):
    """裁出「光标所在的那个词」（按墨迹段，而不是按行高估宽）——长词也不会被切断。

    为什么要按墨迹段：实测固定/估算宽度会把 Fraction 这种 8 字母词从中间切断，
    模型只读到 "frac"、"n" 这类碎片（用户报的「公式里翻译不了」的真正原因）。
    返回带红圈的 PNG（红圈画在光标的真实位置，多词粘连时靠它指定目标）；失败返回 None。
    """
    probe, org = _grab_rect((x - 700, y - 100, x + 700, y + 100))
    if probe is None:
        return None
    try:
        w, h = probe.size          # 曾误写 g.load()/g.size（未定义名被 except 吞掉 →
        cx, cy = x - org[0], y - org[1]   # 本函数恒返回 None，「按词裁剪」整条失效；
        #                                   回归测试见 tests/test_word_crop.py）
        cx, cy = x - org[0], y - org[1]
        if not (0 <= cx < w and 0 <= cy < h):
            return None
        step = max(1, w // 140)
        # 底色 = 全图各通道中位数（RGB 分别取；用亮度会让黄字失去墨迹段）
        rgb_px = probe.load()
        flat = [rgb_px[xx, yy][:3] for yy in range(0, h, 4) for xx in range(0, w, step)]

        def med(vals):
            v = sorted(vals)
            return v[len(v) // 2] if v else 0

        bgc = (med([c[0] for c in flat]), med([c[1] for c in flat]), med([c[2] for c in flat]))

        def far(c3):
            return max(abs(c3[0] - bgc[0]), abs(c3[1] - bgc[1]), abs(c3[2] - bgc[2])) > 40

        def row_ink(yy):
            n = 0
            for xx in range(0, w, step):
                if far(rgb_px[xx, yy][:3]):
                    n += 1
                    if n >= 2:
                        return True
            return False

        def col_ink(xx):
            for yy in range(by0, by1 + 1, 2):
                if far(rgb_px[xx, yy][:3]):
                    return True
            return False

        y0 = y1 = cy
        while y0 > 0 and row_ink(y0 - 1):
            y0 -= 1
        while y1 < h - 1 and row_ink(y1 + 1):
            y1 += 1
        lh = max(8, y1 - y0 + 1)
        by0, by1 = max(0, y0), min(h - 1, y1)
        gap_tol = max(8, int(lh * 0.6))        # 词内字间距容忍（大字号字距也宽）
        x0 = x1 = cx
        gap = 0
        xx = cx
        while xx > 0 and gap <= gap_tol:
            if col_ink(xx):
                x0, gap = xx, 0
            else:
                gap += 1
            xx -= 1
        gap = 0
        xx = cx
        while xx < w - 1 and gap <= gap_tol:
            if col_ink(xx):
                x1, gap = xx, 0
            else:
                gap += 1
            xx += 1
        if x1 - x0 < 2:
            return None
        mx, my = int(lh * 0.4) + 4, int(lh * 0.25) + 4
        bx0, bx1 = max(0, x0 - mx), min(w, x1 + mx + 1)
        by0, by1 = max(0, y0 - my), min(h, y1 + my + 1)
        min_w = int(lh * 3)                    # 段太窄（≈一个字母）→ 至少给 3×行高 的视野，
        if bx1 - bx0 < min_w:                  # 红圈仍在光标处，由模型判断是哪个词里的字母
            c = (bx0 + bx1) // 2               #（用户报的「整词只读到一个字母」就是这个）
            bx0, bx1 = max(0, c - min_w // 2), min(w, c + min_w // 2)
        if bx1 - bx0 > 900:                    # 整段太长（多半是整行粘连）→ 退回首尾截断
            bx0, bx1 = max(0, cx - 450), min(w, cx + 450)
        crop = probe.crop((bx0, by0, bx1, by1))
        d = ImageDraw.Draw(crop)
        rx, ry = max(20, int(lh * 0.42)), max(14, int(lh * 0.3))
        d.ellipse([cx - bx0 - rx, cy - by0 - ry, cx - bx0 + rx, cy - by0 + ry],
                  outline=(255, 0, 0), width=2)
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        _trace(f"({x},{y}) 按词裁剪：行高 {lh}px → {crop.width}x{crop.height}")
        return buf.getvalue()
    except Exception:
        return None


def _zoom_crop_if_large(x: int, y: int, png_std: bytes) -> bytes:
    """小字原样返回（140×56 够用）；大字按行高放大裁剪，并同步放大红圈锚点。

    判据用**行高**（墨迹带高度，不是字号）：正文 ≈14–20px 不触发（保持手上验证过
    的老行为不变）；≥24px（公式、幻灯片、放大的 PDF）才放大 —— 实测 40px 字体的
    墨迹带只有 28px，所以阈值不能定在 32。宽度按 5.5×行高估一个词的长度
    （8 字符词 ≈ 4.4h，11 字符 ≈ 6h），上限 520 —— 再大就超出「一块」的合理范围了。
    """
    try:
        probe = _grab_png(x, y, w=420, h=220)
        if not probe:
            return png_std
        lh = _line_height(Image.open(io.BytesIO(probe)).convert("RGB"))
    except Exception:
        return png_std
    if lh < 24:
        return png_std
    cw = min(520, max(140, int(lh * 7)))     # 7×行高 ≈ 12 字符，够装 Significand 这类长词
    ch = min(160, max(56, int(lh * 2.2)))
    raw = _grab_png(x, y, w=cw, h=ch)
    if not raw:
        return png_std
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        d = ImageDraw.Draw(img)
        cx, cy = img.width // 2, img.height // 2
        rx, ry = max(20, int(lh * 0.42)), max(14, int(lh * 0.3))
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=(255, 0, 0), width=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        _trace(f"({x},{y}) 大字模式：行高 {lh}px → 裁剪 {cw}x{ch}，红圈 ±{rx}x±{ry}")
        return buf.getvalue()
    except Exception:
        return png_std


def word_at_point_ocr(x: int, y: int, cfg: dict):
    """视觉模型 OCR 兜底（本地 Ollama 之类）。识别不到英文一律返回 None。

    位置粘性（用户要求）：同一处**识别失败**之后，只要鼠标没有移开（20px 内），就不再重新
    识别——不反复打模型、不会过一会儿又冒出来。识别成功同理：光标没移开就直接复用结果。
    移开超过 20px（换了个地方）粘性自动解除。"""
    global _POS_SPOT, _FAIL_SPOT
    cfg = cfg or {}
    if _same_spot(x, y, _POS_SPOT):
        return _POS_SPOT[2]              # 同一处已识别成功：原地复用，不重复打模型
    if _same_spot(x, y, _FAIL_SPOT):
        return None                      # 同一处已失败：鼠标没动 → 不重试
    # 配置是嵌套的（model.baseUrl / model.visionModel，与扩展 settings-core 同构）；
    # 早期这里读的是扁平键，永远取不到 → OCR 兜底被静默短路。扁平键仅作兼容回退。
    m = cfg.get("model") or {}
    base = (m.get("baseUrl") or cfg.get("baseUrl") or "").rstrip("/")
    model = m.get("visionModel") or cfg.get("visionModel") or ""
    if not base or not model:
        return None
    if (cfg.get("imageOcr") or {}).get("enabled") is False:
        return None                      # 设置里关掉了图片取词
    if GAMING_FLAG and os.path.exists(GAMING_FLAG):
        return None                      # 游戏中：静默，不加载视觉模型抢显存
    # 缓存：驻留期间同一位置不重复打模型；识别不到/服务不可用也不狂拍（负缓存 30s）
    key = (int(x) // 12, int(y) // 12)
    now = time.time()
    hit = _OCR_CACHE.get(key)
    if hit is not None:
        ts, w = hit
        if w and now - ts < 30:      # 同一个词：30 秒内重悬停直接命中，不再打模型
            return w
        if not w and now - ts < 30:
            return None
    png = _grab_png(x, y)
    if not png:
        return None
    try:
        raw = Image.open(io.BytesIO(png)).convert("RGB")
    except Exception:
        return None
    # 空白区域直接判空（不问模型）：省时间 + 杜绝「空白处冒出字母」的幻觉。
    # ★ 必须在**还没画红圈**的原图上判定：红圈是红像素，而用户的红字也是红像素，
    #   在画了红圈的图上判定就得靠「滤掉红色」来排除锚点 —— 那会把红字一起滤掉，
    #   导致红字窗口里只剩背景、永远判「没有笔迹」（用户报「红字/公式识别不了」的根因）。
    if not _has_ink(raw):
        _OCR_CACHE[key] = (now, None)
        _FAIL_SPOT = (x, y)              # 这处失败了：鼠标没移开就不再重试
        _dump_ocr(png, x, y, "gate 无笔迹(判空)")
        _trace(f"({x},{y}) OCR 跳过：光标处没有笔迹（空白）")
        return None
    # 再画锚点：ImageGrab 不带鼠标光标，模型在多个词的截图里不知道指哪个词
    #（实测「hello world」指 world 会返回 hello）。锚点用**红色圆圈**而不是红叉：
    # 实测模型会把红叉本身当成字母 X 报出来（「空白处冒出 x」的真凶）。
    try:
        img = raw.copy()
        d = ImageDraw.Draw(img)
        cx, cy = img.width // 2, img.height // 2
        d.ellipse([cx - 20, cy - 14, cx + 20, cy + 14], outline=(255, 0, 0), width=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png = buf.getvalue()
    except Exception:
        pass
    # 优先「按词裁剪」：把光标所在的整个墨迹段（一个词）裁进来，长词不会被切断
    wc = _word_crop_png(x, y)
    if wc:
        png = wc
    else:
        # 退化路径：大字按行高放大，否则保持 140×56
        png = _zoom_crop_if_large(x, y, png)
    _dump_ocr(png, x, y, "crop")
    prompt = OCR_PROMPT
    body = {
        "model": model, "temperature": 0, "max_tokens": 60,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}},
        ]}],
    }
    try:
        req = urllib.request.Request(
            base + "/chat/completions", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + (cfg.get("apiKey") or "none")})
        # 冷启动 1–3 分钟：超时给足余量，否则「第一次永远查不到」（用户会以为功能坏了）。
        # 启动时另有 warmup_vision() 把模型预热进内存，正常路径只要几百毫秒。
        with urllib.request.urlopen(req, timeout=float(cfg.get("visionTimeoutSec") or 90.0)) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        _dump_ocr(None, x, y, "resp=" + (content or "")[:160].replace("\n", " "))
    except Exception:
        _OCR_CACHE[key] = (now, None)      # 服务不可用也负缓存，避免狂拍
        _FAIL_SPOT = (x, y)                # 这处打不通模型：鼠标没移开就不再重试
        return None
    from .lookup import extract_json, accept_ocr_word
    obj = extract_json(content) if isinstance(content, str) else None
    if isinstance(obj, dict) and isinstance(obj.get("word"), str):
        w = obj["word"].strip().strip("`\"' \t.,;:!?()[]{}").strip()
        if w.lower() in ("null", "none", "nan", "无", "没有", "—", "-"):
            w = ""                       # 模型有时把 JSON null 写成字符串 "null"
        w0 = w
        # 取词闸门（用户要求）：普通英文单词 / 希腊字母·数学变体才收；
        # **单个普通英文字母不收** —— 图片里单字母遍地都是，而且「整词被裁成一个字母」
        # 的碎片会冒充它，误弹远多于收益。
        w = w if accept_ocr_word(w) else None
        if not w:
            _dump_ocr(None, x, y, "reject 闸门不认: %r (english=%s, letter_like=%s)"
                      % (w0, is_english_word(w0), is_letter_like(w0)))
        _OCR_CACHE[key] = (now, w)
        _POS_SPOT = (x, y, w)              # 成功：光标没移开就一直复用，不重复打模型
        _FAIL_SPOT = None
        _dump_ocr(None, x, y, "ok word=%r" % w)
        return w
    _OCR_CACHE[key] = (now, None)
    _FAIL_SPOT = (x, y)                    # 没读出可翻译内容 → 记作这处失败
    return None


_TRACE_LAST = None
# —— 排障开关：文件 desktop/ocr_dump.on 存在时，把「模型实际看到的那块图」存到 desktop/ocr_dump/ ——
_DUMP_ON = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "ocr_dump.on"))
_DUMP_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "ocr_dump"))


def _dump_ocr(png, x: int, y: int, extra: str = ""):
    """排障用存证（默认关闭）：只写本机，保留最近 40 张，随时可删。"""
    try:
        if not os.path.exists(_DUMP_ON):
            return
        os.makedirs(_DUMP_DIR, exist_ok=True)
        names = sorted(f for f in os.listdir(_DUMP_DIR) if f.endswith(".png"))
        for old in names[:-40]:
            try:
                os.remove(os.path.join(_DUMP_DIR, old))
            except Exception:
                pass
        stamp = time.strftime("%H%M%S")
        if png:
            with open(os.path.join(_DUMP_DIR, "%s_%d_%d.png" % (stamp, x, y)), "wb") as f:
                f.write(png)
        with open(os.path.join(_DUMP_DIR, "log.txt"), "a", encoding="utf-8") as f:
            f.write("%s (%d,%d) %s\n" % (stamp, x, y, extra))
    except Exception:
        pass


def _trace(msg):
    """轻量轨迹（每个新格子一行）——排查「悬停没反应」用；文件超 256KB 自动清掉。"""
    try:
        p = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        os.pardir, "lookup_trace.log"))
        if os.path.exists(p) and os.path.getsize(p) > 262144:
            os.remove(p)
        with open(p, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def word_at_point(x: int, y: int, cfg: dict):
    """屏幕落点 → 英文单词；什么都取不到就返回 None（调用方必须静默）。

    优先级与产品铁律：
      ① UIA 取到英文 → 用它；
      ② UIA 说这里有文字但不是英文 → **就此静默**（中文上绝不弹窗）；
      ③ 这里根本没有文字（图片、自绘 UI）→ 才用视觉模型 OCR 兜底。
    """
    global _TRACE_LAST
    cell = (int(x) // 12, int(y) // 12)
    tr = cell != _TRACE_LAST
    _TRACE_LAST = cell
    word, saw_text = word_at_point_uia(x, y)
    if tr:
        _trace(f"({x},{y}) UIA={word!r} saw_text={saw_text}"
               f" 原因={globals().get('_LAST_UIA_REASON', '')}")
    if word:
        return word, "uia"
    if saw_text:
        if tr:
            _trace(f"({x},{y}) 静默：UIA 认为此处有文字但非英文/是词缝空白（不走 OCR）")
        return None, ""
    word = word_at_point_ocr(x, y, (cfg or {}).get("model") or {})
    if tr:
        _trace(f"({x},{y}) OCR={word!r} → {'出卡片' if word else '静默'}")
    if word:
        return word, "ocr"
    return None, ""
