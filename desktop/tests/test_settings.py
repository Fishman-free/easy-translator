# -*- coding: utf-8 -*-
"""
设置面的两端一致性：
  ① 桌面配置的字段名必须与 lib/settings-core.js 的 DEFAULTS 一致（防漂移）
  ② 设置窗口必须能真正建出来（控件不抛异常），字段一个不少
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "desktop"))

from et_desktop import app as app_mod          # noqa: E402


def js_defaults():
    """用**真实的** lib/settings-core.js 取默认值（ETSettings.normalize({}) = 纯默认），
    不靠正则解析 JS —— 解析器一脆就整片红，还可能解析出错误结果。"""
    import subprocess
    js_path = os.path.join(ROOT, "lib", "settings-core.js").replace("\\", "/")
    script = ("require(" + repr(js_path).replace("'", '"') + ");"
              "process.stdout.write(JSON.stringify(globalThis.ETSettings.normalize({})));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60)
    if not out.stdout.strip():
        raise AssertionError(f"取 JS 默认值失败：{out.stderr[:200]}")
    return json.loads(out.stdout)


class TestSchemaParity(unittest.TestCase):
    """桌面端是扩展设置的**子集**（桌面没有 PDF/阅读器界面），但字段名必须同名、
    共有字段的默认值必须一致 —— 这样才防得住 dwell vs dwellMs 那类漂移。"""

    def test_top_level_keys_are_subset_of_js(self):
        js = js_defaults()
        mine = app_mod.DEFAULTS
        missing = [k for k in mine if k not in js]
        self.assertEqual([], missing, f"桌面字段在 lib/settings-core.js 里找不到同名项：{missing}")

    def test_model_keys_are_subset_of_js(self):
        js, mine = js_defaults()["model"], app_mod.DEFAULTS["model"]
        missing = [k for k in mine if k not in js]
        self.assertEqual([], missing, f"model 字段不同名：{missing}")

    def test_image_ocr_keys_are_subset_of_js(self):
        js, mine = js_defaults()["imageOcr"], app_mod.DEFAULTS["imageOcr"]
        missing = [k for k in mine if k not in js]
        self.assertEqual([], missing, f"imageOcr 字段不同名：{missing}")

    def test_no_legacy_names_in_defaults(self):
        for old in app_mod._LEGACY:
            self.assertNotIn(old, app_mod.DEFAULTS, f"DEFAULTS 里还留着老字段名 {old}")

    def test_values_defaults_agree(self):
        js, mine = js_defaults(), app_mod.DEFAULTS
        self.assertEqual(js["dwellMs"], mine["dwellMs"])
        self.assertEqual(js["engine"], mine["engine"])
        self.assertEqual(js["examplesCount"], mine["examplesCount"])
        self.assertEqual(js["model"]["baseUrl"], mine["model"]["baseUrl"])
        self.assertEqual(js["imageOcr"]["cropW"], mine["imageOcr"]["cropW"])

    def test_legacy_config_keys_are_migrated(self):
        # 老配置文件用 dwell（秒）/ showExamples —— 升级后不该"设置失踪"
        old = {"dwell": 3, "showExamples": 1, "enabled": False}
        merged = app_mod._merge(app_mod.DEFAULTS, {app_mod._LEGACY.get(k, k): v for k, v in old.items()})
        self.assertIn("dwellMs", merged)
        self.assertEqual(merged["examplesCount"], 1)
        self.assertFalse(merged["enabled"])


class TestSettingsWindow(unittest.TestCase):
    def test_window_constructs_with_all_fields(self):
        try:
            import tkinter as tk
        except Exception:
            self.skipTest("无 tkinter")
        if not hasattr(tk, "Tk"):
            self.skipTest("无显示环境")
        from et_desktop import settings_ui, ui
        try:
            root = tk.Tk()
        except Exception as e:
            self.skipTest(f"无法创建 Tk：{e}")
        root.withdraw()
        cfg = json.loads(json.dumps(app_mod.DEFAULTS))
        calls = []
        mascot = ui.load_mascot(os.path.join(ROOT, "assets", "mascot.png"))
        # 带立绘构造 —— 标题气泡那条 PIL→PhotoImage 转换必须真的走通
        win = settings_ui.SettingsWindow(root, cfg, lambda *a: calls.append(a),
                                         mascot=mascot, test_text=lambda: (True, "✔ ok"))
        win.update_idletasks()
        self.assertGreater(win.winfo_width(), 100, "设置窗口没渲染出尺寸")
        labels = []

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Label) and c.cget("text"):
                    labels.append(str(c.cget("text")))
                walk(c)
        walk(win)
        for want in ["通用", "本地小模型（OPENAI 兼容端点）", "图片取词", "数据",
                     "悬停触发时长", "例句条数", "接口地址", "文本模型", "视觉模型", "超时（毫秒）"]:
            self.assertTrue(any(want in s for s in labels), f"设置窗口缺少「{want}」")

        # 关键：字段必须**可见**（winfo_ismapped）。只查标签文本会漏掉
        # 「行容器忘了 pack」——那种情况标签存在但整片字段看不见。
        # 注意顺序：映射状态要等 update() 之后才准（先遍历会整片报 unmapped）。
        win.deiconify()
        win.update_idletasks()
        win.update()
        visible = []

        def walk_mapped(w):
            for c in w.winfo_children():
                if isinstance(c, (tk.Entry, tk.Checkbutton, tk.Scale, tk.Spinbox)):
                    visible.append((type(c).__name__, bool(c.winfo_ismapped())))
                walk_mapped(c)
        walk_mapped(win)
        invisible = [t for t, m in visible if not m]
        self.assertGreaterEqual(len(visible), 12, f"字段控件太少：{visible}")

        def chain(w):
            out = []
            while w is not None and str(w) != str(win):
                try:
                    out.append(f"{w.winfo_class()}{'M' if w.winfo_ismapped() else 'U'}"
                               f"[{w.winfo_width()}x{w.winfo_height()}]")
                except Exception:
                    break
                w = w.master
            return " ← ".join(out)
        dbg = [chain(c) for c in win.winfo_children()
               if isinstance(c, tk.Frame)] if invisible else []
        self.assertEqual([], invisible,
                         f"这些字段没显示出来（容器忘了 pack？）：{invisible}\n祖先链：{dbg[:3]}")
        win.destroy()
        root.destroy()

    def test_header_is_speech_bubble_with_mascot(self):
        from PIL import Image
        from et_desktop import settings_ui, ui
        mascot = ui.load_mascot(os.path.join(ROOT, "assets", "mascot.png"))
        head = settings_ui._header_png(mascot)
        px = head.load()
        navy = sum(1 for y in range(head.height) for x in range(head.width) if px[x, y][:3] == (30, 50, 100))
        white = sum(1 for y in range(head.height) for x in range(head.width)
                    if px[x, y][3] > 120 and px[x, y][:3] == (255, 255, 255))
        self.assertGreater(navy, 150, "标题气泡应有藏青描边/尾点")
        self.assertGreater(white, 800, "标题气泡应是白底")
        # 立绘在右侧且非空
        right = sum(1 for y in range(head.height) for x in range(head.width - 90, head.width)
                    if px[x, y][3] > 120 and px[x, y][:3] != (255, 255, 255))
        self.assertGreater(right, 100, "右上角应有立绘")


if __name__ == "__main__":
    unittest.main(verbosity=2)
