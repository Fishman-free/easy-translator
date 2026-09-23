# -*- coding: utf-8 -*-
"""同构性测试：Python 实现必须与浏览器扩展那份 lib/normalize.js 输出一致。

跑法：python desktop/tests/test_parity.py
      （内部用 node 执行 desktop/tests/parity_probe.mjs 取 JS 侧结果）
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from et_desktop import lookup as L          # noqa: E402


def js_output() -> dict:
    probe = os.path.join(HERE, "parity_probe.mjs")
    res = subprocess.run(["node", probe], capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError("node 探针失败: " + (res.stderr or res.stdout)[-400:])
    return json.loads(res.stdout)


class TestParityWithJs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = js_output()

    def test_is_english_word(self):
        for s, want in self.js["isEnglishWord"]:
            self.assertEqual(L.is_english_word(s), want, "isEnglishWord(%r)" % s)

    def test_words_in(self):
        for t, want in self.js["wordsIn"]:
            got = [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in L.words_in(t)]
            self.assertEqual(got, want, "wordsIn(%r)" % t)

    def test_extract_word_at(self):
        for t, o, want in self.js["extractWordAt"]:
            self.assertEqual(L.extract_word_at(t, o), want, "extractWordAt(%r, %d)" % (t, o))

    def test_split_pos(self):
        for s, want in self.js["splitPos"]:
            self.assertEqual(L._split_pos(s), want, "splitPos(%r)" % s)

    def test_humanize_marks(self):
        for s, want in self.js["humanizeMarks"]:
            self.assertEqual(L._humanize(s), want, "humanizeMarks(%r)" % s)

    def test_normalize_youdao(self):
        self.assertEqual(L.normalize_youdao({
            "ec": {"word": [{"return-phrase": "hello", "ukphone": "həˈləʊ", "usphone": "həˈloʊ",
                             "trs": [{"tr": [{"l": {"i": ["int. 喂", "n. 打招呼"]}}]}],
                             "wfs": [{"wf": {"name": "复数", "value": "hellos"}}]}]},
            "blng_sents_part": {"sentence-pair": [
                {"sentence": "Hello there!", "sentence-translation": "你好！"}]},
            "input": "hello",
        }, "hello"), self.js["normalizeYoudao"])

    def test_extract_json(self):
        cases = [
            ('{"word":"hi","poses":[{"pos":"n.","meaning":"嗨"}]}', '{"word":"hi","poses":[{"pos":"n.","meaning":"嗨"}]}'),
            ("```json 围栏", '```json\n{"word":"hi","poses":[{"pos":"n.","meaning":"嗨"}]}\n```'),
            ("尾逗号", '{"word":"hi","poses":[{"pos":"n.","meaning":"嗨"},]}'),
            ("数组混键值对", '{"word":"hi","poses":["n.","meaning":"嗨"]}'),
            ("漏右括号（应 null）", '{"word":"hi","poses":[{"pos":"n.","meaning":"嗨"}'),
            ("无 JSON（应 null）", "这里没有 JSON，只有说明文字"),
        ]
        for (label, raw), (_, want) in zip(cases, self.js["extractJson"]):
            self.assertEqual(L.extract_json(raw), want, "extractJson(%s)" % label)

    def test_normalize_model(self):
        cases = [
            ('```json\n{"word":"hi","uk":"/haɪ/","poses":[{"pos":"int.","meaning":"嗨"}],'
             '"examples":[{"en":"Hi there.","zh":"嗨。"}]}\n```', "hi"),
            ('{"word":"x"}', "x"),
            ("nonsense", "x"),
        ]
        for (raw, fb), want in zip(cases, self.js["normalizeModel"]):
            self.assertEqual(L.normalize_model(raw, fb), want, "normalizeModel(%r)" % raw[:40])


if __name__ == "__main__":
    unittest.main(verbosity=2)
