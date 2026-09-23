# -*- coding: utf-8 -*-
"""
桌面端到端：证明「整台电脑都能取词」——不是浏览器，是任意应用。

    python tools/e2e_desktop.py

场景：
  ① 起一个真实 Notepad，里面放英文句子与纯中文句子
  ② 把光标停在英文词上 → UIA 必须取到那个词（这是「整台电脑取词」的关键能力）
  ③ 光标停在中文上 → 必须取不到词（不弹窗的产品铁律）
  ④ 查词 + 渲染气泡 → 截屏确认浮层真的显示出来（含鲸鱼娘）
"""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from et_desktop import app as app_mod            # noqa: E402
from et_desktop import lookup, textgrab, ui      # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("  ✔ " if ok else "  ✖ ") + name + ("   [" + str(detail) + "]" if detail else ""))


def main() -> int:
    cfg = app_mod.load_cfg()
    print("== 桌面端到端 ==")

    text = "The serendipity of a good dictionary rewards curiosity.\n这是一段纯中文的文字，不该取词。\n"
    txt = os.path.join(tempfile.gettempdir(), "et-desktop-e2e.txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write(text)
    proc = subprocess.Popen(["notepad.exe", txt])
    time.sleep(3.0)

    try:
        import uiautomation as auto
        win = auto.WindowControl(searchDepth=1, Name="et-desktop-e2e*")
        if not win.Exists(3, 1):
            win = auto.WindowControl(searchDepth=1, ClassName="Notepad")
        check("起真实 Notepad 并找到窗口", win.Exists(2, 1), win.Name if win.Exists(1, 0.2) else "")

        edit = auto.EditControl(searchFromControl=win, searchDepth=8)
        if not edit.Exists(2, 1):
            edit = auto.DocumentControl(searchFromControl=win, searchDepth=8)
        check("找到文本控件", edit.Exists(2, 1), edit.ControlTypeName)

        r = edit.BoundingRectangle
        pattern = edit.GetTextPattern()
        check("文本控件提供 TextPattern", pattern is not None)

        # ② 英文词上取词
        got = None
        for frac in (0.10, 0.16, 0.22, 0.30, 0.38, 0.46):
            x, y = int(r.left + r.width() * frac), int(r.top + 14)
            word, src = textgrab.word_at_point(x, y, cfg)
            if word:
                got = (word, src, x, y)
                break
        check("光标在英文词上 → 取到词", bool(got), got and "%s（%s @ %d,%d）" % (got[0], got[1], got[2], got[3]))
        if not got:
            return finish()

        word = got[0]
        check("取到的是合法英文单词", lookup.is_english_word(word), word)

        # ③ 中文上不取词。用 FindText 精确定位中文串的矩形（别按行高猜：英文首句会换行）
        cn_hits = []
        cn_points = []
        try:
            rng = pattern.DocumentRange.FindText("这是一段纯中文的文字", False, False)
            if rng is not None:
                for rect in (rng.GetBoundingRectangles() or []):
                    # uiautomation 返回 Rect 对象（带属性），不是元组
                    if hasattr(rect, "left"):
                        l, t, rr, b = rect.left, rect.top, rect.right, rect.bottom
                    else:
                        vals = list(rect) if not isinstance(rect, (int, float)) else []
                        if len(vals) < 4:
                            continue
                        l, t, rr, b = vals[:4]
                    if rr > l and b > t:
                        cn_points.append((int((l + rr) / 2), int((t + b) / 2)))
        except Exception as e:
            print("    [注] FindText 取中文矩形失败:", str(e)[:60])
        for (x, y) in cn_points:
            w, _ = textgrab.word_at_point(x, y, cfg)
            if w:
                cn_hits.append(w)
        check("光标在纯中文上 → 一律不取词", bool(cn_points) and not cn_hits,
              "%d 个中文取样点" % len(cn_points) if not cn_hits else cn_hits)

        # ④ 查词 + 渲染 + 显示
        data = lookup.lookup(word, cfg)
        check("查词成功", bool(data), data and "%s：%s" % (data["source"], (data["poses"] or [{}])[0].get("meaning", "")[:18]))
        if not data:
            return finish()

        mascot = ui.load_mascot(app_mod.MASCOT)
        img = ui.render_card(data, mascot, scale=1.0)
        check("气泡渲染出图", img.size[0] > 200 and img.size[1] > 80, "%dx%d" % img.size)

        # 硬边 alpha：窗外区域必须是透明的（否则色键抠图失效）
        alpha = img.split()[3]
        corner = alpha.getpixel((img.size[0] - 2, 2))
        check("圆角外侧已透明（色键抠图生效）", corner == 0, "角点 alpha=%d" % corner)

        # 真显示一次 + 截屏确认它真的出现在屏幕上
        root = app_mod.ui.tk.Tk()
        root.withdraw()
        bubble = ui.Bubble(root)
        x, y = app_mod.cursor_pos()
        bubble.show(img, x, y)
        root.update()
        time.sleep(0.6)
        from PIL import ImageGrab
        shot = ImageGrab.grab(bbox=(x - 40, y - 40, x + img.size[0] + 60, y + img.size[1] + 60), all_screens=True)
        probe = os.path.join(os.environ.get("TEMP", "."), "et-desktop-e2e-shot.png")
        shot.save(probe)
        # 看浮层区域里有没有藏青描边像素（=气泡确实画在了屏幕上）
        navy = sum(1 for px in shot.convert("RGB").getdata() if abs(px[0] - 30) < 24 and abs(px[1] - 50) < 24 and abs(px[2] - 100) < 30)
        check("浮层真的显示在屏幕上（截到藏青描边）", navy > 200, "藏青像素 %d 个，截图 %s" % (navy, probe))
        bubble.hide()
        root.destroy()
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            os.remove(txt)
        except Exception:
            pass

    return finish()


def finish() -> int:
    failed = [n for n, ok in RESULTS if not ok]
    print("-" * 56)
    print("E2E：%d/%d 项通过" % (len(RESULTS) - len(failed), len(RESULTS)))
    if failed:
        print("失败项：" + "；".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
