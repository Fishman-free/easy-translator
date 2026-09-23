# -*- coding: utf-8 -*-
"""
Easy Translator 桌面伴生 · 设置窗口（就是这个伴生程序的「App」主界面）

设计与扩展的设置页保持一致：
  · 布局一一对齐 options/options.html —— 通用 / 本地小模型 / 图片取词 / 数据 四张卡，
    每张卡里是同样的字段、同样的行式（左标签右控件）、同样的说明文字
  · 视觉用鲸鱼娘那套设计语言：纸面白卡 + 藏青 #1E3264 描边/强调 + 右上角立绘 +
    标题做成她的对话气泡（带尾点）—— 与卡片/浮层同一个品牌

配置字段名与 lib/settings-core.js 的 DEFAULTS 一致（dwellMs / examplesCount / model / imageOcr），
避免两端各叫各的；desktop/tests/test_settings.py 会拿 JS 侧逐键比对防漂移。
"""
from __future__ import annotations

import threading

from PIL import Image, ImageDraw

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:                                    # pragma: no cover
    tk = None

# —— 设计令牌（与 content/card.css 的鲸鱼娘语言一致）——
NAVY = "#1e3264"
INK = "#26324b"
MUTED = "#6b7280"
LINE = "#e2e6ef"
BG = "#f4f5f7"
CARD = "#ffffff"
ACCENT = NAVY
OK = "#16a34a"
ERR = "#dc2626"
FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_H2 = ("Microsoft YaHei UI", 9, "bold")


def _header_png(mascot: Image.Image, width: int = 520) -> Image.Image:
    """把标题画成「她的对话气泡」+ 右上角立绘 —— 与卡片同一套画法。"""
    h = 86
    img = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bx1 = width - 96
    d.rounded_rectangle([2, 2, bx1, h - 16], radius=16, fill=(255, 255, 255, 255),
                        outline=(30, 50, 100, 255), width=2)
    # 两颗尾点指向她
    for (cx, cy, r) in ((bx1 - 26, h - 13, 7), (bx1 - 8, h - 5, 4)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 255),
                  outline=(30, 50, 100, 255), width=2)
    mw = 74
    mh = round(mascot.height * mw / mascot.width)
    her = mascot.resize((mw, mh), Image.LANCZOS)
    img.paste(her, (width - mw - 6, h - mh - 2), her)
    return img


