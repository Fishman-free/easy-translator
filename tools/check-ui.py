# -*- coding: utf-8 -*-
"""
Easy Translator · UI 与立绘资产的不变量校验

    python tools/check-ui.py          （或 npm run check:ui）

为什么需要它：视觉资产的退化不会被语法检查或单测发现 —— 立绘被裁掉半边、白衣服被抠成洞、
预览图还是旧立绘的，测试照样全绿，用户一眼就看出来。这里把这些「眼睛能看出来、
但机器默认不查」的东西变成断言。

分节：
  ① 立绘资产不变量（assets/mascot.png，CI 上也能跑）
  ② 本机重抽取对账（原始截图在时才跑：重抽一遍，与已提交资产逐像素比对）
  ③ 桌面气泡渲染（desktop/et_desktop/ui.py）：白底不透明、她完整、她嘴左上是立绘本身（无压脸装饰）
  ④ 扩展 CSS 纯几何推算（content/card.css）：她贴右下角、尾点末端落在嘴上
  ⑤ 资产新鲜度：预览图确实由当前立绘生成（陈旧预览会让人对着过时的图做判断）

退出码：0 = 全过；1 = 有失败（打印失败项）。
"""
import importlib.util
import json
import os
import re
import sys
import time
import datetime

from PIL import Image, ImageGrab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASCOT = os.path.join(ROOT, "assets", "mascot.png")
# 立绘的嘴部位置（tools/make-mascot.py 按肤色像素实测 68.9/134 × 98.9/140）
MOUTH = (0.514, 0.706)
# 原始截图（仅本机，不入库）；存在时额外做重抽取对账
SOURCE_CANDIDATES = [
    r"C:\Users\21560\Pictures\Screenshots\屏幕截图 2026-09-23 094406.png",
    os.path.join(ROOT, "assets", "mascot-source.png"),
]
NAVY = (30, 50, 100)
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("  ✔ " if ok else "  ✖ ") + name + ("   [" + str(detail) + "]" if detail else ""))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def audit_of(art):
    return load(os.path.join(ROOT, "tools", "make-mascot.py"), "make_mascot").audit(art)


def invariants(art, label):
    """立绘的四条不变量：含左半边、头身俱全、无气泡残片、剪影无洞。"""
    mm = load(os.path.join(ROOT, "tools", "make-mascot.py"), "make_mascot")
    w, h = art.size
    px = art.load()
    left = sum(1 for y in range(int(h * 0.45), h) for x in range(0, int(w * 0.20)) if px[x, y][3] > 120)
    head, body, bubble, holes = mm.audit(art)
    check("%s 含左半边（耳朵/头发/袍角）" % label, left > 400, "左缘带不透明 %d px" % left)
    check("%s 头身俱全" % label, head > w * 3 and body > w * 3, "头 %d / 身 %d" % (head, body))
    check("%s 未混入它自带的气泡/尾点" % label, bubble <= 10, "气泡轮廓色 %d px" % bubble)
    check("%s 剪影无洞（白衣服没被抠掉）" % label, holes == 0, "空洞 %d px" % holes)


print("Easy Translator · UI/资产不变量\n")

print("① 立绘资产（assets/mascot.png）")
if not os.path.exists(MASCOT):
    check("立绘存在", False, MASCOT)
else:
    art = Image.open(MASCOT).convert("RGBA")
    check("立绘存在且尺寸合理", art.width >= 130 and art.height >= 130, "%dx%d" % art.size)
    invariants(art, "立绘")

print("\n② 本机重抽取对账")
src = next((p for p in SOURCE_CANDIDATES if os.path.exists(p)), None)
if not src:
    print("  ⚠ 未找到原始截图（非本机环境），跳过 —— ① 已验已提交资产")
else:
    mm = load(os.path.join(ROOT, "tools", "make-mascot.py"), "make_mascot")
    fresh, info = mm.extract_character(Image.open(src).convert("RGB"))
    check("重抽结果与已提交立绘逐像素一致",
          fresh.size == art.size and list(fresh.getdata()) == list(art.getdata()),
          "重抽 %s｜已提交 %s" % (fresh.size, art.size))
    check("嘴部实测可复现", info.get("mouth") and info.get("skin_px", 0) > 200,
          "mouth=%s skin=%s" % (info.get("mouth"), info.get("skin_px")))

