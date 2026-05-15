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


def latest_by_channel(reports: list[Report]) -> dict[str, Report]:
    latest: dict[str, Report] = {}
    for report in reports:
        current = latest.get(report.channel)
        if current is None or report.day > current.day:
            latest[report.channel] = report
    return latest


def count_by_channel(reports: list[Report]) -> dict[str, int]:
    counts = {"listed": 0, "private": 0, "ma": 0, "tender": 0}
    for report in reports:
        counts[report.channel] = counts.get(report.channel, 0) + 1
    return counts


def preview_path(channel: str, day: date, ext: str) -> str:
    return f"assets/previews/{channel}-{day:%Y-%m-%d}.{ext}"


def link_for(report: Report, preferred: tuple[str, ...]) -> str:
    links = dict(report.links)
    for label in preferred:
        if label in links:
            return links[label]
    return report.links[0][1] if report.links else "#archive"


def render_latest_card(report: Report, *, lead: bool = False) -> str:
    channel_names = {
        "listed": "陕西上市公司公告早报",
        "private": "证券私募行业动态日报",
        "ma": "陕西辖区收并购市场动态观察",
        "tender": "陕西金融类招投标项目观察",
    }
    channel_tags = {
        "listed": '<span class="tag blue">上市公司公告</span>',
        "private": '<span class="tag teal">证券私募</span>',
        "ma": '<span class="tag amber">收并购</span>',
        "tender": '<span class="tag blue">金融招投标</span>',
    }
    preferred = ("HTML", "PNG", "Markdown") if report.channel != "ma" else ("PNG", "Markdown")
    link = link_for(report, preferred)
    action_text = "打开图片" if report.channel == "ma" else "打开日报"
    title = channel_names[report.channel]
    summary = report.summary
    if lead:
        return f"""          <article class="lead-report">
            <div class="lead-content">
              <div class="tag-row">
                {channel_tags[report.channel]}
                <span class="tag">{report.day:%Y-%m-%d}</span>
              </div>
              <h3 class="report-title">{html.escape(title)}</h3>
              <p class="report-summary">{html.escape(summary)}</p>
              <div class="fact-list">
                <div class="fact"><b>{report.day:%m-%d}</b><span>最新日期</span></div>
                <div class="fact"><b>{len(report.links)}</b><span>种可打开格式</span></div>
                <div class="fact"><b>V1</b><span>已入库发布</span></div>
              </div>
              <a class="button" href="{html.escape(link)}">{action_text}</a>
            </div>
            <a class="lead-image" href="{html.escape(link)}" aria-label="打开{html.escape(title)}">
              <picture>
                <source srcset="{preview_path(report.channel, report.day, 'webp')}" type="image/webp">
                <img src="{preview_path(report.channel, report.day, 'jpg')}" alt="{html.escape(title)}预览" width="542" height="936" decoding="async" loading="eager" fetchpriority="high">
              </picture>
            </a>
          </article>"""
    return f"""            <article class="compact-report">
              <a class="compact-media" href="{html.escape(link)}" aria-label="打开{html.escape(title)}">
                <picture>
                  <source srcset="{preview_path(report.channel, report.day, 'webp')}" type="image/webp">
                  <img src="{preview_path(report.channel, report.day, 'jpg')}" alt="{html.escape(title)}预览" width="357" height="520" loading="lazy" decoding="async">
                </picture>
              </a>
              <div class="compact-body">
                <div class="tag-row">
                  {channel_tags[report.channel]}
                  <span class="tag">{report.day:%Y-%m-%d}</span>
                </div>
                <h3>{html.escape(title)}</h3>
                <p>{html.escape(summary)}</p>
                <a class="text-link" href="{html.escape(link)}">{action_text}</a>
              </div>
            </article>"""


def render_latest_section(latest: dict[str, Report]) -> str:
    listed = latest.get("listed")
    if not listed:
        return ""
    side_cards = "\n\n".join(
        render_latest_card(latest[channel])
        for channel in ("private", "ma", "tender")
        if channel in latest
    )
    return f"""        <div class="featured-grid">
{render_latest_card(listed, lead=True)}

          <div class="side-stack">
{side_cards}
          </div>
        </div>"""


