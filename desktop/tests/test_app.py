# -*- coding: utf-8 -*-
"""app.py 的环境契约：ctypes 必须是模块级导入、DPI 声明可重复调用。

回归背景：Poller.__init__ 用 ctypes.windll.user32.GetDpiForSystem() 缩放
「移动了」阈值；若 ctypes 未在模块级导入，那行会 NameError 并被外层 except
静默吞掉 —— 表现是阈值恒为 8px（高 DPI 下「不动才翻译」阈值小于实际抖动），
不报错、难发现。这里把这个契约钉住。
"""
import ctypes
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from et_desktop import app  # noqa: E402


class TestAppEnv(unittest.TestCase):
    def test_ctypes_is_module_level(self):
        self.assertIs(getattr(app, "ctypes", None), ctypes,
                      "app.py 必须模块级 import ctypes（Poller 的 DPI 阈值缩放依赖它）")

    def test_dpi_awareness_is_callable_and_dpi_readable(self):
        app._enable_dpi_awareness()          # 幂等；与 main() 中同一处调用
        self.assertGreater(ctypes.windll.user32.GetDpiForSystem(), 0)


if __name__ == "__main__":
    unittest.main()
