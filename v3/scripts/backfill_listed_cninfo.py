#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
CNINFO_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_DATA_URL = "https://www.cninfo.com.cn/new/data"
REFERER = "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search"
TZ = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill all V3 listed-company announcements from CNINFO.")
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--chunk", choices=("quarter", "month", "all"), default="quarter")
    parser.add_argument("--page-size", type=int, default=30)
    parser.add_argument("--sleep", type=float, default=0.04)
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def request_json(url: str, *, data: dict[str, str] | None = None, timeout: float = 25, retries: int = 4) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8") if data else None
    error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(
            url,
            data=body,
            headers={"User-Agent": "Mozilla/5.0", "Referer": REFERER, "Content-Type": "application/x-www-form-urlencoded", "X-Requested-With": "XMLHttpRequest"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            error = exc
            if attempt < retries:
                time.sleep(attempt * 0.8)
    raise RuntimeError(f"request failed after {retries} attempts: {url} {error!r}")


def top_search(keyword: str, timeout: float, retries: int) -> list[dict[str, Any]]:
    url = f"https://www.cninfo.com.cn/new/information/topSearch/query?{urllib.parse.urlencode({'keyWord': keyword, 'maxNum': '20'})}"
    error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, data=b"", method="POST", headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.cninfo.com.cn/new/index", "X-Requested-With": "XMLHttpRequest"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return payload if isinstance(payload, list) else []
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            error = exc
            if attempt < retries:
                time.sleep(attempt * 0.8)
    raise RuntimeError(f"CNINFO top search failed: {keyword} {error!r}")


def month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1).fromordinal(date(year, month + 1, 1).toordinal() - 1)


def chunks(start: date, end: date, mode: str) -> list[tuple[date, date]]:
    if mode == "all":
        return [(start, end)]
    result: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        if mode == "month":
            boundary = month_end(cursor.year, cursor.month)
        else:
            quarter_end_month = ((cursor.month - 1) // 3 + 1) * 3
            boundary = month_end(cursor.year, quarter_end_month)
        chunk_end = min(boundary, end)
        result.append((cursor, chunk_end))
        cursor = date.fromordinal(chunk_end.toordinal() + 1)
    return result


def clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(value or ""))).strip()


def load_taxonomy() -> list[dict[str, Any]]:
    data = json.loads((ROOT / "config/listed-business-taxonomy.json").read_text(encoding="utf-8"))
    tags = []
    for category in data["categories"]:
        for tag in category["tags"]:
            tags.append({**tag, "rmCategory": category["name"], "targetObjects": category["targetObjects"]})
    tags.sort(key=lambda item: (item["name"] != "回购注销", item["name"] != "股份回购"))
    return tags


def classify(title: str, tags: list[dict[str, Any]]) -> dict[str, Any] | None:
    for tag in tags:
        if any(keyword in title for keyword in tag["keywords"]):
            return tag
    return None


