# -*- coding: utf-8 -*-
"""查词引擎：有道公开词典（免 key）+ 任意 OpenAI 兼容端点（默认 Ollama）。

归一化逻辑与浏览器扩展的 lib/normalize.js 同构；`desktop/tests/test_parity.py`
会用 node 跑同一份 JS 并逐字段比对，防止两边跑偏。
"""
from __future__ import annotations

import re
import json
import urllib.request
import urllib.parse

YOUDAO_HOME = "https://dict.youdao.com/result?word=%s&lang=en"
WORD_CHAR = re.compile(r"[A-Za-z'\-\u2019]")
CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\u3040-\u30ff\uac00-\ud7af]")

_TIMEOUT = 6.0


def is_english_word(s) -> bool:
    """全项目唯一的「可查英文单词」判定（与 JS 端 isEnglishWord 同规则）。"""
    if not isinstance(s, str):
        return False
    w = s.strip()
    if not w or len(w) < 2 or len(w) > 45:
        return False
    if CJK.search(w):
        return False
    if not re.match(r"^[A-Za-z][A-Za-z'\-\u2019]*[A-Za-z]$", w):
        return False
    if re.search(r"['\-\u2019]{2,}", w):
        return False
    if len(w) >= 5 and not re.search(r"[aeiouAEIOUyY]", w):
        return False
    return True


def words_in(text: str):
    """枚举文本里所有可查英文单词及其字符区间（供几何兜底用）。"""
    out = []
    if not isinstance(text, str):
        return out
    for m in re.finditer(r"[A-Za-z][A-Za-z'\-\u2019]*[A-Za-z]", text):
        w = m.group(0).replace("\u2019", "'")
        if is_english_word(w):
            out.append({"word": w, "start": m.start(), "end": m.end()})
    return out


def extract_word_at(text: str, offset: int):
    """文本 + 字符偏移处向外扩展出英文单词（与 JS 端 extractWordAt 同规则）。"""
    empty = {"word": "", "start": -1, "end": -1}
    if not isinstance(text, str):
        return empty
    n = max(0, min(offset if isinstance(offset, int) else 0, len(text)))
    at = text[n] if n < len(text) else ""
    before = text[n - 1] if n > 0 else ""

    if at and WORD_CHAR.match(at):
        i = n
    elif not at or at.isspace():
        return empty
    elif before and WORD_CHAR.match(before):
        i = n - 1
    else:
        return empty

    start, end = i, i + 1
    while start > 0 and WORD_CHAR.match(text[start - 1]):
        start -= 1
    while end < len(text) and WORD_CHAR.match(text[end]):
        end += 1

    raw = text[start:end]
    word = re.sub(r"^[^A-Za-z]+", "", re.sub(r"[^A-Za-z]+$", "", raw)).replace("\u2019", "'")
    if not is_english_word(word):
        return empty
    return {"word": word, "start": start, "end": end}


def _phrase(v) -> str:
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        i = (v.get("l") or {}).get("i")
        if isinstance(i, str):
            return i
        if isinstance(i, list) and i and isinstance(i[0], str):
            return i[0]
    return ""


def _humanize(s: str) -> str:
    return re.sub(r"<([^<>]{1,12})>", r"（\1）", s or "")


def _split_pos(line: str):
    text = _humanize(line).strip()
    m = re.match(r"^((?:[a-z]{1,6}\.\s*){1,3})\s*(.+)$", text, re.I)
    if m and m.group(2) and re.search(r"[a-z]", m.group(1)):
        return {"pos": re.sub(r"\s+", " ", m.group(1).strip()), "meaning": m.group(2).strip()}
    return {"pos": "", "meaning": text}


