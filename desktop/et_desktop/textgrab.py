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
import os
import time
import urllib.request

from PIL import Image, ImageDraw

from .lookup import extract_word_at, is_english_word, is_letter_like, CJK

try:
    import uiautomation as auto
except Exception:                     # 未装依赖时仍可只用 OCR 兜底
    auto = None

TEXTUNIT_WORD = 2                     # IUIAutomation TextUnit_Word

# UIA 走树单次要 ~500ms（实测 513ms），而守护每轮轮询都要调一次——驻留 2 秒 = 十几轮，
# 光这一项就吃掉 2 秒以上。按 12px 网格缓存一小段时间，驻留期间的轮询变成内存命中。
_UIA_CACHE: dict = {}
_UIA_TTL = 1.5


def word_at_point_uia(x: int, y: int):
    """（带网格缓存）落点 → (单词, 是否看到文字)。"""
    key = (int(x) // 12, int(y) // 12)
    now = time.time()
    hit = _UIA_CACHE.get(key)
    if hit is not None and now - hit[0] < _UIA_TTL:
        return hit[1], hit[2]
    word, saw = _word_at_point_uia_uncached(x, y)
    if len(_UIA_CACHE) > 512:
        _UIA_CACHE.clear()
    _UIA_CACHE[key] = (now, word, saw)
    return word, saw


def _word_at_point_uia_uncached(x: int, y: int):
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
    for _ in range(24):
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
            # ① 先判定这段文字到底在不在光标底下。
            #   ExpandToEnclosingUnit 会把落点扩展成「邻近的词」，图片/画布/带缩放变换的
            #   容器（PDF 阅读器、Electron）尤其会给出「在别处」的文字 —— 那时必须交给 OCR，
            #   否则会出现「点在图上却静默」或「点在 A 处翻译 B 处」。
            try:
                rects = rng.GetBoundingRectangles()
                if rects:
                    inside = any(r.left - 4 <= x <= r.right + 4 and
                                 r.top - 4 <= y <= r.bottom + 4 for r in rects)
                    if not inside:
                        gap = min(max(max(r.left - x, x - r.right),
                                      max(r.top - y, y - r.bottom)) for r in rects)
                        if gap > 24:          # 不是紧贴的词缝 → 文字在别处
                            return None, False
                        return None, True     # 词缝空白：按铁律静默
            except Exception:
                pass
            # 取回来的可能是「词 + 尾随空格」甚至标点，统一过取词闸门
            found = extract_word_at(got, 0)
            if found["word"]:
                return found["word"], True
            for cand in _tokenize(got):
                if is_english_word(cand):
                    return cand, True
            for ch in got:                 # 希腊字母 / 花体·双线体等变体字母：内置表有读音
                if is_letter_like(ch):
                    return ch, True
            # 剩下的情况：这段文字确实在光标下，但它不是英文/希腊字母/数学变体。
            #   · 含中文 → 按产品铁律静默（中文上绝不弹窗）；
            #   · 其它（数字、符号、箭头、空白…）→ 报「这里没文字」，交给 OCR 按像素再试
            #     （数学符号 PDF 就靠这一步；OCR 读到中文会返回 null，依旧静默）
            if CJK.search(got):
                return None, True
            return None, False
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


def _grab_png(x: int, y: int, w: int = 160, h: int = 64) -> bytes | None:
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


_OCR_CACHE: dict = {}          # (12px 网格坐标) -> (ts, word或None)；成功缓存数秒、失败缓存 30 秒
# 游戏守护标记（可选，环境变量 ET_GAMING_FLAG 指定）：文件存在时不发起 OCR，
# 避免把本地视觉模型重新拉回显存（打游戏时抢显存会卡）。
GAMING_FLAG = os.environ.get("ET_GAMING_FLAG")


def _confirm_single(x: int, y: int, base: str, model: str, cfg: dict, ch: str) -> bool:
    """单字符答案复核：用更紧的裁剪再问一次「红叉中心是什么字符」，一致才采用。

    3B 模型偶尔会凭空报一个字母（用户报过「范围过大」——空白处冒出 X）。
    紧裁剪里只剩一个字符，模型要么读对、要么说没有，幻觉明显更少。"""
    png = _grab_png(x, y, w=96, h=60)
    if not png:
        return True                    # 复核不了就别拦，宁可弹出
    try:
        img = Image.open(io.BytesIO(png)).convert("RGB")
        d = ImageDraw.Draw(img)
        cx, cy = img.width // 2, img.height // 2
        d.ellipse([cx - 16, cy - 11, cx + 16, cy + 11], outline=(255, 0, 0), width=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png = buf.getvalue()
    except Exception:
        return True
    body = {
        "model": model, "temperature": 0, "max_tokens": 20,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "红色圆圈只是鼠标标记（不是字符）。圆圈圈住的是哪个字符？"
                                     "只输出那一个字符（希腊字母/花体字母原样输出，如 Ω ℱ λ）；"
                                     "圈住的位置没有字符就只输出 null。"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,"
                                                 + base64.b64encode(png).decode()}}]}],
    }
    try:
        req = urllib.request.Request(
            base + "/chat/completions", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + (cfg.get("apiKey") or "none")})
        with urllib.request.urlopen(req, timeout=float(cfg.get("visionTimeoutSec") or 90.0)) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        ans = (raw["choices"][0]["message"]["content"] or "").strip().strip("`\"' ")
    except Exception:
        return True                    # 复核通道失败不影响主流程
    if not ans or ans.lower() in ("null", "none", "无", "没有"):
        return True         # 紧裁剪里认不出来 → 不据此否决（实测它对小字号真字符也常认不出）
    # 允许大小写/写法差异（ℱ 与 F、Ω 与 omega）
    a, b = ans.strip(), ch.strip()
    if a == b or a.lower() == b.lower():
        return True
    if len(a) == 1 and len(b) == 1 and a.upper() == b.upper():
        return True
    return False            # 两次读数明显矛盾（如 X vs Y）→ 判为幻觉