def render_channels(latest: dict[str, Report], counts: dict[str, int]) -> str:
    latest_date = lambda channel: latest[channel].day.isoformat() if channel in latest else "待更新"
    return f"""        <div class="channel-grid">
          <article class="channel-card">
            <div class="channel-top listed">
              <small>Channel 01</small>
              <h3>陕西上市公司公告早报</h3>
            </div>
            <div class="channel-body">
              <p>面向辖区 A 股上市公司公告，突出交易风险、股权管理、分红回购、监管事项和次日跟踪清单。</p>
              <div class="mini-facts">
                <div><span>最新日期</span><strong>{latest_date('listed')}</strong></div>
                <div><span>历史数量</span><strong>{counts.get('listed', 0)} 期</strong></div>
                <div><span>内容形态</span><strong>HTML + Markdown</strong></div>
              </div>
            </div>
          </article>

          <article class="channel-card">
            <div class="channel-top private">
              <small>Channel 02</small>
              <h3>证券私募行业动态日报</h3>
            </div>
            <div class="channel-body">
              <p>基于协会公示信息，整理全国证券私募管理人新增退出、陕西辖区动态和新产品备案情况。</p>
              <div class="mini-facts">
                <div><span>最新日期</span><strong>{latest_date('private')}</strong></div>
                <div><span>历史数量</span><strong>{counts.get('private', 0)} 期</strong></div>
                <div><span>内容形态</span><strong>HTML + Markdown</strong></div>
              </div>
            </div>
          </article>

          <article class="channel-card">
            <div class="channel-top ma">
              <small>Channel 03</small>
              <h3>陕西辖区收并购市场动态看板</h3>
            </div>
            <div class="channel-body">
              <p>把辖区收并购案例沉淀成可视化长图，用于阶段复盘、领导汇报和专题研究。</p>
              <div class="mini-facts">
                <div><span>最新观察</span><strong>{latest_date('ma')}</strong></div>
                <div><span>历史数量</span><strong>{counts.get('ma', 0)} 期</strong></div>
                <div><span>内容形态</span><strong>PNG 看板</strong></div>
              </div>
            </div>
          </article>

          <article class="channel-card">
            <div class="channel-top tender">
              <small>Channel 04</small>
              <h3>陕西金融类招投标项目清单</h3>
            </div>
            <div class="channel-body">
              <p>跟踪陕西地区证券公司、投行、固收投研或相关金融机构可能参与的业务机会。</p>
              <div class="mini-facts">
                <div><span>最新观察</span><strong>{latest_date('tender')}</strong></div>
                <div><span>历史数量</span><strong>{counts.get('tender', 0)} 期</strong></div>
                <div><span>内容形态</span><strong>HTML + PNG</strong></div>
              </div>
            </div>
          </article>
        </div>"""


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
    latest = latest_by_channel(reports)
    counts = count_by_channel(reports)

    content = INDEX.read_text(encoding="utf-8")
    rows = "\n\n".join(render_report(report) for report in reports)
    pattern = re.compile(
        r'(<div class="archive-list" id="archiveList">\n).*?(\n        </div>\n\n        <div class="empty-state")',
        re.S,
    )
    updated, count = pattern.subn(rf"\1{rows}\2", content)
    if count != 1:
        raise SystemExit("Could not locate archive list in v1/index.html.")

    latest_html = render_latest_section(latest)
    updated, count = re.subn(
        r'(<section id="latest" class="band alt">.*?<div class="section-head">.*?</div>\n\n)(.*?)(\n      </div>\n    </section>\n\n    <section id="channels")',
        rf"\1{latest_html}\3",
        updated,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit("Could not locate latest section in v1/index.html.")

    channels_html = render_channels(latest, counts)
    updated, count = re.subn(
        r'(<section id="channels" class="band alt">.*?<div class="section-head">.*?</div>\n\n)(.*?)(\n      </div>\n    </section>\n\n    <section id="archive")',
        rf"\1{channels_html}\3",
        updated,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit("Could not locate channels section in v1/index.html.")

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
    if "listed" in latest:
        updated = re.sub(
            r'(<link rel="preload" as="image" href=")assets/previews/listed-\d{4}-\d{2}-\d{2}\.webp(" type="image/webp" fetchpriority="high">)',
            rf"\g<1>{preview_path('listed', latest['listed'].day, 'webp')}\2",
            updated,
            count=1,
        )
    INDEX.write_text(updated, encoding="utf-8")
    print(f"Updated {INDEX.relative_to(ROOT.parent)} with {len(reports)} archive rows.")


if __name__ == "__main__":
    main()
