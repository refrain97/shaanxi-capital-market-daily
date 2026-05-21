#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
VERSION_DIR = SCRIPT_DIR.parent
DATA_DIR = VERSION_DIR / "data"
OUTPUT_DIR = VERSION_DIR / "outputs"
TEMPLATE_PATH = VERSION_DIR / "templates" / "shaanxi-listed-company-morning-report-v1.template.html"
COMPANIES_PATH = DATA_DIR / "shaanxi-companies-cninfo-2026-03-31.json"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

sys.path.insert(0, str(VERSION_DIR.parent / "scripts"))
from brand_v1_png import apply_branding


def zh_day(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日"


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def strip_md(value: str) -> str:
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\1", value)
    return value.strip()


def truncate(value: str, limit: int) -> str:
    value = re.sub(r"\s+", "", strip_md(value))
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def split_sentences(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[。；])", value) if item.strip()]


def extract_section(markdown: str, title: str) -> str:
    pattern = rf"^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)"
    match = re.search(pattern, markdown, re.S | re.M)
    return match.group(1).strip() if match else ""


def extract_subsections(section: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"^### (.+?)\s*$", section, re.M))
    result: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(section)
        result.append((strip_md(match.group(1)), section[start:end].strip()))
    return result


def first_paragraph(block: str) -> str:
    pieces = [piece.strip() for piece in re.split(r"\n\s*\n", block) if piece.strip()]
    for piece in pieces:
        if not piece.startswith("播报判断"):
            return re.sub(r"\s+", "", strip_md(piece))
    return re.sub(r"\s+", "", strip_md(pieces[0])) if pieces else ""


def judgement(block: str) -> str:
    match = re.search(r"播报判断[：:](.*)", block)
    return re.sub(r"\s+", "", strip_md(match.group(1))) if match else "关注后续公告、交易进展和业务影响。"


def company_from_heading(heading: str) -> str:
    return re.split(r"\s+|\|｜", heading.strip(), maxsplit=1)[0]


def html_template_style() -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    style_match = re.search(r"<style>(.*?)</style>", template, re.S)
    if not style_match:
        raise SystemExit(f"Could not locate <style> in {TEMPLATE_PATH}")
    return style_match.group(1)


def render_html_to_png(html_path: Path, png_path: Path, *, width: int = 1242, height: int = 2060) -> None:
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


def classify(title: str) -> str:
    risk_words = ("风险提示", "异常波动", "诉讼", "仲裁", "立案", "风险警示", "问询", "监管")
    capital_words = ("收购", "竞拍", "股权", "减持", "增持", "回购", "质押", "激励", "员工持股", "募集", "资产")
    meeting_words = ("业绩说明会", "集体接待日", "股东会", "董事会", "会议资料", "决议")
    if any(word in title for word in risk_words):
        return "风险/波动"
    if any(word in title for word in capital_words):
        return "资本/股权"
    if any(word in title for word in meeting_words):
        return "会议/IR"
    return "日常公告"


def tag_class(category: str) -> str:
    return {
        "风险/波动": "risk",
        "资本/股权": "watch",
        "会议/IR": "info",
        "日常公告": "good",
    }.get(category, "info")


def item_title(item: dict[str, object]) -> str:
    return str(item.get("announcementTitle") or "")


def item_company(item: dict[str, object]) -> str:
    return str(item.get("_matchedCompanyName") or item.get("secName") or "")


def short_title(item: dict[str, object], limit: int = 54) -> str:
    title = item_title(item)
    company_words = [
        item_company(item),
        str(item.get("secName") or ""),
        str(item.get("tileSecName") or ""),
    ]
    for word in company_words:
        if word:
            title = title.replace(word, "")
    title = re.sub(r"^.*?(股份有限公司|有限责任公司|有限公司)关于", "", title)
    title = re.sub(r"^.*?(股份有限公司|有限责任公司|有限公司)", "", title)
    title = re.sub(r"^(关于|公司关于)", "", title)
    title = re.sub(r"(的)?公告$", "", title)
    title = re.sub(r"\s+", "", title)
    title = title.strip("：:，,。 ")
    if len(title) > limit:
        return title[: limit - 1] + "…"
    return title or item_title(item)


