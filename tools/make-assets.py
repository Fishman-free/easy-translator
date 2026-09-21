"""Easy Translator — 生成扩展图标与视觉模型测试图。

用法：  python tools/make-assets.py
产物：  icons/icon{16,32,48,128}.png、assets/vision-test.png
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "icons"
ASSET_DIR = ROOT / "assets"

FONT_CJK_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
]
FONT_LATIN_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

TOP = (99, 102, 241)      # indigo-500
BOTTOM = (67, 56, 202)    # indigo-700


def pick_font(candidates, size):
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def rounded_mask(size, radius):
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size * 4 - 1, size * 4 - 1), radius=radius * 4, fill=255
    )
    return mask.resize((size, size), Image.LANCZOS)


def make_icon(size, glyph, font_candidates, radius_ratio=0.24):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # 竖向渐变背景
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        grad.putpixel(
            (0, y),
            tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)),
        )
    grad = grad.resize((size, size))
    img.paste(grad, (0, 0), rounded_mask(size, max(3, int(size * radius_ratio))))

    draw = ImageDraw.Draw(img)
    font_size = int(size * (0.62 if size <= 32 else 0.58))
    font = pick_font(font_candidates, font_size)

    bbox = draw.textbbox((0, 0), glyph, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text(
        ((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]),
        glyph,
        font=font,
        fill=(255, 255, 255, 255),
    )
    return img


def make_vision_test_image():
    """给「测试图片识别」按钮用：一张干净的英文图片，期望模型读出 Hello。"""
    img = Image.new("RGB", (360, 140), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = pick_font(FONT_LATIN_CANDIDATES, 84)
    text = "Hello"
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((360 - (bbox[2] - bbox[0])) / 2 - bbox[0], (140 - (bbox[3] - bbox[1])) / 2 - bbox[1]),
        text,
        font=font,
        fill=(17, 24, 39),
    )
    return img


def main():
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    for size in (16, 32):
        make_icon(size, "A", FONT_LATIN_CANDIDATES).save(ICON_DIR / f"icon{size}.png")
    for size in (48, 128):
        make_icon(size, "译", FONT_CJK_CANDIDATES).save(ICON_DIR / f"icon{size}.png")

    make_vision_test_image().save(ASSET_DIR / "vision-test.png")
    print("icons + assets written to", ROOT)


if __name__ == "__main__":
    main()
