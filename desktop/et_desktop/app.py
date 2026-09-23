# -*- coding: utf-8 -*-
"""
Easy Translator 桌面伴生：整台电脑的悬停查词。

用法：
    python -m et_desktop                 # 打开设置窗口（就是这个程序的主界面）并开始监听
    python -m et_desktop --selftest      # 自检：UIA 取词 + 渲染 + 引擎连通
    python -m et_desktop --settings      # 只开设置窗口，不监听
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

try:
    import tkinter as tk
except Exception:                                   # pragma: no cover
    tk = None

from . import lookup, settings_ui, textgrab, ui

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MASCOT = os.path.join(REPO, "assets", "mascot.png")
CFG_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "EasyTranslator", "config.json")

# 字段名与 lib/settings-core.js 的 DEFAULTS 保持一致 —— 两端各叫各的就会漂移，
# desktop/tests/test_settings.py 会拿 JS 侧逐键比对。
DEFAULTS = {
    "enabled": True,
    "dwellMs": 5000,
    "engine": "auto",
    "examplesCount": 3,
    "showSpeak": True,
    "model": {"enabled": False, "baseUrl": "http://127.0.0.1:11434/v1", "apiKey": "",
              "textModel": "qwen2.5:1.5b", "visionModel": "qwen2.5vl:3b", "timeoutMs": 60000},
    "imageOcr": {"enabled": True, "dwellMs": 1500, "cropW": 460, "cropH": 140, "hint": True},
}

# 老配置文件里的旧字段名 → 新名（读到就搬过来，避免升级后设置"失踪"）
_LEGACY = {"dwell": "dwellMs", "showExamples": "examplesCount"}


def _merge(base: dict, extra: dict) -> dict:
    out = json.loads(json.dumps(base))
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def load_cfg() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            user = json.load(f)
        for old, new in _LEGACY.items():             # 老字段名平移
            if old in user and new not in user:
                user[new] = user.pop(old)
        if "dwell" in user:                          # 老的是「秒」，新的是毫秒
            try:
                user["dwellMs"] = int(float(user.pop("dwell")) * 1000)
            except Exception:
                user.pop("dwell", None)
        cfg = _merge(cfg, user)
    except Exception:
        pass
    cfg["dwellMs"] = max(1000, min(15000, int(cfg.get("dwellMs") or 5000)))
    cfg["examplesCount"] = max(0, min(5, int(cfg.get("examplesCount") or 0)))
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
                if time.time() - self.since < float(self.cfg.get("dwellMs", 5000)) / 1000.0:
                    continue
                self.shown = True
            threading.Thread(target=self._fire, args=(word, x, y, src), daemon=True).start()

    def _fire(self, word, x, y, src):
        data = lookup.lookup(word, self.cfg)
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

    if tk is not None:
        try:
            root = tk.Tk()
            root.withdraw()
            mascot = ui.load_mascot(MASCOT)
            win = settings_ui.SettingsWindow(root, json.loads(json.dumps(DEFAULTS)), lambda *a: None, mascot=mascot)
            win.update_idletasks()
            print(f"  设置窗口可创建: {win.winfo_width()}x{win.winfo_height()} ✔")
            win.destroy()
            root.destroy()
        except Exception as e:
            print(f"  设置窗口可创建: ✘ {e}")
            ok = False
    print("自检" + ("通过" if ok else "有项失败"))
    return 0 if ok else 1


class App:
    """主界面 = 设置窗口；查词浮层另有窗口。"""

    def __init__(self, cfg, root, on_quit):
        self.root = root
        self.cfg = cfg
        self._mascot = ui.load_mascot(MASCOT)
        self._cache = {}
        self._last_word = ""
        self.bubble = ui.Bubble(root, on_copy=self._copy, on_leave=self._hide)
        self.win = settings_ui.SettingsWindow(
            root, cfg, self._change, on_toggle=self._on_toggle, on_quit=on_quit,
            mascot=self._mascot, test_text=self._test_text)
        self.win.on_reset = self._reset
        self.win.set_status("已启用" if cfg.get("enabled", True) else "已暂停")
        self.watcher = Watcher(cfg, self._render, self)

    # Watcher 通过这两个方法回调（panel.after / panel.show_bubble）
    def after(self, ms, fn):
        self.root.after(ms, fn)

    def show_bubble(self, img, x, y, word):
        self._last_word = word
        self.bubble.show(img, x, y)

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

    def _hide(self):
        self.bubble.hide()

    def _copy(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self._last_word)
        except Exception:
            pass

    def _change(self, key, value):
        # 设置窗口已改好 self.cfg，这里只负责落盘
        save_cfg(self.cfg)

    def _on_toggle(self, on):
        self.win.set_status("已启用" if on else "已暂停")

    def _reset(self):
        self.cfg.clear()
        self.cfg.update(json.loads(json.dumps(DEFAULTS)))
        save_cfg(self.cfg)

    def _test_text(self):
        got = lookup.lookup("hello", self.cfg)
        return bool(got), (f"✔ {got.get('source') or '查到 hello'}" if got else "✘ 查不到 hello（检查网络或本地模型）")

    def stop(self):
        self.watcher.stop_flag = True
        self.win.destroy()
        self.root.destroy()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Easy Translator 桌面取词")
    ap.add_argument("--selftest", action="store_true", help="跑一遍自检后退出")
    ap.add_argument("--settings", action="store_true", help="只打开设置窗口，不开始监听")
    args = ap.parse_args(argv)
    cfg = load_cfg()
    if args.selftest:
        return selftest(cfg)
    if tk is None:
        print("缺少 tkinter，无法打开界面（可用 --selftest 走命令行自检）")
        return 2

    root = tk.Tk()
    root.withdraw()

    app = App(cfg, root, lambda: app.stop())
    if not args.settings:
        app.watcher.start()
    root.protocol("WM_DELETE_WINDOW", app.stop)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