class SettingsWindow(tk.Toplevel if tk else object):
    """设置窗口 = 这个伴生程序的主界面。字段与 options/options.html 一一对应。"""

    def __init__(self, master, cfg, save, on_toggle=None, on_quit=None, mascot=None, test_text=None):
        super().__init__(master)
        self.cfg = cfg
        self.save = save
        self.on_toggle = on_toggle
        self.on_quit = on_quit
        self.test_text = test_text
        self.title("Easy Translator — 桌面取词设置")
        self.configure(bg=BG)
        self.geometry("560x720")
        self.minsize(520, 560)

        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=14, pady=(10, 14))

        # —— 标题气泡 + 立绘 ——
        if mascot is not None:
            self._head_img = _header_png(mascot)
            self._head_photo = _to_photo(self._head_img)
            tk.Label(outer, image=self._head_photo, bg=BG, bd=0).pack(anchor="w")

        # —— 状态行：启用开关 + 引擎 ——
        bar = tk.Frame(outer, bg=BG)
        bar.pack(fill="x", pady=(2, 8))
        self.enabled_var = tk.BooleanVar(value=bool(cfg.get("enabled", True)))
        self.enable_btn = tk.Checkbutton(
            bar, text="启用桌面取词", variable=self.enabled_var, command=self._toggle,
            bg=BG, fg=INK, activebackground=BG, activeforeground=INK,
            font=FONT_BOLD, bd=0, highlightthickness=0)
        self.enable_btn.pack(side="left")
        self.status_lbl = tk.Label(bar, text="", bg=BG, fg=MUTED, font=FONT)
        self.status_lbl.pack(side="right")

        # —— 四张卡，与 options/options.html 同序 ——
        # 内容区必须**可滚动**：字段多，窗口不够高时 Tk 的 pack 会给后面的控件
        # 分不到空间、**直接不映射**（表现为"设置窗口缺一整张卡、用不了"）。
        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._cards = tk.Frame(canvas, bg=BG)
        inner = canvas.create_window((0, 0), window=self._cards, anchor="nw")
        self._cards.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(inner, width=e.width))
        try:
            canvas.bind_all("<MouseWheel>",
                            lambda e: canvas.yview_scroll(-int(e.delta / 120), "units"))
        except Exception:
            pass

        self._card_general()
        self._card_model()
        self._card_ocr()
        self._card_data()

        if on_quit:
            tk.Button(outer, text="退出桌面取词", command=on_quit, font=FONT,
                      bg=CARD, fg=INK, activebackground=CARD, bd=1,
                      highlightthickness=1, highlightbackground=LINE).pack(anchor="e", pady=(6, 0))

    # ---------- 卡片：通用 ----------
    def _card_general(self):
        c = self._card("通用")
        self._row_scale(c, "悬停触发时长", "dwellMs", 1000, 15000, 500, lambda v: f"{v / 1000:g} 秒")
        self._row_number(c, "例句条数", "examplesCount", 0, 5)
        self._row_check(c, "显示发音按钮", "showSpeak")

    # ---------- 卡片：本地小模型 ----------
    def _card_model(self):
        c = self._card("本地小模型（OpenAI 兼容端点）")
        m = self.cfg.get("model", {})
        self._row_check(c, "启用小模型", "model.enabled", sub="model", key2="enabled")
        self._row_text(c, "接口地址", "model.baseUrl", sub="model", key2="baseUrl",
                       placeholder="http://127.0.0.1:11434/v1")
        self._row_text(c, "API Key（可空）", "model.apiKey", sub="model", key2="apiKey",
                       placeholder="本地 Ollama 留空即可", secret=True)
        self._row_text(c, "文本模型", "model.textModel", sub="model", key2="textModel")
        self._row_text(c, "视觉模型", "model.visionModel", sub="model", key2="visionModel",
                       placeholder="qwen2.5vl:3b")
        self._row_number(c, "超时（毫秒）", "model.timeoutMs", 2000, 180000, sub="model", key2="timeoutMs")

        row = tk.Frame(c, bg=CARD)
        row.pack(fill="x", pady=6)
        tk.Button(row, text="测试文本查词", command=self._test, font=FONT, bg=CARD, fg=INK,
                  bd=1, highlightthickness=1, highlightbackground=LINE).pack(side="left")
        self.result_lbl = tk.Label(row, text="", bg=CARD, fg=MUTED, font=FONT)
        self.result_lbl.pack(side="left", padx=10)
        self._note(c, "本地模型冷启动要读权重（CPU 上 1–3 分钟）；之后每次查词几百毫秒。\n"
                      "本地 Ollama：先 ollama pull qwen2.5:1.5b（文本）与 qwen2.5vl:3b（视觉）。")

    # ---------- 卡片：图片取词 ----------
    def _card_ocr(self):
        c = self._card("图片取词")
        self._row_check(c, "启用", "imageOcr.enabled", sub="imageOcr", key2="enabled")
        self._row_scale(c, "图片驻留时长", "imageOcr.dwellMs", 500, 8000, 100,
                        lambda v: f"{v / 1000:g} 秒", sub="imageOcr", key2="dwellMs")
        self._row_number(c, "裁剪宽度", "imageOcr.cropW", 200, 900, sub="imageOcr", key2="cropW")
        self._row_number(c, "裁剪高度", "imageOcr.cropH", 80, 500, sub="imageOcr", key2="cropH")
        self._row_check(c, "识别期间显示提示点", "imageOcr.hint", sub="imageOcr", key2="hint")
        self._note(c, "图片里的文字会被截屏裁剪后发给本地视觉模型识别；识别不到英文单词时不弹窗。")

    # ---------- 卡片：数据 ----------
    def _card_data(self):
        c = self._card("数据")
        row = tk.Frame(c, bg=CARD)
        row.pack(fill="x", pady=6)
        tk.Button(row, text="恢复默认设置", command=self._reset, font=FONT, bg=CARD, fg=INK,
                  bd=1, highlightthickness=1, highlightbackground=LINE).pack(side="left")
        self._note(c, "查询结果仅保存在本机，用于加速重复查词；不上传任何记录。\n"
                      "配置文件：%APPDATA%\\EasyTranslator\\config.json")

    # ---------- 组件工厂 ----------
    def _card(self, title: str):
        wrap = tk.Frame(self._cards, bg=BG)
        wrap.pack(fill="x", pady=(0, 10))
        c = tk.Frame(wrap, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        c.pack(fill="x", padx=1, pady=1)
        tk.Label(c, text=title.upper(), bg=CARD, fg=MUTED, font=FONT_H2, anchor="w").pack(
            fill="x", padx=14, pady=(12, 4))
        body = tk.Frame(c, bg=CARD)
        body.pack(fill="both", expand=True, pady=(0, 8))
        return body

    def _row(self, parent, label):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=14, pady=4)
        tk.Label(row, text=label, bg=CARD, fg=INK, font=FONT, width=18, anchor="w").pack(side="left")
        return row

    def _get(self, path, sub=None, key2=None):
        if sub:
            return self.cfg.get(sub, {}).get(key2)
        return self.cfg.get(path)

    def _set(self, value, sub=None, key2=None, path=None):
        if sub:
            self.cfg.setdefault(sub, {})[key2] = value
            self.save(self.cfg, f"{sub}.{key2}")
        else:
            self.cfg[path] = value
            self.save(self.cfg, path)

    def _row_check(self, parent, label, path, sub=None, key2=None):
        row = self._row(parent, label)
        var = tk.BooleanVar(value=bool(self._get(path, sub, key2)))
        tk.Checkbutton(row, variable=var, bg=CARD, activebackground=CARD, bd=0, highlightthickness=0,
                       command=lambda: self._set(var.get(), sub, key2, path)).pack(side="left")

    def _row_text(self, parent, label, path, sub=None, key2=None, placeholder="", secret=False):
        row = self._row(parent, label)
        e = tk.Entry(row, font=FONT, show="•" if secret else "", bd=1, highlightthickness=1,
                     highlightbackground=LINE, relief="flat")
        e.insert(0, str(self._get(path, sub, key2) or ""))
        e.pack(side="left", fill="x", expand=True)
        e.bind("<FocusOut>", lambda ev: self._set(e.get(), sub, key2, path))
        e.bind("<Return>", lambda ev: self._set(e.get(), sub, key2, path))

    def _row_number(self, parent, label, path, lo, hi, sub=None, key2=None):
        row = self._row(parent, label)
        var = tk.IntVar(value=int(self._get(path, sub, key2) or 0))
        sp = tk.Spinbox(row, from_=lo, to=hi, textvariable=var, font=FONT, width=8,
                        bd=1, highlightthickness=1, highlightbackground=LINE, relief="flat",
                        command=lambda: self._set(var.get(), sub, key2, path))
        sp.pack(side="left")
        sp.bind("<FocusOut>", lambda ev: self._set(var.get(), sub, key2, path))

    def _row_scale(self, parent, label, path, lo, hi, res, fmt, sub=None, key2=None):
        row = self._row(parent, label)
        cur = int(self._get(path, sub, key2) or lo)
        var = tk.IntVar(value=cur)
        out = tk.Label(row, text=fmt(cur), bg=CARD, fg=MUTED, font=FONT, width=8, anchor="e")

        def on_move(_v):
            out.configure(text=fmt(int(float(_v))))
        sc = tk.Scale(row, from_=lo, to=hi, resolution=res, orient="horizontal", variable=var,
                      bg=CARD, fg=INK, highlightthickness=0, bd=0, troughcolor=LINE,
                      showvalue=False, command=on_move)
        sc.configure(sliderrelief="flat", activebackground=ACCENT)
        sc.pack(side="left", fill="x", expand=True)
        out.pack(side="left", padx=(8, 0))
        sc.bind("<ButtonRelease-1>", lambda ev: self._set(var.get(), sub, key2, path))

    def _note(self, parent, text):
        tk.Label(parent, text=text, bg=CARD, fg=MUTED, font=9, justify="left", anchor="w",
                 wraplength=470).pack(fill="x", padx=14, pady=(4, 12))

    # ---------- 动作 ----------
    def _toggle(self):
        on = bool(self.enabled_var.get())
        self._set(on, path="enabled")
        if self.on_toggle:
            self.on_toggle(on)
        self.set_status("已启用" if on else "已暂停")

    def _test(self):
        if not self.test_text:
            return
        self.result_lbl.configure(text="查询中…", fg=MUTED)

        def run():
            ok, msg = self.test_text()
            self.after(0, lambda: self.result_lbl.configure(text=msg, fg=OK if ok else ERR))
        threading.Thread(target=run, daemon=True).start()

    def _reset(self):
        if self.on_reset:
            self.on_reset()
        self.result_lbl.configure(text="已恢复默认设置", fg=OK)

    on_reset = None

    def set_status(self, text: str):
        try:
            self.status_lbl.configure(text=text)
        except Exception:
            pass


def _to_photo(img: Image.Image):
    """PIL → tk.PhotoImage。走 Pillow 的 ImageTk（Pillow 已是依赖），
    不自己拼 base64/PPM —— 那条路 Tk 会报「couldn't recognize image data」。"""
    from PIL import ImageTk
    return ImageTk.PhotoImage(img.convert("RGB"))