def _has_ink(img, half_w: int = 26, half_h: int = 20) -> bool:
    """光标正下方（裁剪图中心那一小块）有没有笔迹。

    只看中心那一小块：光标必须真的**压在字符上**才算数。裁剪图里别处有字（旁边的文字、
    图标、窗口边框）不算——否则满屏都是「有墨迹」，空白处照样弹窗。
    纯空白直接判空、不问模型：既省掉 1-2 秒的模型调用，也杜绝「空白处凭空冒出字母」。"""
    try:
        px = img.load()
        w, h = img.size
        cx, cy = w // 2, h // 2
        x0, x1 = max(0, cx - half_w), min(w, cx + half_w)
        y0, y1 = max(0, cy - half_h), min(h, cy + half_h)
        dark = 0
        for yy in range(y0, y1, 2):        # 隔行隔列采样，够用且快
            for xx in range(x0, x1, 2):
                r, g, b = px[xx, yy][:3]
                if r > g + 45 and r > b + 45:
                    continue               # 红色标记（圆圈/叉）自己不算
                if (r * 299 + g * 587 + b * 114) // 1000 < 150:
                    dark += 1
                    if dark >= 6:
                        return True
        return False
    except Exception:
        return True                        # 判不了就不拦


def word_at_point_ocr(x: int, y: int, cfg: dict):
    """视觉模型 OCR 兜底（本地 Ollama 之类）。识别不到英文一律返回 None。"""
    cfg = cfg or {}
    # 配置是嵌套的（model.baseUrl / model.visionModel，与扩展 settings-core 同构）；
    # 早期这里读的是扁平键，永远取不到 → OCR 兜底被静默短路。扁平键仅作兼容回退。
    m = cfg.get("model") or {}
    base = (m.get("baseUrl") or cfg.get("baseUrl") or "").rstrip("/")
    model = m.get("visionModel") or cfg.get("visionModel") or ""
    if not base or not model:
        return None
    if (cfg.get("imageOcr") or {}).get("enabled") is False:
        return None                      # 设置里关掉了图片取词
    if GAMING_FLAG and os.path.exists(GAMING_FLAG):
        return None                      # 游戏中：静默，不加载视觉模型抢显存
    # 缓存：驻留期间同一位置不重复打模型；识别不到/服务不可用也不狂拍（负缓存 30s）
    key = (int(x) // 12, int(y) // 12)
    now = time.time()
    hit = _OCR_CACHE.get(key)
    if hit is not None:
        ts, w = hit
        if w and now - ts < 30:      # 同一个词：30 秒内重悬停直接命中，不再打模型
            return w
        if not w and now - ts < 30:
            return None
    png = _grab_png(x, y)
    if not png:
        return None
    # 关键：ImageGrab 不带鼠标光标，模型在多个词的截图里根本不知道指哪个词
    #（实测「hello world」指 world 会返回 hello）。在截图中心画一个红叉当鼠标锚点。
    try:
        img = Image.open(io.BytesIO(png)).convert("RGB")
        d = ImageDraw.Draw(img)
        cx, cy = img.width // 2, img.height // 2
        # 锚点用**红色圆圈**而不是红叉：实测模型会把红叉本身当成字母 X 报出来
        #（「空白处冒出 x」的真凶就是这个）。
        d.ellipse([cx - 20, cy - 14, cx + 20, cy + 14], outline=(255, 0, 0), width=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png = buf.getvalue()
    except Exception:
        img = None
    # 空白区域直接判空（不问模型）：省时间 + 杜绝「空白处冒出字母」的幻觉
    if img is not None and not _has_ink(img):
        _OCR_CACHE[key] = (now, None)
        _trace(f"({x},{y}) OCR 跳过：光标处没有笔迹（空白）")
        return None
    prompt = ("图中有一个红色圆圈，圆圈只是鼠标位置的标记（它不是字符，不要把它读成 X 或 ○）；\n"
              "圆圈圈住的位置就是要读的字符。按下面规则只输出一个 JSON，不要解释：\n"
              "- 圈住的是英文字母 → 输出它所在的**完整英文单词**：{\"word\":\"word\"}\n"
              "- 圈住的是一个孤立的单个字母（数学变量，如 F X n，也可能写成花体 ℱ ℒ 𝒩）"
              "→ 输出这个字母本身：{\"word\":\"F\"}\n"
              "- 圈住的是希腊字母 → 原样输出该字母（如 Ω α λ β）：{\"word\":\"Ω\"}\n"
              "- 圈住的是花体/双线体/哥特体字母（如 ℒ ℝ 𝔼 𝒩 𝔤 𝓛 ℱ）→ 原样输出该字符：{\"word\":\"ℒ\"}\n"
              "- 圈住的是中文/数字/标点/空白/什么都没有 → {\"word\":null}")
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
        # 冷启动 1–3 分钟：超时给足余量，否则「第一次永远查不到」（用户会以为功能坏了）。
        # 启动时另有 warmup_vision() 把模型预热进内存，正常路径只要几百毫秒。
        with urllib.request.urlopen(req, timeout=float(cfg.get("visionTimeoutSec") or 90.0)) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
    except Exception:
        _OCR_CACHE[key] = (now, None)      # 服务不可用也负缓存，避免狂拍
        return None
    from .lookup import normalize_model, extract_json
    obj = extract_json(content) if isinstance(content, str) else None
    if isinstance(obj, dict) and isinstance(obj.get("word"), str):
        w = obj["word"].strip().strip("`").strip()
        if w.lower() in ("null", "none", "nan", "无", "没有", "—", "-"):
            w = ""                       # 模型有时把 JSON null 写成字符串 "null"
        w = w if (is_english_word(w) or is_letter_like(w)
                  or (len(w) == 1 and w.isascii() and w.isalpha())) else None
        # 末尾那项：图片/PDF 里的孤立单字母（数学变量 F、X、n…）——文字取词那边单字母
        # 仍按产品规则不触发，这里只放开 OCR 路径（需要在图上停住才会走到）。
        if w and len(w) == 1 and w.isascii() and w.isalpha():
            # 普通单字母（数学变量 F X n）最容易被凭空报出来 → 复核一次；
            # 希腊字母/花体字母有辨识度、复核又慢，就不复核了。
            if not _confirm_single(x, y, base, model, cfg, w):
                _OCR_CACHE[key] = (now, None)
                return None
        _OCR_CACHE[key] = (now, w)
        return w
    _OCR_CACHE[key] = (now, None)
    return None


_TRACE_LAST = None


def _trace(msg):
    """轻量轨迹（每个新格子一行）——排查「悬停没反应」用；文件超 256KB 自动清掉。"""
    try:
        p = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        os.pardir, "lookup_trace.log"))
        if os.path.exists(p) and os.path.getsize(p) > 262144:
            os.remove(p)
        with open(p, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def word_at_point(x: int, y: int, cfg: dict):
    """屏幕落点 → 英文单词；什么都取不到就返回 None（调用方必须静默）。

    优先级与产品铁律：
      ① UIA 取到英文 → 用它；
      ② UIA 说这里有文字但不是英文 → **就此静默**（中文上绝不弹窗）；
      ③ 这里根本没有文字（图片、自绘 UI）→ 才用视觉模型 OCR 兜底。
    """
    global _TRACE_LAST
    cell = (int(x) // 12, int(y) // 12)
    tr = cell != _TRACE_LAST
    _TRACE_LAST = cell
    word, saw_text = word_at_point_uia(x, y)
    if tr:
        _trace(f"({x},{y}) UIA={word!r} saw_text={saw_text}")
    if word:
        return word, "uia"
    if saw_text:
        if tr:
            _trace(f"({x},{y}) 静默：UIA 认为此处有文字但非英文/是词缝空白（不走 OCR）")
        return None, ""
    word = word_at_point_ocr(x, y, (cfg or {}).get("model") or {})
    if tr:
        _trace(f"({x},{y}) OCR={word!r} → {'出卡片' if word else '静默'}")
    if word:
        return word, "ocr"
    return None, ""
