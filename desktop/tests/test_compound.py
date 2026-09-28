"""连字符复合词：定向重问条件的回归测试。

背景：图上写 `state-of-the-art`，红圈压在中间的 `of` 上时，3B 视觉模型会按
「圈住的是一个完整单词」规则只答 `of`（或只答 `piano`，若词是 Mezzo-piano）。
提示词已点名这个场景；这里测的是兜底判据 —— 什么时候值得*再问一次*。

判据基于「按词裁剪量出的墨迹段宽度」与「模型答的那个词该有多宽」的关系：
墨迹段 ≈ 词宽 → 模型读的就是整个词，不必再问（普通正文里悬停 the/of 就是这种）；
墨迹段明显更宽 → 多半只读到复合词里的一截 → 再问一次。

（曾经还试过在像素上直接找「连字符样墨迹」，实测不可靠：字母 e 的中横、t 的
 横杠与连字符几何上无法区分，已删除。）

跑：python -m pytest tests/test_compound.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from et_desktop.textgrab import need_compound_retry          # noqa: E402


# ── 该重问的情形 ──────────────────────────────────────────────────────
def test_retry_when_only_inner_small_word_read():
    # 用户实测场景：state-of-the-art（行高 26、墨迹段约 230px）里只读到 of
    assert need_compound_retry("of", 230, 26) is True
    assert need_compound_retry("the", 250, 26) is True
    assert need_compound_retry("to", 300, 30) is True


def test_retry_on_real_screen_geometry():
    # 实机量到的数据：大字（行高 74）、按词裁剪 900px 宽
    assert need_compound_retry("of", 900, 74) is True


def test_retry_on_fragment_stem():
    # of-the-art 这类残段（含连字符，但比墨迹段窄很多）
    assert need_compound_retry("of-the-art", 230, 26) is True


# ── 不该重问的情形（不然会白花一次推理 / 或把答案换成别处的词）────────
def test_no_retry_when_word_fills_the_run():
    # 墨迹段≈词宽：模型读的就是整个词
    assert need_compound_retry("of", 48, 26) is False
    assert need_compound_retry("the", 40, 26) is False


def test_no_retry_when_already_complete():
    # 已经读全了整个复合词 → 不必再问
    assert need_compound_retry("state-of-the-art", 230, 26) is False
    assert need_compound_retry("well-known", 130, 22) is False
    assert need_compound_retry("Mezzo-piano", 200, 26) is False


def test_no_retry_for_ordinary_words():
    for w in ("hello", "Fraction", "Subnormal", "IEEE", "Exponent", "Bias"):
        assert need_compound_retry(w, 900, 74) is False, w


def test_no_retry_on_empty_input():
    assert need_compound_retry("", 900, 74) is False
    assert need_compound_retry("of", 900, 0) is False
    assert need_compound_retry(None, 900, 26) is False


def test_inner_word_set_is_lowercase_only():
    # 只有「小词」本身才会被视为可能的一截；实词不会
    assert need_compound_retry("Of", 900, 74) is True     # 大小写不敏感
    assert need_compound_retry("off", 900, 74) is False   # off 是实词，不是内部小词