def normalize_youdao(raw: dict, fallback_word: str = ""):
    """有道 jsonapi 响应 → 统一结构；无有效内容返回 None。"""
    if not isinstance(raw, dict):
        return None
    ec_word = ((raw.get("ec") or {}).get("word") or [None])[0]
    simple_word = ((raw.get("simple") or {}).get("word") or [None])[0]
    word = (_phrase((ec_word or {}).get("return-phrase"))
            or _phrase((simple_word or {}).get("return-phrase"))
            or raw.get("input") or fallback_word or "")

    out = {
        "word": word,
        "phonetics": {
            "uk": (ec_word or {}).get("ukphone") or (simple_word or {}).get("ukphone") or "",
            "us": (ec_word or {}).get("usphone") or (simple_word or {}).get("usphone") or "",
        },
        "poses": [],
        "examples": [],
        "forms": [],
        "source": "有道词典",
        "sourceUrl": YOUDAO_HOME % urllib.parse.quote(word or ""),
    }

    for tr in ((ec_word or {}).get("trs") or []):
        lines = (((tr or {}).get("tr") or [None])[0] or {}).get("l", {}).get("i") or []
        for line in lines:
            line = line.strip() if isinstance(line, str) else ""
            if line:
                out["poses"].append(_split_pos(line))

    if not out["poses"] and isinstance((raw.get("fanyi") or {}).get("tran"), str) and raw["fanyi"]["tran"]:
        out["poses"].append({"pos": "", "meaning": _humanize(raw["fanyi"]["tran"])})

    for wf in ((ec_word or {}).get("wfs") or []):
        w = (wf or {}).get("wf") or {}
        if w.get("name") and w.get("value"):
            out["forms"].append({"name": w["name"], "value": w["value"]})

    pairs = (raw.get("blng_sents_part") or {}).get("sentence-pair") or []
    if isinstance(pairs, list):
        for p in pairs:
            en = p.get("sentence") if isinstance(p.get("sentence"), str) else ""
            zh = p.get("sentence-translation") if isinstance(p.get("sentence-translation"), str) else ""
            en, zh = en.strip(), zh.strip()
            if en:
                out["examples"].append({"en": en, "zh": zh})

    has = out["poses"] or out["examples"] or out["phonetics"]["uk"] or out["phonetics"]["us"]
    return out if has else None


