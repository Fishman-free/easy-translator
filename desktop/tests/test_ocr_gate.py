# -*- coding: utf-8 -*-
"""OCR 取词闸门单测：普通单词/数学符号才收，单个普通英文字母一律不收（纯函数，无网络无 GUI）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from et_desktop import lookup as L          # noqa: E402


class TestAcceptWord(unittest.TestCase):
    def test_real_words_accepted(self):
        for w in ["Subnormal", "Fraction", "Exponent", "Bias", "IEEE", "hello", "normal",
                  "abc", "don't", "e-mail", "COVID"]:
            self.assertTrue(L.accept_ocr_word(w), w)

    def test_single_latin_letter_rejected(self):
        """用户要求：普通英文字母不要识别出来（整词被裁成一个字母的碎片会冒充它）。"""
        for w in ["a", "F", "n", "X", "x", "Q", "P", "Z"]:
            self.assertFalse(L.accept_ocr_word(w), w)

    def test_math_symbols_kept(self):
        """希腊字母 / 花体·双线体是读论文要用的，保留。"""
        for w in ["α", "Ω", "λ", "β", "ℱ", "ℒ", "𝒩", "ℝ", "𝔼", "𝔤"]:
            self.assertTrue(L.accept_ocr_word(w), w)

    def test_junk_rejected(self):
        for w in ["", "   ", "3", "42", "+", "=", "×", "中文", "概", None, 7, ["a"]]:
            self.assertFalse(L.accept_ocr_word(w), repr(w))

    def test_null_like_strings_rejected(self):
        """模型把「没有」写成字符串 null/None 时不能当成单词。"""
        for w in ["null", "NULL", "None", "none", "nan", "无", "没有"]:
            self.assertFalse(L.accept_ocr_word(w), w)

    def test_backtick_and_space_tolerated(self):
        self.assertTrue(L.accept_ocr_word("  Fraction  "))
        self.assertTrue(L.accept_ocr_word("Subnormal."))     # 末尾标点由 is_english_word 规则处理


if __name__ == "__main__":
    unittest.main()
