# -*- coding: utf-8 -*-
"""桌面浮层：鲸鱼娘对话气泡（与浏览器扩展同一套设计语言）。

透明的实现要点：颜色在白底上正常抗锯齿渲染，但 alpha 用**硬边形状蒙版**重写，
再配合 tkinter 的 `-transparentcolor` 抠掉窗外区域 —— 圆角边缘因此没有色键毛边。
"""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageFont, ImageTk

# —— 设计令牌：与 content/card.css 保持一致 ——
NAVY = (30, 50, 100)
INK = (38, 50, 75)
MUTED = (122, 135, 163)
SKIN = (253, 239, 230)
PAPER = (255, 255, 255)
SOFT = (244, 246, 251)
HAIR = (231, 235, 244)
KEY = (255, 0, 255)              # 色键（窗外区域）

MARGIN = 2                        # 气泡描边外留白
BORDER = 2                        # 描边宽
RADIUS = 18
PAD_X, PAD_Y = 15, 13
MASCOT_W = 58
GUTTER = 26                       # 气泡与她之间的天沟
BOTTOM = 34                       # 底部留给她的高度
MAX_W = 340

_FONTS = {}


def _font_path(cjk: bool) -> str:
    win = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in (("msyh.ttc", "msyhbd.ttc") if cjk else ("segoeui.ttf", "seguisb.ttf")):
        p = os.path.join(win, name)
        if os.path.exists(p):
            return p
    return os.path.join(win, "arial.ttf")


def font(size: int, bold: bool = False, cjk: bool = True) -> ImageFont.FreeTypeFont:
    key = (size, bold, cjk)
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(_font_path(cjk) if not bold else _font_path(cjk), size=size)
    return _FONTS[key]


def _is_cjk(ch: str) -> bool:
    """该用雅黑渲染吗。注意必须含**全角标点 U+FF00–FFEF**（，；（）之类）——
    否则这些字会被派给 Segoe UI，缺字形就画成 □（用户：分号逗号变成了方框）。"""
    o = ord(ch)
    return (0x2E80 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or 0x3040 <= o <= 0x30FF
            or 0xAC00 <= o <= 0xD7AF or 0xFF00 <= o <= 0xFFEF or 0xFE30 <= o <= 0xFE4F)


def _runs(text: str):
    """按书写系统切分，中文用雅黑、西文/IPA 用 Segoe UI（雅黑缺 IPA 字形）。"""
    out, cur, cur_cjk = [], [], None
    for ch in text:
        c = _is_cjk(ch)
        if cur_cjk is None or c == cur_cjk or ch == ' ':
            if ch == ' ' and cur and cur_cjk is not None:
                cur.append(ch)
                continue
            cur.append(ch)
            cur_cjk = c if cur_cjk is None else cur_cjk
            continue
        out.append(("".join(cur), cur_cjk))
        cur, cur_cjk = [ch], c
    if cur:
        out.append(("".join(cur), cur_cjk))
    return out


def _draw_line(draw: ImageDraw.ImageDraw, xy, text: str, size: int, bold: bool, color):
    """混排绘制：中文与西文各用其字体，逐段排布。返回总宽。"""
    x, y = xy
    for chunk, cjk in _runs(text):
        f = font(size, bold, cjk)
        draw.text((x, y), chunk, font=f, fill=color)
        x += draw.textlength(chunk, font=f)
    return x - xy[0]


def _line_width(draw, text, size, bold=False) -> float:
    w = 0.0
    for chunk, cjk in _runs(text):
        w += draw.textlength(chunk, font=font(size, bold, cjk))
    return w


def _wrap(draw, text: str, size: int, bold: bool, max_w: float):
    """按宽度折行（对中英混排逐词测量，避免把词从中间截断）。"""
    lines, cur = [], ""
    for token in _split_tokens(text):
        trial = cur + token
        if cur and _line_width(draw, trial, size, bold) > max_w:
            lines.append(cur.rstrip())
            cur = token.lstrip()
        else:
            cur = trial
    if cur.strip():
        lines.append(cur.rstrip())
    return lines or [""]


