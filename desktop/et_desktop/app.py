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


def _enable_dpi_awareness():
    """声明进程 DPI 感知 —— 必须在任何取坐标之前调用。

    不声明时（150% 缩放的笔记本屏上）：GetCursorPos / UIA 给的是**逻辑坐标**
    （1707×1067），而 PIL 的 ImageGrab(all_screens=True) 给的是**物理坐标**
    （2560×1600），两套坐标差 1.5 倍 → OCR 截图中心整体偏移，红叉指到旁边的词，
    于是「鼠标在 desktop 上却翻译成 et」。声明后三套坐标统一为物理像素；
    顺带 _scale() 拿到真实 DPI，气泡按 1.5 倍渲染再 1:1 显示，更清晰。
    """
    try:
        import ctypes
        try:
            # Windows 10 1703+：per-monitor v2
            if ctypes.windll.user32.SetProcessDpiAwarenessContext(-4):
                return
        except Exception:
            pass
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)   # PER_MONITOR_DPI_AWARE
            return
        except Exception:
            pass
        ctypes.windll.user32.SetProcessDPIAware()            # 老系统兜底
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


def _lbutton_down():
    """左键是否正按下（无需焦点/钩子，轮询式全局检测）。"""
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
    except Exception:
        return False


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
        self._last_seen = 0.0
        self._dwell = 5.0
        self.shown = False
        self.lock = threading.Lock()
        self.stop_flag = False

    def run(self):
        # UIA 依赖 COM：非主线程必须显式 CoInitialize，否则 uiautomation 每次调用都报
        # 「尚未调用 CoInitialize」并失败 → 文本取词全废、只能走 OCR 兜底。
        try:
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass
        while not self.stop_flag:
            time.sleep(0.12)
            if not self.cfg.get("enabled", True):
                with self.lock:
                    self.word, self.shown = None, False
                continue
            x, y = cursor_pos()
            t_poll = time.time()
            with self.lock:
                if self.shown:
                    # 快速收起：光标明显移开（>28px，微动不算）或单击 → 立即收起，
                    # 不等下面那轮可能耗时 1-2 秒的 OCR。钉在气泡上时（pinned）不收起。
                    pinned = self.panel.is_pinned()
                    moved = abs(x - self.anchor[0]) > 28 or abs(y - self.anchor[1]) > 28
                    if not pinned and (moved or _lbutton_down()):
                        self.shown = False
                        self.word, self.since = None, t_poll
                        self._schedule_hide()
                        continue
            word, src = textgrab.word_at_point(x, y, self.cfg)
            now = time.time()
            with self.lock:
                if not word:
                    # 瞬时取不到词（焦点瞬变 / 光标微动到词缝）不立即重置计时；
                    # 超过 0.8s 宽限期才清空。气泡钉在鼠标下时（pinned）不收起。
                    if self.word is None or now - self._last_seen > 0.8:
                        if self.shown and not self.panel.is_pinned():
                            self.shown = False
                            self._schedule_hide()
                        self.word = None
                    continue
                self._last_seen = now
                if word != self.word:
                    # 鼠标移到了别的词（或从别处回来）：收起旧气泡，重新驻留
                    if self.shown:
                        self.shown = False
                        self._schedule_hide()
                    # OCR 取词用图片取词自己的驻留时长（与浏览器扩展一致：约 1.4s）
                    if src == "ocr":
                        self._dwell = float((self.cfg.get("imageOcr") or {}).get("dwellMs", 1500)) / 1000.0
                    else:
                        self._dwell = float(self.cfg.get("dwellMs", 5000)) / 1000.0
                    self.word, self.anchor, self.since = word, (x, y), now
                    continue
                if self.shown:
                    continue
                if now - self.since < self._dwell:
                    # 「不动才翻译」：驻留期间光标明显移动（>8px，微抖不算）→ 重新驻留
                    if abs(x - self.anchor[0]) > 8 or abs(y - self.anchor[1]) > 8:
                        self.anchor, self.since = (x, y), now
                    continue
                self.shown = True
            threading.Thread(target=self._fire, args=(word, x, y, src), daemon=True).start()

    def _schedule_hide(self):
        try:
            self.panel.after(0, self.panel.hide_bubble)
        except Exception:
            pass

    def _fire(self, word, x, y, src):
        data = lookup.lookup(word, self.cfg)
        if not lookup.has_definition(data):
            return        # 查不到、或只有音标没有释义 → 静默，不弹空壳
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

    def __init__(self, cfg, root, on_quit, headless=False):
        self.root = root
        self.cfg = cfg
        self._mascot = ui.load_mascot(MASCOT)
        self._cache = {}
        self._last_word = ""
        self._pinned = False
        self.bubble = ui.Bubble(root, on_copy=self._copy, on_leave=self._on_bubble_leave,
                                on_enter=self._on_bubble_enter, on_click=self._on_bubble_click)
        self.win = None
        if not headless:
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

    def hide_bubble(self):
        self._hide()

    def is_pinned(self):
        return self._pinned

    def _on_bubble_enter(self):
        self._pinned = True

    def _on_bubble_leave(self):
        self._pinned = False
        self._hide()

    def _on_bubble_click(self):
        self._copy()
        self._hide()

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

    @staticmethod
    def warmup(cfg):
        """后台预热视觉模型（微信/游戏等无文字界面要靠它）—— 冷启动 1–3 分钟，别挡界面。"""
        threading.Thread(target=lookup.warmup_vision, args=(cfg,), daemon=True).start()

    def stop(self):
        self.watcher.stop_flag = True
        if self.win is not None:
            self.win.destroy()
        self.root.destroy()


