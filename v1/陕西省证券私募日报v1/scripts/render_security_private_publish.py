#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
VERSION_DIR = SCRIPT_DIR.parent
DATA_DIR = VERSION_DIR / "data"
OUTPUT_DIR = VERSION_DIR / "outputs"


def date_from_ms(value: Any) -> str:
    if not value:
        return ""
    return dt.datetime.utcfromtimestamp(int(value) / 1000).date().isoformat()


def clean(value: Any) -> str:
    return html.escape(str(value or "").replace("\n", " ").strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render securities private fund daily publish HTML from JSON.")
    parser.add_argument("--date", required=True, help="Report date, YYYY-MM-DD.")
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    return parser.parse_args()


def row_product(item: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td class=\"name\">{clean(item.get('fundName'))}</td>"
        f"<td>{clean(item.get('managerName'))}</td>"
        f"<td>{clean(item.get('mandatorName'))}</td>"
        f"<td>{date_from_ms(item.get('putOnRecordDate'))}</td>"
        f"<td>{date_from_ms(item.get('establishDate'))}</td>"
        f"<td>{clean(item.get('fundNo'))}</td>"
        "</tr>"
    )


def row_cancel(item: dict[str, Any]) -> str:
    detail = item.get("detail") or {}
    return (
        "<tr>"
        f"<td class=\"name\">{clean(item.get('orgName'))}</td>"
        f"<td>{date_from_ms(item.get('cancelDate'))}</td>"
        f"<td>{clean(detail.get('cancelType') or item.get('statusName'))}</td>"
        f"<td>{clean(detail.get('productCount', 0))}</td>"
        f"<td>{clean(detail.get('registeredCapital'))}</td>"
        f"<td>{clean(detail.get('paidInCapital'))}</td>"
        "</tr>"
    )


def render(report: dict[str, Any]) -> str:
    report_date = report["reportDate"]
    start = report["startDate"]
    end = report["endDate"]
    shaanxi_start = report["shaanxiStartDate"]
    products = report["shaanxiOfficeProducts"]
    shaanxi_cancel = report["shaanxiCancellations"]
    notable_cancel = report["nationalNotableCancellations"]

    top_exits = "、".join(
        f"{clean(item.get('orgName'))}产品{clean((item.get('detail') or {}).get('productCount', 0))}只"
        for item in notable_cancel[:3]
    ) or "暂无达到重点阈值的退出样本"
    cancel_rows = "\n".join(row_cancel(item) for item in shaanxi_cancel) or (
        "<tr><td colspan=\"6\" class=\"empty\">本统计窗口内暂无陕西证券私募退出/注销样本。</td></tr>"
    )
    product_rows = "\n".join(row_product(item) for item in products[:24]) or (
        "<tr><td colspan=\"6\" class=\"empty\">本统计窗口内暂无陕西办公地证券私募管理人新备案产品。</td></tr>"
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>证券私募行业动态日报｜{report_date}</title>
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: #f2f4f7; color: #172033; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", Arial, sans-serif; }}
.sheet {{ width: 1242px; height: 1810px; margin: 0 auto; background: #f7f8fa; padding: 42px 54px 34px; overflow: hidden; }}
.header {{ border-bottom: 4px solid #1f3a5f; padding-bottom: 18px; display: grid; grid-template-columns: 1fr auto; gap: 24px; align-items: end; }}
.kicker {{ font-size: 23px; color: #667085; margin-bottom: 8px; }}
h1 {{ margin: 0; font-size: 53px; line-height: 1.08; letter-spacing: 0; color: #111827; }}
.datebox {{ text-align: right; color: #1f3a5f; }}
.datebox .date {{ font-size: 34px; font-weight: 800; }}
.datebox .range {{ margin-top: 8px; font-size: 20px; color: #667085; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 22px 0 18px; }}
.kpi {{ background: #fff; border: 1px solid #d8dde6; border-radius: 8px; padding: 15px 16px 14px; min-height: 92px; }}
.kpi .label {{ font-size: 19px; color: #667085; line-height: 1.25; }}
.kpi .value {{ margin-top: 7px; font-size: 39px; font-weight: 800; color: #111827; }}
.kpi .value span {{ font-size: 22px; font-weight: 600; color: #667085; margin-left: 4px; }}
.section {{ margin-top: 17px; padding-top: 15px; border-top: 1px solid #d8dde6; }}
.section-title {{ display: flex; align-items: baseline; justify-content: space-between; gap: 18px; margin-bottom: 10px; }}
h2 {{ margin: 0; font-size: 29px; color: #111827; letter-spacing: 0; }}
.meta {{ font-size: 17px; color: #667085; }}
.summary-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
.note {{ background: #fff; border: 1px solid #d8dde6; border-left: 6px solid #1f3a5f; border-radius: 8px; padding: 14px 16px; font-size: 20px; line-height: 1.43; color: #25324a; min-height: 96px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d8dde6; border-radius: 8px; overflow: hidden; table-layout: fixed; }}
th {{ background: #e9edf3; color: #25324a; font-weight: 750; font-size: 16px; line-height: 1.22; padding: 9px 8px; border-bottom: 1px solid #d8dde6; text-align: left; }}
td {{ font-size: 15.2px; line-height: 1.24; padding: 7px 8px; border-bottom: 1px solid #e5e8ef; color: #1f2937; vertical-align: top; word-break: break-word; }}
tr:last-child td {{ border-bottom: 0; }}
td.name {{ font-weight: 700; color: #111827; }}
.empty {{ text-align: center; color: #667085; padding: 18px; }}
.cancel-table th:nth-child(1), .cancel-table td:nth-child(1) {{ width: 31%; }}
.cancel-table th:nth-child(2), .cancel-table td:nth-child(2) {{ width: 15%; }}
.cancel-table th:nth-child(3), .cancel-table td:nth-child(3) {{ width: 14%; }}
.cancel-table th:nth-child(4), .cancel-table td:nth-child(4) {{ width: 12%; }}
.cancel-table th:nth-child(5), .cancel-table td:nth-child(5) {{ width: 14%; }}
.cancel-table th:nth-child(6), .cancel-table td:nth-child(6) {{ width: 14%; }}
.product-table th:nth-child(1), .product-table td:nth-child(1) {{ width: 30%; }}
.product-table th:nth-child(2), .product-table td:nth-child(2) {{ width: 20%; }}
.product-table th:nth-child(3), .product-table td:nth-child(3) {{ width: 18%; }}
.product-table th:nth-child(4), .product-table td:nth-child(4) {{ width: 11%; }}
.product-table th:nth-child(5), .product-table td:nth-child(5) {{ width: 11%; }}
.product-table th:nth-child(6), .product-table td:nth-child(6) {{ width: 10%; }}
.footer {{ margin-top: 16px; color: #667085; font-size: 15px; line-height: 1.45; border-top: 1px solid #d8dde6; padding-top: 12px; }}
.source {{ margin-top: 6px; font-size: 14px; color: #7b8494; }}
</style>
</head>
<body>
<main class="sheet">
  <header class="header">
    <div>
      <div class="kicker">中国证券投资基金业协会公示数据整理</div>
      <h1>证券私募行业动态日报</h1>
    </div>
    <div class="datebox">
      <div class="date">{report_date}</div>
      <div class="range">统计：{start} 至 {end}</div>
    </div>
  </header>

  <section class="kpis">
    <div class="kpi"><div class="label">全国今年新增证券私募</div><div class="value">{len(report['nationalAdditions'])}<span>家</span></div></div>
    <div class="kpi"><div class="label">全国重点退出/注销</div><div class="value">{len(notable_cancel)}<span>家</span></div></div>
    <div class="kpi"><div class="label">陕西今年退出/注销</div><div class="value">{len(shaanxi_cancel)}<span>家</span></div></div>
    <div class="kpi"><div class="label">陕西今年新备案产品</div><div class="value">{len(products)}<span>只</span></div></div>
  </section>

  <section class="section">
    <div class="section-title"><h2>一、全国证券私募管理人重点变化</h2><div class="meta">今年以来</div></div>
    <div class="summary-grid">
      <div class="note"><strong>新增：</strong>今年以来新增证券私募管理人{len(report['nationalAdditions'])}家，脚本识别{len(report['nationalHighlightAdditions'])}家具备团队履历、人员或规模线索；新增机构仍以上海、北京、深圳为主。</div>
      <div class="note"><strong>退出/注销：</strong>今年以来已确认证券私募退出/注销{report['nationalCancellationTotal']}家，按产品数量/资本代理指标筛出重点{len(notable_cancel)}家。{top_exits}。</div>
    </div>
  </section>

  <section class="section">
    <div class="section-title"><h2>二、陕西证券私募动态</h2><div class="meta">今年以来：{shaanxi_start} 至 {end}</div></div>
    <table class="cancel-table">
      <thead><tr><th>管理人</th><th>注销日期</th><th>注销类型</th><th>产品数量</th><th>注册资本</th><th>实缴资本</th></tr></thead>
      <tbody>{cancel_rows}</tbody>
    </table>
  </section>

  <section class="section">
    <div class="section-title"><h2>三、办公地在陕西的管理人新产品备案</h2><div class="meta">陕西办公地证券私募管理人基数：{report['shaanxiOfficeManagerCount']} 家</div></div>
    <table class="product-table">
      <thead><tr><th>备案产品名称</th><th>管理人</th><th>托管人</th><th>备案日期</th><th>成立日期</th><th>基金编号</th></tr></thead>
      <tbody>
        {product_rows}
      </tbody>
    </table>
  </section>

  <footer class="footer">
    资料来源：中国证券投资基金业协会私募基金管理人分类查询公示、已注销私募基金管理人公示、私募基金公示。仅作公开信息整理，不构成投资建议。
    <div class="source">华泰证券西安锦业路证券营业部（西北分公司机构业务中心）｜https://refrain97.github.io/shaanxi-capital-market-daily/v1/</div>
    <div class="source">数据文件：v1/陕西省证券私募日报v1/data/security-private-fund-daily-{report_date}.json</div>
  </footer>
</main>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    data_path = Path(args.data_dir) / f"security-private-fund-daily-{args.date}.json"
    output_path = Path(args.output_dir) / f"security-private-fund-daily-{args.date}-publish.html"
    report = json.loads(data_path.read_text(encoding="utf-8"))
    output_path.write_text(render(report), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
