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
    o = ord(ch)
    return 0x2E80 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or 0x3040 <= o <= 0x30FF or 0xAC00 <= o <= 0xD7AF


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
            lines_of[len(heights)] = ls
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
            for ln in lines_of[idx][0]:
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

    # —— 尾点：两颗「白底 + 藏青描边」小圆，挂在气泡右下角外（与原图同款）——
    r1, r2 = int(6.5 * s), int(4 * s)
    d1 = (bx1 - int(2 * s) - r1, by1 + int(9 * s) + r1)
    d2 = (d1[0] + int(11 * s), d1[1] + int(7 * s))
    for (cx, cy), r in ((d1, r1), (d2, r2)):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PAPER,
                     outline=NAVY, width=max(1, int(BORDER * s)))

    # —— 鲸鱼娘：站在气泡右下角的白色区域里（不透明） ——
    her = mascot.resize((mw, mh), Image.LANCZOS)
    mx, my = W - mw - int(10 * s), by1 - int(2 * s) - mh
    canvas.paste(her, (mx, my), her)

    # —— 硬边 alpha：气泡圆角矩形 ∪ 两颗尾点 ∪ 她的轮廓 ——
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([bx0, by0, bx1, by1], radius=int(RADIUS * s), fill=255)
    for (cx, cy), r in ((d1, r1), (d2, r2)):
        md.ellipse([cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1], fill=255)
    her_alpha = her.split()[3]
    mask.paste(her_alpha, (mx, my), her_alpha)
    canvas.putalpha(mask)
    return canvas


def load_mascot(path: str) -> Image.Image:
    return Image.open(path).convert("RGBA")


class Bubble(tk.Toplevel):
    """无边框置顶浮层：承载渲染好的卡片图；鼠标移入钉住、移出收起；点击复制。"""

    def __init__(self, master, on_copy=None, on_leave=None):
        super().__init__(master)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.wm_attributes("-transparentcolor", "#%02x%02x%02x" % KEY)
        self.on_copy = on_copy
        self.on_leave = on_leave
        self._photo = None
        self.label = tk.Label(self, bd=0, bg="#%02x%02x%02x" % KEY, cursor="arrow")
        self.label.pack()
        self.label.bind("<Enter>", lambda e: self._cancel_leave())
        self.label.bind("<Leave>", lambda e: self.on_leave and self.on_leave())
        self.label.bind("<Button-1>", lambda e: self.on_copy and self.on_copy())
        self.withdraw()

    def _cancel_leave(self):
        pass

    def show(self, img: Image.Image, x: int, y: int):
        self._photo = ImageTk.PhotoImage(img.convert("RGB"))
        self.label.configure(image=self._photo)
        w, h = img.size
        vw = self.winfo_screenwidth()
        vh = self.winfo_screenheight()
        left = x + 14 if x + 14 + w < vw else max(4, x - w - 14)
        top = y + 18 if y + 18 + h < vh else max(4, y - h - 18)
        self.geometry(f"{w}x{h}+{int(left)}+{int(top)}")
        self.deiconify()
        self.lift()

    def hide(self):
        self.withdraw()


class Panel(tk.Tk):
    """控制面板：启用开关、驻留秒数、引擎状态、退出。"""

    def __init__(self, cfg: dict, on_change, on_quit):
        super().__init__()
        self.title("Easy Translator · 桌面取词")
        self.wm_attributes("-topmost", True)
        self.geometry("300x176")
        self.resizable(False, False)
        self.cfg = cfg
        self.on_change = on_change

        self.enabled = tk.BooleanVar(value=cfg.get("enabled", True))
        tk.Checkbutton(self, text="启用悬停取词", variable=self.enabled,
                       command=lambda: on_change("enabled", self.enabled.get())).pack(anchor="w", padx=14, pady=(12, 2))

        row = tk.Frame(self)
        row.pack(anchor="w", padx=14, pady=4)
        tk.Label(row, text="驻留").pack(side="left")
        self.dwell = tk.Scale(row, from_=2, to=10, resolution=1, orient="horizontal", length=170,
                              command=lambda v: on_change("dwell", float(v)))
        self.dwell.set(cfg.get("dwell", 5))
        self.dwell.pack(side="left", fill="x", expand=True)
        tk.Label(row, text="秒").pack(side="left")

        self.status = tk.Label(self, text="引擎：有道词典", anchor="w", fg="#5b6b8c")
        self.status.pack(anchor="w", padx=14, pady=(2, 0))
        self.hint = tk.Label(self, text="鼠标停在任意英文单词上约 5 秒即可查词", anchor="w", fg="#8b97ad", wraplength=270)
        self.hint.pack(anchor="w", padx=14, pady=(0, 4))
        tk.Button(self, text="退出", command=on_quit).pack(anchor="e", padx=14, pady=(2, 10))

    def set_status(self, text: str):
        self.status.configure(text=text)
