#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
VERSION_DIR = SCRIPT_DIR.parent
DATA_DIR = VERSION_DIR / "data"
OUTPUT_DIR = VERSION_DIR / "outputs"
TEMPLATE_PATH = VERSION_DIR / "templates" / "shaanxi-listed-company-morning-report-v1.template.html"
COMPANIES_PATH = DATA_DIR / "shaanxi-companies-cninfo-2026-03-31.json"


def zh_day(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日"


def esc(value: object) -> str:
    return html.escape(str(value or ""))


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument(
        "--auto-draft",
        action="store_true",
        help="Generate an automatic draft only. V1 official reports must follow the精读版 SOP.",
    )
    args = parser.parse_args()
    if not args.auto_draft:
        raise SystemExit(
            "Listed-company V1 official reports use the 精读版 workflow. "
            "Read templates/shaanxi-listed-company-morning-report-v1-sop.md, "
            "extract PDF numbers, and hand-curate the Markdown/HTML. "
            "Use --auto-draft only for a non-final starting draft."
        )
    day = date.fromisoformat(args.date)
    data_path = Path(args.data_dir) / f"cninfo-shaanxi-announcements-{day:%Y-%m-%d}.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    items = data[f"{day:%Y-%m-%d}~{day:%Y-%m-%d}"]
    universe_count = int(data.get("_summary", {}).get("companyUniverseCount") or 85)
    companies = len({str(item.get("_matchedCompanyName") or item.get("secName")) for item in items})

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"shaanxi-listed-company-morning-{day:%Y-%m-%d}.md"
    html_path = out_dir / f"shaanxi-listed-company-morning-{day:%Y-%m-%d}-publish.html"
    md_path.write_text(render_markdown(day, items, companies), encoding="utf-8")
    html_path.write_text(render_html(day, items, universe_count), encoding="utf-8")
    print(f"Wrote {md_path}")
    print(f"Wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