def _http_json(url: str, payload: dict | None = None, headers: dict | None = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def lookup_youdao(word: str):
    """在线词典（免 key）。网络异常一律返回 None，由调用方决定如何提示。"""
    try:
        raw = _http_json("https://dict.youdao.com/jsonapi?q=" + urllib.parse.quote(word))
    except Exception:
        return None
    return normalize_youdao(raw, word)


def build_model_prompt(word: str) -> str:
    return "\n".join([
        f"请解释英文单词「{word}」，输出一个 JSON 对象，只要这个对象，不要任何其他文字。",
        '格式示例：{"word":"serendipity","uk":"/ˌserənˈdɪpəti/","us":"/ˌserənˈdɪpəti/",'
        '"poses":[{"pos":"n.","meaning":"意外发现珍奇事物的天赋"}],'
        '"examples":[{"en":"...", "zh":"..."}]}',
        "要求：poses 的 meaning 用中文；examples 给 1-2 句英文例句并附中文翻译；没有的字段留空数组。",
    ])


def extract_json(text):
    """小模型输出容错（与 JS 端 extractJson 同契约）：剥围栏、取首 { 到末 }、
    修复「数组里混进键值对」这类畸形、清尾逗号；4 个候选依次试解析，都不行返回 None。
    契约：**不猜着补括号**——抠不出来就返回 None，由调用方静默。
    """
    if not text:
        return None
    t = str(text).strip()
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.I)
    t = re.sub(r"```\s*$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        return None
    s = t[start:end + 1]

    pos_key = r'"(?:meaning|zh|释义|中文|definition|translation)"'

    def fix(m, opener, closer):
        return opener + '{"pos":"%s","meaning":"%s"}' % (m.group(1), m.group(2)) + closer

    rep = re.sub(r'\[\s*"([^"]{1,20})"\s*,\s*' + pos_key + r'\s*:\s*"((?:[^"\\]|\\.)*)"\s*\]',
                 lambda m: fix(m, '[', ']'), s)
    rep = re.sub(r'\[\s*"([^"]{1,20})"\s*,\s*' + pos_key + r'\s*:\s*"((?:[^"\\]|\\.)*)"',
                 lambda m: fix(m, '[', ''), rep)
    rep = re.sub(r',\s*"([^"]{1,20})"\s*,\s*' + pos_key + r'\s*:\s*"((?:[^"\\]|\\.)*)"(?=\s*[,\]}])',
                 lambda m: fix(m, ',', ''), rep)

    for cand in (s, re.sub(r",\s*([}\]])", r"\1", s), rep, re.sub(r",\s*([}\]])", r"\1", rep)):
        try:
            return json.loads(cand)
        except Exception:
            pass
    return None


def _s(v) -> str:
    """与 JS safeStr 同语义：只认字符串。"""
    return v if isinstance(v, str) else ""


PLACEHOLDERS = ["英文例句", "例句", "中文翻译", "翻译", "中文释义", "英文句子", "英文释义"]


def _example_pair(raw):
    """小模型各种例句写法 → {en, zh}（与 JS examplePair 同语义，含占位符过滤）。"""
    if not raw:
        return None
    if isinstance(raw, str):
        s = raw.strip()
        return {"en": s, "zh": ""} if s and s not in PLACEHOLDERS else None
    if isinstance(raw, list):
        arr = [v.strip() for v in raw if isinstance(v, str) and v.strip()]
        arr = [v for v in arr if v not in PLACEHOLDERS]
        return {"en": arr[0], "zh": arr[1] if len(arr) > 1 else ""} if arr else None
    if isinstance(raw, dict):
        en = (_s(raw.get("en") or raw.get("english") or raw.get("sentence") or raw.get("orig"))).strip()
        zh = (_s(raw.get("zh") or raw.get("cn") or raw.get("chinese") or raw.get("translation") or raw.get("trans"))).strip()
        if en in PLACEHOLDERS:
            en = ""
        if zh in PLACEHOLDERS:
            zh = ""
        if not en:
            vals = [(_s(v)).strip() for v in raw.values()]
            vals = [v for v in vals if v and v not in PLACEHOLDERS]
            if vals:
                en = vals[0]
                if not zh and len(vals) > 1:
                    zh = vals[1]
        return {"en": en, "zh": zh} if en else None
    return None


def _push_pos_lines(out: dict, text):
    for line in re.split(r"[;；\n]+", str(text or "")):
        t = line.strip()
        if t:
            out["poses"].append(_split_pos(t))


def normalize_model(text, fallback_word: str = ""):
    """小模型自由文本 → 统一结构（与 JS normalizeModel 同契约）；无可用内容返回 None。"""
    j = extract_json(text) if not isinstance(text, dict) else text
    if not isinstance(j, dict):
        return None

    out = {
        "word": _s(j.get("word")) or fallback_word or "",
        "phonetics": {"uk": _s(j.get("phonetic_uk")), "us": _s(j.get("phonetic_us"))},
        "poses": [], "forms": [], "examples": [],
        "source": "本地小模型", "sourceUrl": "",
    }

    # 词性释义：扁平字符串 / 字符串数组 / 对象数组 / 映射对象
    pos = j.get("pos") or j.get("pos_list") or j.get("part_of_speech")
    if isinstance(pos, str):
        _push_pos_lines(out, pos)
    elif isinstance(pos, list):
        for item in pos:
            if isinstance(item, str):
                _push_pos_lines(out, item)
            elif isinstance(item, dict):
                meaning = (_s(item.get("meaning") or item.get("zh") or item.get("definition")
                              or item.get("translation"))).strip()
                if meaning:
                    out["poses"].append({"pos": (_s(item.get("pos") or item.get("type"))).strip(),
                                         "meaning": _humanize(meaning)})
    elif isinstance(pos, dict):
        for key, v in pos.items():
            if isinstance(v, str) and v.strip():
                out["poses"].append({"pos": key, "meaning": _humanize(v.strip())})

    ex = j.get("examples") or j.get("example") or j.get("sentences")
    if isinstance(ex, list):
        for e in ex:
            pair = _example_pair(e)
            if pair:
                out["examples"].append(pair)
    elif ex:
        single = _example_pair(ex)
        if single:
            out["examples"].append(single)

    if isinstance(j.get("meaning"), str) and j["meaning"].strip() and not out["poses"]:
        out["poses"].append({"pos": "", "meaning": _humanize(j["meaning"])})

    has = out["poses"] or out["examples"] or out["phonetics"]["uk"] or out["phonetics"]["us"]
    return out if has else None


def lookup_model(word: str, cfg: dict):
    """小模型查词。cfg: {baseUrl, apiKey, textModel}。不可用返回 None。"""
    base = (cfg.get("baseUrl") or "").rstrip("/")
    model = cfg.get("textModel") or ""
    if not base or not model:
        return None
    try:
        raw = _http_json(
            base + "/chat/completions",
            {"model": model, "temperature": 0.1, "max_tokens": 500,
             "messages": [{"role": "user", "content": build_model_prompt(word)}]},
            {"Authorization": "Bearer " + (cfg.get("apiKey") or "none")},
        )
    except Exception:
        return None
    try:
        content = raw["choices"][0]["message"]["content"]
    except Exception:
        return None
    return normalize_model(content, word)


def lookup(word: str, cfg: dict):
    """按引擎顺序取词，返回统一结构或 None。"""
    eng = (cfg or {}).get("engine") or "auto"
    if eng in ("auto", "youdao"):
        got = lookup_youdao(word)
        if got:
            return got
    if eng in ("auto", "model"):
        return lookup_model(word, cfg.get("model") or {})
    return None