def _split_tokens(text: str):
    out, cur = [], []
    for ch in text:
        cur.append(ch)
        if ch == ' ' or _is_cjk(ch):
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def render_card(entry: dict, mascot: Image.Image, scale: float = 1.0) -> Image.Image:
    """把词条渲染成一张带气泡、尾点与鲸鱼娘的卡片图（含硬边 alpha）。"""
    s = scale
    pad_r = int((MASCOT_W + GUTTER) * s)
    bottom = int(BOTTOM * s)
    max_w = int(MAX_W * s)
    inner_w = max_w - pad_r - 2 * (MARGIN + BORDER) - 2 * int(PAD_X * s)

    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    f_word, f_body, f_small = int(20 * s), int(13 * s), int(11 * s)

    blocks = []                       # (kind, payload) 用于排版
    blocks.append(("word", entry.get("word") or ""))
    ph = entry.get("phonetics") or {}
    ph_text = "   ".join(x for x in (("英 " + ph["uk"]) if ph.get("uk") else "",
                                     ("美 " + ph["us"]) if ph.get("us") else "") if x)
    if ph_text:
        blocks.append(("phon", ph_text))
    for p in (entry.get("poses") or [])[:8]:
        blocks.append(("pos", (p.get("pos") or "", p.get("meaning") or "")))
    if entry.get("examples"):
        blocks.append(("ex-title", "例句"))
        for ex in entry["examples"][:2]:
            blocks.append(("ex-en", ex.get("en") or ""))
            if ex.get("zh"):
                blocks.append(("ex-zh", ex.get("zh") or ""))
    if entry.get("source"):
        blocks.append(("foot", entry.get("source")))

    # —— 量高 ——
    gap = int(5 * s)
    heights, lines_of = [], {}
    for kind, payload in blocks:
        if kind == "pos":
            pos, meaning = payload
            ls = _wrap(probe, meaning, f_body, False, inner_w - (int(40 * s) if pos else 0))
            # 注意存 (ls, size) 元组，与其它块一致 —— 存裸 ls 的话绘制端 lines_of[idx][0]
            # 会取到「第一行字符串」，for 循环就逐字符迭代（释义被排成一字一行）。
            lines_of[len(heights)] = (ls, f_body)
            heights.append((len(ls), f_body))
        elif kind in ("ex-en", "ex-zh"):
            size = f_body if kind == "ex-en" else int(12 * s)
            ls = _wrap(probe, payload, size, False, inner_w - int(12 * s))
            lines_of[len(heights)] = (ls, size)
            heights.append((len(ls), size))
        elif kind == "word":
            ls = _wrap(probe, payload, f_word, True, inner_w)
            lines_of[len(heights)] = (ls, f_word)
            heights.append((len(ls), f_word))
        else:
            size = int(12.5 * s) if kind == "phon" else f_small
            ls = _wrap(probe, payload, size, False, inner_w)
            lines_of[len(heights)] = (ls, size)
            heights.append((len(ls), size))

    text_h = sum(n * (int(sz * 1.5)) for n, sz in heights) + gap * (len(blocks) - 1)
    mw = int(MASCOT_W * s)
    mh = round(mascot.height * mw / mascot.width)
    bubble_h = int(2 * (MARGIN + BORDER) + 2 * PAD_Y * s) + text_h
    bubble_h = max(bubble_h, mh + int(8 * s))     # 气泡至少要装得下她（loading 态也不能顶出去）
    W = max_w
    H = bubble_h + bottom

    canvas = Image.new("RGBA", (W, H), KEY + (255,))
    draw = ImageDraw.Draw(canvas)

    # —— 气泡：整块白底 + 藏青描边 + 圆角（**不做透明**，深色页面上也看得清）——
    bx0, by0 = MARGIN, MARGIN
    bx1, by1 = W - MARGIN, bubble_h - MARGIN
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=int(RADIUS * s), fill=PAPER,
                           outline=NAVY, width=max(1, int(BORDER * s)))

    # —— 正文 ——
    y = by0 + int(PAD_Y * s)
    for idx, (kind, payload) in enumerate(blocks):
        if kind == "word":
            for ln in lines_of[idx][0]:
                _draw_line(draw, (bx0 + int(PAD_X * s), y), ln, f_word, True, NAVY)
                y += int(f_word * 1.5)
        elif kind == "phon":
            for ln in lines_of[idx][0]:
                _draw_line(draw, (bx0 + int(PAD_X * s), y), ln, int(12.5 * s), False, MUTED)
                y += int(12.5 * s * 1.5)
        elif kind == "pos":
            pos, meaning = payload
            x = bx0 + int(PAD_X * s)
            if pos:
                x += _draw_line(draw, (x, y), pos, int(11.5 * s), True, NAVY) + int(6 * s)
            ls, _sz = lines_of[idx]
            for ln in ls:
                _draw_line(draw, (x, y), ln, f_body, False, INK)
                y += int(f_body * 1.5)
                x = bx0 + int(PAD_X * s)
        elif kind == "ex-title":
            _draw_line(draw, (bx0 + int(PAD_X * s), y), payload, f_small, True, MUTED)
            y += int(f_small * 1.5)
        elif kind in ("ex-en", "ex-zh"):
            ls, size = lines_of[idx]
            x0 = bx0 + int(PAD_X * s) + int(9 * s)
            draw.rectangle([x0 - int(7 * s), y + 1, x0 - int(5 * s), y + int(size * 1.4)], fill=HAIR)
            for ln in ls:
                _draw_line(draw, (x0, y), ln, size, False, INK if kind == "ex-en" else MUTED)
                y += int(size * 1.5)
        elif kind == "foot":
            _draw_line(draw, (bx0 + int(PAD_X * s), y), payload, f_small, False, MUTED)
            y += int(f_small * 1.5)
        y += gap

    # —— 鲸鱼娘：贴在整个对话框的右下角（白底内，不透明） ——
    her = mascot.resize((mw, mh), Image.LANCZOS)
    mx, my = W - mw - int(6 * s), by1 - int(2 * s) - mh
    canvas.paste(her, (mx, my), her)

    # —— 尾点按用户要求**不画**（曾压在她脸上，看起来像多了一个黑色小圈圈）——
    pass

    # —— 硬边 alpha：气泡圆角矩形 ∪ 她的轮廓（尾点已按要求去掉）——
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([bx0, by0, bx1, by1], radius=int(RADIUS * s), fill=255)
    her_alpha = her.split()[3]
    mask.paste(her_alpha, (mx, my), her_alpha)
    canvas.putalpha(mask)
    return canvas