print("\n③ 桌面气泡渲染（desktop/et_desktop/ui.py）")
sys.path.insert(0, os.path.join(ROOT, "desktop"))
ui = load(os.path.join(ROOT, "desktop", "et_desktop", "ui.py"), "et_ui")
card = ui.render_card({"word": "serendipity",
                       "poses": [{"pos": "n.", "meaning": "意外发现珍奇事物的天赋"}],
                       "examples": [{"en": "A stroke of serendipity.", "zh": "一次机缘。"}],
                       "source": "自检"},
                      ui.load_mascot(MASCOT), scale=1.0)
cw, ch = card.size
cpx = card.load()
mid = [cpx[cw // 2, ch // 2 + dy] for dy in range(-6, 7)]
check("气泡内部不透明（alpha=255）", all(p[3] == 255 for p in mid),
      "中线 alpha=%s" % sorted({p[3] for p in mid}))
check("气泡内部是白色（用户要求：不透明、看得清）", all(p[:3] == (255, 255, 255) for p in mid),
      "中线色=%s" % sorted({p[:3] for p in mid})[:2])
mw = ui.MASCOT_W
mh = round(art.height * mw / art.width)
mx, my = cw - mw - 6, (ch - 34) - 2 - mh
her_left = sum(1 for y in range(my + int(mh * 0.45), my + mh) for x in range(mx, mx + 8) if cpx[x, y][3] > 120)
check("渲染图里她的左半边也在", her_left > 8, "她左缘不透明 %d px" % her_left)
# 尾点已按用户要求去掉 —— 这里断言「她嘴的左上就是立绘本身」，谁再画回小圆就变红
# （旧断言是"尾点末端贴嘴"，尾点删除后它正确地报了红：检查与设计要同步改）
mouth = (mx + int(mw * MOUTH[0]), my + int(mh * MOUTH[1]))
probe_pt = (mouth[0] - 24, mouth[1] - 17)            # 尾点旧圆心
art_px = art.load()
ax = min(art.width - 1, max(0, round((probe_pt[0] - mx) * art.width / mw)))
ay = min(art.height - 1, max(0, round((probe_pt[1] - my) * art.height / mh)))
want = art_px[ax, ay]
got = cpx[probe_pt[0], probe_pt[1]]
# 立绘在该点透明 → 渲染里应是白底气泡；有像素 → 应与立绘一致（容抗锯齿/羽化）
expect = (255, 255, 255) if want[3] < 120 else want[:3]
check("她嘴的左上就是立绘本身（尾点已按要求去掉，不许再压脸）",
      all(abs(got[i] - expect[i]) <= 14 for i in range(3)),
      f"渲染 {got[:3]} vs 应为 {expect[:3]}（旧尾点圆心 {probe_pt}）")

# 释义必须整句横排 —— 曾因「存裸 ls / 取 [0]」被排成一字一行（用户：太丑了）
long_card = ui.render_card(
    {"word": "github", "phonetics": {"us": "/ˈɡɪthʌb/"},
     "poses": [{"pos": "n.", "meaning": "一个开源项目托管平台，让所有人都能参与协作开发"}],
     "source": "回归"}, ui.load_mascot(MASCOT), scale=1.0)
check("长释义整句横排（不许一字一行）", long_card.height < 320,
      "23 字释义渲染高 %d（一字一行会 ≥500）" % long_card.height)
_prev = Image.new("RGB", long_card.size, (255, 255, 255))
_prev.paste(long_card, (0, 0), long_card)
_prev.save(os.path.join(ROOT, "docs", "screenshot-card-long.png"))

print("\n④ 扩展 CSS 纯几何推算（content/card.css，与 ③ 同一套嘴部比例）")
css = open(os.path.join(ROOT, "content", "card.css"), encoding="utf-8").read()


def px_of(block, prop):
    m = re.search(prop + r":\s*(-?\d+)px", block)
    return int(m.group(1)) if m else None


m_block = css.split(".et-mascot {")[1].split("}")[0]
t_block = css.split(".et-tail {")[1].split("}")[0]
m_right, m_bottom, m_w = px_of(m_block, "right"), px_of(m_block, "bottom"), px_of(m_block, "width")
t_right, t_bottom = px_of(t_block, "right"), px_of(t_block, "bottom")
CARD_W, CARD_H = 380, 502          # 布局探针实测的卡片尺寸
m_h = round(m_w * art.height / art.width)
m_left, m_top = CARD_W - m_right - m_w, CARD_H - m_bottom - m_h
css_mouth = (m_left + round(m_w * MOUTH[0]), m_top + round(m_h * MOUTH[1]))
dots_right, dots_bottom = CARD_W - t_right, CARD_H - t_bottom + 6   # 第二颗点有 -6px 下边距
check("CSS 里她贴在整个对话框的右下角", m_right <= 10 and m_bottom <= 4,
      "right=%s bottom=%s" % (m_right, m_bottom))
check("CSS 是白底气泡（不透明背景）", "background: #ffffff" in css and ".et-card" in css)
check("CSS 里尾点已按要求去掉（.et-tail/.et-dot 不再有绘制规则）",
      ".et-tail {" not in css and ".et-dot {" not in css)

print("\n⑤ 资产新鲜度（预览图是否由当前立绘生成）")
prev_path = os.path.join(ROOT, "docs", "mascot-preview.png")
if os.path.exists(prev_path):
    prev = Image.open(prev_path).convert("RGB")
    big = art.resize((art.width * 3, art.height * 3), Image.NEAREST)   # make_preview 的几何：16px 边距、3x
    bpx, ppx = big.load(), prev.load()
    same = diff = 0
    for y in range(0, big.height, 2):
        for x in range(0, big.width, 2):
            r, g, b, a = bpx[x, y]
            if a < 120:
                continue
            pr, pg, pb = ppx[16 + x, 16 + y]
            if abs(pr - r) <= 3 and abs(pg - g) <= 3 and abs(pb - b) <= 3:
                same += 1
            else:
                diff += 1
    check("docs/mascot-preview.png 与当前立绘逐像素一致", diff == 0 and same > 4000,
          "一致 %d / 不一致 %d" % (same, diff))
else:
    check("docs/mascot-preview.png 存在", False)

art_mtime = os.path.getmtime(MASCOT)
for rel in ("docs/screenshot-web.png", "store/screenshots/1-web.png"):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        check("%s 存在" % rel, False)
        continue
    m = os.path.getmtime(p)
    fmt = lambda t: datetime.datetime.fromtimestamp(t).strftime("%H:%M:%S")
    check("%s 不陈旧（否则那张图用的是旧立绘）" % rel, m >= art_mtime - 1,
          "图 %s｜立绘 %s" % (fmt(m), fmt(art_mtime)))

print("\n⑥ 设置窗口真机出图（desktop/et_desktop/settings_ui.py）")
try:
    import tkinter as tk
    from et_desktop import settings_ui
    root = tk.Tk()
    root.withdraw()
    win = settings_ui.SettingsWindow(root, json.loads(json.dumps(
        {"enabled": True, "dwellMs": 5000, "engine": "auto", "examplesCount": 3, "showSpeak": True,
         "model": {"enabled": False, "baseUrl": "http://127.0.0.1:11434/v1", "apiKey": "",
                   "textModel": "qwen2.5:1.5b", "visionModel": "qwen2.5vl:3b", "timeoutMs": 60000},
         "imageOcr": {"enabled": True, "dwellMs": 1500, "cropW": 460, "cropH": 140, "hint": True}})),
        lambda *a: None, mascot=art, test_text=lambda: (True, "✔ ok"))
    win.update_idletasks()
    win.deiconify()
    # 必须真正置顶：不然截到的是盖在它上面的窗口（曾截成终端：纯白 0、藏青 5）
    win.lift()
    try:
        win.attributes("-topmost", True)
    except Exception:
        pass
    win.update()
    time.sleep(0.5)
    win.update()
    x, y = win.winfo_rootx(), win.winfo_rooty()
    w, h = win.winfo_width(), win.winfo_height()
    shot = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    out = os.path.join(ROOT, "docs", "screenshot-desktop-settings.png")
    shot.save(out)
    check("设置窗口真机出图", w > 200 and h > 300, f"{w}x{h} → {os.path.relpath(out, ROOT)}")
    sp = shot.convert("RGB").load()
    navy = sum(1 for yy in range(0, shot.height, 2) for xx in range(0, shot.width, 2)
               if abs(sp[xx, yy][0] - 30) < 18 and abs(sp[xx, yy][1] - 50) < 18 and abs(sp[xx, yy][2] - 100) < 22)
    white = sum(1 for yy in range(0, shot.height, 2) for xx in range(0, shot.width, 2) if sp[xx, yy] == (255, 255, 255))
    check("设置窗口是白卡 + 藏青描边（鲸鱼娘设计语言）", navy > 200 and white > 2000,
          f"藏青 {navy} / 纯白 {white}（每 4 像素采样）")
    win.destroy()
    root.destroy()
except Exception as e:
    check("设置窗口真机出图", False, str(e)[:80])

failed = [n for n, ok in results if not ok]
print("\n" + "─" * 58)
print("UI/资产校验：%d/%d 项通过" % (len(results) - len(failed), len(results)))
if failed:
    print("失败项：" + "；".join(failed))
    sys.exit(1)