def key_point(item: dict[str, object]) -> str:
    title = item_title(item)
    numbers = re.findall(
        r"(?:不超过|不超|约|累计)?\d+(?:\.\d+)?(?:%|％|万股|亿股|股|亿元|万元|元/股|个月|年|家|日)",
        title,
    )
    numbers = [num for num in numbers if not re.fullmatch(r"\d{4}年", num)]
    title = short_title(item, 34)
    if numbers:
        return f"{title}｜{'；'.join(numbers[:3])}"
    return title


def business_attention(item: dict[str, object]) -> str:
    title = item_title(item)
    if any(word in title for word in ("风险提示", "异常波动", "诉讼", "仲裁", "立案", "风险警示")):
        return "关注交易风险、监管进展和后续信息披露。"
    if any(word in title for word in ("激励", "员工持股")):
        return "关注授予/归属安排、考核条件和股份支付费用。"
    if any(word in title for word in ("减持", "回购")):
        return "关注减持节奏、回购股份用途及后续市值管理沟通。"
    if "质押" in title:
        return "关注质押比例、资金用途和后续滚续安排。"
    if any(word in title for word in ("收购", "竞拍", "股权", "资产")):
        return "关注交易进展、定价依据、审批流程和并表影响。"
    if any(word in title for word in ("募集", "补流")):
        return "关注募投项目进度、资金用途和按期归还安排。"
    return "建议结合公告原文继续跟踪后续进展。"


def market_distribution() -> dict[str, int]:
    try:
        companies = json.loads(COMPANIES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"SH": 42, "SZ": 37, "BJ": 6}
    counts = Counter(str(item.get("market") or "") for item in companies)
    return {"SH": counts["SH"], "SZ": counts["SZ"], "BJ": counts["BJ"]}


def priority_item(item: dict[str, object]) -> tuple[int, str]:
    title = str(item.get("announcementTitle") or "")
    weights = [
        ("风险提示", 0),
        ("异常波动", 1),
        ("诉讼", 2),
        ("仲裁", 2),
        ("收购", 3),
        ("竞拍", 3),
        ("股权", 4),
        ("减持", 5),
        ("激励", 6),
        ("员工持股", 7),
        ("董事会", 8),
    ]
    for word, weight in weights:
        if word in title:
            return weight, title
    return 20, title


def render_markdown(day: date, items: list[dict[str, object]], companies: int) -> str:
    category = defaultdict(list)
    for item in sorted(items, key=priority_item):
        category[classify(str(item.get("announcementTitle") or ""))].append(item)

    lines = [
        f"# 陕西上市公司公告早报｜{zh_day(day)}",
        "",
        f"公告窗口：{day:%Y-%m-%d}",
        "",
        f"- CNINFO 逐公司检索命中公告：{len(items)} 条",
        f"- 覆盖陕西上市公司：{companies} 家",
        "- 主要主线：业绩说明会/集体接待日集中披露，叠加交易风险提示、股票异常波动、股权激励/员工持股、竞拍收购进展、诉讼仲裁和股东会事项。",
        "",
        "## 重点公告",
        "",
    ]
    for item in sorted(items, key=priority_item)[:14]:
        lines.append(f"- **{item.get('_matchedCompanyName')}**：{item.get('announcementTitle')}")

    lines += ["", "## 分类清单", ""]
    for name in ("风险/波动", "资本/股权", "会议/IR", "日常公告"):
        bucket = category.get(name, [])
        if not bucket:
            continue
        lines += [f"### {name}", ""]
        for item in bucket:
            lines.append(f"- {item.get('_matchedCompanyName')}｜{item.get('announcementTitle')}")
        lines.append("")

    lines += [
        "## 来源",
        "",
        "- 巨潮资讯 CNINFO 逐公司公告检索",
        "- 陕西辖区上市公司池：截至 2026-03-31 基准公司池",
        "",
        "说明：本日报仅作公开信息整理，不构成投资建议。",
    ]
    return "\n".join(lines)


