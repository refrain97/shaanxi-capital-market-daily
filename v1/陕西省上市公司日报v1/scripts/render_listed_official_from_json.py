#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from datetime import date
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
VERSION_DIR = SCRIPT_DIR.parent
ROOT = VERSION_DIR.parent
DATA_DIR = VERSION_DIR / "data"
OUTPUT_DIR = VERSION_DIR / "outputs"
TEMPLATE_PATH = VERSION_DIR / "templates" / "shaanxi-listed-company-morning-report-v1.template.html"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

sys.path.insert(0, str(ROOT / "scripts"))
from brand_v1_png import apply_branding


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def zh_day(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日"


def style() -> str:
    source = TEMPLATE_PATH.read_text(encoding="utf-8")
    start = source.index("<style>") + len("<style>")
    end = source.index("</style>")
    return source[start:end]


def require_list(data: dict[str, object], key: str, length: int | None = None) -> list[object]:
    value = data.get(key)
    if not isinstance(value, list):
        raise SystemExit(f"curated listed report field must be a list: {key}")
    if length is not None and len(value) != length:
        raise SystemExit(f"curated listed report field {key} must contain {length} items, found {len(value)}")
    return value


def validate(data: dict[str, object], day: date) -> None:
    if data.get("date") != day.isoformat():
        raise SystemExit(f"curated listed report date mismatch: {data.get('date')} != {day:%Y-%m-%d}")
    if data.get("template") != "listed-v1-official":
        raise SystemExit("curated listed report must set template=listed-v1-official")
    require_list(data, "kpis", 4)
    require_list(data, "opportunities", 4)
    require_list(data, "risk_rows", 4)
    require_list(data, "tiles", 4)
    require_list(data, "capital_rows", 5)
    fixed_columns = require_list(data, "fixed_columns", 2)
    for column in fixed_columns:
        if not isinstance(column, dict) or len(column.get("items", [])) != 4:
            raise SystemExit("each fixed_columns item must contain exactly 4 fixed items")
    require_list(data, "follow_items", 6)


def kpi_html(items: list[object]) -> str:
    parts = []
    for item in items:
        assert isinstance(item, dict)
        parts.append(
            f'<div class="kpi"><div class="num">{esc(item["num"])}</div>'
            f'<div class="label">{esc(item["label"])}</div></div>'
        )
    return "\n        ".join(parts)


def chip_html(items: list[object]) -> str:
    parts = []
    for item in items:
        assert isinstance(item, dict)
        parts.append(f'<div class="chip"><b>{esc(item["title"])}</b>{esc(item["body"])}</div>')
    return "\n            ".join(parts)


def risk_rows_html(items: list[object]) -> str:
    parts = []
    for item in items:
        assert isinstance(item, dict)
        tag_class = esc(item.get("tagClass", "watch"))
        parts.append(
            f'<tr><td>{esc(item["company"])}</td><td>{esc(item["event"])}</td>'
            f'<td><span class="tag {tag_class}">{esc(item["tag"])}</span></td></tr>'
        )
    return "\n                ".join(parts)


def tiles_html(items: list[object]) -> str:
    parts = []
    for item in items:
        assert isinstance(item, dict)
        parts.append(f'<div class="tile"><b>{esc(item["title"])}</b><span>{esc(item["body"])}</span></div>')
    return "\n            ".join(parts)


def capital_rows_html(items: list[object]) -> str:
    parts = []
    for item in items:
        assert isinstance(item, dict)
        parts.append(
            f'<tr><td>{esc(item["company"])}</td><td>{item["numbersHtml"]}</td>'
            f'<td>{esc(item["attention"])}</td></tr>'
        )
    return "\n                ".join(parts)


def fixed_columns_html(items: list[object]) -> str:
    columns = []
    for column in items:
        assert isinstance(column, dict)
        rows = []
        for row in column["items"]:
            rows.append(f'<div class="fixed-item"><b>{esc(row["title"])}</b>{esc(row["body"])}</div>')
        columns.append(
            f'<div>\n              <p class="subhead">{esc(column["title"])}</p>\n'
            f'              <div class="fixed-list">{"".join(rows)}</div>\n            </div>'
        )
    return "\n            ".join(columns)


def follow_html(items: list[object]) -> str:
    parts = []
    for item in items:
        assert isinstance(item, dict)
        parts.append(f'<div><b>{esc(item["title"])}</b>{esc(item["body"])}</div>')
    return "\n            ".join(parts)


def render_html(data: dict[str, object], day: date) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>陕西上市公司公告早报｜{zh_day(day)}</title>
  <style>{style()}</style>
</head>
<body>
  <main class="page" data-template="listed-v1-official">
    <header class="topbar">
      <div>
        <h1>陕西上市公司公告早报</h1>
        <div class="subtitle">{esc(data["subtitle"])}</div>
      </div>
      <div class="source">
        <strong>覆盖 85 家上市公司</strong>
        沪市42家｜深市37家｜北交所6家<br>
        名单来源：陕西证监局｜公告源：巨潮资讯 CNINFO
      </div>
    </header>

    <section class="content">
      <div class="kpis">
        {kpi_html(data["kpis"])}
      </div>

      <div class="grid">
        <section class="section">
          <div class="section-title"><span class="no">01</span>今日业务机会</div>
          <div class="body chips">
            {chip_html(data["opportunities"])}
          </div>
        </section>

        <section class="section">
          <div class="section-title"><span class="no">02</span>重大事项与风险公告</div>
          <div class="body">
            <table>
              <colgroup><col style="width:20%"><col style="width:57%"><col style="width:23%"></colgroup>
              <thead><tr><th>公司</th><th>事项</th><th>业务判断</th></tr></thead>
              <tbody>
                {risk_rows_html(data["risk_rows"])}
              </tbody>
            </table>
          </div>
        </section>

        <section class="section wide">
          <div class="section-title"><span class="no">03</span>上市公司动态</div>
          <div class="body tiles">
            {tiles_html(data["tiles"])}
          </div>
        </section>

        <section class="section wide">
          <div class="section-title"><span class="no">04</span>股东变动与资本运作</div>
          <div class="body">
            <table>
              <colgroup><col style="width:16%"><col style="width:44%"><col style="width:40%"></colgroup>
              <thead><tr><th>公司</th><th>关键数字</th><th>业务关注</th></tr></thead>
              <tbody>
                {capital_rows_html(data["capital_rows"])}
              </tbody>
            </table>
          </div>
        </section>

        <section class="section wide">
          <div class="section-title"><span class="no">05</span>股东会、治理与固定披露清单</div>
          <div class="body two-col">
            {fixed_columns_html(data["fixed_columns"])}
          </div>
        </section>

        <section class="section wide">
          <div class="section-title"><span class="no">06</span>今日重点跟踪公司</div>
          <div class="body follow">
            {follow_html(data["follow_items"])}
          </div>
        </section>
      </div>
    </section>

    <footer class="note">
      <span>资料来源：陕西证监局《陕西辖区上市公司基本情况表（2026年3月31日）》、巨潮资讯公告原文及本地PDF抽取文本。仅作公告信息整理，不构成投资建议。</span>
      <span>华泰证券西安锦业路证券营业部（西北分公司机构业务中心）｜https://refrain97.github.io/shaanxi-capital-market-daily/v1/</span>
    </footer>
  </main>
</body>
</html>"""


def render_png(html_path: Path, png_path: Path) -> None:
    if not CHROME.exists():
        raise SystemExit(f"Chrome not found: {CHROME}")
    subprocess.run(
        [
            str(CHROME),
            "--headless",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--window-size=1242,2060",
            f"--screenshot={png_path}",
            str(html_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    apply_branding(png_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render official Shaanxi listed-company V1 report from curated JSON.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--curated-json", type=Path)
    parser.add_argument("--png", action="store_true")
    args = parser.parse_args()
    day = date.fromisoformat(args.date)
    curated = args.curated_json or DATA_DIR / "curated" / f"listed-official-{day:%Y-%m-%d}.json"
    data = json.loads(curated.read_text(encoding="utf-8"))
    validate(data, day)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUTPUT_DIR / f"shaanxi-listed-company-morning-{day:%Y-%m-%d}-publish.html"
    html_path.write_text(render_html(data, day), encoding="utf-8")
    print(f"Wrote {html_path}")
    if args.png:
        png_path = OUTPUT_DIR / f"{zh_day(day)}陕西上市公司早报.png"
        render_png(html_path, png_path)
        print(f"Wrote {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
