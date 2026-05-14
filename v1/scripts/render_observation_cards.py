#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from brand_v1_png import apply_branding


ROOT = Path(__file__).resolve().parents[1]
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def zh_day(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日"


def render_html_to_png(html_path: Path, png_path: Path, *, width: int, height: int) -> None:
    if not CHROME.exists():
        raise FileNotFoundError(f"Chrome not found: {CHROME}")
    subprocess.run(
        [
            str(CHROME),
            "--headless",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--window-size={width},{height}",
            f"--screenshot={png_path}",
            str(html_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    apply_branding(png_path)
    print(f"Wrote {png_path}")


def previous_file(pattern: str, target: date, output_dir: Path) -> Path:
    dated: list[tuple[date, Path]] = []
    for path in output_dir.glob(pattern):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
        if not match:
            continue
        file_date = date.fromisoformat(match.group(1))
        if file_date < target:
            dated.append((file_date, path))
    if not dated:
        raise FileNotFoundError(f"No previous template matched {pattern} before {target:%Y-%m-%d}")
    return sorted(dated)[-1][1]


def carry_forward_tender(day: date) -> None:
    output_dir = ROOT / "陕西省金融招投标项目v1" / "outputs"
    prev_html = previous_file("shaanxi-finance-tender-projects-*-publish.html", day, output_dir)
    prev_iso = re.search(r"(\d{4}-\d{2}-\d{2})", prev_html.name).group(1)
    prev_day = date.fromisoformat(prev_iso)

    target_html = output_dir / f"shaanxi-finance-tender-projects-{day:%Y-%m-%d}-publish.html"
    target_png = output_dir / f"shaanxi-finance-tender-projects-{day:%Y-%m-%d}.png"

    html = prev_html.read_text(encoding="utf-8")
    html = html.replace(prev_iso, day.isoformat())
    html = html.replace(zh_day(prev_day), zh_day(day))
    html = html.replace(
        f"今日观察未发现新增可确认项目；本图为截至 {day:%Y-%m-%d} 的累计项目库。",
        f"今日观察未发现新增可确认项目；本图沿用累计项目库并更新至 {day:%Y-%m-%d}。",
    )
    target_html.write_text(html, encoding="utf-8")
    print(f"Wrote {target_html}")
    render_html_to_png(target_html, target_png, width=1242, height=2120)


def carry_forward_ma(day: date) -> None:
    script = ROOT / "陕西省收并购日报v1" / "scripts" / "render_shaanxi_ma_cases.py"
    subprocess.run([sys.executable, str(script), "--date", day.isoformat()], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Render low-frequency V1 carry-forward images. "
            "When there is no content change, keep the full previous data display and update only the report date."
        )
    )
    parser.add_argument("--date", required=True)
    parser.add_argument("--type", choices=("ma", "tender"), required=True)
    args = parser.parse_args()
    day = date.fromisoformat(args.date)

    if args.type == "ma":
        carry_forward_ma(day)
    else:
        carry_forward_tender(day)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
