# -*- coding: utf-8 -*-
"""Easy Translator 桌面伴生：整台电脑的悬停查词。

用法：
    python -m et_desktop                 # 打开控制面板并开始监听
    python -m et_desktop --selftest      # 自检：UIA 取词 + 渲染 + 引擎连通
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time

from PIL import Image

# Windows 高 DPI：必须在任何窗口/截图之前声明，否则坐标全错位
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

from . import lookup, textgrab, ui

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MASCOT = os.path.join(REPO, "assets", "mascot.png")
CFG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "EasyTranslator", "config.json")

DEFAULTS = {
    "enabled": True,
    "dwell": 5.0,
    "engine": "auto",
    "showExamples": 2,
    "model": {"enabled": False, "baseUrl": "http://127.0.0.1:11434/v1",
              "apiKey": "", "textModel": "qwen2.5:1.5b", "visionModel": "qwen2.5vl:3b"},
}


def load_cfg() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            user = json.load(f)
        for k, v in (user or {}).items():
            if k == "model" and isinstance(v, dict):
                cfg["model"].update(v)
            else:
                cfg[k] = v
    except Exception:
        pass
    return cfg


def save_cfg(cfg: dict):
    try:
        os.makedirs(os.path.dirname(CFG_PATH), exist_ok=True)
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def cursor_pos():
    try:
        import ctypes
        from ctypes import wintypes
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return 0, 0


class Watcher(threading.Thread):
    """同词驻留计时：目标变化即重置；微动不打断；取不到词一律静默。"""

    def __init__(self, cfg, bubble_img, panel):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.render = bubble_img
        self.panel = panel
        self.word = None
        self.anchor = (0, 0)
        self.since = 0.0
        self.shown = False
        self.lock = threading.Lock()
        self.stop_flag = False

    def run(self):
        while not self.stop_flag:
            time.sleep(0.12)
            if not self.cfg.get("enabled", True):
                with self.lock:
                    self.word, self.shown = None, False
                continue
            x, y = cursor_pos()
            word, src = textgrab.word_at_point(x, y, self.cfg)
            if not word:
                with self.lock:
                    self.word, self.shown = None, False
                continue
            with self.lock:
                if word != self.word:
                    self.word, self.anchor, self.since, self.shown = word, (x, y), time.time(), False
                    continue
                if self.shown:
                    continue
                if time.time() - self.since < float(self.cfg.get("dwell", 5.0)):
                    continue
                self.shown = True
            threading.Thread(target=self._fire, args=(word, x, y, src), daemon=True).start()

    def _fire(self, word, x, y, src):
        data = lookup.lookup(word, self.cfg if self.cfg.get("engine") else self.cfg)
        if not data:
            return                       # 查不到就静默，不打扰
        try:
            img = self.render(data)
            self.panel.after(0, lambda: self.panel.show_bubble(img, x, y, word))
        except Exception:
            pass


def selftest(cfg) -> int:
    print("== 自检 ==")
    ok = True

    mascot = ui.load_mascot(MASCOT)
    print(f"  鲸鱼娘立绘: {mascot.size} ✔")

    sample = {"word": "serendipity", "phonetics": {"uk": "/ˌserənˈdɪpəti/", "us": "/ˌserənˈdɪpəti/"},
              "poses": [{"pos": "n.", "meaning": "意外发现珍奇事物的天赋"}],
              "examples": [{"en": "A fortunate stroke of serendipity brought them together.",
                            "zh": "一次幸运的机缘让他们相遇。"}], "source": "自检样例"}
    img = ui.render_card(sample, mascot, scale=1.0)
    out = os.path.join(os.environ.get("TEMP", "."), "et-desktop-card-preview.png")
    bg = Image.new("RGB", img.size, (255, 255, 255))
    bg.paste(img, (0, 0), img)
    bg.save(out)
    print(f"  气泡渲染: {img.size} ✔ 预览 → {out}")

    word, src = textgrab.word_at_point(*cursor_pos(), cfg)
    print(f"  当前光标取词: {word!r}（来源 {src or '无'}）"
          + ("   [注: 光标不在文字上属正常]" if not word else ""))

    got = lookup.lookup("hello", cfg)
    print(f"  引擎连通: {'✔ ' + (got.get('source') or '') if got else '✘ 查不到 hello（检查网络或本地模型）'}")
    if not got:
        ok = False
    print("自检" + ("通过" if ok else "有项失败"))
    return 0 if ok else 1


class App(ui.Panel):
    def __init__(self, cfg, on_quit):
        self._mascot = ui.load_mascot(MASCOT)
        self._cache = {}
        super().__init__(cfg, self._change, on_quit)
        self.cfg = cfg
        self.bubble = ui.Bubble(self, on_copy=self._copy, on_leave=self._hide)
        self.watcher = Watcher(cfg, self._render, self)

    def _render(self, data):
        key = (data.get("word"), tuple(sorted((p.get("pos"), p.get("meaning")) for p in data.get("poses") or [])))
        if key not in self._cache:
            self._cache[key] = ui.render_card(data, self._mascot, scale=self._scale())
        return self._cache[key]

    def _scale(self):
        try:
            import ctypes
            return max(1.0, min(2.0, ctypes.windll.user32.GetDpiForSystem() / 96.0))
        except Exception:
            return 1.0

    def show_bubble(self, img, x, y, word):
        self._last_word = word
        self.bubble.show(img, x, y)

    def _hide(self):
        self.bubble.hide()

    def _copy(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(getattr(self, "_last_word", ""))
        except Exception:
            pass

    def _change(self, key, value):
        self.cfg[key] = value
        save_cfg(self.cfg)

    def stop(self):
        self.watcher.stop_flag = True
        self.destroy()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Easy Translator 桌面取词")
    ap.add_argument("--selftest", action="store_true", help="跑一遍自检后退出")
    args = ap.parse_args(argv)

    cfg = load_cfg()
    if args.selftest:
        return selftest(cfg)

    def quit_all():
        app.stop()

    app = App(cfg, quit_all)
    app.watcher.start()
    app.protocol("WM_DELETE_WINDOW", quit_all)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
