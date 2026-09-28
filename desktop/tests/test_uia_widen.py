"""UIA 词位扩展的回归测试。

背景（用户机器上的 daemon 日志为证）：`ExpandToEnclosingUnit(Word)` 得到的是什么，
由**应用程序自己**决定 —— PDF 阅读器把 `state-of-the-art` 报成 `of`、把 `trill`
报成 `tr`、把 `Mezzo-piano` 报成 `Mezzo`。只信它给的词就会弹半截词。

修法：拿应用给的**整行文字** + 词在行内的字符偏移，用 extract_word_at（跨连字符、
遇空白停）重新抠一次整词。

跑：python -m pytest tests/test_uia_widen.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from et_desktop.textgrab import _uia_widen, TEXTUNIT_WORD, TEXTUNIT_LINE     # noqa: E402


class FakeRange:
    """最小 UIA TextRange 替身：语义与真实接口一致（整行 / 词 / 端点移动 / 取文本）。"""

    def __init__(self, text: str, start: int, end: int):
        self.text, self.start, self.end = text, start, end

    def Clone(self):
        c = FakeRange(self.text, self.start, self.end)
        c.starts_with_clone = True
        return c

    def ExpandToEnclosingUnit(self, unit):
        if unit == TEXTUNIT_LINE:
            self.start, self.end = 0, len(self.text)
        # WORD：保持原样 —— 替身代表的正是「应用报出来的那个词」

    def MoveEndpointByRange(self, endpoint, other, target_endpoint):
        self.end = other.start          # 只用到这一种：把终点挪到对方的起点

    def GetText(self, max_length=8192):
        return self.text[self.start:max(0, self.end - self.start + self.start)][:max_length]


def app_reported_word(line: str, word: str, occurrence: int = 1):
    """模拟应用把 line 里的 word 报成一个「词」（Word 单元返回它本身）。"""
    off = -1
    for _ in range(occurrence):
        off = line.find(word, off + 1)
    assert off >= 0, (line, word)
    return FakeRange(line, off, off + len(word))


def widen(line: str, reported: str, occurrence: int = 1) -> str:
    return _uia_widen(app_reported_word(line, reported, occurrence), reported)


# ── 用户实测到的三种半截词 ────────────────────────────────────────────
def test_state_of_the_art():
    line = "Our approach is state-of-the-art and simple to use."
    assert widen(line, "of") == "state-of-the-art"
    assert widen(line, "the") == "state-of-the-art"
    assert widen(line, "art") == "state-of-the-art"
    assert widen(line, "state") == "state-of-the-art"


def test_trill_tr():
    assert widen("The trill is hard to play.", "tr") == "trill"


def test_mezzo_piano():
    assert widen("Above it stands Mezzo-piano, meaning medium soft.", "Mezzo") == "Mezzo-piano"
    assert widen("Above it stands Mezzo-piano, meaning medium soft.", "piano") == "Mezzo-piano"


# ── 不该被改变的情形 ──────────────────────────────────────────────────
def test_plain_word_unchanged():
    assert widen("The quick brown fox jumps.", "quick") == "quick"


def test_word_not_on_the_line_is_unchanged():
    # 词不在这一行里（偏移拿不到）→ 原样返回，不猜
    rng = FakeRange("some other text entirely", 0, 4)
    assert _uia_widen(rng, "zzz") == "zzz"


def test_punctuation_is_stripped_not_included():
    assert widen("He said state-of-the-art, loudly.", "of") == "state-of-the-art"


def test_broken_range_does_not_raise():
    class Broken:
        def Clone(self):
            raise RuntimeError("no text pattern")

    assert _uia_widen(Broken(), "of") == "of"


def test_empty_word_unchanged():
    assert _uia_widen(FakeRange("abc def", 4, 7), "") == ""
