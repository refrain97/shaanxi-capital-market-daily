#!/usr/bin/env python3
"""Generate a daily AMAC securities private fund industry report.

Data source: Asset Management Association of China public disclosure pages.
The script uses public endpoints behind gs.amac.org.cn disclosure tables.
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import random
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - friendly runtime error
    raise SystemExit("Missing dependency: beautifulsoup4. Install with `python3 -m pip install beautifulsoup4`.") from exc


BASE = "https://gs.amac.org.cn"
API_BASE = f"{BASE}/amac-infodisc/api"
MANAGER_REFERER = f"{BASE}/amac-infodisc/res/pof/manager/managerList.html"
FUND_REFERER = f"{BASE}/amac-infodisc/res/pof/fund/index.html"
CANCEL_REFERER = MANAGER_REFERER
SCRIPT_DIR = Path(__file__).resolve().parent
VERSION_DIR = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = VERSION_DIR / "outputs"
DEFAULT_DATA_DIR = VERSION_DIR / "data"

SECURITY_MANAGER_TYPE = "私募证券投资基金管理人"
SECURITY_FUND_TYPE = "OT0101"
SHAANXI = "陕西省"
PAGE_SIZE = 20
STATUS_MAP = {
    100: "主动注销",
    200: "依公告注销",
    300: "协会注销",
    500: "12个月无在管注销",
}


def parse_args() -> argparse.Namespace:
    today = dt.date.today().isoformat()
    parser = argparse.ArgumentParser(description="Generate AMAC securities private fund daily report.")
    parser.add_argument("--date", default=today, help="Report date, YYYY-MM-DD. Default: today.")
    parser.add_argument("--since", help="Start date, YYYY-MM-DD. Default: same as --date.")
    parser.add_argument("--shaanxi-since", help="Shaanxi section start date. Default: Jan 1 of report year.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for markdown report.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Directory for raw JSON.")
    parser.add_argument("--max-cancel-pages", type=int, default=80, help="Safety cap for cancelled manager pages.")
    parser.add_argument("--max-cancel-details", type=int, default=300, help="Safety cap for cancelled manager detail pages.")
    parser.add_argument("--max-product-pages", type=int, default=220, help="Safety cap for product pages.")
    parser.add_argument("--notable-product-threshold", type=int, default=5, help="Cancelled manager product-count proxy for notable exits.")
    parser.add_argument("--notable-capital-threshold", type=float, default=5000, help="Registered/paid capital proxy in RMB 10k for notable exits.")
    parser.add_argument("--sleep", type=float, default=0.15, help="Pause between detail page requests.")
    return parser.parse_args()


def to_date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def date_from_ms(value: Any) -> str:
    if not value:
        return ""
    return dt.datetime.utcfromtimestamp(int(value) / 1000).date().isoformat()


def date_in_range(value: Any, start: dt.date, end: dt.date) -> bool:
    text = date_from_ms(value)
    if not text:
        return False
    day = dt.date.fromisoformat(text)
    return start <= day <= end


def endpoint(path: str, page: int, size: int = PAGE_SIZE) -> str:
    params = {
        "rand": f"{random.random():.17f}",
        "page": page,
        "size": size,
    }
    return f"{API_BASE}{path}?{urllib.parse.urlencode(params)}"


def post_json(path: str, payload: dict[str, Any], page: int = 0, referer: str = MANAGER_REFERER) -> dict[str, Any]:
    url = endpoint(path, page)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json",
        "Origin": BASE,
        "Referer": referer,
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
    }
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"AMAC request failed {exc.code}: {url} {detail}")
            if exc.code not in (500, 502, 503, 504):
                raise last_error from exc
        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
            http.client.RemoteDisconnected,
            http.client.IncompleteRead,
        ) as exc:
            last_error = exc
        time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"AMAC request failed after retries: {url} {last_error}") from last_error


def get_text(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0", "Referer": BASE}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_all(path: str, payload: dict[str, Any], referer: str, max_pages: int = 80) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(max_pages):
        data = post_json(path, payload, page=page, referer=referer)
        content = data.get("content") or []
        rows.extend(content)
        if data.get("last") or not content:
            break
    return rows


def fetch_manager_additions(start: str, end: str) -> list[dict[str, Any]]:
    payload = {
        "primaryInvestType": SECURITY_MANAGER_TYPE,
        "registerDate": {"from": start, "to": end},
    }
    return fetch_all("/pof/manager/query", payload, MANAGER_REFERER)


def fetch_shaanxi_security_managers() -> list[dict[str, Any]]:
    payload = {
        "primaryInvestType": SECURITY_MANAGER_TYPE,
        "offiProvinceFsc": "province",
        "officeProvince": SHAANXI,
    }
    return fetch_all("/pof/manager/query", payload, MANAGER_REFERER, max_pages=20)


def fetch_security_products(start: str, end: str, max_pages: int) -> list[dict[str, Any]]:
    payload = {
        "fundType": SECURITY_FUND_TYPE,
        "putOnRecordDate": {"from": start, "to": end},
    }
    return fetch_all("/pof/fund", payload, FUND_REFERER, max_pages=max_pages)


def fetch_cancelled_in_window(start: dt.date, end: dt.date, max_pages: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in range(max_pages):
        data = post_json("/cancelled/manager", {}, page=page, referer=CANCEL_REFERER)
        content = data.get("content") or []
        if not content:
            break
        for row in content:
            key = str(row.get("userTenantId") or row.get("orgCode") or row.get("orgName"))
            if key in seen or not date_in_range(row.get("cancelDate"), start, end):
                continue
            rows.append(row)
            seen.add(key)
        page_dates = [dt.date.fromisoformat(date_from_ms(row.get("cancelDate"))) for row in content if row.get("cancelDate")]
        if page_dates and min(page_dates) < start:
            break
    return rows


def fetch_cancelled_by_keywords(start: dt.date, end: dt.date, keywords: list[str], max_pages: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for keyword in keywords:
        for page in range(max_pages):
            data = post_json("/cancelled/manager", {"keyword": keyword}, page=page, referer=CANCEL_REFERER)
            content = data.get("content") or []
            if not content:
                break
            for row in content:
                key = str(row.get("userTenantId") or row.get("orgCode") or row.get("orgName"))
                if key in seen or not date_in_range(row.get("cancelDate"), start, end):
                    continue
                rows.append(row)
                seen.add(key)
            page_dates = [dt.date.fromisoformat(date_from_ms(row.get("cancelDate"))) for row in content if row.get("cancelDate")]
            if page_dates and min(page_dates) < start:
                break
    return rows


def absolutize(relative_url: str, kind: str = "manager") -> str:
    if relative_url.startswith("http"):
        return relative_url
    if relative_url.startswith("../manager/"):
        return f"{BASE}/amac-infodisc/res/pof/manager/{relative_url.rsplit('/', 1)[-1]}"
    if kind == "cancelled":
        return f"{BASE}/amac-infodisc/res/cancelled/manager/{relative_url}"
    return f"{BASE}/amac-infodisc/res/pof/{kind}/{relative_url}"


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_markup(value: Any) -> str:
    return clean_text(re.sub(r"<[^>]+>", "", str(value or "")))


def section_title(section: Any) -> str:
    title = section.select_one(".common-tit span")
    return clean_text(title.get_text(" ", strip=True)) if title else ""


def kv_from_table(table: Any) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for row in table.select("tr"):
        row_kv = kv_from_row(row)
        for key, values in row_kv.items():
            result.setdefault(key, []).extend(values)
    return result


def kv_from_row(row: Any) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    cells = row.find_all(["td", "th"], recursive=False)
    i = 0
    while i < len(cells):
        cell = cells[i]
        classes = cell.get("class") or []
        if "title" in classes and i + 1 < len(cells):
            key = clean_text(cell.get_text(" ", strip=True))
            value = clean_text(cells[i + 1].get_text(" ", strip=True))
            if key and value:
                result.setdefault(key, []).append(value)
            i += 2
        else:
            i += 1
    return result


def first(kv: dict[str, list[str]], *keys: str) -> str:
    for key in keys:
        values = kv.get(key)
        if values:
            return values[0]
    return ""


def parse_executives(section: Any) -> list[dict[str, str]]:
    executives: list[dict[str, str]] = []
    for row in section.select("tr"):
        row_kv = kv_from_row(row)
        role = first(row_kv, "职务")
        name = first(row_kv, "姓名")
        qualification = first(row_kv, "是否有基金从业资格")
        if role and name:
            executives.append({"name": name, "role": role, "qualification": qualification})
    deduped: list[dict[str, str]] = []
    seen = set()
    for item in executives:
        key = (item["name"], item["role"])
        if key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped


def parse_work_history(section: Any) -> list[dict[str, str]]:
    histories: list[dict[str, str]] = []
    for table in section.select("table.list-table"):
        headers = [clean_text(cell.get_text(" ", strip=True)) for cell in table.select("tr th")]
        if not {"任职单位", "任职部门", "职务"}.issubset(set(headers)):
            continue
        for row in table.select("tr"):
            cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
            if len(cells) >= 4:
                histories.append({
                    "time": cells[0],
                    "company": cells[1],
                    "department": cells[2],
                    "role": cells[3],
                })
    deduped: list[dict[str, str]] = []
    seen = set()
    for item in histories:
        key = (item["company"], item["department"], item["role"])
        if item["company"] and key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped


def parse_shareholders(section: Any) -> list[dict[str, str]]:
    shareholders: list[dict[str, str]] = []
    rows = section.select("table.list-table tr")
    for row in rows:
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
        if len(cells) >= 3 and cells[0].isdigit():
            shareholders.append({"name": cells[1], "ratio": cells[2]})
    return shareholders


def parse_product_count(section: Any) -> int:
    count = 0
    for row in section.select("table.list-table tr"):
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
        if cells and cells[0].isdigit():
            count += 1
    return count


def parse_manager_detail(url: str) -> dict[str, Any]:
    soup = BeautifulSoup(get_text(url), "html.parser")
    detail: dict[str, Any] = {"url": url, "kv": {}, "executives": [], "workHistory": [], "shareholders": [], "productCount": 0}
    for section in soup.select(".section"):
        title = section_title(section)
        if not title:
            continue
        kv: dict[str, list[str]] = {}
        for table in section.select("table"):
            table_kv = kv_from_table(table)
            for key, values in table_kv.items():
                kv.setdefault(key, []).extend(values)
        detail["kv"][title] = kv
        if "高管信息" in title:
            detail["executives"] = parse_executives(section)
            detail["workHistory"] = parse_work_history(section)
        if "出资人信息" in title:
            detail["shareholders"] = parse_shareholders(section)
        if "产品信息" in title:
            detail["productCount"] = parse_product_count(section)
    return detail


def enrich_manager(row: dict[str, Any]) -> dict[str, Any]:
    url = absolutize(row.get("url", ""), "manager")
    detail = parse_manager_detail(url)
    org = detail["kv"].get("机构信息", {})
    controller = detail["kv"].get("实际控制人信息", {})
    row = dict(row)
    row["detailUrl"] = url
    row["detail"] = {
        "officeAddress": first(org, "办公地址") or row.get("officeAddress", ""),
        "registeredCapital": first(org, "注册资本(万元)(人民币)", "注册资本(万元)人民币"),
        "paidInCapital": first(org, "实缴资本(万元)(人民币)", "实缴资本(万元)人民币"),
        "paidRatio": first(org, "注册资本实缴比例"),
        "employeeCount": first(org, "全职员工人数"),
        "qualifiedCount": first(org, "取得基金从业人数"),
        "scaleRange": first(org, "管理规模区间"),
        "actualController": first(controller, "实际控制人姓名 / 名称"),
        "executives": detail.get("executives", []),
        "workHistory": detail.get("workHistory", [])[:12],
        "shareholders": detail.get("shareholders", [])[:3],
    }
    row["teamSummary"] = team_summary(row)
    row["highlightReason"] = highlight_reason(row)
    return row


def enrich_cancelled(row: dict[str, Any]) -> dict[str, Any]:
    url = absolutize(f"{row['userTenantId']}.html", "cancelled")
    detail = parse_manager_detail(url)
    org = detail["kv"].get("机构信息", {})
    cancel = {}
    for kv in detail["kv"].values():
        for key in ("注销时间", "注销类型", "注销原因"):
            if key in kv:
                cancel[key] = kv[key][0]
    row = dict(row)
    row["orgName"] = strip_markup(row.get("orgName", ""))
    row["detailUrl"] = url
    row["statusName"] = STATUS_MAP.get(row.get("status"), str(row.get("status", "")))
    row["detail"] = {
        "managerType": first(org, "机构类型"),
        "registerAddress": first(org, "注册地址"),
        "officeAddress": first(org, "办公地址"),
        "registeredCapital": first(org, "注册资本(万元)(人民币)", "注册资本(万元)人民币"),
        "paidInCapital": first(org, "实缴资本(万元)(人民币)", "实缴资本(万元)人民币"),
        "productCount": detail.get("productCount", 0),
        "cancelReason": cancel.get("注销原因", ""),
        "cancelType": cancel.get("注销类型", row["statusName"]),
    }
    return row


def parse_money_10k(value: str) -> float:
    if not value:
        return 0.0
    match = re.search(r"[\d,.]+", value)
    if not match:
        return 0.0
    return float(match.group(0).replace(",", ""))


def team_summary(row: dict[str, Any]) -> str:
    detail = row.get("detail", {})
    parts: list[str] = []
    if detail.get("actualController"):
        parts.append(f"实控人：{detail['actualController']}")
    executives = detail.get("executives") or []
    if executives:
        exec_text = "、".join(f"{item['name']}（{item['role']}）" for item in executives[:4])
        parts.append(f"高管：{exec_text}")
    employee = detail.get("employeeCount")
    qualified = detail.get("qualifiedCount")
    if employee or qualified:
        parts.append(f"人员：全职{employee or '-'}人，基金从业{qualified or '-'}人")
    scale = detail.get("scaleRange")
    if scale:
        parts.append(f"管理规模区间：{scale}")
    work_history = detail.get("workHistory") or []
    background = background_summary(work_history)
    if background:
        parts.append(f"履历线索：{background}")
    shareholders = detail.get("shareholders") or []
    if shareholders:
        holder_text = "、".join(f"{item['name']} {item['ratio']}" for item in shareholders)
        parts.append(f"主要出资人：{holder_text}")
    return "；".join(parts) if parts else "协会公示页未披露可结构化提取的团队信息。"


def background_summary(work_history: list[dict[str, str]]) -> str:
    keywords = ("基金", "证券", "资管", "资产管理", "信托", "期货", "保险", "银行", "投资")
    companies: list[str] = []
    seen = set()
    for item in work_history:
        company = item.get("company", "")
        if company and any(keyword in company for keyword in keywords) and company not in seen:
            companies.append(company)
            seen.add(company)
    return "、".join(companies[:4])


def highlight_reason(row: dict[str, Any]) -> str:
    detail = row.get("detail", {})
    reasons: list[str] = []
    scale = detail.get("scaleRange", "")
    if scale and scale != "0-5亿元":
        reasons.append(f"管理规模区间{scale}")
    background = background_summary(detail.get("workHistory") or [])
    if background:
        reasons.append(f"核心人员曾任职于{background}")
    employee = detail.get("employeeCount")
    if employee and employee.isdigit() and int(employee) >= 10:
        reasons.append(f"全职员工{employee}人")
    return "；".join(reasons)


def is_notable_addition(row: dict[str, Any]) -> bool:
    return bool(row.get("highlightReason"))


def is_notable_cancelled(row: dict[str, Any], product_threshold: int, capital_threshold: float) -> bool:
    detail = row.get("detail", {})
    product_count = int(detail.get("productCount") or 0)
    registered = parse_money_10k(detail.get("registeredCapital", ""))
    paid = parse_money_10k(detail.get("paidInCapital", ""))
    return product_count >= product_threshold or registered >= capital_threshold or paid >= capital_threshold


def manager_id_from_url(url: str) -> str:
    match = re.search(r"(\d+)\.html", url or "")
    return match.group(1) if match else ""


def is_shaanxi_manager(row: dict[str, Any]) -> bool:
    return row.get("officeProvince") == SHAANXI or row.get("registerProvince") == SHAANXI


def is_shaanxi_cancelled(row: dict[str, Any]) -> bool:
    detail = row.get("detail", {})
    return "陕西" in (detail.get("officeAddress", "") + detail.get("registerAddress", ""))


def product_matches_manager(product: dict[str, Any], manager_ids: set[str], manager_names: set[str]) -> bool:
    if product.get("managerName") in manager_names:
        return True
    if manager_id_from_url(product.get("managerUrl", "")) in manager_ids:
        return True
    for item in product.get("managersInfo") or []:
        if str(item.get("managerId", "")) in manager_ids or item.get("managerName") in manager_names:
            return True
    return False


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "无。\n"
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        safe = [str(cell).replace("\n", " ").replace("|", "｜") for cell in row]
        lines.append("| " + " | ".join(safe) + " |")
    return "\n".join(lines) + "\n"


def manager_rows(rows: list[dict[str, Any]], include_team: bool = True) -> list[list[str]]:
    result = []
    for row in rows:
        item = [
            strip_markup(row.get("managerName", row.get("orgName", ""))),
            date_from_ms(row.get("registerDate") or row.get("orgSignDate")),
            row.get("registerNo", ""),
            row.get("regAdrAgg") or row.get("registerProvince", ""),
            row.get("officeAdrAgg") or row.get("officeProvince", ""),
        ]
        if include_team:
            item.append(row.get("teamSummary", ""))
        result.append(item)
    return result


def cancelled_rows(rows: list[dict[str, Any]]) -> list[list[str]]:
    result = []
    for row in rows:
        detail = row.get("detail", {})
        result.append([
            strip_markup(row.get("orgName", "")),
            date_from_ms(row.get("cancelDate")),
            detail.get("cancelType", row.get("statusName", "")),
            str(detail.get("productCount", 0)),
            detail.get("registeredCapital", ""),
            detail.get("paidInCapital", ""),
            detail.get("cancelReason", ""),
        ])
    return result


def product_rows(rows: list[dict[str, Any]]) -> list[list[str]]:
    result = []
    for row in rows:
        result.append([
            strip_markup(row.get("fundName", "")),
            strip_markup(row.get("managerName", "")),
            strip_markup(row.get("mandatorName", "")),
            date_from_ms(row.get("putOnRecordDate")),
            date_from_ms(row.get("establishDate")),
            row.get("fundNo", ""),
        ])
    return result


def generate_report(report: dict[str, Any]) -> str:
    report_date = report["reportDate"]
    start = report["startDate"]
    end = report["endDate"]
    national_add = report["nationalAdditions"]
    national_highlight_add = report["nationalHighlightAdditions"]
    national_notable_cancel = report["nationalNotableCancellations"]
    national_cancel_total = report["nationalCancellationTotal"]
    shaanxi_add = report["shaanxiAdditions"]
    shaanxi_cancel = report["shaanxiCancellations"]
    products = report["shaanxiOfficeProducts"]

    lines = [
        f"# 证券私募行业动态日报（{report_date}）",
        "",
        f"统计窗口：{start} 至 {end}",
        "",
        "数据源：中国证券投资基金业协会私募基金管理人分类查询公示、已注销私募基金管理人公示、私募基金公示。",
        "",
        "## 一、全国证券私募管理人新增及退出",
        "",
        f"- 新增证券私募管理人：{len(national_add)} 家；其中识别出重点团队/规模线索：{len(national_highlight_add)} 家",
        f"- 退出/注销证券私募管理人：{national_cancel_total} 家；其中按产品数量/资本代理指标列为重点：{len(national_notable_cancel)} 家",
        "",
        "### 重点新增管理人",
        "",
        md_table(["管理人", "登记日期", "登记编号", "注册地", "办公地", "团队背景"], manager_rows(national_highlight_add)),
        "",
        "### 重点退出/注销管理人",
        "",
        md_table(["管理人", "注销日期", "注销类型", "产品数量", "注册资本(万元)", "实缴资本(万元)", "注销原因"], cancelled_rows(national_notable_cancel)),
        "",
        "## 二、陕西证券私募动态（今年以来）",
        "",
        f"口径：注册地或办公地在陕西省的证券私募管理人；统计窗口：{report['shaanxiStartDate']} 至 {end}。",
        "",
        f"- 新增：{len(shaanxi_add)} 家",
        f"- 退出/注销：{len(shaanxi_cancel)} 家",
        "",
        "### 陕西新增管理人",
        "",
        md_table(["管理人", "登记日期", "登记编号", "注册地", "办公地", "团队背景"], manager_rows(shaanxi_add)),
        "",
        "### 陕西退出/注销管理人",
        "",
        md_table(["管理人", "注销日期", "注销类型", "产品数量", "注册资本(万元)", "实缴资本(万元)", "注销原因"], cancelled_rows(shaanxi_cancel)),
        "",
        "## 三、办公地在陕西的私募管理人新产品备案",
        "",
        f"办公地在陕西省的证券私募管理人基数：{report['shaanxiOfficeManagerCount']} 家；产品备案统计窗口：{report['shaanxiStartDate']} 至 {end}。",
        "",
        md_table(["备案产品名称", "管理人", "托管人", "备案日期", "成立日期", "基金编号"], product_rows(products)),
        "",
        "## 来源链接",
        "",
        f"- 私募基金管理人分类查询公示：{MANAGER_REFERER}",
        f"- 已注销私募基金管理人公示：{MANAGER_REFERER}",
        f"- 私募基金公示：{FUND_REFERER}",
        "",
        "说明：协会公示信息不构成对管理人投资能力、持续合规情况或基金财产安全的认可；本日报仅作公开信息整理，不构成投资建议。",
        "",
    ]
    if report.get("cancelDetailLimitHit"):
        lines.insert(
            9,
            f"- 提示：本次注销详情确认达到上限，已确认前 {report['cancelDetailChecked']} 条注销记录；如需完整长窗口结果，请提高 `--max-cancel-details` 后重跑。",
        )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    end_date = to_date(args.date)
    start_date = to_date(args.since or args.date)
    shaanxi_start_date = to_date(args.shaanxi_since or f"{end_date.year}-01-01")
    if start_date > end_date:
        raise SystemExit("--since cannot be later than --date")
    if shaanxi_start_date > end_date:
        raise SystemExit("--shaanxi-since cannot be later than --date")

    start = start_date.isoformat()
    end = end_date.isoformat()
    shaanxi_start = shaanxi_start_date.isoformat()

    additions = fetch_manager_additions(start, end)
    enriched_additions = []
    for idx, row in enumerate(additions, 1):
        print(f"Enriching new manager {idx}/{len(additions)}: {row.get('managerName', '')}", file=sys.stderr)
        time.sleep(args.sleep)
        enriched_additions.append(enrich_manager(row))

    cancelled = fetch_cancelled_in_window(start_date, end_date, args.max_cancel_pages)
    enriched_cancelled = []
    cancel_detail_limit_hit = len(cancelled) > args.max_cancel_details
    cancelled_for_detail = cancelled[: args.max_cancel_details]
    for idx, row in enumerate(cancelled_for_detail, 1):
        if idx == 1 or idx % 25 == 0 or idx == len(cancelled_for_detail):
            print(f"Checking cancelled manager detail {idx}/{len(cancelled_for_detail)}", file=sys.stderr)
        time.sleep(args.sleep)
        detail = enrich_cancelled(row)
        if detail["detail"].get("managerType") == SECURITY_MANAGER_TYPE:
            enriched_cancelled.append(detail)

    shaanxi_managers = fetch_shaanxi_security_managers()
    manager_ids = {manager_id_from_url(item.get("url", "")) for item in shaanxi_managers}
    manager_ids.discard("")
    manager_names = {item.get("managerName", "") for item in shaanxi_managers if item.get("managerName")}

    products = fetch_security_products(start, end, args.max_product_pages)
    shaanxi_products_all = fetch_security_products(shaanxi_start, end, args.max_product_pages)
    shaanxi_products = [row for row in shaanxi_products_all if product_matches_manager(row, manager_ids, manager_names)]

    shaanxi_additions = fetch_manager_additions(shaanxi_start, end)
    enriched_shaanxi_additions = []
    shaanxi_addition_candidates = [row for row in shaanxi_additions if is_shaanxi_manager(row)]
    for idx, row in enumerate(shaanxi_addition_candidates, 1):
        print(f"Enriching Shaanxi new manager {idx}/{len(shaanxi_addition_candidates)}: {row.get('managerName', '')}", file=sys.stderr)
        time.sleep(args.sleep)
        enriched_shaanxi_additions.append(enrich_manager(row))

    shaanxi_keywords = ["陕西", "西安", "咸阳", "宝鸡", "铜川", "渭南", "汉中", "安康", "商洛", "榆林", "延安", "杨凌"]
    shaanxi_cancel_candidates = fetch_cancelled_by_keywords(shaanxi_start_date, end_date, shaanxi_keywords, max_pages=20)
    enriched_shaanxi_cancelled = []
    for idx, row in enumerate(shaanxi_cancel_candidates, 1):
        print(f"Checking Shaanxi cancelled manager {idx}/{len(shaanxi_cancel_candidates)}", file=sys.stderr)
        time.sleep(args.sleep)
        detail = enrich_cancelled(row)
        if detail["detail"].get("managerType") == SECURITY_MANAGER_TYPE and is_shaanxi_cancelled(detail):
            enriched_shaanxi_cancelled.append(detail)

    national_highlight_additions = [row for row in enriched_additions if is_notable_addition(row)]
    national_notable_cancelled = [
        row for row in enriched_cancelled
        if is_notable_cancelled(row, args.notable_product_threshold, args.notable_capital_threshold)
    ]

    report = {
        "reportDate": args.date,
        "startDate": start,
        "endDate": end,
        "shaanxiStartDate": shaanxi_start,
        "nationalAdditions": enriched_additions,
        "nationalHighlightAdditions": national_highlight_additions,
        "nationalCancellations": enriched_cancelled,
        "nationalCancellationTotal": len(enriched_cancelled),
        "nationalNotableCancellations": national_notable_cancelled,
        "shaanxiAdditions": enriched_shaanxi_additions,
        "shaanxiCancellations": enriched_shaanxi_cancelled,
        "shaanxiOfficeManagerCount": len(shaanxi_managers),
        "shaanxiOfficeProducts": shaanxi_products,
        "cancelDetailChecked": len(cancelled_for_detail),
        "cancelDetailTotalInWindow": len(cancelled),
        "cancelDetailLimitHit": cancel_detail_limit_hit,
        "raw": {
            "shaanxiOfficeManagers": shaanxi_managers,
            "allSecurityProductsInWindow": products,
            "allSecurityProductsInShaanxiWindow": shaanxi_products_all,
        },
    }

    output_dir = Path(args.output_dir)
    data_dir = Path(args.data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = output_dir / f"security-private-fund-daily-{args.date}.md"
    data_path = data_dir / f"security-private-fund-daily-{args.date}.json"
    markdown_path.write_text(generate_report(report), encoding="utf-8")
    data_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {markdown_path}")
    print(f"Wrote {data_path}")
    print(
        "Counts: "
        f"national_add={len(report['nationalAdditions'])}, "
        f"national_highlight_add={len(report['nationalHighlightAdditions'])}, "
        f"national_cancel={report['nationalCancellationTotal']}, "
        f"national_notable_cancel={len(report['nationalNotableCancellations'])}, "
        f"shaanxi_add={len(report['shaanxiAdditions'])}, "
        f"shaanxi_cancel={len(report['shaanxiCancellations'])}, "
        f"shaanxi_products={len(report['shaanxiOfficeProducts'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
