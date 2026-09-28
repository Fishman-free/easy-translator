# -*- coding: utf-8 -*-
"""特称表单测：命中规则、大小写保护、表完整性、与 lookup() 的挂接（全部离线）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from et_desktop import lookup as L              # noqa: E402
from et_desktop import terms as T               # noqa: E402


class TestHit(unittest.TestCase):
    def test_common_acronyms(self):
        for w, must in [("IEEE", "电气"), ("IBM", "国际商业机器"), ("GPU", "图形处理器"),
                        ("SEI", "固体电解质"), ("CV", "计算机视觉"), ("LLM", "大语言模型"),
                        ("XRD", "衍射"), ("LiTFSI", "双三氟甲磺酰亚胺锂")]:
            got = T.lookup_term(w)
            self.assertIsNotNone(got, w)
            blob = got["word"] + "".join(p["meaning"] for p in got["poses"])
            self.assertIn(must, blob, w)

    def test_exact_case_words(self):
        for w in ["arXiv", "PyTorch", "TensorFlow", "Adam", "ReLU", "iid", "scikit-learn", "pandas",
                  "NeurIPS", "OpenAI", "DeepMind", "PCIe", "NVMe", "LoRA", "Microsoft", "HuggingFace"]:
            self.assertIsNotNone(T.lookup_term(w), w)

    def test_canonical_spellings_hit(self):
        """论文里实际怎么写，就必须能命中（键的大小写写错 = 永远匹配不上）。"""
        for w in ["NaN", "LiTFSI", "LiFSI", "ULP", "FPU", "SIMD", "Mantissa", "Subnormal",
                  "arXiv", "NeurIPS", "PyTorch", "ReLU", "PCIe", "NVMe", "LoRA", "iid"]:
            self.assertIsNotNone(T.lookup_term(w), w)

    def test_ambiguity_lists_both(self):
        for w in ["CV", "VC", "PDF", "DOS"]:   # MD 用的是「也可是…」列举，不含 ②
            got = T.lookup_term(w)
            blob = got["word"] + "".join(p["meaning"] for p in got["poses"])   # ①② 列举写在标题里
            self.assertIn("②", blob, w)

    def test_trailing_punctuation(self):
        self.assertIsNotNone(T.lookup_term("IEEE."))
        self.assertIsNotNone(T.lookup_term("(IBM)"))
        self.assertIsNotNone(T.lookup_term('"GPU",'))


class TestCaseSafety(unittest.TestCase):
    """核心：普通小写词绝不能被特称表劫持（it≠IT、cv≠CV）。"""

    def test_lowercase_shorts_not_hijacked(self):
        for w in ["it", "cv", "ml", "ai", "ec", "vc", "md", "dos", "gp", "bn", "ln", "lib", "map", "mle"]:
            self.assertIsNone(T.lookup_term(w), w)

    def test_mixedcase_not_hijacked(self):
        for w in ["Ieee", "ibm", "Gpu", "arxiv", "pytorch", "relu", "adam", "softmax"]:
            self.assertIsNone(T.lookup_term(w), w)

    def test_unknown_returns_none(self):
        for w in ["hello", "serendipity", "", "中", "ZZZZ", "xyz-1"]:
            self.assertIsNone(T.lookup_term(w), w)


class TestShape(unittest.TestCase):
    def test_entry_shape(self):
        e = T.lookup_term("IEEE")
        for k in ("word", "phonetics", "poses", "examples", "source"):
            self.assertIn(k, e)
        self.assertEqual(e["source"], "特称表（内置）")
        self.assertTrue(e["poses"])
        self.assertIsInstance(e["examples"], list)
        self.assertIn("IEEE", e["word"])

    def test_lookup_prefers_term_table(self):
        """lookup() 第一步就命中，不应走联网/模型（cfg 里给个必坏的地址也不会被用到）。"""
        got = L.lookup("IBM", {"engine": "auto", "model": {"baseUrl": "http://127.0.0.1:1", "visionModel": "x"}})
        self.assertIsNotNone(got)
        self.assertEqual(got["source"], "特称表（内置）")

    def test_lookup_still_handles_normal_words(self):
        """特称表不能把普通词的路径吃掉（这里只验证不误命中）。"""
        self.assertIsNone(T.lookup_term("serendipity"))


class TestTableIntegrity(unittest.TestCase):
    def test_all_values_are_3_tuples_of_str(self):
        for name, table in (("TERMS_UPPER", T.TERMS_UPPER), ("TERMS_EXACT", T.TERMS_EXACT)):
            for k, v in table.items():
                self.assertIsInstance(k, str, (name, k))
                self.assertIsInstance(v, tuple, (name, k))
                self.assertEqual(len(v), 3, (name, k))
                for part in v:
                    self.assertIsInstance(part, str, (name, k))
                self.assertTrue(v[0].strip(), ("中文译名不能为空", name, k))
                self.assertTrue(v[1].strip() or v[2].strip(), ("全称/说明至少要有一个", name, k))

    def test_upper_table_keys_are_upper(self):
        for k in T.TERMS_UPPER:
            self.assertEqual(k, k.upper(), k)

    # HTTPS 五个字母且无元音 → 过不了 is_english_word 的「长词必须有元音」规则，
    # 悬停取不到，只有 OCR/图片路径可能把它送进来；保留它但不要求可悬停。
    UNHOVERABLE = {"HTTPS"}

    def test_every_key_is_hoverable(self):
        """所有键都必须能通过 is_english_word（否则鼠标根本取不到这个词，键等于白写）。"""
        for table in (T.TERMS_UPPER, T.TERMS_EXACT):
            for k in table:
                if k in self.UNHOVERABLE:
                    self.assertFalse(L.is_english_word(k), k)   # 白名单里的确实取不到，别误放
                    continue
                self.assertTrue(L.is_english_word(k), k)


if __name__ == "__main__":
    unittest.main()
