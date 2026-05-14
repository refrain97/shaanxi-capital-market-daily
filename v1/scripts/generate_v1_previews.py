#!/usr/bin/env python3
from __future__ import annotations

from datetime import date
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PREVIEW_DIR = ROOT / "assets" / "previews"


def zh_day(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日"


def save_preview(source: Path, target_stem: str, *, width: int, quality: int = 74) -> None:
    if not source.exists():
        print(f"skip missing preview source: {source.relative_to(ROOT)}")
        return

    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as img:
        rgb = img.convert("RGB")
        ratio = width / rgb.width
        height = max(1, round(rgb.height * ratio))
        preview = rgb.resize((width, height), Image.Resampling.LANCZOS)
        jpg = PREVIEW_DIR / f"{target_stem}.jpg"
        webp = PREVIEW_DIR / f"{target_stem}.webp"
        preview.save(jpg, "JPEG", quality=quality, optimize=True, progressive=True)
        preview.save(webp, "WEBP", quality=max(62, quality - 2), method=6)
        print(f"wrote {jpg.relative_to(ROOT)} and {webp.relative_to(ROOT)}")


def main() -> int:
    today = date.today()
    values = {
        "listed": (
            ROOT / "陕西省上市公司日报v1" / "outputs" / f"{zh_day(today)}陕西上市公司早报.png",
            f"listed-{today:%Y-%m-%d}",
            542,
            74,
        ),
        "private": (
            ROOT / "陕西省证券私募日报v1" / "outputs" / f"{zh_day(today)}证券私募行业动态日报.png",
            f"private-{today:%Y-%m-%d}",
            357,
            72,
        ),
        "ma": (
            ROOT / "陕西省收并购日报v1" / "outputs" / f"{zh_day(today)}陕西辖区收并购事件详细案例看板.png",
            f"ma-{today:%Y-%m-%d}",
            217,
            70,
        ),
        "tender": (
            ROOT / "陕西省金融招投标项目v1" / "outputs" / f"shaanxi-finance-tender-projects-{today:%Y-%m-%d}.png",
            f"tender-{today:%Y-%m-%d}",
            304,
            70,
        ),
    }
    for source, stem, width, quality in values.values():
        save_preview(source, stem, width=width, quality=quality)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
