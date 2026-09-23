# -*- coding: utf-8 -*-
"""屏幕取词：UIA（Windows 辅助功能）为主，视觉模型 OCR 为兜底。

实测（2026-09-23，Windows 11 + Python 3.14 + uiautomation 2.0.29）：
  · `TextPattern.RangeFromPoint(x, y)` + `ExpandToEnclosingUnit(TextUnit.Word)`
    能精确取到光标下那个英文单词，浏览器、记事本、Word、Electron 系应用都支持；
  · 词下方偏一点（约 6px）也能取到 —— 与浏览器扩展的行盒容差一致；
  · 取不到的情形（图片、游戏、自绘 UI）交给视觉模型 OCR 兜底；两者都没有则静默。
"""
from __future__ import annotations

import base64
import io
import json
import urllib.request

from .lookup import extract_word_at, is_english_word

try:
    import uiautomation as auto
except Exception:                     # 未装依赖时仍可只用 OCR 兜底
    auto = None

TEXTUNIT_WORD = 2                     # IUIAutomation TextUnit_Word


def word_at_point_uia(x: int, y: int):
    """落点 → (单词, 是否看到文字)。

    第二个返回值很关键：辅助功能说「这里有文字，但不是英文」时，
    必须就此静默（中文上不弹窗的产品铁律）；只有「根本没有文字」才轮到 OCR 兜底。
    """
    if auto is None:
        return None, False
    try:
        ctrl = auto.ControlFromPoint(int(x), int(y))
    except Exception:
        return None, False
    if ctrl is None:
        return None, False

    node = ctrl
    for _ in range(6):
        if node is None:
            break
        try:
            pattern = node.GetTextPattern()
        except Exception:
            pattern = None
        if pattern is not None:
            try:
                rng = pattern.RangeFromPoint(int(x), int(y))
                if rng is None:
                    return None, False
                rng.ExpandToEnclosingUnit(TEXTUNIT_WORD)
                got = (rng.GetText(64) or "").strip()
            except Exception:
                return None, False
            if not got:
                return None, False
            # 取回来的可能是「词 + 尾随空格」甚至标点，统一过取词闸门
            found = extract_word_at(got, 0)
            if found["word"]:
                return found["word"], True
            for cand in _tokenize(got):
                if is_english_word(cand):
                    return cand, True
            return None, True              # 有文字但不是英文 → 静默
        try:
            node = node.GetParentControl()
        except Exception:
            return None, False
    return None, False


def _tokenize(s: str):
    out, cur = [], []
    for ch in s or "":
        if ch.isalpha() or ch in "'-\u2019":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def _grab_png(x: int, y: int, w: int = 220, h: int = 84) -> bytes | None:
    """截取光标附近一小块（要小：块大了会把邻行的英文也收进来，误判成\"指到的词\"）。"""
    try:
        from PIL import ImageGrab
    except Exception:
        return None
    try:
        img = ImageGrab.grab(bbox=(x - w // 2, y - h // 2, x + w // 2, y + h // 2), all_screens=True)
    except Exception:
        return None
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def word_at_point_ocr(x: int, y: int, cfg: dict):
    """视觉模型 OCR 兜底（本地 Ollama 之类）。识别不到英文一律返回 None。"""
    cfg = cfg or {}
    base = (cfg.get("baseUrl") or "").rstrip("/")
    model = cfg.get("visionModel") or ""
    if not base or not model:
        return None
    png = _grab_png(x, y)
    if not png:
        return None
    prompt = ("这是一张截图的小块，用户鼠标停在图的正中央附近。"
              "找出该位置附近的英文单词：有就输出 {\"word\":\"单词\"}，"
              "没有可辨认的英文单词就输出 {\"word\":null}。只输出这一个 JSON，不要解释。")
    body = {
        "model": model, "temperature": 0, "max_tokens": 60,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}},
        ]}],
    }
    try:
        req = urllib.request.Request(
            base + "/chat/completions", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + (cfg.get("apiKey") or "none")})
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
    except Exception:
        return None
    from .lookup import normalize_model, extract_json
    obj = extract_json(content) if isinstance(content, str) else None
    if isinstance(obj, dict) and isinstance(obj.get("word"), str):
        w = obj["word"].strip()
        return w if is_english_word(w) else None
    return None


def word_at_point(x: int, y: int, cfg: dict):
    """屏幕落点 → 英文单词；什么都取不到就返回 None（调用方必须静默）。

    优先级与产品铁律：
      ① UIA 取到英文 → 用它；
      ② UIA 说这里有文字但不是英文 → **就此静默**（中文上绝不弹窗）；
      ③ 这里根本没有文字（图片、自绘 UI）→ 才用视觉模型 OCR 兜底。
    """
    word, saw_text = word_at_point_uia(x, y)
    if word:
        return word, "uia"
    if saw_text:
        return None, ""
    word = word_at_point_ocr(x, y, (cfg or {}).get("model") or {})
    if word:
        return word, "ocr"
    return None, ""