def resolve_universe(timeout: float, retries: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    universe_path = ROOT / "data/listed/universe.json"
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    master_dir = ROOT / "data/backfill/listed/master"
    master_dir.mkdir(parents=True, exist_ok=True)
    master: dict[str, dict[str, Any]] = {}
    for dataset in ("szse_stock", "hke_stock"):
        payload = request_json(f"{CNINFO_DATA_URL}/{dataset}.json", timeout=timeout, retries=retries)
        (master_dir / f"{dataset}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for item in payload.get("stockList", []):
            master[str(item.get("code"))] = item

    resolved: list[dict[str, Any]] = []
    missing: list[str] = []
    for entity in universe["entities"]:
        raw_code, market = entity["securityCode"].split(".")
        query_code = raw_code.zfill(5) if market == "HK" else raw_code
        record = master.get(query_code)
        if not record:
            category = "港股" if market == "HK" else "A股"
            search_results = top_search(raw_code, timeout, retries)
            record = next((item for item in search_results if str(item.get("code")) == query_code and item.get("category") == category), None)
            if not record:
                search_results = top_search(entity["canonicalName"], timeout, retries)
                record = next((item for item in search_results if str(item.get("code")) == query_code and item.get("category") == category), None)
        org_id = entity.get("cninfoOrgId") or (record or {}).get("orgId")
        if not org_id:
            missing.append(entity["securityCode"])
            continue
        entity["cninfoOrgId"] = org_id
        entity["cninfoQueryCode"] = query_code
        resolved.append(entity)
    if missing:
        raise RuntimeError(f"CNINFO master data did not resolve: {missing}")
    universe["retrievalCoverage"] = {
        "cninfoCompanyCount": sum(item["universeTier"] == "L1" for item in resolved),
        "hkexCompanyCount": sum(item["universeTier"] == "L2" for item in resolved),
        "l3CninfoCompanyCount": sum(item["universeTier"] == "L3" for item in resolved),
        "note": "117家主体均已解析巨潮证券主数据标识；港股公告仍需以HKEX披露易作最终完整性复核。",
    }
    universe_path.write_text(json.dumps(universe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return universe, resolved


def fetch_entity(entity: dict[str, Any], start: date, end: date, page_size: int, timeout: float, retries: int) -> list[dict[str, Any]]:
    page = 1
    results: list[dict[str, Any]] = []
    while True:
        payload = request_json(
            CNINFO_QUERY_URL,
            data={
                "pageNum": str(page), "pageSize": str(page_size), "column": "", "tabName": "fulltext", "plate": "",
                "stock": f"{entity['cninfoQueryCode']},{entity['cninfoOrgId']}", "searchkey": "", "secid": "", "category": "",
                "trade": "", "seDate": f"{start.isoformat()}~{end.isoformat()}", "sortName": "", "sortType": "", "isHLtitle": "true",
            },
            timeout=timeout,
            retries=retries,
        )
        announcements = payload.get("announcements") or []
        total = int(payload.get("totalRecordNum") or 0)
        for item in announcements:
            item["_entityId"] = entity["entityId"]
            item["_universeTier"] = entity["universeTier"]
            item["_canonicalName"] = entity["canonicalName"]
            item["_securityCode"] = entity["securityCode"]
            results.append(item)
        if len(announcements) < page_size or page * page_size >= total:
            break
        page += 1
        time.sleep(0.04)
    return results


def valid_cached(path: Path, expected_count: int) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("summary", {}).get("queriedEntityCount") == expected_count and not data.get("summary", {}).get("errors")
    except (json.JSONDecodeError, OSError):
        return False


def normalize(raw_paths: list[Path], universe: dict[str, Any], start: date, end: date) -> dict[str, Any]:
    tags = load_taxonomy()
    seen: set[str] = set()
    sources: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for path in raw_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("announcements", []):
            announcement_id = str(item.get("announcementId") or "")
            if not announcement_id or announcement_id in seen:
                continue
            seen.add(announcement_id)
            title = clean_title(item.get("announcementTitle") or "")
            published = datetime.fromtimestamp((item.get("announcementTime") or 0) / 1000, TZ).isoformat()
            source = {
                "sourceRecordId": f"src-cninfo-{announcement_id}", "announcementId": announcement_id,
                "entityId": item["_entityId"], "canonicalName": item["_canonicalName"], "securityCode": item["_securityCode"],
                "universeTier": item["_universeTier"], "title": title, "publishedAt": published,
                "url": f"https://static.cninfo.com.cn/{item.get('adjunctUrl')}", "sourceQuality": "official",
            }
            sources.append(source)
            tag = classify(title, tags)
            if tag:
                candidates.append({
                    "eventCandidateId": f"listed-ann-{announcement_id}", "eventKeySeed": f"{item['_securityCode']}:{announcement_id}",
                    "primaryEntityId": item["_entityId"], "title": title, "publishedAt": published, "discoveredAt": None,
                    "noveltyStatus": "backfill", "rmCategory": tag["rmCategory"], "rmSubcategory": tag["name"],
                    "businessPriority": tag["businessPriority"], "targetObjects": tag["targetObjects"],
                    "sourceRecordIds": [source["sourceRecordId"]], "normalizationStatus": "title_classified_pdf_pending",
                })
    sources.sort(key=lambda item: (item["publishedAt"], item["securityCode"], item["announcementId"]))
    candidates.sort(key=lambda item: (item["publishedAt"], item["eventCandidateId"]))
    tier_counts = Counter(source["universeTier"] for source in sources)
    return {
        "schemaVersion": "0.1", "startDate": start.isoformat(), "endDate": end.isoformat(), "generatedAt": datetime.now(TZ).isoformat(),
        "coverage": {"subjectCount": universe["counts"]["total"], "resolvedSubjectCount": universe["counts"]["total"], "sourceRecordCount": len(sources), "candidateCount": len(candidates), "sourceRecordsByTier": dict(tier_counts), "hkexCompletenessReviewRequired": True},
        "sources": sources, "candidates": candidates,
    }


def main() -> int:
    args = parse_args()
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    if start > end:
        raise SystemExit("start date must not be after end date")
    universe, entities = resolve_universe(args.timeout, args.retries)
    raw_dir = ROOT / "data/backfill/listed/raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_paths: list[Path] = []
    total_errors: list[dict[str, str]] = []
    for chunk_start, chunk_end in chunks(start, end, args.chunk):
        output = raw_dir / f"cninfo-{chunk_start.isoformat()}_{chunk_end.isoformat()}.json"
        raw_paths.append(output)
        if args.resume and valid_cached(output, len(entities)):
            print(f"resume: {output.name}")
            continue
        announcements: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for index, entity in enumerate(entities, start=1):
            try:
                announcements.extend(fetch_entity(entity, chunk_start, chunk_end, args.page_size, args.timeout, args.retries))
            except Exception as exc:  # noqa: BLE001
                errors.append({"entityId": entity["entityId"], "securityCode": entity["securityCode"], "error": repr(exc)})
            if index % 20 == 0:
                print(f"{chunk_start}~{chunk_end}: {index}/{len(entities)} entities, {len(announcements)} announcements")
            time.sleep(args.sleep)
        unique = {str(item.get("announcementId")): item for item in announcements if item.get("announcementId")}
        payload = {
            "summary": {"startDate": chunk_start.isoformat(), "endDate": chunk_end.isoformat(), "queriedEntityCount": len(entities), "announcementCount": len(unique), "errorCount": len(errors), "errors": errors, "contentSha256": hashlib.sha256(json.dumps(unique, ensure_ascii=False, sort_keys=True).encode()).hexdigest()},
            "announcements": sorted(unique.values(), key=lambda item: (item.get("announcementTime") or 0, item.get("announcementId") or "")),
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        total_errors.extend(errors)
    normalized = normalize(raw_paths, universe, start, end)
    normalized_path = ROOT / "data/backfill/listed/normalized-2026.json"
    normalized_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    coverage = {
        "schemaVersion": "0.1", "startDate": start.isoformat(), "endDate": end.isoformat(), "generatedAt": datetime.now(TZ).isoformat(),
        "channels": {
            "listed": {"status": "RAW_COMPLETE_CLASSIFICATION_PENDING_REVIEW" if not total_errors else "PARTIAL", **normalized["coverage"], "errors": total_errors},
            "private_fund": {"status": "PENDING"}, "equity_financing": {"status": "PENDING"}, "ma": {"status": "PENDING"}, "tender": {"status": "PENDING"}, "soe": {"status": "PENDING"},
        },
    }
    coverage_path = ROOT / "data/backfill/coverage-2026.json"
    coverage_path.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"normalized": str(normalized_path.relative_to(ROOT)), "coverage": normalized["coverage"], "errorCount": len(total_errors)}, ensure_ascii=False, indent=2))
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
