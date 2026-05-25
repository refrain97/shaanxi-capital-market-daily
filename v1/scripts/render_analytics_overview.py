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
    chart_w = 760
    row_h = 86
    for idx, (key, label, color) in enumerate(labels):
        yy = y + idx * row_h
        value = counts.get(key, 0)
        text(draw, (x, yy + 6), label, 24, "ink", 1)
        draw.rounded_rectangle((x + 130, yy + 10, x + 130 + chart_w, yy + 42), radius=12, fill="#edf2f7")
        width = int(chart_w * value / max_value)
        draw.rounded_rectangle((x + 130, yy + 10, x + 130 + width, yy + 42), radius=12, fill=COLORS[color])
        text(draw, (x + 130 + chart_w + 22, yy + 6), f"{value}期", 24, "ink", 1)
        text(draw, (x + 130, yy + 50), "归档入口已接入打开/下载跳转统计", 17, "muted", 0)


def render_flow(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    steps = [
        ("首页/分享链接", "用户点击"),
        ("/api/track", "服务端记录"),
        ("Umami", "事件入库"),
        ("日报文件", "302打开"),
    ]
    for idx, (title, sub) in enumerate(steps):
        sx = x + idx * 275
        draw.rounded_rectangle((sx, y, sx + 220, y + 118), radius=16, fill="#f8fafc", outline=COLORS["line"], width=2)
        text(draw, (sx + 22, y + 24), title, 25, "ink", 1)
        text(draw, (sx + 22, y + 68), sub, 18, "muted", 0)
        if idx < len(steps) - 1:
            draw.line((sx + 232, y + 58, sx + 266, y + 58), fill=COLORS["muted"], width=4)
            draw.polygon([(sx + 266, y + 58), (sx + 254, y + 50), (sx + 254, y + 66)], fill=COLORS["muted"])


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

    img = Image.new("RGB", (1400, 1640), COLORS["bg"])
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 1400, 176), fill=COLORS["navy"])
    text(draw, (72, 42), "V1 打开记录与统计覆盖看板", 48, "#ffffff", 1)
    text(draw, (74, 106), f"{day:%Y-%m-%d}｜首页链接已接入 Vercel 服务端跳转统计 + Umami 前端统计", 24, "#d8e4f2", 0)

    card(draw, (72, 220, 392, 392), "归档日报", f"{len(reports)}期", "四个频道历史入口", "blue")
    card(draw, (416, 220, 736, 392), "可统计链接", f"{tracked_links}个", "首页/归档/分享入口", "teal")
    card(draw, (760, 220, 1080, 392), "服务端事件", "2类", "打开日报 / 下载资产", "amber")
    card(draw, (1104, 220, 1328, 392), "今日预览", f"{preview_total / 1024:.0f}KB", "WebP 预览总量", "green")

    draw.rounded_rectangle((72, 430, 1328, 870), radius=18, fill=COLORS["paper"], outline=COLORS["line"], width=2)
    text(draw, (104, 466), "频道归档覆盖", 30, "ink", 1)
    text(draw, (104, 508), "每个归档按钮现在都会优先经过 /api/track，再跳转到真实日报文件。", 20, "muted", 0)
    render_bar_chart(draw, (104, 570), counts)

    draw.rounded_rectangle((72, 912, 1328, 1138), radius=18, fill=COLORS["paper"], outline=COLORS["line"], width=2)
    text(draw, (104, 948), "打开记录链路", 30, "ink", 1)
    render_flow(draw, 104, 1000)

    draw.rounded_rectangle((72, 1180, 1328, 1516), radius=18, fill=COLORS["paper"], outline=COLORS["line"], width=2)
    text(draw, (104, 1216), "今日发布资源体积", 30, "ink", 1)
    y = 1272
    for label, path in latest_pngs.items():
        draw.rounded_rectangle((104, y, 1296, y + 48), radius=10, fill="#f8fafc", outline="#e8edf4", width=1)
        text(draw, (128, y + 10), label, 22, "ink", 1)
        text(draw, (1090, y + 10), fmt_size(path), 22, "muted", 1)
        y += 62

    text(draw, (104, 1548), "说明：真实访客、打开次数、来源渠道会进入 Umami 后台；本图展示的是当前工程侧已接入的统计覆盖与今日资源状态。", 18, "muted", 0)
    text(draw, (104, 1582), "建议后续统一使用 Vercel 首页/分享链接作为对外入口，GitHub Pages 可继续作为静态备份。", 18, "muted", 0)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"v1-open-record-dashboard-{day:%Y-%m-%d}.png"
    img.save(out, "PNG", optimize=True)
    print(out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