def load_mascot(path: str) -> Image.Image:
    return Image.open(path).convert("RGBA")


class Bubble(tk.Toplevel):
    """无边框置顶浮层：承载渲染好的卡片图；鼠标移入钉住、移出收起；点击复制。

    内容**可滚动**（滚轮 + 细滚动条）：词条长时卡片会比屏幕高，必须能滑着看全，
    所以窗口高度封顶（屏高的 MAX_H_RATIO），超出就滚。"""

    MAX_H_RATIO = 0.72          # 窗口最高占屏高比例

    def __init__(self, master, on_copy=None, on_leave=None, on_enter=None, on_click=None):
        super().__init__(master)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        key = "#%02x%02x%02x" % KEY
        self.wm_attributes("-transparentcolor", key)
        self.on_copy = on_copy
        self.on_leave = on_leave
        self.on_enter = on_enter
        self.on_click = on_click
        self._photo = None
        self.canvas = tk.Canvas(self, bd=0, highlightthickness=0, bg=key, cursor="arrow")
        self.sb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview, width=9)
        self.canvas.configure(yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda e: self.on_enter and self.on_enter())
        self.canvas.bind("<Leave>", lambda e: self.on_leave and self.on_leave())
        self.canvas.bind("<Button-1>", lambda e: self.on_click and self.on_click())
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.withdraw()

    def _wheel(self, e):
        self.canvas.yview_scroll(-int((e.delta or 0) / 120), "units")

    def show(self, img: Image.Image, x: int, y: int):
        self._photo = ImageTk.PhotoImage(img.convert("RGB"))
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        w, h = img.size
        vw = self.winfo_screenwidth()
        vh = self.winfo_screenheight()
        view_h = int(min(h, vh * self.MAX_H_RATIO))
        self.canvas.configure(scrollregion=(0, 0, w, h))
        left = x + 14 if x + 14 + w + 10 < vw else max(4, x - w - 24)
        top = y + 18 if y + 18 + view_h < vh else max(4, y - view_h - 18)
        self.geometry(f"{w + 10}x{view_h}+{int(left)}+{int(top)}")
        self.canvas.yview_moveto(0)          # 每次都从顶部开始看
        self.deiconify()
        self.lift()
        self._force_topmost()

    def _force_topmost(self):
        """确保浮层压在其它窗口之上 —— 光靠 wm_attributes('-topmost') 不够可靠。"""
        try:
            import win32con
            import win32gui
            hwnd = int(self.frame(), 16) or self.winfo_id()
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        except Exception:
            pass

    def hide(self):
        self.withdraw()
