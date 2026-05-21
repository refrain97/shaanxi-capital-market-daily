#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent


def zh_day(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日"


def fail(message: str) -> None:
    print(f"validate_v1_outputs: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(path: Path, label: str) -> None:
    if not path.exists():
        fail(f"missing {label}: {path.relative_to(REPO_ROOT)}")


def validate_listed(day: date) -> None:
    listed = ROOT / "陕西省上市公司日报v1"
    outputs = listed / "outputs"
    data = listed / "data"
    md_path = outputs / f"shaanxi-listed-company-morning-{day:%Y-%m-%d}.md"
    html_path = outputs / f"shaanxi-listed-company-morning-{day:%Y-%m-%d}-publish.html"
    png_path = outputs / f"{zh_day(day)}陕西上市公司早报.png"
    json_path = data / f"cninfo-shaanxi-announcements-{day:%Y-%m-%d}.json"
    curated_path = data / "curated" / f"listed-official-{day:%Y-%m-%d}.json"
    pdf_dir = data / f"pdfs-{day:%Y-%m-%d}"
    text_dir = data / f"pdf-text-{day:%Y-%m-%d}"

    for label, path in (
        ("listed Markdown", md_path),
        ("listed HTML", html_path),
        ("listed PNG", png_path),
        ("listed CNINFO JSON", json_path),
        ("listed curated official JSON", curated_path),
        ("listed PDF dir", pdf_dir),
        ("listed PDF text dir", text_dir),
    ):
        require(path, label)

    md = md_path.read_text(encoding="utf-8")
    html = html_path.read_text(encoding="utf-8")
    data_json = json.loads(json_path.read_text(encoding="utf-8"))
    curated = json.loads(curated_path.read_text(encoding="utf-8"))
    if curated.get("template") != "listed-v1-official" or curated.get("date") != f"{day:%Y-%m-%d}":
        fail("listed curated JSON has wrong template or date")
    for key, expected_len in (
        ("kpis", 4),
        ("opportunities", 4),
        ("risk_rows", 4),
        ("tiles", 4),
        ("capital_rows", 5),
        ("fixed_columns", 2),
        ("follow_items", 6),
    ):
        value = curated.get(key)
        if not isinstance(value, list) or len(value) != expected_len:
            fail(f"listed curated JSON field {key} must contain {expected_len} items")
    day_key = f"{day:%Y-%m-%d}~{day:%Y-%m-%d}"
    items = data_json.get(day_key, [])
    if not isinstance(items, list) or not items:
        fail(f"listed CNINFO JSON has no announcement list for {day_key}")

    if "CNINFO逐公司检索" not in md and "CNINFO 逐公司检索" not in md:
        fail("listed Markdown lost the CNINFO company-by-company retrieval statement")
    if "PDF原文" not in md or "高价值精读" not in md:
        fail("listed Markdown lost the PDF original-text / deep-reading statement")

    pdf_count = len(list(pdf_dir.glob("*.pdf")))
    text_count = len(list(text_dir.glob("*.txt")))
    if pdf_count < len(items) or text_count < len(items):
        fail(
            "listed PDF extraction incomplete: "
            f"announcements={len(items)}, pdf={pdf_count}, text={text_count}"
        )

    if 'data-template="listed-v1-official"' not in html:
        fail("listed HTML is not rendered by the official V1 renderer")
    if 'class="lab"' in html:
        fail("listed HTML contains simplified-template KPI class 'lab'")
    main_html = html.split('<!-- V1_ANALYTICS_BODY_START -->', 1)[0]
    if "…" in main_html:
        fail("listed HTML contains auto-truncated ellipsis; use a hand-curated 精读版 layout")
    if "2026年；" in main_html or "2025年；" in main_html:
        fail("listed HTML appears to contain mechanically extracted year tokens as key numbers")
    for title in (
        "01</span>今日业务机会",
        "02</span>重大事项与风险公告",
        "03</span>上市公司动态",
        "04</span>股东变动与资本运作",
        "05</span>",
        "06</span>今日重点跟踪公司",
    ):
        if title not in html:
            fail(f"listed HTML missing official section marker: {title}")

    kpis = re.findall(
        r'<div class="kpi">\s*<div class="num">.*?</div>\s*<div class="label">.*?</div>\s*</div>',
        html,
        re.S,
    )
    if len(kpis) != 4:
        fail(f"listed HTML requires exactly 4 official KPI blocks, found {len(kpis)}")
    for item in curated["kpis"]:
        if str(item["num"]) not in html or str(item["label"]) not in html:
            fail(f"listed HTML does not include curated KPI: {item}")


def validate_index(day: date) -> None:
    index = ROOT / "index.html"
    require(index, "V1 index")
    html = index.read_text(encoding="utf-8")
    if f"{day:%Y-%m-%d} 更新" not in html:
        fail("index does not show today's update date")
    if f">{day:%m-%d}</b><span>最新日期" in html or ">V1</b><span>已入库发布" in html:
        fail("index latest card is using generic fallback facts")
    if f"listed-{day:%Y-%m-%d}.webp" not in html:
        fail("index does not point to today's listed preview")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate V1 daily outputs before upload/deploy.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    day = date.fromisoformat(args.date)

    validate_listed(day)
    validate_index(day)
    print(f"validate_v1_outputs: ok for {day:%Y-%m-%d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
