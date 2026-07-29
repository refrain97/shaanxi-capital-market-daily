#!/usr/bin/env python3
"""Scan V2-owned official MA inputs and append verified project milestones."""
from __future__ import annotations

import argparse
import json
import re
import ssl
import time
from copy import deepcopy
from datetime import date, datetime
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from scanner_common import (
    extract_ma_facts,
    infer_ma_stage,
    ma_keyword_match,
    merge_ma_project,
    normalize_title,
    sha256_file,
    sha256_json,
    stable_project_id,
    write_json,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "v2/config/ma-sources.json"
CONTRACT_PATH = ROOT / "v2/config/source-contract.json"
STORE_PATH = ROOT / "v2/data/source/ma/events-2026.json"
BASE_DIR = ROOT / "v2/data/source/ma"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch(url: str, timeout: int, retries: int = 3) -> tuple[int, str, bytes, dict]:
    """Fetch an official MA page with bounded retries for transient TLS EOFs."""
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = Request(url, headers={"User-Agent": "Shaanxi-Capital-Market-V2-MA/2.0"})
        try:
            with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
                raw = response.read(3_000_000)
                return response.status, response.geturl(), raw, dict(response.headers.items())
        except (HTTPError, URLError, TimeoutError, ssl.SSLError) as error:
            last_error = error
            if attempt == retries:
                break
            time.sleep(1.5 * attempt)
    assert last_error is not None
    raise last_error


def decode(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def visible_text(raw: bytes) -> str:
    text = decode(raw)
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.I | re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def iso_date(value: object) -> str:
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(value / 1000).date().isoformat()
    match = re.search(r"20\d{2}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else ""


def probe(url: str, timeout: int) -> dict:
    started = time.monotonic()
    try:
        request = Request(url, headers={"User-Agent": "Shaanxi-Capital-Market-V2-MA/1.0"})
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            raw = response.read(200_000)
            return {
                "httpStatus": response.status,
                "finalUrl": response.geturl(),
                "contentBytes": len(raw),
                "elapsedMs": round((time.monotonic() - started) * 1000),
            }
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        return {
            "error": f"{type(error).__name__}: {error}",
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }


def _ma_record(
    source: dict,
    *,
    record_id: str,
    title: str,
    published: str,
    source_url: str,
    body: str,
    company: str = "",
    category: str = "",
    match_text: str | None = None,
) -> dict:
    audit = ma_keyword_match(
        match_text if match_text is not None else f"{title} {body}",
        {"eventKeywords": MA_KEYWORDS},
    )
    return {
        "recordId": f"{source['sourceId']}:{record_id}",
        "announcementId": record_id,
        "company": company,
        "securityCode": "",
        "universeTier": "nonlisted_official",
        "title": title,
        "publishedAt": published,
        "sourceName": source["name"],
        "sourceUrl": source_url,
        "stage": infer_ma_stage(f"{title} {body}"),
        "keywordAudit": audit,
        "relatedParties": [company] if company else [],
        "shaanxiRelation": "陕西官方产权/国资/企业官网来源",
        "facts": extract_ma_facts(f"{title} {body}"),
        "industry": category,
        "discoveredCategories": [category] if category else [],
        "officialDocumentRetrieved": bool(body),
        "officialBodyExcerpt": body[:4000],
    }


MA_KEYWORDS = [
    "收购", "出售", "股权转让", "控制权变更", "增资", "重大资产重组",
    "发行股份购买资产", "购买资产", "交割", "完成", "工商变更", "终止",
]

XBCQ_CAPITAL_CATEGORY_SIGNALS = {
    "企业增资正式披露": "增资",
    "企业增资预披露": "增资",
    "股权转让": "股权转让",
}
XBCQ_SINGLE_ASSET_CATEGORY_PATTERN = re.compile(
    r"土地资产|资产综合|机械设备|机动车|存货|在建工程|其他资产|房屋资产"
)
XBCQ_SINGLE_ASSET_TITLE_PATTERN = re.compile(
    r"车辆|轿车|客车|货车|机动车|报废(?:资产|物资)|废旧(?:物资|设备)|"
    r"土地使用权|单宗土地|房产|房屋|不动产|机器设备|机械设备|"
    r"设备一批|租赁权|经营权租赁|一批存货"
)
XBCQ_EXPLICIT_CAPITAL_PATTERN = re.compile(
    r"股权|股份(?:转让|收购|出售|受让)|控制权|增资|重大资产重组|发行股份购买资产|"
    r"(?:企业|公司|整体)产权|经营性资产|资产组|整项业务"
)


def xbcq_scope_audit(title: str, category: str, audit: dict) -> dict:
    """Keep capital-market transactions and reject ordinary physical disposals."""
    result = deepcopy(audit)
    explicit_capital = bool(XBCQ_EXPLICIT_CAPITAL_PATTERN.search(title or ""))
    single_asset = bool(
        XBCQ_SINGLE_ASSET_TITLE_PATTERN.search(title or "")
        or XBCQ_SINGLE_ASSET_CATEGORY_PATTERN.search(category or "")
    )
    result.update(
        {
            "scope": "xbcq_capital_market_ma",
            "explicitCapitalSignal": explicit_capital,
            "singlePhysicalAssetSignal": single_asset,
        }
    )
    if single_asset and not explicit_capital:
        result["matched"] = False
        result["reason"] = "excluded_single_physical_asset_disposal"
    return result


def _discovery_evidence(row: dict) -> list[dict]:
    evidence = row.get("discoveryEvidence")
    if isinstance(evidence, list):
        return deepcopy(evidence)
    item = row.get("listAndDetailEvidence")
    if isinstance(item, dict):
        return [
            {
                "category": row.get("industry") or "",
                **deepcopy(item),
            }
        ]
    return []


def ma_record_identity(row: dict) -> str:
    return sorted(ma_record_aliases(row))[0]


def ma_record_aliases(row: dict) -> set[str]:
    aliases = set()
    record_id = str(row.get("recordId") or "").strip()
    if record_id:
        aliases.add(f"id:{record_id}")
    source_url = str(row.get("sourceUrl") or "").strip()
    title = normalize_title(str(row.get("title") or ""))
    if source_url and title:
        aliases.add(f"url-title:{source_url}|{title}")
    if not aliases:
        aliases.add(f"title:{title}")
    return aliases


def dedupe_ma_records(rows: list[dict]) -> list[dict]:
    """Merge repeated category discoveries while preserving their evidence."""
    merged: dict[str, dict] = {}
    aliases_to_key: dict[str, str] = {}
    for row in rows:
        aliases = ma_record_aliases(row)
        key = next(
            (
                aliases_to_key[alias]
                for alias in sorted(aliases)
                if alias in aliases_to_key
            ),
            sorted(aliases)[0],
        )
        if key not in merged:
            merged[key] = deepcopy(row)
            merged[key]["discoveredCategories"] = sorted(
                {
                    *row.get("discoveredCategories", []),
                    *([row.get("industry")] if row.get("industry") else []),
                }
            )
            merged[key]["discoveryEvidence"] = _discovery_evidence(row)
            for alias in aliases:
                aliases_to_key[alias] = key
            continue
        current = merged[key]
        current["discoveredCategories"] = sorted(
            {
                *current.get("discoveredCategories", []),
                *row.get("discoveredCategories", []),
                *([row.get("industry")] if row.get("industry") else []),
            }
        )
        evidence_by_hash = {
            sha256_json(item): item
            for item in [
                *current.get("discoveryEvidence", []),
                *_discovery_evidence(row),
            ]
        }
        current["discoveryEvidence"] = [
            evidence_by_hash[key] for key in sorted(evidence_by_hash)
        ]
        for alias in aliases:
            aliases_to_key[alias] = key
    return sorted(
        merged.values(),
        key=lambda row: (
            str(row.get("publishedAt") or ""),
            ma_record_identity(row),
        ),
        reverse=True,
    )


def scan_date_flags(
    store: dict,
    imported_project_ids: list[str],
    pending_candidates: list[dict],
    scan_day: str,
) -> tuple[bool, bool]:
    candidate_on_date = any(
        row.get("publishedAt") == scan_day for row in pending_candidates
    )
    imported = set(imported_project_ids)
    event_on_date = bool(imported) and any(
        project.get("maProjectId") in imported
        and any(
            source.get("publishedAt") == scan_day
            for source in project.get("sourceRecords", [])
        )
        for project in store.get("projects", [])
    )
    return candidate_on_date, event_on_date


def _xbcq_record(
    source: dict,
    *,
    record_id: str,
    title: str,
    published: str,
    source_url: str,
    body: str,
    company: str,
    category: str,
) -> dict:
    category_signal = XBCQ_CAPITAL_CATEGORY_SIGNALS.get(category, "")
    normalized = _ma_record(
        source,
        record_id=record_id,
        title=title,
        published=published,
        source_url=source_url,
        body=body,
        company=company,
        category=category,
        match_text=f"{title} {category_signal}".strip(),
    )
    normalized["keywordAudit"] = xbcq_scope_audit(
        title, category, normalized["keywordAudit"]
    )
    return normalized


def _ma_exclusion(row: dict) -> dict:
    return {
        "recordId": row.get("recordId") or "",
        "title": row.get("title") or "",
        "sourceUrl": row.get("sourceUrl") or "",
        "reason": row.get("keywordAudit", {}).get("reason")
        or row.get("reason")
        or "no_substantive_ma_signal",
        "industry": row.get("industry") or "",
        "discoveredCategories": row.get("discoveredCategories", []),
        "listAndDetailEvidence": row.get("listAndDetailEvidence", {}),
    }


def scan_xbcq(source: dict, scan_day: str, timeout: int) -> tuple[dict, list[dict], list[dict]]:
    records = []
    exclusions = []
    pages = []
    all_categories_complete = True
    for category in source["categories"]:
        page = 1
        category_complete = False
        while page <= 30:
            params = {
                "current": page,
                "page": page,
                "size": 100,
                "cateid": category["cateid"],
                "gpksrqdesc": 1,
                **category.get("extraParams", {}),
            }
            endpoint = category.get("endpoint") or source["listEndpoint"]
            request_url = f"{endpoint}?{urlencode(params)}"
            started = time.monotonic()
            status, final_url, raw, _ = fetch(request_url, timeout)
            payload = json.loads(decode(raw))
            rows = payload.get("records") or []
            row_dates = [
                iso_date(row.get("gpksrq") or row.get("cjsj") or row.get("bgsj"))
                for row in rows
            ]
            pages.append(
                {
                    "category": category["name"],
                    "cateid": category["cateid"],
                    "page": page,
                    "requestUrl": final_url,
                    "requestParams": params,
                    "httpStatus": status,
                    "reportedTotal": int(payload.get("total") or 0),
                    "rowCount": len(rows),
                    "newestDate": max(row_dates or [""]),
                    "oldestDate": min(row_dates or [""]),
                    "responseSha256": sha256_json(payload),
                    "elapsedMs": round((time.monotonic() - started) * 1000),
                }
            )
            for row in rows:
                published = iso_date(row.get("gpksrq") or row.get("cjsj") or row.get("bgsj"))
                if published != scan_day:
                    continue
                row_id = str(row.get("id") or row.get("xmid") or "")
                detail_url = source["detailEndpoint"].format(id=row_id)
                d_status, d_final, d_raw, _ = fetch(detail_url, timeout)
                detail = json.loads(decode(d_raw))
                title = str(row.get("jymc") or row.get("xmmc") or row.get("jjmc") or "").strip()
                detail_text = visible_text(
                    json.dumps(detail, ensure_ascii=False).encode("utf-8")
                )
                evidence = {
                    "listRecordId": row_id,
                    "detailUrl": d_final,
                    "detailHttpStatus": d_status,
                    "detailSha256": sha256_json(detail),
                }
                normalized = _xbcq_record(
                    source,
                    record_id=row_id,
                    title=title,
                    published=published,
                    source_url=(
                        f"https://www.xbcq.com/cms/view/catalog/502421399564357?id={row_id}"
                    ),
                    body=detail_text,
                    company=title,
                    category=category["name"],
                )
                normalized["listAndDetailEvidence"] = evidence
                if normalized["keywordAudit"]["matched"]:
                    records.append(normalized)
                else:
                    exclusions.append(_ma_exclusion(normalized))
            if not rows or min(row_dates or ["9999-12-31"]) < scan_day:
                category_complete = True
                break
            page += 1
        all_categories_complete &= category_complete
    for result_list in source.get("resultLists", []):
        if result_list["adapter"] == "xbcq_result_api":
            page = 1
            result_complete = False
            while page <= 30:
                params = {"page": page, "size": 100, "cateid": result_list["cateid"]}
                request_url = f"{result_list['url']}?{urlencode(params)}"
                status, final_url, raw, _ = fetch(request_url, timeout)
                payload = json.loads(decode(raw))
                rows = payload.get("records") or []
                row_dates = [
                    iso_date(
                        (row.get("ttransactionTicketEntity") or {}).get("ffsj")
                        or row.get("createdate")
                    )
                    for row in rows
                ]
                pages.append(
                    {
                        "category": result_list["name"],
                        "page": page,
                        "requestUrl": final_url,
                        "requestParams": params,
                        "httpStatus": status,
                        "reportedTotal": int(payload.get("total") or 0),
                        "rowCount": len(rows),
                        "newestDate": max(row_dates or [""]),
                        "oldestDate": min(row_dates or [""]),
                        "responseSha256": sha256_json(payload),
                    }
                )
                for row in rows:
                    published = iso_date(
                        (row.get("ttransactionTicketEntity") or {}).get("ffsj")
                        or row.get("createdate")
                    )
                    if published != scan_day:
                        continue
                    row_id = str(row.get("id") or "")
                    title = f"{row.get('jjmc') or ''}成交公告".strip()
                    body = visible_text(json.dumps(row, ensure_ascii=False).encode())
                    normalized = _xbcq_record(
                        source,
                        record_id=f"result-{row_id}",
                        title=title,
                        published=published,
                        source_url=final_url,
                        body=body,
                        company=str(row.get("jjmc") or ""),
                        category=result_list["name"],
                    )
                    normalized["listAndDetailEvidence"] = {
                        "officialApiRecordSha256": sha256_json(row),
                        "detailMode": "official_result_api_record",
                    }
                    if normalized["keywordAudit"]["matched"]:
                        records.append(normalized)
                    else:
                        exclusions.append(_ma_exclusion(normalized))
                if not rows or min(row_dates or ["9999-12-31"]) < scan_day:
                    result_complete = True
                    break
                page += 1
            all_categories_complete &= result_complete
        elif result_list["adapter"] == "xbcq_termination_html":
            status, final_url, raw, _ = fetch(result_list["url"], timeout)
            html = decode(raw)
            termination_rows = []
            for href, raw_title, published in re.findall(
                r'<h1[^>]*>[\s\S]*?<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>'
                r"[\s\S]*?<h2[^>]*>\s*(20\d{2}-\d{2}-\d{2})\s*</h2>",
                html,
                re.I,
            ):
                termination_rows.append(
                    {
                        "sourceUrl": urljoin(final_url, href),
                        "title": visible_text(raw_title.encode()),
                        "publishedAt": published,
                    }
                )
            row_dates = [row["publishedAt"] for row in termination_rows]
            pages.append(
                {
                    "category": result_list["name"],
                    "page": 1,
                    "requestUrl": final_url,
                    "httpStatus": status,
                    "rowCount": len(termination_rows),
                    "newestDate": max(row_dates or [""]),
                    "oldestDate": min(row_dates or [""]),
                    "responseSha256": sha256_json(html),
                }
            )
            for row in termination_rows:
                if row["publishedAt"] != scan_day:
                    continue
                d_status, d_final, d_raw, _ = fetch(row["sourceUrl"], timeout)
                body = visible_text(d_raw)
                normalized = _xbcq_record(
                    source,
                    record_id=f"termination-{sha256_json(d_final)[:20]}",
                    title=row["title"],
                    published=row["publishedAt"],
                    source_url=d_final,
                    body=body,
                    company=row["title"],
                    category=result_list["name"],
                )
                normalized["listAndDetailEvidence"] = {
                    "detailHttpStatus": d_status,
                    "detailSha256": sha256_json(body),
                }
                if normalized["keywordAudit"]["matched"]:
                    records.append(normalized)
                else:
                    exclusions.append(_ma_exclusion(normalized))
            all_categories_complete &= bool(termination_rows) and min(row_dates) < scan_day
    records = dedupe_ma_records(records)
    matched_keys = {
        alias for row in records for alias in ma_record_aliases(row)
    }
    exclusions = dedupe_ma_records(
        [
            row
            for row in exclusions
            if ma_record_aliases(row).isdisjoint(matched_keys)
        ]
    )
    return (
        {
            "sourceId": source["sourceId"],
            "name": source["name"],
            "adapter": source["adapter"],
            "status": "completed" if all_categories_complete else "failed",
            "searchCompleted": all_categories_complete,
            "coverageMode": "same_day_category_paginated_list_and_detail_api",
            "categoryCount": len(source["categories"]),
            "resultListCount": len(source.get("resultLists", [])),
            "pageCount": len(pages),
            "detailVerifiedCount": len(records) + len(exclusions),
            "recordCount": len(records),
            "pages": pages,
            **(
                {}
                if all_categories_complete
                else {"failureReason": "产权交易栏目未全部跨越扫描日边界"}
            ),
        },
        records,
        exclusions,
    )


def parse_sasac_rows(base_url: str, html: str) -> list[dict]:
    rows = []
    pattern = re.compile(
        r'<a[^>]+href="([^"]+)"[^>]*>[\s\S]*?'
        r'<div[^>]+class="text[^"]*"[^>]*>([\s\S]*?)</div>[\s\S]*?'
        r'<div[^>]+class="time[^"]*"[^>]*>\s*(20\d{2}-\d{2}-\d{2})\s*</div>',
        re.I,
    )
    for href, raw_title, published in pattern.findall(html):
        title = visible_text(raw_title.encode())
        rows.append(
            {
                "title": title,
                "publishedAt": published,
                "sourceUrl": urljoin(base_url, href),
            }
        )
    return rows


def scan_sasac(source: dict, scan_day: str, timeout: int) -> tuple[dict, list[dict], list[dict]]:
    records = []
    exclusions = []
    pages = []
    sections_complete = True
    for entry in source["entryPoints"]:
        page = 0
        section_complete = False
        while page < 20:
            page_url = entry["url"] if page == 0 else urljoin(entry["url"], f"index_{page}.html")
            started = time.monotonic()
            status, final_url, raw, _ = fetch(page_url, timeout)
            html = decode(raw)
            rows = parse_sasac_rows(final_url, html)
            row_dates = [row["publishedAt"] for row in rows]
            pages.append(
                {
                    "section": entry["name"],
                    "page": page + 1,
                    "requestUrl": final_url,
                    "httpStatus": status,
                    "rowCount": len(rows),
                    "newestDate": max(row_dates or [""]),
                    "oldestDate": min(row_dates or [""]),
                    "responseSha256": sha256_json(html),
                    "elapsedMs": round((time.monotonic() - started) * 1000),
                }
            )
            for row in rows:
                if row["publishedAt"] != scan_day:
                    continue
                d_status, d_final, d_raw, _ = fetch(row["sourceUrl"], timeout)
                body = visible_text(d_raw)
                normalized = _ma_record(
                    source,
                    record_id=sha256_json(d_final)[:20],
                    title=row["title"],
                    published=row["publishedAt"],
                    source_url=d_final,
                    body=body,
                    company=row["title"].split("】", 1)[0].lstrip("【"),
                    category=entry["name"],
                )
                normalized["listAndDetailEvidence"] = {
                    "detailHttpStatus": d_status,
                    "detailSha256": sha256_json(body),
                }
                if normalized["keywordAudit"]["matched"]:
                    records.append(normalized)
                else:
                    exclusions.append(_ma_exclusion(normalized))
            if not rows or min(row_dates or ["9999-12-31"]) < scan_day:
                section_complete = True
                break
            page += 1
        sections_complete &= section_complete
    return (
        {
            "sourceId": source["sourceId"],
            "name": source["name"],
            "adapter": source["adapter"],
            "status": "completed" if sections_complete else "failed",
            "searchCompleted": sections_complete,
            "coverageMode": "same_day_section_paginated_list_and_official_detail",
            "sectionCount": len(source["entryPoints"]),
            "pageCount": len(pages),
            "detailVerifiedCount": len(records) + len(exclusions),
            "recordCount": len(records),
            "pages": pages,
            **(
                {}
                if sections_complete
                else {"failureReason": "国资栏目未全部跨越扫描日边界"}
            ),
        },
        dedupe_ma_records(records),
        dedupe_ma_records(exclusions),
    )


def scan_issuer_registry(
    source: dict, registry: dict, scan_day: str, timeout: int
) -> tuple[dict, list[dict], list[dict]]:
    records = []
    exclusions = []
    site_runs = []
    for site in registry["configuredSites"]:
        page_runs = []
        site_ok = True
        for list_url in site["listUrls"]:
            try:
                started = time.monotonic()
                status, final_url, raw, _ = fetch(list_url, timeout)
                html = decode(raw)
                page_runs.append(
                    {
                        "listUrl": final_url,
                        "httpStatus": status,
                        "contentBytes": len(raw),
                        "responseSha256": sha256_json(html),
                        "elapsedMs": round((time.monotonic() - started) * 1000),
                    }
                )
                for href, raw_title in re.findall(
                    r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>', html, re.I
                ):
                    title = visible_text(raw_title.encode())
                    if not title or not any(term in title for term in MA_KEYWORDS):
                        continue
                    context = html[max(0, html.find(raw_title) - 180): html.find(raw_title) + len(raw_title) + 180]
                    published = iso_date(context)
                    if published != scan_day:
                        continue
                    detail_url = urljoin(final_url, href)
                    d_status, d_final, d_raw, _ = fetch(detail_url, timeout)
                    body = visible_text(d_raw)
                    normalized = _ma_record(
                        source,
                        record_id=sha256_json(d_final)[:20],
                        title=title,
                        published=published,
                        source_url=d_final,
                        body=body,
                        company=site["entityName"],
                        category="企业官网",
                    )
                    normalized["listAndDetailEvidence"] = {
                        "detailHttpStatus": d_status,
                        "detailSha256": sha256_json(body),
                    }
                    if normalized["keywordAudit"]["matched"]:
                        records.append(normalized)
                    else:
                        exclusions.append(_ma_exclusion(normalized))
            except Exception as error:
                site_ok = False
                page_runs.append(
                    {
                        "listUrl": list_url,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
        site_runs.append(
            {
                "entityId": site["entityId"],
                "entityName": site["entityName"],
                "status": "completed" if site_ok else "external_blocked",
                "listPages": page_runs,
            }
        )
    complete = bool(site_runs) and all(row["status"] == "completed" for row in site_runs)
    return (
        {
            "sourceId": source["sourceId"],
            "name": source["name"],
            "adapter": source["adapter"],
            "status": "completed" if complete else "external_blocked",
            "searchCompleted": complete,
            "coverageMode": "configured_official_site_registry_100_percent",
            "configuredSiteCount": len(registry["configuredSites"]),
            "scannedSiteCount": sum(row["status"] == "completed" for row in site_runs),
            "coverageBacklogCount": len(registry.get("coverageBacklog", [])),
            "coverageBacklog": registry.get("coverageBacklog", []),
            "siteRuns": site_runs,
            "recordCount": len(records),
            **(
                {}
                if complete
                else {"failureReason": "正式注册表内企业官网未达到100%扫描"}
            ),
        },
        dedupe_ma_records(records),
        dedupe_ma_records(exclusions),
    )


def official_pdf_check(url: str, timeout: int) -> dict:
    try:
        request = Request(url, headers={"User-Agent": "Shaanxi-Capital-Market-V2-MA/1.0"})
        with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
            raw = response.read(2_000_000)
            content_type = response.headers.get("Content-Type", "")
            verified = response.status == 200 and len(raw) > 3_000 and (
                raw.startswith(b"%PDF") or "pdf" in content_type.lower()
            )
            return {
                "httpStatus": response.status,
                "contentType": content_type,
                "contentBytes": len(raw),
                "officialDocumentRetrieved": verified,
            }
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        return {
            "officialDocumentRetrieved": False,
            "error": f"{type(error).__name__}: {error}",
        }


def daily_rows(payload: dict) -> list[dict]:
    return [
        row
        for key, rows in payload.items()
        if not key.startswith("_") and isinstance(rows, list)
        for row in rows
        if isinstance(row, dict)
    ]


def listed_source_runs(config: dict, daily: dict, daily_path: Path) -> list[dict]:
    summary = daily.get("_summary", {})
    return [
        {
            "sourceId": "ma-listed-cninfo",
            "name": "巨潮资讯上市公司逐主体公告",
            "adapter": "v2_cninfo_daily",
            "status": (
                "completed"
                if summary.get("companyUniverseCount") == 110 and not summary.get("errors")
                else "failed"
            ),
            "searchCompleted": summary.get("companyUniverseCount") == 110 and not summary.get("errors"),
            "coverage": {
                "universeCount": summary.get("companyUniverseCount", 0),
                "announcementCount": summary.get("announcementCount", 0),
                "dateRange": [summary.get("startDate", ""), summary.get("endDate", "")],
                "inputPath": daily_path.relative_to(ROOT).as_posix(),
            },
            "failureReason": (
                ""
                if summary.get("companyUniverseCount") == 110 and not summary.get("errors")
                else "上市观察池逐主体检索不完整或存在错误"
            ),
        },
        {
            "sourceId": "ma-listed-hkex",
            "name": "香港交易所披露易逐主体复核",
            "adapter": "v2_hkex_daily_receipt",
            "status": (
                "completed"
                if summary.get("hkexOfficialReview", {}).get("status") == "completed"
                and summary.get("hkexOfficialReview", {}).get("companyCount") == 14
                else "failed"
            ),
            "searchCompleted": (
                summary.get("hkexOfficialReview", {}).get("status") == "completed"
                and summary.get("hkexOfficialReview", {}).get("companyCount") == 14
            ),
            "coverage": summary.get("hkexOfficialReview", {}),
            "failureReason": (
                ""
                if summary.get("hkexOfficialReview", {}).get("status") == "completed"
                and summary.get("hkexOfficialReview", {}).get("companyCount") == 14
                else "L2港股逐主体复核不完整"
            ),
        },
    ]


def find_existing(store: dict, candidate: dict) -> dict | None:
    company = candidate.get("company") or ""
    for project in store.get("projects", []):
        if any(
            source.get("url") == candidate["sourceUrl"]
            for source in project.get("sourceRecords", [])
        ):
            return project
        parties = f"{project.get('title', '')} {project.get('partiesText', '')}"
        if company and company in parties:
            left = set(re.findall(r"[\u4e00-\u9fff]{2,}", normalize_title(project.get("title") or "")))
            right = set(re.findall(r"[\u4e00-\u9fff]{2,}", normalize_title(candidate["title"])))
            if left & right:
                return project
    return None


def merge_verified(store: dict, candidates: list[dict]) -> tuple[dict, list[str], list[dict]]:
    imported = []
    pending_new = []
    for candidate in candidates:
        if not candidate.get("officialDocumentRetrieved"):
            pending_new.append({**candidate, "reviewReason": "官方PDF正文未成功取得"})
            continue
        existing = find_existing(store, candidate)
        if not existing:
            pending_new.append(
                {
                    **candidate,
                    "proposedProjectId": stable_project_id(
                        "ma", candidate["title"], candidate.get("company") or ""
                    ),
                    "reviewReason": "新项目需人工核验主体、金额、比例及陕西关系后入库",
                }
            )
            continue
        source_id = f"src-{candidate['announcementId']}"
        merge_candidate = {
            "sourceRecord": {
                "sourceRecordId": source_id,
                "sourceName": candidate["sourceName"],
                "sourceQuality": "exchange_or_regulator_original",
                "publishedAt": candidate["publishedAt"],
                "title": candidate["title"],
                "url": candidate["sourceUrl"],
            },
            "milestone": {
                "milestoneId": "m-" + stable_project_id(
                    "milestone", candidate["title"], candidate["publishedAt"]
                ).split("-", 1)[1][:12],
                "at": candidate["publishedAt"],
                "label": candidate["title"],
                "stageAfter": candidate["stage"],
                "sourceIds": [source_id],
            },
        }
        index = store["projects"].index(existing)
        merged = merge_ma_project(existing, merge_candidate)
        if sha256_json(merged) != sha256_json(existing):
            store["projects"][index] = merged
            imported.append(existing["maProjectId"])
    return store, sorted(set(imported)), pending_new


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新V2自有收并购事件库")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slot", choices=("morning", "midday", "closing"), default="morning")
    parser.add_argument("--verify-network", action="store_true")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    scan_day = date.fromisoformat(args.date).isoformat()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    config = load(CONFIG_PATH)
    issuer_registry_path = ROOT / next(
        row["registryPath"]
        for row in config["sources"]
        if row["sourceId"] == "ma-nonlisted-company-sites"
    )
    issuer_registry = load(issuer_registry_path)
    contract = load(CONTRACT_PATH)
    daily_path = (
        ROOT
        / contract["listedDailyDirectory"]
        / f"cninfo-announcements-{scan_day}.json"
    )
    if not daily_path.is_file():
        raise FileNotFoundError(
            f"缺少V2上市公司官方公告扫描输入：{daily_path.relative_to(ROOT)}"
        )
    daily = load(daily_path)
    source_runs = listed_source_runs(config, daily, daily_path)
    configured = {row["sourceId"]: row for row in config["sources"]}
    external_records = []
    external_exclusions = []
    if args.verify_network:
        for source_id, scanner in (
            ("ma-sx-property-exchanges", lambda source: scan_xbcq(source, scan_day, args.timeout)),
            ("ma-sx-sasac", lambda source: scan_sasac(source, scan_day, args.timeout)),
            (
                "ma-nonlisted-company-sites",
                lambda source: scan_issuer_registry(
                    source, issuer_registry, scan_day, args.timeout
                ),
            ),
        ):
            source = configured[source_id]
            try:
                run, records, excluded = scanner(source)
                source_runs.append(run)
                external_records.extend(records)
                external_exclusions.extend(excluded)
            except Exception as error:
                source_runs.append(
                    {
                        "sourceId": source_id,
                        "name": source["name"],
                        "adapter": source["adapter"],
                        "status": "external_blocked",
                        "searchCompleted": False,
                        "failureReason": f"{type(error).__name__}: {error}",
                        "recordCount": 0,
                    }
                )
    else:
        for source_id in (
            "ma-sx-property-exchanges",
            "ma-sx-sasac",
            "ma-nonlisted-company-sites",
        ):
            source = configured[source_id]
            source_runs.append(
                {
                    "sourceId": source_id,
                    "name": source["name"],
                    "adapter": source["adapter"],
                    "status": "not_run",
                    "searchCompleted": False,
                    "failureReason": "未启用--verify-network，正式网络扫描未执行",
                    "recordCount": 0,
                }
            )

    rows = daily_rows(daily)
    raw_records = list(external_records)
    exclusions = list(external_exclusions)
    for row in rows:
        title = str(row.get("announcementTitle") or "")
        audit = ma_keyword_match(title, config)
        source_url = (
            "https://static.cninfo.com.cn/"
            + str(row.get("adjunctUrl") or "").lstrip("/")
        )
        normalized = {
            "recordId": f"ma-listed-cninfo:{row.get('announcementId')}",
            "announcementId": str(row.get("announcementId") or ""),
            "company": row.get("_matchedCompanyName") or row.get("secName") or "",
            "securityCode": row.get("_securityCode") or row.get("secCode") or "",
            "universeTier": row.get("_universeTier") or "",
            "title": title,
            "publishedAt": iso_date(row.get("announcementTime")),
            "sourceName": "巨潮资讯",
            "sourceUrl": source_url,
            "stage": infer_ma_stage(title),
            "keywordAudit": audit,
            "relatedParties": [row.get("_matchedCompanyName") or row.get("secName") or ""],
            "shaanxiRelation": row.get("_inclusionReason") or row.get("_universeTier") or "",
            "facts": extract_ma_facts(title),
            "industry": "",
        }
        if audit["matched"]:
            if args.verify_network:
                normalized.update(official_pdf_check(source_url, args.timeout))
            else:
                normalized["officialDocumentRetrieved"] = False
                normalized["verificationNote"] = "本次未启用网络正文核验"
            raw_records.append(normalized)
        else:
            exclusions.append(
                {
                    "recordId": normalized["recordId"],
                    "company": normalized["company"],
                    "title": title,
                    "sourceUrl": source_url,
                    "reason": audit["reason"],
                }
            )

    raw_records = dedupe_ma_records(raw_records)
    matched_keys = {
        alias for row in raw_records for alias in ma_record_aliases(row)
    }
    exclusions = dedupe_ma_records(
        [
            row
            for row in exclusions
            if ma_record_aliases(row).isdisjoint(matched_keys)
        ]
    )
    store_before = load(STORE_PATH)
    original_ids = [row["maProjectId"] for row in store_before.get("projects", [])]
    store_after, imported, pending_new = merge_verified(
        deepcopy(store_before), raw_records
    )
    pending_new = dedupe_ma_records(pending_new)
    after_ids = [row["maProjectId"] for row in store_after.get("projects", [])]
    if len(original_ids) < 25 or set(original_ids) - set(after_ids):
        raise ValueError("MA项目不得少于25个基线项目，且既有项目标识不得删除或变化")
    store_changed = sha256_json(store_after) != sha256_json(store_before)
    if store_changed:
        dates = [
            source.get("publishedAt") or ""
            for project in store_after.get("projects", [])
            for source in project.get("sourceRecords", [])
            if source.get("publishedAt")
        ]
        stage_counts: dict[str, int] = {}
        primary_verified = 0
        for project in store_after["projects"]:
            stage = str(project.get("stage") or "unknown")
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
            if any(
                source.get("sourceQuality") == "exchange_or_regulator_original"
                and source.get("url")
                for source in project.get("sourceRecords", [])
            ):
                primary_verified += 1
        store_after.update(
            {
                "projectCount": len(store_after["projects"]),
                "officialSourceProjectCount": primary_verified,
                "sourceBackfillCount": len(store_after["projects"]) - primary_verified,
                "stageCounts": dict(sorted(stage_counts.items())),
                "scanAsOf": scan_day,
                "eventAsOf": max(dates or [store_after.get("eventAsOf", "")]),
            }
        )
        write_json(STORE_PATH, store_after)

    raw_path = BASE_DIR / "raw" / f"raw-{scan_day}-{args.slot}.json"
    candidate_path = BASE_DIR / "candidates" / f"candidates-{scan_day}-{args.slot}.json"
    exclusion_path = BASE_DIR / "exclusions" / f"excluded-{scan_day}-{args.slot}.json"
    write_json(raw_path, {"scanAsOf": scan_day, "slot": args.slot, "records": raw_records})
    write_json(
        candidate_path,
        {"scanAsOf": scan_day, "slot": args.slot, "records": pending_new},
    )
    write_json(
        exclusion_path,
        {"scanAsOf": scan_day, "slot": args.slot, "records": exclusions},
    )
    required_ids = {row["sourceId"] for row in config["sources"] if row.get("required")}
    completed_ids = {
        row["sourceId"]
        for row in source_runs
        if row.get("searchCompleted") and row.get("status") == "completed"
    }
    coverage_complete = required_ids == completed_ids
    latest_dates = [
        source.get("publishedAt") or ""
        for project in store_after.get("projects", [])
        for source in project.get("sourceRecords", [])
        if source.get("publishedAt")
    ]
    candidate_on_scan_date, event_on_scan_date = scan_date_flags(
        store_after, imported, pending_new, scan_day
    )
    artifact_paths = (raw_path, candidate_path, exclusion_path, STORE_PATH)
    receipt = {
        "schemaVersion": "1.0",
        "channel": "ma",
        "scanAsOf": scan_day,
        "slot": args.slot,
        "startedAt": started_at,
        "finishedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "completed" if coverage_complete else "blocked",
        "coverageComplete": coverage_complete,
        "networkVerified": args.verify_network,
        "sourceRuns": source_runs,
        "coverageScope": {
            "listedUniverseCount": daily.get("_summary", {}).get("companyUniverseCount", 0),
            "cninfoAnnouncementCount": daily.get("_summary", {}).get("announcementCount", 0),
            "hkexCompanyCount": daily.get("_summary", {}).get("hkexOfficialReview", {}).get("companyCount", 0),
            "nonlistedRegistryCount": len(issuer_registry["configuredSites"]),
            "nonlistedCoverageBacklogCount": len(issuer_registry.get("coverageBacklog", [])),
        },
        "searchTerms": config["eventKeywords"],
        "counts": {
            "existingProjectsBefore": len(original_ids),
            "rawMatched": len(raw_records),
            "candidateForManualReview": len(pending_new),
            "importedOrUpdated": len(imported),
            "excluded": len(exclusions),
            "projectsAfter": len(after_ids),
        },
        "importedProjectIds": imported,
        "candidateOnScanDate": candidate_on_scan_date,
        "eventOnScanDate": event_on_scan_date,
        "latestEventDate": max(latest_dates or [""]),
        "inputSha256": sha256_json(
            {
                "config": config,
                "daily": daily,
                "storeBefore": store_before,
                "issuerRegistry": issuer_registry,
                "date": scan_day,
                "slot": args.slot,
            }
        ),
        "configSha256": sha256_file(CONFIG_PATH),
        "issuerRegistrySha256": sha256_file(issuer_registry_path),
        "scannerSha256": sha256_file(Path(__file__).resolve()),
        "eventStoreSha256": sha256_file(STORE_PATH),
        "artifactHashes": {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in artifact_paths
        },
        "failureReasons": [
            f"{row['sourceId']}:{row.get('failureReason') or '未完成覆盖'}"
            for row in source_runs
            if not row.get("searchCompleted")
        ],
    }
    receipt_path = BASE_DIR / "scans" / f"scan-{scan_day}-{args.slot}.json"
    write_json(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if coverage_complete else 3


if __name__ == "__main__":
    raise SystemExit(main())
