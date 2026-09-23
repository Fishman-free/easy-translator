# -*- coding: utf-8 -*-
"""取词与归一化的纯函数单测（无网络、无 GUI）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from et_desktop import lookup as L          # noqa: E402


class TestWordGate(unittest.TestCase):
    def test_accepts(self):
        for w in ["hello", "serendipity", "test", "don't", "COVID", "ab"]:
            self.assertTrue(L.is_english_word(w), w)

    def test_rejects(self):
        for w in ["a", "xzqwt", "can't--t", "中文", "", "x1y", "x" * 46]:
            self.assertFalse(L.is_english_word(w), w)


class TestWordsIn(unittest.TestCase):
    def test_mixed_cjk(self):
        self.assertEqual([w["word"] for w in L.words_in("这是test词，中文hello世界")], ["test", "hello"])
        self.assertEqual([w["word"] for w in L.words_in("紧贴着的serendipity也不能漏")], ["serendipity"])

    def test_positions_are_sliceable(self):
        first = L.words_in("这是test词")[0]
        self.assertEqual("这是test词"[first["start"]:first["end"]], "test")

    def test_empty_and_noise(self):
        self.assertEqual(L.words_in(""), [])
        self.assertEqual(L.words_in("这是一段纯中文"), [])
        self.assertEqual(L.words_in("1234 56.78"), [])


class TestExtractWordAt(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(L.extract_word_at("这是test词", 2)["word"], "test")
        self.assertEqual(L.extract_word_at("这是test词", 3)["word"], "test")
        self.assertEqual(L.extract_word_at("中文hello世界", 4)["word"], "hello")
        self.assertEqual(L.extract_word_at("The quick brown fox", 5)["word"], "quick")

    def test_gaps_return_empty(self):
        self.assertEqual(L.extract_word_at("abc 中文", 3)["word"], "")
        self.assertEqual(L.extract_word_at("中文 abc", 1)["word"], "")
        self.assertEqual(L.extract_word_at("a", 0)["word"], "")


class TestNormalize(unittest.TestCase):
    def test_split_pos(self):
        self.assertEqual(L._split_pos("int. 喂，你好")["pos"], "int.")
        self.assertEqual(L._split_pos("plain text without pos")["pos"], "")

    def test_humanize_marks(self):
        self.assertEqual(L._humanize("这是<英，旧>标记"), "这是（英，旧）标记")

    def test_normalize_youdao(self):
        raw = {"ec": {"word": [{"return-phrase": "hello", "ukphone": "həˈləʊ", "usphone": "həˈloʊ",
                                "trs": [{"tr": [{"l": {"i": ["int. 喂", "n. 打招呼"]}}]}],
                                "wfs": [{"wf": {"name": "复数", "value": "hellos"}}]}]},
               "blng_sents_part": {"sentence-pair": [
                   {"sentence": "Hello there!", "sentence-translation": "你好！"}]},
               "input": "hello"}
        got = L.normalize_youdao(raw, "hello")
        self.assertEqual(got["word"], "hello")
        self.assertEqual(got["phonetics"]["uk"], "həˈləʊ")
        self.assertEqual(len(got["poses"]), 2)
        self.assertEqual(got["examples"][0]["zh"], "你好！")
        self.assertEqual(got["forms"][0]["name"], "复数")

    def test_normalize_model_success_path(self):
        # 按契约：音标键是 phonetic_uk/phonetic_us，词性键是 pos/pos_list/part_of_speech
        got = L.normalize_model(
            '{"word":"hi","phonetic_uk":"/haɪ/","pos":[{"pos":"int.","meaning":"嗨"}],'
            '"examples":[{"en":"Hi there.","zh":"嗨。"}]}', "hi")
        self.assertEqual(got["phonetics"]["uk"], "/haɪ/")
        self.assertEqual(got["poses"], [{"pos": "int.", "meaning": "嗨"}])
        self.assertEqual(got["examples"], [{"en": "Hi there.", "zh": "嗨。"}])

    def test_normalize_model_drops_placeholders(self):
        # 小模型会照抄提示词里的占位符（例句/翻译…），这些一律丢弃
        got = L.normalize_model('{"word":"hi","examples":[{"en":"例句","zh":"中文翻译"}],"pos":"嗨"}', "hi")
        self.assertEqual(got["examples"], [])
        self.assertEqual(got["poses"], [{"pos": "", "meaning": "嗨"}])

    def test_normalize_model_tolerates_bad_json(self):
        # 小模型常见毛病：照抄占位符、裹 ``` 围栏、数组里混进键值对、带尾逗号
        self.assertIsNone(L.normalize_model('{"word":"x"}', "x"))
        self.assertIsNotNone(L.normalize_model('```json\n{"word":"hi","pos":[{"pos":"n.","meaning":"嗨"}]}\n```', "hi"))
        self.assertIsNotNone(L.normalize_model('{"word":"hi","pos":["n.","meaning":"嗨"]}', "hi"))
        # 漏右括号：与 JS 契约一致 —— 抠不出来就返回 None（宁可静默，也不猜着补）
        self.assertIsNone(L.normalize_model('{"word":"hi","pos":[{"pos":"n.","meaning":"嗨"}', "hi"))

    def test_lookup_is_silent_when_engine_unavailable(self):
        # 没配端点时必须返回 None（调用方静默），绝不抛异常
        self.assertIsNone(L.lookup_model("hello", {}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
