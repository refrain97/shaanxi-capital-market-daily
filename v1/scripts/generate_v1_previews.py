#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PREVIEW_DIR = ROOT / "assets" / "previews"


def zh_day(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日"


def resize_to_width(img: Image.Image, width: int) -> Image.Image:
    target_width = min(width, img.width)
    ratio = target_width / img.width
    height = max(1, round(img.height * ratio))
    return img.resize((target_width, height), Image.Resampling.LANCZOS)


def save_image_pair(image: Image.Image, stem: str, *, quality: int) -> None:
    jpg = PREVIEW_DIR / f"{stem}.jpg"
    webp = PREVIEW_DIR / f"{stem}.webp"
    image.save(jpg, "JPEG", quality=quality, optimize=True, progressive=True)
    image.save(webp, "WEBP", quality=max(76, quality - 2), method=6)


def save_preview(source: Path, target_stem: str, *, width: int, quality: int = 84) -> None:
    if not source.exists():
        print(f"skip missing preview source: {source.relative_to(ROOT)}")
        return

    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as img:
        rgb = img.convert("RGB")
        preview = resize_to_width(rgb, width)
        retina = resize_to_width(rgb, width * 2)
        save_image_pair(preview, target_stem, quality=quality)
        save_image_pair(retina, f"{target_stem}@2x", quality=quality)
        print(
            "wrote "
            f"{(PREVIEW_DIR / f'{target_stem}.jpg').relative_to(ROOT)}, "
            f"{(PREVIEW_DIR / f'{target_stem}.webp').relative_to(ROOT)}, "
            f"{(PREVIEW_DIR / f'{target_stem}@2x.jpg').relative_to(ROOT)} and "
            f"{(PREVIEW_DIR / f'{target_stem}@2x.webp').relative_to(ROOT)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate V1 homepage preview images.")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    today = date.fromisoformat(args.date)
    values = {
        "listed": (
            ROOT / "陕西省上市公司日报v1" / "outputs" / f"{zh_day(today)}陕西上市公司早报.png",
            f"listed-{today:%Y-%m-%d}",
            520,
            78,
        ),
        "private": (
            ROOT / "陕西省证券私募日报v1" / "outputs" / f"{zh_day(today)}证券私募行业动态日报.png",
            f"private-{today:%Y-%m-%d}",
            360,
            78,
        ),
        "ma": (
            ROOT / "陕西省收并购日报v1" / "outputs" / f"{zh_day(today)}陕西辖区收并购事件详细案例看板.png",
            f"ma-{today:%Y-%m-%d}",
            360,
            78,
        ),
        "tender": (
            ROOT / "陕西省金融招投标项目v1" / "outputs" / f"shaanxi-finance-tender-projects-{today:%Y-%m-%d}.png",
            f"tender-{today:%Y-%m-%d}",
            360,
            78,
        ),
    }
    for source, stem, width, quality in values.values():
        save_preview(source, stem, width=width, quality=quality)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
