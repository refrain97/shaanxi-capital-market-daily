#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import update_v1_index


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "analytics"
FONT_PATHS = (
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
)

COLORS = {
    "paper": "#ffffff",
    "bg": "#f4f7fb",
    "navy": "#102640",
    "ink": "#172033",
    "muted": "#667085",
    "line": "#d8dee8",
    "blue": "#2f6fbd",
    "teal": "#17746f",
    "amber": "#b26b18",
    "red": "#ba3f36",
    "green": "#257a52",
}


def font(size: int, weight: int = 0) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size=size, index=weight)
        except OSError:
            continue
    return ImageFont.load_default()


def zh_day(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日"


def text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int, fill: str = "ink", weight: int = 0) -> None:
    draw.text(xy, value, font=font(size, weight), fill=COLORS.get(fill, fill))


def card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, value: str, note: str, color: str = "blue") -> None:
    draw.rounded_rectangle(box, radius=16, fill=COLORS["paper"], outline=COLORS["line"], width=2)
    x1, y1, _, _ = box
    draw.rounded_rectangle((x1 + 22, y1 + 22, x1 + 34, y1 + 88), radius=6, fill=COLORS[color])
    text(draw, (x1 + 52, y1 + 22), title, 22, "muted", 0)
    text(draw, (x1 + 52, y1 + 62), value, 42, "ink", 1)
    text(draw, (x1 + 52, y1 + 118), note, 18, "muted", 0)


def fmt_size(path: Path) -> str:
    if not path.exists():
        return "-"
    size = path.stat().st_size
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f}MB"
    return f"{size / 1024:.0f}KB"


def render_bar_chart(draw: ImageDraw.ImageDraw, origin: tuple[int, int], counts: dict[str, int]) -> None:
    labels = [
        ("listed", "上市公司", "blue"),
        ("private", "证券私募", "teal"),
        ("ma", "收并购", "amber"),
        ("tender", "招投标", "green"),
    ]
    x, y = origin
    max_value = max(counts.values()) if counts else 1
    chart_w = 610
    row_h = 50
    for idx, (key, label, color) in enumerate(labels):
        yy = y + idx * row_h
        value = counts.get(key, 0)
        text(draw, (x, yy + 5), label, 22, "ink", 1)
        draw.rounded_rectangle((x + 116, yy + 9, x + 116 + chart_w, yy + 35), radius=10, fill="#edf2f7")
        width = int(chart_w * value / max_value)
        draw.rounded_rectangle((x + 116, yy + 9, x + 116 + width, yy + 35), radius=10, fill=COLORS[color])
        text(draw, (x + 116 + chart_w + 18, yy + 5), f"{value}期", 22, "ink", 1)


def simple_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    number: str,
    title: str,
    lines: list[str],
    color: str,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=18, fill=COLORS["paper"], outline=COLORS["line"], width=2)
    draw.ellipse((x1 + 28, y1 + 28, x1 + 82, y1 + 82), fill=COLORS[color])
    text(draw, (x1 + 46, y1 + 37), number, 24, "#ffffff", 1)
    text(draw, (x1 + 104, y1 + 30), title, 30, "ink", 1)
    yy = y1 + 92
    for line in lines:
        text(draw, (x1 + 42, yy), line, 22, "muted", 0)
        yy += 38


def main() -> int:
    parser = argparse.ArgumentParser(description="Render V1 analytics coverage overview as PNG.")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()
    day = date.fromisoformat(args.date)

    reports = update_v1_index.collect_reports()
    counts = update_v1_index.count_by_channel(reports)
    index_html = (ROOT / "index.html").read_text(encoding="utf-8")
    tracked_links = len(re.findall(r"https://shaanxi-capital-market-daily\.vercel\.app/api/track\?", index_html))

    latest_pngs = {
        "上市公司长图": ROOT / "陕西省上市公司日报v1" / "outputs" / f"{zh_day(day)}陕西上市公司早报.png",
        "私募长图": ROOT / "陕西省证券私募日报v1" / "outputs" / f"{zh_day(day)}证券私募行业动态日报.png",
        "收并购看板": ROOT / "陕西省收并购日报v1" / "outputs" / f"{zh_day(day)}陕西辖区收并购事件详细案例看板.png",
        "招投标长图": ROOT / "陕西省金融招投标项目v1" / "outputs" / f"shaanxi-finance-tender-projects-{day:%Y-%m-%d}.png",
    }
    preview_total = sum(path.stat().st_size for path in (ROOT / "assets" / "previews").glob(f"*{day:%Y-%m-%d}*.webp"))

    img = Image.new("RGB", (1200, 1120), COLORS["bg"])
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 1200, 150), fill=COLORS["navy"])
    text(draw, (64, 36), "打开记录怎么用", 48, "#ffffff", 1)
    text(draw, (66, 98), f"{day:%Y-%m-%d}｜一句话：从网页入口打开日报，就能记录；直接发原始图片，记录不到。", 23, "#d8e4f2", 0)

    simple_box(
        draw,
        (64, 190, 1136, 360),
        "1",
        "现在能记录什么？",
        [
            "打开 HTML 日报、打开 PNG 图片、打开 Markdown、复制分享链接。",
            f"目前首页和归档里已有 {tracked_links} 个可统计入口。"
        ],
        "blue",
    )
    simple_box(
        draw,
        (64, 386, 1136, 556),
        "2",
        "在哪里看数据？",
        [
            "到 Umami 后台看：访问人数、打开次数、热门日报、来源渠道。",
            "事件名称主要是：open_report、download_asset、share_copy。"
        ],
        "teal",
    )
    simple_box(
        draw,
        (64, 582, 1136, 752),
        "3",
        "什么情况记录不到？",
        [
            "别人如果绕过首页，直接打开原始 .png 或 .md 文件，网页代码不会运行。",
            "所以对外统一发 Vercel 首页或“复制分享链接”。"
        ],
        "amber",
    )

    draw.rounded_rectangle((64, 786, 1136, 1068), radius=18, fill=COLORS["paper"], outline=COLORS["line"], width=2)
    text(draw, (96, 812), f"当前覆盖：{len(reports)} 期归档日报", 28, "ink", 1)
    render_bar_chart(draw, (96, 862), counts)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"v1-open-record-dashboard-{day:%Y-%m-%d}.png"
    img.save(out, "PNG", optimize=True)
    print(out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
