# -*- coding: utf-8 -*-
"""按词裁剪（_word_crop_png）回归测试：长词必须被完整框进裁剪图。

背景：该函数一度因 `g.load()`（未定义名，被 except 吞掉）恒返回 None，
「按词裁剪」整条路失效 —— 长词（Fraction/Exponent/Significand）仍被固定
140px 宽度切断，模型只读到 frac/n 这类碎片。这里用合成图钉死：
投喂一张含长横条（模拟墨迹段）的图，裁剪结果必须真的产出，且宽度由墨迹段
决定（明显超过 140）。
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from et_desktop import textgrab  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


def _synthetic():
    """白底 + 中央一条 300x20 的「长词」横条（模拟墨迹段）。"""
    img = Image.new("RGB", (1400, 200), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([700 - 150, 100 - 10, 700 + 150, 100 + 10], fill=(20, 20, 30))
    return img


class TestWordCrop(unittest.TestCase):
    def setUp(self):
        self._orig = textgrab._grab_rect

    def tearDown(self):
        textgrab._grab_rect = self._orig

    def test_returns_png_for_long_ink_run(self):
        textgrab._grab_rect = lambda rect: (_synthetic(), (0, 0))
        png = textgrab._word_crop_png(700, 100)
        self.assertIsNotNone(png, "按词裁剪必须产出裁剪图（曾因未定义名恒为 None）")
        self.assertTrue(png.startswith(b"\x89PNG"), "必须是 PNG")
        with Image.open(io.BytesIO(png)) as im:
            self.assertGreater(im.width, 140,
                               "裁剪宽度应由墨迹段决定（长词 > 固定 140），实际 %d" % im.width)
            self.assertLessEqual(im.width, 901)
            self.assertGreaterEqual(im.height, 20)

    def test_blank_area_returns_none(self):
        """没有墨迹 → 不产出（该函数只负责「有词可裁」的情形）。"""
        textgrab._grab_rect = lambda rect: (Image.new("RGB", (1400, 200), (255, 255, 255)), (0, 0))
        self.assertIsNone(textgrab._word_crop_png(700, 100))


if __name__ == "__main__":
    unittest.main()