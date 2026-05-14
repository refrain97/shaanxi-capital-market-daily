#!/usr/bin/env python3
"""Fetch CNINFO announcements for the Shaanxi listed-company universe.

The v1 daily workflow must query CNINFO company-by-company. Full-market
pagination can miss Shaanxi announcements on busy disclosure days.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


CNINFO_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
REFERER = "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="逐公司抓取陕西上市公司 CNINFO 公告，避免全市场分页漏报。"
    )
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--companies",
        default="data/shaanxi-companies-cninfo-2026-03-31.json",
        help="陕西公司池 JSON，需包含 code/name/orgId/market 字段。",
    )
    parser.add_argument(
        "--output",
        help="输出 JSON 路径；默认 data/cninfo-shaanxi-announcements-START_END.json",
    )
    parser.add_argument("--page-size", type=int, default=30)
    parser.add_argument("--sleep", type=float, default=0.08, help="公司之间请求间隔秒数。")
    parser.add_argument("--timeout", type=float, default=20)
    return parser.parse_args()


def load_companies(path: Path) -> list[dict[str, Any]]:
    companies = json.loads(path.read_text(encoding="utf-8"))
    required = {"code", "name", "orgId"}
    for idx, company in enumerate(companies):
        missing = required - set(company)
        if missing:
            raise ValueError(f"company #{idx} missing fields: {sorted(missing)}")
    return companies


def post_cninfo(params: dict[str, str], timeout: float) -> dict[str, Any]:
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        CNINFO_QUERY_URL,
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": REFERER,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_company(
    company: dict[str, Any],
    start_date: str,
    end_date: str,
    page_size: int,
    timeout: float,
) -> list[dict[str, Any]]:
    page = 1
    results: list[dict[str, Any]] = []
    stock = f"{company['code']},{company['orgId']}"

    while True:
        params = {
            "pageNum": str(page),
            "pageSize": str(page_size),
            "column": "",
            "tabName": "fulltext",
            "plate": "",
            "stock": stock,
            "searchkey": "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": f"{start_date}~{end_date}",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        payload = post_cninfo(params, timeout)
        announcements = payload.get("announcements") or []
        total = int(payload.get("totalRecordNum") or 0)

        for announcement in announcements:
            announcement["_matchedCompanyCode"] = company["code"]
            announcement["_matchedCompanyName"] = company["name"]
            announcement["_companyMarket"] = company.get("market")
            announcement["_queryStock"] = stock
            results.append(announcement)

        if len(announcements) < page_size or page * page_size >= total:
            break
        page += 1
        time.sleep(0.05)

    return results


def dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, Any, Any]] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (item.get("announcementId"), item.get("secCode"), item.get("announcementTitle"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def local_day(timestamp_ms: int | None) -> str:
    if not timestamp_ms:
        return "unknown"
    return time.strftime("%Y-%m-%d", time.localtime(timestamp_ms / 1000))


def main() -> int:
    args = parse_args()
    base_dir = Path.cwd()
    companies_path = Path(args.companies)
    if not companies_path.is_absolute():
        companies_path = base_dir / companies_path

    output_path = Path(args.output) if args.output else Path(
        f"data/cninfo-shaanxi-announcements-{args.start_date}_{args.end_date}.json"
    )
    if not output_path.is_absolute():
        output_path = base_dir / output_path

    # Fail early on malformed dates.
    datetime.strptime(args.start_date, "%Y-%m-%d")
    datetime.strptime(args.end_date, "%Y-%m-%d")

    companies = load_companies(companies_path)
    all_items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for index, company in enumerate(companies, start=1):
        try:
            all_items.extend(
                fetch_company(
                    company,
                    args.start_date,
                    args.end_date,
                    args.page_size,
                    args.timeout,
                )
            )
        except Exception as exc:  # noqa: BLE001 - record and continue for daily work.
            errors.append(
                {
                    "code": str(company.get("code", "")),
                    "name": str(company.get("name", "")),
                    "error": repr(exc),
                }
            )
        if index % 20 == 0:
            print(f"queried {index}/{len(companies)} companies, raw_items={len(all_items)}", file=sys.stderr)
        time.sleep(args.sleep)

    items = dedupe(all_items)
    items.sort(
        key=lambda item: (
            item.get("announcementTime") or 0,
            item.get("secCode") or "",
            item.get("announcementId") or "",
        ),
        reverse=True,
    )

    date_counter = Counter(local_day(item.get("announcementTime")) for item in items)
    summary = {
        "startDate": args.start_date,
        "endDate": args.end_date,
        "companyUniverseCount": len(companies),
        "announcementCount": len(items),
        "coveredCompanyCount": len({item.get("secCode") for item in items}),
        "dateDistribution": dict(sorted(date_counter.items())),
        "errorCount": len(errors),
        "errors": errors,
        "queryMethod": "company_by_company_cninfo_stock_code_orgId",
        "warning": (
            "If announcementCount is 0, do not publish a no-announcement report "
            "until the SOP second-pass verification is complete."
        ),
    }
    payload = {f"{args.start_date}~{args.end_date}": items, "_summary": summary}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
