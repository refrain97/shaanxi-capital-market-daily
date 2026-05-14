#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ORG_TEXT = "华泰证券西安锦业路证券营业部（西北分公司机构业务中心）"
SITE_TEXT = "https://shaanxi-capital-market-daily.vercel.app/v1/"
FONT_PATH = "/System/Library/Fonts/PingFang.ttc"


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FONT_PATH, size=size, index=0)
    except OSError:
        return ImageFont.load_default()


def fit_font(draw: ImageDraw.ImageDraw, text: str, width: int, start_size: int) -> ImageFont.ImageFont:
    size = start_size
    while size >= 18:
        font = load_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= width:
            return font
        size -= 2
    return load_font(18)


def looks_branded(img: Image.Image) -> bool:
    w, h = img.size
    if h < 120:
        return False
    sample = img.crop((0, h - 24, w, h)).resize((1, 1))
    r, g, b, *_ = sample.getpixel((0, 0))
    return abs(r - 15) < 18 and abs(g - 36) < 24 and abs(b - 63) < 30


def apply_branding(path: Path, *, dry_run: bool = False) -> bool:
    if not path.exists():
        raise FileNotFoundError(path)

    with Image.open(path) as source:
        img = source.convert("RGBA")

    if looks_branded(img):
        return False

    w, h = img.size
    bar_h = max(72, min(132, int(h * 0.042)))
    pad_x = max(36, int(w * 0.032))
    pad_y = max(14, int(bar_h * 0.20))
    text_width = w - pad_x * 2

    bar = Image.new("RGBA", (w, bar_h), (15, 36, 63, 255))
    d = ImageDraw.Draw(bar)
    brand_font = fit_font(d, ORG_TEXT, text_width, max(24, int(bar_h * 0.30)))
    site_font = fit_font(d, SITE_TEXT, text_width, max(20, int(bar_h * 0.24)))

    d.text((pad_x, pad_y), ORG_TEXT, font=brand_font, fill=(255, 255, 255, 255))
    d.text((pad_x, bar_h - pad_y - site_font.size), SITE_TEXT, font=site_font, fill=(205, 221, 239, 255))

    branded = Image.new("RGBA", (w, h + bar_h), (255, 255, 255, 255))
    branded.alpha_composite(img, (0, 0))
    branded.alpha_composite(bar, (0, h))

    if dry_run:
        return True

    if path.suffix.lower() == ".png":
        branded.convert("RGB").save(path, "PNG", optimize=True)
    else:
        raise ValueError(f"Only PNG is supported: {path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Add V1 source branding to PNG images in-place.")
    parser.add_argument("images", nargs="+", help="PNG paths to brand.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without writing files.")
    args = parser.parse_args()

    for image in args.images:
        path = Path(image)
        changed = apply_branding(path, dry_run=args.dry_run)
        action = "checked" if args.dry_run else ("branded" if changed else "already branded")
        print(f"{action}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