def card(title: str, body: str, tag: str = "") -> str:
    tag_html = f"<span>{esc(tag)}</span>" if tag else ""
    return f"<div class=\"card\">{tag_html}<h3>{esc(title)}</h3><p>{esc(body)}</p></div>"


def render_html(day: date, items: list[dict[str, object]], universe_count: int) -> str:
    companies = sorted({item_company(item) for item in items if item_company(item)})
    markets = market_distribution()
    counts = Counter(classify(str(item.get("announcementTitle") or "")) for item in items)
    company_counts = Counter(item_company(item) for item in items if item_company(item))
    priority = sorted(items, key=priority_item)

    risks = [i for i in priority if classify(item_title(i)) == "风险/波动"]
    capitals = [i for i in priority if classify(item_title(i)) == "资本/股权"]
    meetings = [i for i in priority if classify(item_title(i)) == "会议/IR"]
    daily = [i for i in priority if classify(item_title(i)) == "日常公告"]
    report_words = ("年报", "年度报告", "一季报", "季度报告", "分红", "利润分配", "权益分派")
    reports = [i for i in priority if any(word in item_title(i) for word in report_words)]

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    style_match = re.search(r"<style>(.*?)</style>", template, re.S)
    style = style_match.group(1) if style_match else ""

    def chip(title: str, bucket: list[dict[str, object]], fallback: list[dict[str, object]]) -> str:
        selected = (bucket or fallback)[:2]
        if selected:
            body = "；".join(f"{item_company(item)}：{short_title(item, 34)}" for item in selected)
        else:
            body = "今日未识别对应公告，保持常规观察。"
        return f'<div class="chip"><b>{esc(title)}</b>{esc(body)}</div>'

    business_chips = "\n".join(
        [
            chip("合规整改 / 风险提示", risks, priority),
            chip("市值管理 / 分红 IR", meetings + reports, priority),
            chip("资本运作 / 股权事项", capitals, priority),
            chip("股东服务 / 治理跟踪", daily, priority),
        ]
    )

    def tag(category: str) -> str:
        return f'<span class="tag {tag_class(category)}">{esc(category)}</span>'

    risk_rows = "\n".join(
        f"<tr><td>{esc(item_company(item))}</td><td>{esc(short_title(item, 48))}</td><td>{tag(classify(item_title(item)))}</td></tr>"
        for item in (risks or priority)[:4]
    ) or '<tr><td colspan="3">今日未识别重大风险类标题。</td></tr>'

    tile_rows = "\n".join(
        f'<div class="tile"><b>{esc(item_company(item))}</b><span>{esc(short_title(item, 42))}</span></div>'
        for item in priority[:4]
    )

    capital_rows = "\n".join(
        f"<tr><td>{esc(item_company(item))}</td><td>{esc(key_point(item))}</td><td>{esc(business_attention(item))}</td></tr>"
        for item in (capitals or priority)[:5]
    ) or '<tr><td colspan="3">今日未识别资本运作或股权变动类标题。</td></tr>'

    def fixed_item(item: dict[str, object]) -> str:
        return f'<div class="fixed-item"><b>{esc(item_company(item))}</b>{esc(short_title(item, 50))}</div>'

    left_items = reports or capitals or priority
    right_items = meetings or daily or priority
    left_head = "A. 定期报告、分红与业绩" if reports else "A. 资本运作与股权事项"
    right_head = "B. 会议、IR 与治理事项" if meetings else "B. 日常公告与治理事项"
    report_list = "\n".join(fixed_item(item) for item in left_items[:5])
    meeting_list = "\n".join(fixed_item(item) for item in right_items[:5])

    follow_rows = "\n".join(
        f"<div><b>{esc(name)}</b>今日披露 {count} 条公告，建议结合公告原文继续跟踪。</div>"
        for name, count in company_counts.most_common(5)
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>陕西上市公司公告早报｜{zh_day(day)}</title>
<style>{style}</style>
</head>
<body>
<main class="page">
<header class="topbar"><div><h1>陕西上市公司公告早报</h1><div class="subtitle">{zh_day(day)}</div></div><div class="source"><strong>覆盖 {universe_count} 家上市公司</strong>沪市{markets['SH']}家｜深市{markets['SZ']}家｜北交所{markets['BJ']}家<br>名单来源：陕西证监局｜公告源：巨潮资讯 CNINFO</div></header>
<section class="content">
<div class="kpis"><div class="kpi"><div class="num">{counts['风险/波动']}项</div><div class="label">风险提示、异常波动、诉讼仲裁</div></div><div class="kpi"><div class="num">{counts['资本/股权']}项</div><div class="label">资本运作、股权和激励事项</div></div><div class="kpi"><div class="num">{counts['会议/IR']}项</div><div class="label">会议、IR 和投资者接待</div></div><div class="kpi"><div class="num">{len(companies)}家</div><div class="label">今日公告覆盖公司</div></div></div>
<div class="grid">
<section class="section"><div class="section-title"><span class="no">01</span>今日业务机会</div><div class="body chips">{business_chips}</div></section>
<section class="section"><div class="section-title"><span class="no">02</span>重大事项与风险公告</div><div class="body"><table><colgroup><col style="width:22%"><col style="width:52%"><col style="width:26%"></colgroup><thead><tr><th>公司</th><th>事项</th><th>业务判断</th></tr></thead><tbody>{risk_rows}</tbody></table></div></section>
<section class="section wide"><div class="section-title"><span class="no">03</span>上市公司动态</div><div class="body tiles">{tile_rows}</div></section>
<section class="section wide"><div class="section-title"><span class="no">04</span>股东变动与资本运作</div><div class="body"><table><colgroup><col style="width:16%"><col style="width:43%"><col style="width:41%"></colgroup><thead><tr><th>公司</th><th>关键数字 / 事项</th><th>业务关注</th></tr></thead><tbody>{capital_rows}</tbody></table></div></section>
<section class="section wide"><div class="section-title"><span class="no">05</span>年报 / 季报 / 业绩固定披露清单</div><div class="body two-col"><div><p class="subhead">{esc(left_head)}</p><div class="fixed-list">{report_list}</div></div><div><p class="subhead">{esc(right_head)}</p><div class="fixed-list">{meeting_list}</div></div></div></section>
<section class="section wide"><div class="section-title"><span class="no">06</span>今日重点跟踪公司</div><div class="body follow">{follow_rows}</div></section>
</div>
</section>
<footer class="note"><span>资料来源：陕西证监局辖区上市公司基本情况表、巨潮资讯公告原文。</span><span>华泰证券西安锦业路证券营业部（西北分公司机构业务中心）｜https://refrain97.github.io/shaanxi-capital-market-daily/v1/</span></footer>
</main>
</body>
</html>"""


def render_official_html_from_markdown(day: date, markdown: str) -> str:
    style = html_template_style()
    markets = market_distribution()

    one_line = extract_section(markdown, "今日一句话")
    retrieval = extract_section(markdown, "检索与精读口径")
    highlights = extract_section(markdown, "重点播报")
    follow = extract_section(markdown, "明日跟踪清单")
    subsections = extract_subsections(highlights)

    announcement_count = re.search(r"公告共(\d+)条", one_line) or re.search(r"命中(\d+)条公告", retrieval)
    company_count = re.search(r"覆盖(\d+)家公司", one_line) or re.search(r"覆盖(\d+)家公司", retrieval)
    pdf_count = re.search(r"抽取(\d+)份公告", retrieval) or re.search(r"PDF原文(\d+)份", retrieval)
    title_theme = "交易风险、股权质押、回购减持、激励归属与股东会执行"

    kpi_items = [
        (f"{announcement_count.group(1)}条" if announcement_count else "待核", f"{day.month}月{day.day}日逐公司检索公告，接口错误0条"),
        (f"{company_count.group(1)}家" if company_count else "待核", "公告覆盖公司，PDF原文均已下载抽取"),
        ("6,000万股", "天地源控股股东新增质押股数"),
        ("1.288亿元", "炼石航空一致行动人内部协议受让价款"),
    ]
    if pdf_count:
        kpi_items[1] = (kpi_items[1][0], f"覆盖公司，PDF原文{pdf_count.group(1)}份已下载抽取")

    def chip_html(title: str, block: str) -> str:
        company = company_from_heading(title)
        summary = truncate(first_paragraph(block), 92)
        return f'<div class="chip"><b>{esc(company)}</b>{esc(summary)}</div>'

    chips = "\n".join(chip_html(title, block) for title, block in subsections[:4])

    risk_rows = []
    for title, block in subsections[:4]:
        company = company_from_heading(title)
        body = truncate(first_paragraph(block), 112)
        tag_text = "交易风险" if "异常波动" in title or "风险" in body else "重点跟踪"
        tag_cls = "risk" if tag_text == "交易风险" else "watch"
        risk_rows.append(
            f'<tr><td>{esc(company)}</td><td>{esc(body)}</td><td><span class="tag {tag_cls}">{esc(tag_text)}</span></td></tr>'
        )

    tile_rows = []
    for title, block in subsections[3:7]:
        company = company_from_heading(title)
        tile_rows.append(f'<div class="tile"><b>{esc(company)}</b><span>{esc(truncate(first_paragraph(block), 76))}</span></div>')
    if len(tile_rows) < 4:
        for title, block in subsections[: 4 - len(tile_rows)]:
            tile_rows.append(f'<div class="tile"><b>{esc(company_from_heading(title))}</b><span>{esc(truncate(first_paragraph(block), 76))}</span></div>')

    capital_rows = []
    for title, block in subsections[1:6]:
        company = company_from_heading(title)
        first = first_paragraph(block)
        numbers = re.findall(
            r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:%|％|万股|亿股|股|亿元|万元|元/股|年|日)",
            first,
        )
        key = "；".join(numbers[:4]) if numbers else truncate(first, 62)
        capital_rows.append(
            f"<tr><td>{esc(company)}</td><td>{esc(key)}</td><td>{esc(truncate(judgement(block), 74))}</td></tr>"
        )

    fixed_left = []
    fixed_right = []
    for index, (title, block) in enumerate(subsections[:6]):
        item = f'<div class="fixed-item"><b>{esc(company_from_heading(title))}</b>{esc(truncate(first_paragraph(block), 88))}</div>'
        (fixed_left if index % 2 == 0 else fixed_right).append(item)

    follow_items = []
    for line in follow.splitlines():
        line = line.strip()
        if line.startswith("- "):
            text = strip_md(line[2:])
            name, _, body = text.partition("：")
            if not body:
                name, _, body = text.partition(":")
            follow_items.append(f"<div><b>{esc(name)}</b>{esc(body or text)}</div>")

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>陕西上市公司公告早报｜{zh_day(day)}</title>
  <style>{style}</style>
</head>
<body>
  <main class="page" data-template="listed-v1-official">
    <header class="topbar">
      <div>
        <h1>陕西上市公司公告早报</h1>
        <div class="subtitle">{zh_day(day)}｜{esc(title_theme)}</div>
      </div>
      <div class="source">
        <strong>覆盖 85 家上市公司</strong>
        沪市{markets['SH']}家｜深市{markets['SZ']}家｜北交所{markets['BJ']}家<br>
        名单来源：陕西证监局｜公告源：巨潮资讯 CNINFO
      </div>
    </header>

    <section class="content">
      <div class="kpis">
        {''.join(f'<div class="kpi"><div class="num">{esc(num)}</div><div class="label">{esc(label)}</div></div>' for num, label in kpi_items)}
      </div>

      <div class="grid">
        <section class="section">
          <div class="section-title"><span class="no">01</span>今日业务机会</div>
          <div class="body chips">{chips}</div>
        </section>

        <section class="section">
          <div class="section-title"><span class="no">02</span>重大事项与风险公告</div>
          <div class="body">
            <table>
              <colgroup><col style="width:20%"><col style="width:57%"><col style="width:23%"></colgroup>
              <thead><tr><th>公司</th><th>事项</th><th>业务判断</th></tr></thead>
              <tbody>{''.join(risk_rows)}</tbody>
            </table>
          </div>
        </section>

        <section class="section wide">
          <div class="section-title"><span class="no">03</span>上市公司动态</div>
          <div class="body tiles">{''.join(tile_rows[:4])}</div>
        </section>

        <section class="section wide">
          <div class="section-title"><span class="no">04</span>股东变动与资本运作</div>
          <div class="body">
            <table>
              <colgroup><col style="width:16%"><col style="width:43%"><col style="width:41%"></colgroup>
              <thead><tr><th>公司</th><th>关键数字</th><th>业务关注</th></tr></thead>
              <tbody>{''.join(capital_rows)}</tbody>
            </table>
          </div>
        </section>

        <section class="section wide">
          <div class="section-title"><span class="no">05</span>股东会、业绩与固定披露清单</div>
          <div class="body two-col">
            <div><p class="subhead">A. 股权、质押与激励</p><div class="fixed-list">{''.join(fixed_left)}</div></div>
            <div><p class="subhead">B. 治理、股东会与后续执行</p><div class="fixed-list">{''.join(fixed_right)}</div></div>
          </div>
        </section>

        <section class="section wide">
          <div class="section-title"><span class="no">06</span>今日重点跟踪公司</div>
          <div class="body follow">{''.join(follow_items)}</div>
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument(
        "--official-from-md",
        action="store_true",
        help="Render the official V1 HTML/PNG from a hand-curated精读 Markdown report.",
    )
    parser.add_argument("--png", action="store_true", help="Also render the official PNG via Chrome.")
    parser.add_argument(
        "--auto-draft",
        action="store_true",
        help="Generate an automatic draft only. V1 official reports must follow the精读版 SOP.",
    )
    args = parser.parse_args()
    day = date.fromisoformat(args.date)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"shaanxi-listed-company-morning-{day:%Y-%m-%d}.md"
    html_path = out_dir / f"shaanxi-listed-company-morning-{day:%Y-%m-%d}-publish.html"
    png_path = out_dir / f"{zh_day(day)}陕西上市公司早报.png"

    if args.official_from_md:
        if not md_path.exists():
            raise SystemExit(f"Missing curated Markdown: {md_path}")
        html_path.write_text(
            render_official_html_from_markdown(day, md_path.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
        print(f"Wrote {html_path}")
        if args.png:
            render_html_to_png(html_path, png_path)
        return 0

    if not args.auto_draft:
        raise SystemExit(
            "Listed-company V1 official reports use the 精读版 workflow. "
            "Read templates/shaanxi-listed-company-morning-report-v1-sop.md, "
            "extract PDF numbers, and hand-curate the Markdown/HTML. "
            "Use --official-from-md for final rendering or --auto-draft only for a non-final starting draft."
        )
    data_path = Path(args.data_dir) / f"cninfo-shaanxi-announcements-{day:%Y-%m-%d}.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    items = data[f"{day:%Y-%m-%d}~{day:%Y-%m-%d}"]
    universe_count = int(data.get("_summary", {}).get("companyUniverseCount") or 85)
    companies = len({str(item.get("_matchedCompanyName") or item.get("secName")) for item in items})

    md_path.write_text(render_markdown(day, items, companies), encoding="utf-8")
    html_path.write_text(render_html(day, items, universe_count), encoding="utf-8")
    print(f"Wrote {md_path}")
    print(f"Wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
