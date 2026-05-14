#!/usr/bin/env python3
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"

WEEKDAYS = "一二三四五六日"


@dataclass(frozen=True)
class Report:
    day: date
    channel: str
    title: str
    tags: tuple[tuple[str, str], ...]
    summary: str
    search: str
    links: tuple[tuple[str, str], ...]


def rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def zh_day(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日"


def parse_day(value: str) -> date:
    year, month, day = map(int, value.split("-"))
    return date(year, month, day)


def existing_links(*paths: tuple[str, Path | None]) -> tuple[tuple[str, str], ...]:
    links: list[tuple[str, str]] = []
    for label, path in paths:
        if path and path.exists():
            links.append((label, rel(path)))
    return tuple(links)


def listed_summary(day: date) -> str:
    if day >= date(2026, 5, 13):
        return "陕西辖区上市公司公告早报，突出交易风险、诉讼仲裁、股权收购、激励计划和固定披露清单。"
    return "陕西辖区上市公司公告早报，保留网页正文、Markdown 底稿和发布图片。"


def collect_reports() -> list[Report]:
    reports: list[Report] = []

    listed_dir = ROOT / "陕西省上市公司日报v1" / "outputs"
    for html_path in sorted(listed_dir.glob("shaanxi-listed-company-morning-*-publish.html")):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", html_path.name)
        if not match:
            continue
        day = parse_day(match.group(1))
        md_path = listed_dir / f"shaanxi-listed-company-morning-{day:%Y-%m-%d}.md"
        png_path = listed_dir / f"{zh_day(day)}陕西上市公司早报.png"
        reports.append(
            Report(
                day=day,
                channel="listed",
                title=f"陕西上市公司公告早报｜{zh_day(day)}",
                tags=(("tag blue", "上市公司公告"), ("tag", "公告早报")),
                summary=listed_summary(day),
                search=f"陕西上市公司公告早报 {day:%Y-%m-%d} 上市公司 公告 早报",
                links=existing_links(("HTML", html_path), ("Markdown", md_path), ("PNG", png_path)),
            )
        )

    private_dir = ROOT / "陕西省证券私募日报v1" / "outputs"
    for html_path in sorted(private_dir.glob("security-private-fund-daily-*-publish.html")):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", html_path.name)
        if not match:
            continue
        day = parse_day(match.group(1))
        md_path = private_dir / f"security-private-fund-daily-{day:%Y-%m-%d}.md"
        png_path = private_dir / f"{zh_day(day)}证券私募行业动态日报.png"
        reports.append(
            Report(
                day=day,
                channel="private",
                title=f"证券私募行业动态日报（{day:%Y-%m-%d}）",
                tags=(("tag teal", "证券私募"), ("tag", "协会公示")),
                summary="证券私募管理人新增、退出注销、陕西辖区动态和产品备案跟踪。",
                search=f"证券私募行业动态日报 {day:%Y-%m-%d} 管理人 注销 产品备案 陕西",
                links=existing_links(("HTML", html_path), ("Markdown", md_path), ("PNG", png_path)),
            )
        )

    ma_dir = ROOT / "陕西省收并购日报v1" / "outputs"
    for md_path in sorted(ma_dir.glob("shaanxi-ma-daily-*.md")):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", md_path.name)
        if not match:
            continue
        day = parse_day(match.group(1))
        png_path = ma_dir / f"{zh_day(day)}陕西辖区收并购事件详细案例看板.png"
        reports.append(
            Report(
                day=day,
                channel="ma",
                title=f"陕西省收并购日报（{day:%Y-%m-%d}）",
                tags=(("tag amber", "收并购"), ("tag", "日报底稿")),
                summary="陕西辖区收并购事件日报底稿和详细案例看板。",
                search=f"陕西省收并购日报 {day:%Y-%m-%d} 收购 并购 市场动态 案例",
                links=existing_links(("Markdown", md_path), ("PNG", png_path)),
            )
        )

    tender_dir = ROOT / "陕西省金融招投标项目v1" / "outputs"
    for md_path in sorted(tender_dir.glob("shaanxi-finance-tender-projects-*.md")):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", md_path.name)
        if not match:
            continue
        day = parse_day(match.group(1))
        html_path = tender_dir / f"shaanxi-finance-tender-projects-{day:%Y-%m-%d}-publish.html"
        png_path = tender_dir / f"shaanxi-finance-tender-projects-{day:%Y-%m-%d}.png"
        reports.append(
            Report(
                day=day,
                channel="tender",
                title=f"陕西金融类招投标项目清单（{day:%Y-%m-%d}）",
                tags=(("tag blue", "金融招投标"), ("tag", "项目机会")),
                summary="陕西地区金融类招投标项目机会、发布主体和结果回溯清单。",
                search=f"陕西金融类招投标项目清单 {day:%Y-%m-%d} 债券承销 主承销商 金融机构",
                links=existing_links(("HTML", html_path), ("Markdown", md_path), ("PNG", png_path)),
            )
        )

    order = {"listed": 0, "private": 1, "ma": 2, "tender": 3}
    return sorted(reports, key=lambda item: (item.day, -order[item.channel]), reverse=True)


def render_report(report: Report) -> str:
    tags = "\n".join(
        f'                <span class="{html.escape(class_name)}">{html.escape(label)}</span>'
        for class_name, label in report.tags
    )
    actions = "\n".join(
        f'              <a class="button" href="{html.escape(url)}">{html.escape(label)}</a>'
        for label, url in report.links
    )
    return f"""          <article class="archive-row" data-type="{report.channel}" data-search="{html.escape(report.search)}">
            <div class="date-block">
              <strong>{report.day:%m-%d}</strong>
              {report.day.year} · 星期{WEEKDAYS[report.day.weekday()]}
            </div>
            <div class="archive-main">
              <div class="tag-row">
{tags}
              </div>
              <h3>{html.escape(report.title)}</h3>
              <p>{html.escape(report.summary)}</p>
            </div>
            <div class="archive-actions">
{actions}
            </div>
          </article>"""


def main() -> None:
    reports = collect_reports()
    if not reports:
        raise SystemExit("No V1 reports found.")

    content = INDEX.read_text(encoding="utf-8")
    rows = "\n\n".join(render_report(report) for report in reports)
    pattern = re.compile(
        r'(<div class="archive-list" id="archiveList">\n).*?(\n        </div>\n\n        <div class="empty-state")',
        re.S,
    )
    updated, count = pattern.subn(rf"\1{rows}\2", content)
    if count != 1:
        raise SystemExit("Could not locate archive list in v1/index.html.")

    updated = re.sub(
        r"(<div class=\"metric\">\n\s*<b>)\d+(</b>\n\s*<span>份现有日报/看板可直接打开</span>)",
        rf"\g<1>{len(reports)}\2",
        updated,
        count=1,
    )
    updated = re.sub(
        r'(<span class="eyebrow">)\d{4}-\d{2}-\d{2} 更新(?: · [^<]+)?(</span>)',
        rf"\g<1>{reports[0].day:%Y-%m-%d} 更新\2",
        updated,
        count=1,
    )
    INDEX.write_text(updated, encoding="utf-8")
    print(f"Updated {INDEX.relative_to(ROOT.parent)} with {len(reports)} archive rows.")


if __name__ == "__main__":
    main()
