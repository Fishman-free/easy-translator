"""Easy Translator — 生成商店上架素材（图标 / 宣传图 / 商店截图）。

用法：  python tools/make-store-assets.py
产物：  store/logo-300.png          商店图标（官方要求 1:1，推荐 300x300）
        store/tile-440x280.png      小宣传图（官方要求 440x280）
        store/tile-1400x560.png     大宣传图（官方要求 1400x560）

官方规格来源（Microsoft Edge Add-ons / Partner Center 文档，2026-09 核对）：
  Extension logo          1:1，推荐 300x300，最小 128x128
  Small promotional tile  440 x 280
  Large promotional tile  1400 x 560（PNG）
  Screenshots            最多 6 张，640x480 或 1280x800
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
STORE_DIR = ROOT / "store"

TOP = (99, 102, 241)      # indigo-500
BOTTOM = (67, 56, 202)    # indigo-700
INK = (17, 24, 39)
MUTED = (100, 116, 139)

FONT_CJK = [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
FONT_LATIN = [r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def pick_font(candidates, size):
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def gradient(size, top=TOP, bottom=BOTTOM):
    w, h = size
    img = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        img.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img.resize((w, h))


def rounded(img, radius):
    mask = Image.new("L", (img.width * 4, img.height * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, img.width * 4 - 1, img.height * 4 - 1), radius=radius * 4, fill=255
    )
    mask = mask.resize(img.size, Image.LANCZOS)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def centered(draw, text, font, box, fill, y_offset=0):
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((x0 + x1 - w) / 2 - bbox[0], (y0 + y1 - h) / 2 - bbox[1] + y_offset),
              text, font=font, fill=fill)


def make_logo(size=300):
    """商店图标：圆角渐变底 + 白色「译」。"""
    bg = rounded(gradient((size, size)), max(8, int(size * 0.22)))
    draw = ImageDraw.Draw(bg)
    font = pick_font(FONT_CJK, int(size * 0.56))
    centered(draw, "译", font, (0, 0, size, size), (255, 255, 255, 255))
    return bg


def fit_font(text, max_width, candidates, start_size, min_size=12):
    """从 start_size 往下找第一个能把 text 塞进 max_width 的字号。"""
    size = start_size
    while size > min_size:
        font = pick_font(candidates, size)
        bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
        size -= max(1, int(size * 0.06))
    return pick_font(candidates, min_size)


def make_tile(w, h):
    """宣传图：白底 + 左侧图标 + 右侧文案。文案按可用宽度自适应字号，绝不溢出。"""
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    pad = int(h * 0.10)
    logo_size = min(int(h * 0.44), int(w * 0.24))
    logo = make_logo(logo_size)
    img.paste(logo, (pad, (h - logo_size) // 2), logo)

    x = pad * 2 + logo_size
    max_w = w - x - pad

    # 单行版本：小图只放一行卖点，大图放两行
    two_lines = h >= 400
    features = "音标 · 词性 · 双语例句 · 网页/PDF/图片取词" if not two_lines \
        else "音标 · 词性 · 双语例句 · 网页 / PDF / 图片取词"

    brand_text = "Easy Translator"
    headline_text = "悬停 5 秒，即得中文释义"
    sub2_text = "本地小模型可选 · 零配置 · 轻量无依赖"

    rows = [
        (brand_text, fit_font(brand_text, max_w, FONT_LATIN, int(h * 0.115)), TOP),
        (headline_text, fit_font(headline_text, max_w, FONT_CJK, int(h * 0.165)), INK),
        (features, fit_font(features, max_w, FONT_CJK, int(h * 0.075)), MUTED),
    ]
    if two_lines:
        rows.append((sub2_text, fit_font(sub2_text, max_w, FONT_CJK, int(h * 0.075)), MUTED))

    def height_of(font):
        bbox = draw.textbbox((0, 0), "汉Hg", font=font)
        return bbox[3] - bbox[1]

    gaps = int(h * 0.035)
    y = (h - (sum(height_of(f) for _, f, _ in rows) + gaps * (len(rows) - 1))) / 2

    for text, font, color in rows:
        draw.text((x, y), text, font=font, fill=color)
        y += height_of(font) + gaps
    return img


def main():
    STORE_DIR.mkdir(parents=True, exist_ok=True)

    make_logo(300).save(STORE_DIR / "logo-300.png")
    make_tile(440, 280).save(STORE_DIR / "tile-440x280.png")
    make_tile(1400, 560).save(STORE_DIR / "tile-1400x560.png")

    for name in ("logo-300.png", "tile-440x280.png", "tile-1400x560.png"):
        p = STORE_DIR / name
        with Image.open(p) as im:
            print(f"{name:22} {im.width}x{im.height}  {p.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