def main(argv=None) -> int:
    _enable_dpi_awareness()      # 必须在取任何坐标 / 建 Tk 之前：统一物理像素坐标系
    ap = argparse.ArgumentParser(description="Easy Translator 桌面取词")
    ap.add_argument("--selftest", action="store_true", help="跑一遍自检后退出")
    ap.add_argument("--settings", action="store_true", help="只打开设置窗口，不开始监听")
    ap.add_argument("--daemon", action="store_true", help="只监听不弹窗口（开机自启用的静默模式）")
    args = ap.parse_args(argv)
    cfg = load_cfg()
    if args.daemon:
        # 单实例：已有一个守护在跑就直接退出（自启 + 自愈 + 手动启动可能同时发生）
        import ctypes as _ct
        _k32 = _ct.windll.kernel32
        _mtx = _k32.CreateMutexW(None, False, "EasyTranslatorDaemonMutex")
        if _mtx and _k32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
            return 0
        # 静默模式没有控制台：把 stderr 重定向到日志文件，崩溃原因可事后查。
        # （Tk 主循环回调异常、线程异常、excepthook 全部经 stderr 落入此文件）
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                os.pardir, "daemon.log")
        log_path = os.path.abspath(log_path)
        try:
            if os.path.exists(log_path) and os.path.getsize(log_path) > 1_000_000:
                os.remove(log_path)        # 轮转：太大就从头写
        except Exception:
            pass
        logf = open(log_path, "a", encoding="utf-8")
        logf.write("\n=== daemon start %s ===\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        logf.flush()
        sys.stderr = logf
        def _excepthook(t, v, tb):
            import traceback as _tb
            _tb.print_exception(t, v, tb, file=logf)
            logf.flush()
        sys.excepthook = _excepthook
    if args.selftest:
        return selftest(cfg)
    if tk is None:
        print("缺少 tkinter，无法打开界面（可用 --selftest 走命令行自检）")
        return 2

    root = tk.Tk()
    root.withdraw()

    app = App(cfg, root, lambda: app.stop(), headless=args.daemon)
    app.warmup(cfg)                      # 预热视觉模型：微信/游戏等无文字界面的取词靠它
    if not args.settings:
        app.watcher.start()
    root.protocol("WM_DELETE_WINDOW", app.stop)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
