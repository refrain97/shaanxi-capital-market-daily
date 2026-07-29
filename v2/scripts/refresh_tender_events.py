#!/usr/bin/env python3
"""Scan V2-owned tender sources and merge only verified official records."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import ssl
import time
from datetime import date, datetime
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from scanner_common import (
    infer_tender_stage,
    merge_tender_project,
    normalize_title,
    sha256_file,
    sha256_json,
    stable_project_id,
    tender_keyword_match,
    write_json,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "v2/config/tender-sources.json"
STORE_PATH = ROOT / "v2/data/source/tender/events-2026.json"
BASE_DIR = ROOT / "v2/data/source/tender"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict | None = None,
    timeout: int = 20,
) -> tuple[int, str, bytes, dict]:
    request = Request(
        url,
        data=body,
        method=method,
        headers={
            "User-Agent": "Shaanxi-Capital-Market-V2-Tender/1.0",
            **(headers or {}),
        },
    )
    with urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
        raw = response.read(2_000_000)
        return response.status, response.geturl(), raw, dict(response.headers.items())


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


def parse_buyer(text: str) -> str:
    match = re.search(
        r"(?:招标人|采购人|项目业主|征集人)[^：:]{0,30}[：:为]\s*([^，。；;]{2,100})",
        text,
    )
    return match.group(1).strip() if match else ""


def parse_deadline(text: str) -> str:
    match = re.search(
        r"(?:投标文件递交截止时间|投标截止时间|响应文件提交截止时间|"
        r"递交截止时间|开标时间)[^0-9]{0,24}"
        r"(20\d{2})[年\-/\.](\d{1,2})[月\-/\.](\d{1,2})日?"
        r"(?:[^0-9]{0,8}(\d{1,2})[:时](\d{1,2}))?",
        text,
    )
    if not match:
        return ""
    year, month, day, hour, minute = match.groups()
    if hour:
        return f"{year}-{int(month):02d}-{int(day):02d} {int(hour):02d}:{int(minute or 0):02d}"
    return f"{year}-{int(month):02d}-{int(day):02d}"


def parse_winners(text: str) -> list[dict]:
    names = []
    for match in re.finditer(
        r"(第一|第二|第三)?(?:中标候选人|成交候选人|中标人|成交供应商)"
        r"[^：:]{0,12}[：:]\s*([^，。；;]{2,100})",
        text,
    ):
        rank, name = match.groups()
        cleaned = re.sub(r"\s+", " ", name).strip()
        if cleaned and cleaned not in {row["name"] for row in names}:
            names.append({"rank": rank or "winner", "name": cleaned})
    return names


def sxggzy_payload(keyword: str, scan_day: str) -> dict:
    return {
        "esdsid": "1",
        "token": "",
        "pn": 0,
        "rn": 50,
        "sdt": scan_day,
        "edt": scan_day,
        "wd": keyword,
        "inc_wd": "",
        "exc_wd": "",
        "fields": "title",
        "cnum": "001",
        "sort": '{"webdate":"0"}',
        "ssort": "title",
        "cl": 5000,
        "cutIngore": "title;linkurl",
        "terminal": "",
        "condition": [],
        "time": [],
        "highlights": "title",
        "statistics": None,
        "unionCondition": None,
        "accuracy": "",
        "noParticiple": "1",
        "searchRange": [],
        "isBusiness": "1",
    }


def scan_sxggzy(
    source: dict,
    config: dict,
    scan_day: str,
    timeout: int,
    max_queries: int | None = None,
) -> tuple[dict, list[dict]]:
    records: dict[str, dict] = {}
    queries = []
    terms = list(dict.fromkeys(config["keywordGroups"]["products"] + config["keywordGroups"]["services"]))
    selected_terms = terms[:max_queries] if max_queries else terms
    for keyword in selected_terms:
        started = time.monotonic()
        payload = json.dumps(sxggzy_payload(keyword, scan_day), ensure_ascii=False).encode()
        status, final_url, raw, _ = fetch(
            source["searchEndpoint"],
            method="POST",
            body=payload,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )
        outer = json.loads(decode(raw))
        inner = json.loads(outer["content"]) if isinstance(outer.get("content"), str) else outer["content"]
        result = inner.get("result", {})
        rows = result.get("records", [])
        queries.append(
            {
                "keyword": keyword,
                "httpStatus": status,
                "resultCount": len(rows),
                "reportedTotal": int(result.get("totalcount") or 0),
                "elapsedMs": round((time.monotonic() - started) * 1000),
            }
        )
        for row in rows:
            title = re.sub(r"<[^>]+>", "", str(row.get("title") or "")).strip()
            source_url = urljoin(source["url"], str(row.get("linkurl") or ""))
            record_id = f"{source['sourceId']}:{row.get('infoid') or sha256_json(source_url)[:20]}"
            records[record_id] = {
                "recordId": record_id,
                "sourceId": source["sourceId"],
                "sourceName": source["name"],
                "sourceQuality": source["authority"],
                "sourceUrl": source_url,
                "title": title,
                "publishedAt": iso_date(row.get("webdate")),
                "category": row.get("categoryname") or "",
                "indexExcerpt": re.sub(r"<[^>]+>", " ", str(row.get("content") or "")).strip(),
            }
    return (
        {
            "sourceId": source["sourceId"],
            "name": source["name"],
            "adapter": source["adapter"],
            "status": "completed" if len(selected_terms) == len(terms) else "degraded",
            "searchCompleted": len(selected_terms) == len(terms),
            "queryCount": len(queries),
            "recordCount": len(records),
            "queries": queries,
            **(
                {"failureReason": "可控实扫只执行部分关键词，不构成全量检索"}
                if len(selected_terms) != len(terms)
                else {}
            ),
        },
        list(records.values()),
    )


def scan_ccgp(
    source: dict,
    config: dict,
    scan_day: str,
    timeout: int,
) -> tuple[dict, list[dict]]:
    """Call the signed official full-list API; captcha failures remain external blocks."""
    records: dict[str, dict] = {}
    pages = []
    page = 1
    crossed_boundary = False
    public_key = b"""-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCS2TZDs5+orLYCL5SsJ54+bPCV
s1ZQQwP2RoPkFQF2jcT0HnNNT8ZoQgJTrGwNi5QNTBDoHC4oJesAVYe6DoxXS9Nl
s8WbGE8ZNgOC5tVv1WVjyBw7k2x72C/qjPoyo/kO7TYl6Qnu4jqW/ImLoup/nsJp
pUznF0YgbyU/dFFNBQIDAQAB
-----END PUBLIC KEY-----"""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    while page <= 100:
        params = {
            "siteId": source["siteId"],
            "channel": source["channel"],
            "currPage": page,
            "pageSize": 100,
            "regionCode": source["regionCode"],
            "noticeType": source["noticeType"],
            "cityOrArea": "",
            "selectTimeName": "noticeTime",
            "purchaseManner": "",
            "title": "",
            "verifyCode": "",
            "openTenderCode": "",
            "purchaseNature": "",
            "operationStartTime": f"{scan_day} 00:00:00",
            "operationEndTime": f"{scan_day} 23:59:59",
        }
        query_url = f"{source['searchEndpoint']}?{urlencode(params)}"
        timestamp = str(int(time.time() * 1000))
        rsa_key = serialization.load_pem_public_key(public_key)
        encrypted = rsa_key.encrypt(
            f"{source['searchEndpoint']}$${timestamp}".encode(), padding.PKCS1v15()
        )
        sha1 = hashlib.sha1(
            (
                f"{timestamp}_{source['searchEndpoint']}"
                "_bosssoft_platform_095285"
            ).encode()
        ).hexdigest()
        signed_headers = {
            "nsssjss": base64.b64encode(encrypted).decode(),
            "time": timestamp,
            "url": source["searchEndpoint"],
            "sign": hashlib.md5(sha1.encode()).hexdigest(),
        }
        started = time.monotonic()
        status, final_url, raw, _ = fetch(
            query_url, headers=signed_headers, timeout=timeout
        )
        payload = json.loads(decode(raw))
        rows = payload.get("data") or []
        row_dates = [iso_date(row.get("noticeTime")) for row in rows]
        pages.append(
            {
                "page": page,
                "requestUrl": final_url,
                "requestParams": params,
                "httpStatus": status,
                "apiCode": payload.get("code"),
                "apiMessage": payload.get("msg") or "",
                "reportedTotal": int(payload.get("total") or 0),
                "rowCount": len(rows),
                "newestDate": max(row_dates or [""]),
                "oldestDate": min(row_dates or [""]),
                "responseSha256": sha256_json(payload),
                "elapsedMs": round((time.monotonic() - started) * 1000),
            }
        )
        if str(payload.get("code")) not in {"0", "200"}:
            break
        for row in rows:
            published = iso_date(row.get("noticeTime"))
            if published != scan_day:
                continue
            record_id = f"{source['sourceId']}:{row.get('id')}"
            body = visible_text(str(row.get("content") or "").encode())
            records[record_id] = {
                "recordId": record_id,
                "sourceId": source["sourceId"],
                "sourceName": source["name"],
                "sourceQuality": source["authority"],
                "sourceUrl": urljoin(source["url"], str(row.get("pageurl") or "")),
                "title": str(row.get("title") or "").strip(),
                "publishedAt": published,
                "category": str(row.get("noticeType") or ""),
                "indexExcerpt": body[:1000],
                "embeddedBody": body,
                "embeddedBodySha256": sha256_json(body),
                "buyer": str(row.get("purchaser") or "").strip(),
                "deadlineOrOpening": iso_date(row.get("openTenderTime"))
                or iso_date(row.get("expireTime")),
                "winningOrCandidateUnits": (
                    [{"rank": "winner", "name": str(row.get("bidCompany")).strip()}]
                    if row.get("bidCompany")
                    else []
                ),
            }
        if not rows:
            break
        if min(row_dates or ["9999-12-31"]) < scan_day:
            crossed_boundary = True
            break
        page += 1
    homepage_params = {
        "siteId": source["siteId"],
        "channel": source["channel"],
        "currPage": 1,
        "pageSize": 100,
        "regionCode": source["regionCode"],
        "noticeType": "00101",
        "cityOrArea": "",
        "selectTimeName": "noticeTime",
    }
    _, homepage_url, homepage_raw, _ = fetch(
        f"{source['homepageEndpoint']}?{urlencode(homepage_params)}", timeout=timeout
    )
    homepage_payload = json.loads(decode(homepage_raw))
    homepage_evidence = {
        "requestUrl": homepage_url,
        "requestParams": homepage_params,
        "rowCount": len(homepage_payload.get("data") or []),
        "responseSha256": sha256_json(homepage_payload),
        "coverageUse": "仅证明站点可达及当日样本，不作为完整覆盖",
    }
    complete = crossed_boundary
    last_page = pages[-1] if pages else {}
    failure_reason = (
        "官方全文列表接口要求有效验证码，已完成签名请求但无法分页检索；"
        f"apiCode={last_page.get('apiCode')}, message={last_page.get('apiMessage')}"
        if last_page.get("apiCode") not in (0, "0", 200, "200")
        else "公告列表未跨越扫描日边界，无法证明同日全量覆盖"
    )
    return (
        {
            "sourceId": source["sourceId"],
            "name": source["name"],
            "adapter": source["adapter"],
            "status": "completed" if complete else "external_blocked",
            "searchCompleted": complete,
            "coverageMode": "same_day_paginated_list_and_embedded_official_body",
            "pageCount": len(pages),
            "recordCount": len(records),
            "detailVerificationRequiredCount": len(records),
            "detailVerifiedCount": len(records),
            "pages": pages,
            "homepageSampleEvidence": homepage_evidence,
            **(
                {}
                if complete
                else {"failureReason": failure_reason}
            ),
        },
        list(records.values()),
    )


def scan_sntba(
    source: dict,
    config: dict,
    scan_day: str,
    timeout: int,
) -> tuple[dict, list[dict]]:
    """Use the platform's public list API; captcha pagination is recorded fail-closed."""
    records: dict[str, dict] = {}
    pages = []
    cursor = ""
    page_no = 1
    crossed_boundary = False
    while page_no <= 50:
        params = {"pageNo": page_no, "pageSize": 100}
        if cursor:
            params.update({"pageAction": "next", "cursor": cursor})
        request_url = f"{source['searchEndpoint']}?{urlencode(params)}"
        started = time.monotonic()
        status, final_url, raw, _ = fetch(request_url, timeout=timeout)
        payload = json.loads(decode(raw))
        data = payload.get("data") or {}
        rows = data.get("list") or []
        row_dates = [iso_date(row.get("publishDate")) for row in rows]
        page_evidence = {
            "page": page_no,
            "requestUrl": final_url,
            "requestParams": params,
            "httpStatus": status,
            "apiCode": payload.get("code"),
            "apiMessage": payload.get("msg") or "",
            "rowCount": len(rows),
            "reportedTotal": int(data.get("total") or 0),
            "newestDate": max(row_dates or [""]),
            "oldestDate": min(row_dates or [""]),
            "responseSha256": sha256_json(payload),
            "elapsedMs": round((time.monotonic() - started) * 1000),
        }
        pages.append(page_evidence)
        if payload.get("code") not in (0, 200):
            break
        for row in rows:
            published = iso_date(row.get("publishDate"))
            if published != scan_day:
                continue
            title = str(row.get("title") or "").strip()
            record_id = f"{source['sourceId']}:{row.get('id')}"
            records[record_id] = {
                "recordId": record_id,
                "sourceId": source["sourceId"],
                "sourceName": source["name"],
                "sourceQuality": source["authority"],
                "sourceUrl": (
                    f"{source['url'].rstrip('/')}/detail/{row.get('id')}?"
                    + urlencode({"type": "notice"})
                ),
                "title": title,
                "publishedAt": published,
                "category": infer_tender_stage(title),
                "indexExcerpt": title,
                "area": row.get("area") or "",
            }
        if not rows:
            break
        if min(row_dates or ["9999-12-31"]) < scan_day:
            crossed_boundary = True
            break
        next_cursor = data.get("nextCursor")
        if not data.get("hasNext") or not next_cursor:
            crossed_boundary = True
            break
        cursor = str(next_cursor)
        page_no += 1
    complete = crossed_boundary
    reason = ""
    if not complete:
        last = pages[-1] if pages else {}
        reason = (
            "主站公开API在同日列表翻页时要求验证码，未能跨越日期边界；"
            f"apiCode={last.get('apiCode')}, message={last.get('apiMessage') or 'unknown'}"
        )
    return (
        {
            "sourceId": source["sourceId"],
            "name": source["name"],
            "adapter": source["adapter"],
            "status": "completed" if complete else "external_blocked",
            "searchCompleted": complete,
            "coverageMode": "same_day_cursor_paginated_list_and_detail",
            "pageCount": len(pages),
            "recordCount": len(records),
            "pages": pages,
            **({} if complete else {"failureReason": reason}),
        },
        list(records.values()),
    )


def parse_ceb_rows(
    source: dict, html: str, stage: str, keyword: str, scan_day: str
) -> list[dict]:
    records = []
    for row in re.findall(r"<tr>[\s\S]*?</tr>", html):
        detail = re.search(r"urlOpen\('([^']+)'\)[\s\S]*?title=\"([^\"]+)\"", row)
        if not detail:
            continue
        uuid, raw_title = detail.groups()
        title = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", raw_title))).strip()
        area = (re.search(r"<span\s+title\s*=\s*\"([^\"]+)\"[\s\S]*?【", row) or [None, ""])[1]
        if "陕西" not in f"{area} {title}":
            continue
        published = (re.search(r"\b20\d{2}-\d{2}-\d{2}\b", row) or [None])[0] or ""
        if published != scan_day:
            continue
        source_url = (
            "https://ctbpsp.com/#/bulletinDetail?"
            + urlencode({"uuid": uuid, "inpvalue": "", "dataSource": "0", "tenderAgency": ""})
        )
        records.append(
            {
                "recordId": f"{source['sourceId']}:{uuid}",
                "sourceId": source["sourceId"],
                "sourceName": source["name"],
                "sourceQuality": source["authority"],
                "sourceUrl": source_url,
                "title": title,
                "publishedAt": published,
                "category": stage,
                "indexExcerpt": title,
                "queryKeyword": keyword,
            }
        )
    return records


def scan_ceb(
    source: dict,
    config: dict,
    scan_day: str,
    timeout: int,
    max_queries: int | None = None,
) -> tuple[dict, list[dict]]:
    records: dict[str, dict] = {}
    queries = []
    stage_rows = {
        "announcement": ("bulletin", "88"),
        "change": ("change", "89"),
        "candidate": ("candidate", "91"),
        "award": ("result", "90"),
    }
    terms = list(dict.fromkeys(config["keywordGroups"]["products"] + config["keywordGroups"]["services"]))
    query_budget = max_queries
    stop = False
    for stage, (endpoint, category_id) in stage_rows.items():
        for keyword in terms:
            if query_budget is not None and query_budget <= 0:
                stop = True
                break
            query = (
                f"{source['searchEndpoint']}/{endpoint}.html?"
                + urlencode(
                    {
                        "searchDate": scan_day,
                        "dates": "1",
                        "categoryId": category_id,
                        "industryName": "",
                        "area": "",
                        "status": "",
                        "publishMedia": "",
                        "sourceInfo": "",
                        "showStatus": "",
                        "word": keyword,
                    }
                )
            )
            started = time.monotonic()
            status, _, raw, _ = fetch(query, timeout=timeout)
            parsed = parse_ceb_rows(source, decode(raw), stage, keyword, scan_day)
            for record in parsed:
                records[record["recordId"]] = record
            queries.append(
                {
                    "keyword": keyword,
                    "stage": stage,
                    "httpStatus": status,
                    "resultCount": len(parsed),
                    "elapsedMs": round((time.monotonic() - started) * 1000),
                }
            )
            if query_budget is not None:
                query_budget -= 1
        if stop:
            break
    expected_queries = len(stage_rows) * len(terms)
    complete = len(queries) == expected_queries
    return (
        {
            "sourceId": source["sourceId"],
            "name": source["name"],
            "adapter": source["adapter"],
            "status": "completed" if complete else "degraded",
            "searchCompleted": complete,
            "coverageEligible": complete and not records,
            "queryCount": len(queries),
            "recordCount": len(records),
            "coverageProof": {
                "date": scan_day,
                "regionRule": "解析结果只保留地区或标题含陕西的官方公告",
                "stageCount": len(stage_rows),
                "keywordCount": len(terms),
                "expectedQueryCount": expected_queries,
            "detailVerificationRequiredCount": len(records),
            "detailVerifiedCount": 0,
            },
            "queries": queries,
            **(
                {"failureReason": "可控实扫只执行部分关键词/阶段，不构成全量检索"}
                if not complete
                else {}
            ),
        },
        list(records.values()),
    )


def probe(source: dict, timeout: int) -> dict:
    started = time.monotonic()
    try:
        status, final_url, raw, headers = fetch(source["url"], timeout=timeout)
        return {
            "sourceId": source["sourceId"],
            "name": source["name"],
            "adapter": source["adapter"],
            "status": "degraded",
            "searchCompleted": False,
            "healthProbe": {
                "httpStatus": status,
                "finalUrl": final_url,
                "contentBytes": len(raw),
                "contentType": headers.get("Content-Type", ""),
                "elapsedMs": round((time.monotonic() - started) * 1000),
            },
            "failureReason": "健康探针不等于全量关键词检索；当前来源未配置全文搜索适配器",
            "recordCount": 0,
        }
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        return {
            "sourceId": source["sourceId"],
            "name": source["name"],
            "adapter": source["adapter"],
            "status": "failed",
            "searchCompleted": False,
            "failureReason": f"{type(error).__name__}: {error}",
            "recordCount": 0,
        }


def verify_source_body(record: dict, timeout: int) -> dict:
    if record.get("embeddedBody"):
        return {
            **record,
            "bodyExcerpt": record["embeddedBody"][:3000],
            "verificationStatus": "official_body_verified",
            "buyer": record.get("buyer") or parse_buyer(record["embeddedBody"]),
            "deadlineOrOpening": record.get("deadlineOrOpening")
            or parse_deadline(record["embeddedBody"]),
            "winningOrCandidateUnits": record.get("winningOrCandidateUnits")
            or parse_winners(record["embeddedBody"]),
        }
    url = record["sourceUrl"]
    if "#/" in url:
        return {
            **record,
            "verificationStatus": "pending_original_body",
            "verificationReason": "平台SPA详情页未取得可独立核验正文",
        }
    try:
        status, final_url, raw, _ = fetch(url, timeout=timeout)
        text = visible_text(raw)
        title_tokens = [token for token in re.split(r"[\s，。；：()（）_-]+", record["title"]) if len(token) >= 4]
        title_verified = any(token in text for token in title_tokens[:6])
        if status == 200 and len(text) >= 80 and title_verified:
            return {
                **record,
                "sourceUrl": final_url,
                "bodyExcerpt": text[:3000],
                "verificationStatus": "official_body_verified",
                "buyer": parse_buyer(text),
                "deadlineOrOpening": parse_deadline(text),
                "winningOrCandidateUnits": parse_winners(text),
            }
        return {
            **record,
            "verificationStatus": "pending_original_body",
            "verificationReason": "原文响应未同时满足正文长度与标题证据",
        }
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        return {
            **record,
            "verificationStatus": "pending_original_body",
            "verificationReason": f"{type(error).__name__}: {error}",
        }


def candidate_from_record(record: dict, config: dict, timeout: int) -> dict:
    indexed = f"{record['title']} {record.get('indexExcerpt') or ''}"
    preliminary = tender_keyword_match(indexed, config)
    if not preliminary["matched"]:
        return {
            **record,
            "verificationStatus": "not_required_nonmatch",
            "stage": infer_tender_stage(indexed),
            "keywordAudit": preliminary,
            "projectFingerprint": stable_project_id(
                "tender-project", record["title"], ""
            ),
            "securitiesCompanyFit": False,
        }
    verified = verify_source_body(record, timeout)
    combined = f"{verified['title']} {verified.get('bodyExcerpt') or verified.get('indexExcerpt') or ''}"
    match = tender_keyword_match(combined, config)
    stage = infer_tender_stage(combined)
    buyer = verified.get("buyer") or ""
    fingerprint = stable_project_id("tender-project", verified["title"], buyer)
    return {
        **verified,
        "stage": stage,
        "keywordAudit": match,
        "projectFingerprint": fingerprint,
        "securitiesCompanyFit": bool(match["groups"]["products"] or match["groups"]["services"]),
    }


def find_existing(store: dict, candidate: dict) -> dict | None:
    for row in store.get("opportunities", []):
        fingerprint = row.get("projectFingerprint") or stable_project_id(
            "tender-project", row.get("projectName") or "", row.get("buyer") or ""
        )
        if fingerprint == candidate["projectFingerprint"]:
            return row
        if normalize_title(row.get("projectName") or "") == normalize_title(candidate["title"]):
            return row
    return None


def merge_verified(store: dict, candidates: list[dict]) -> tuple[dict, list[str]]:
    imported = []
    for candidate in candidates:
        if (
            not candidate["keywordAudit"]["matched"]
            or candidate.get("verificationStatus") != "official_body_verified"
            or not candidate.get("publishedAt")
            or not candidate.get("buyer")
        ):
            continue
        existing = find_existing(store, candidate)
        source_record = {
            "sourceRecordId": candidate["recordId"],
            "sourceName": candidate["sourceName"],
            "sourceQuality": "official_public_disclosure",
            "publishedAt": candidate["publishedAt"],
            "title": candidate["title"],
            "url": candidate["sourceUrl"],
        }
        milestone = {
            "at": candidate["publishedAt"],
            "stage": candidate["stage"],
            "title": candidate["title"],
            "sourceRecordIds": [candidate["recordId"]],
        }
        merge_candidate = {
            **candidate,
            "sourceRecord": source_record,
            "milestone": milestone,
        }
        if existing:
            index = store["opportunities"].index(existing)
            store["opportunities"][index] = merge_tender_project(existing, merge_candidate)
            imported.append(existing["id"])
            continue
        project_id = stable_project_id("SX-V2-TENDER", candidate["title"], candidate["buyer"])
        store["opportunities"].append(
            {
                "id": project_id,
                "projectFingerprint": candidate["projectFingerprint"],
                "publishDate": candidate["publishedAt"],
                "projectName": candidate["title"],
                "buyer": candidate["buyer"],
                "location": "陕西省",
                "opportunityType": "资本市场专业服务",
                "projectScale": "以原文为准",
                "stage": candidate["stage"],
                "stageCode": candidate["stage"],
                "deadlineOrOpening": candidate.get("deadlineOrOpening") or None,
                "winnerStatus": "",
                "winningOrCandidateUnits": candidate.get("winningOrCandidateUnits") or [],
                "securitiesCompanyFit": "关键词与官方正文命中，进入正式项目库",
                "sourceReliability": "官方原文已核验",
                "sources": [{"name": candidate["sourceName"], "url": candidate["sourceUrl"]}],
                "sourceRecords": [source_record],
                "milestones": [milestone],
            }
        )
        imported.append(project_id)
    store["opportunities"] = sorted(
        store.get("opportunities", []),
        key=lambda row: (row.get("publishDate") or "", row.get("id") or ""),
    )
    return store, sorted(set(imported))


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新V2自有金融招投标事件库")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slot", choices=("morning", "midday", "closing"), default="morning")
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument(
        "--max-queries",
        type=int,
        help="仅用于可控实扫证据；限制每个全文适配器的请求数并强制阻断就绪",
    )
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    scan_day = date.fromisoformat(args.date).isoformat()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    config = load(CONFIG_PATH)
    store_before = load(STORE_PATH)
    source_runs = []
    raw_records = []
    for source in config["sources"]:
        try:
            if args.probe_only:
                source_runs.append(probe(source, args.timeout))
            elif source["adapter"] == "sxggzy_fulltext_v2":
                run, records = scan_sxggzy(
                    source, config, scan_day, args.timeout, args.max_queries
                )
                source_runs.append(run)
                raw_records.extend(records)
            elif source["adapter"] == "ccgp_shaanxi_notice_api_v2":
                run, records = scan_ccgp(source, config, scan_day, args.timeout)
                source_runs.append(run)
                raw_records.extend(records)
            elif source["adapter"] == "sntba_notice_api_v2":
                run, records = scan_sntba(source, config, scan_day, args.timeout)
                source_runs.append(run)
                raw_records.extend(records)
            elif source["adapter"] == "ceb_html_search_v2":
                run, records = scan_ceb(
                    source, config, scan_day, args.timeout, args.max_queries
                )
                source_runs.append(run)
                raw_records.extend(records)
            else:
                source_runs.append(
                    {
                        "sourceId": source["sourceId"],
                        "name": source["name"],
                        "adapter": source["adapter"],
                        "status": "failed",
                        "searchCompleted": False,
                        "failureReason": "未知适配器",
                        "recordCount": 0,
                    }
                )
        except Exception as error:  # source isolation is intentional
            source_runs.append(
                {
                    "sourceId": source["sourceId"],
                    "name": source["name"],
                    "adapter": source["adapter"],
                    "status": "failed",
                    "searchCompleted": False,
                    "failureReason": f"{type(error).__name__}: {error}",
                    "recordCount": 0,
                }
            )

    candidates = [candidate_from_record(row, config, args.timeout) for row in raw_records]
    matched = [row for row in candidates if row["keywordAudit"]["matched"]]
    exclusions = [
        {
            "recordId": row["recordId"],
            "title": row["title"],
            "sourceUrl": row["sourceUrl"],
            "reason": row["keywordAudit"]["reason"],
            "excludedKeywords": row["keywordAudit"]["excludedKeywords"],
        }
        for row in candidates
        if not row["keywordAudit"]["matched"]
    ]
    store_after, imported = merge_verified(store_before, matched)
    store_changed = sha256_json(store_after) != sha256_json(store_before)
    if store_changed:
        write_json(STORE_PATH, store_after)

    raw_path = BASE_DIR / "raw" / f"raw-{scan_day}-{args.slot}.json"
    candidate_path = BASE_DIR / "candidates" / f"candidates-{scan_day}-{args.slot}.json"
    exclusion_path = BASE_DIR / "exclusions" / f"excluded-{scan_day}-{args.slot}.json"
    write_json(raw_path, {"scanAsOf": scan_day, "slot": args.slot, "records": raw_records})
    write_json(candidate_path, {"scanAsOf": scan_day, "slot": args.slot, "records": matched})
    write_json(exclusion_path, {"scanAsOf": scan_day, "slot": args.slot, "records": exclusions})
    required_ids = {row["sourceId"] for row in config["sources"] if row.get("required")}
    completed_ids = {
        row["sourceId"]
        for row in source_runs
        if row.get("searchCompleted") and row.get("status") == "completed"
    }
    source_by_id = {row["sourceId"]: row for row in source_runs}
    coverage_groups = []
    for group in config.get("coverageGroups", []):
        members = [source_by_id.get(member, {}) for member in group["members"]]
        completed_members = [
            row.get("sourceId")
            for row in members
            if row.get("searchCompleted")
            and row.get("status") == "completed"
            and row.get("coverageEligible", True)
        ]
        group_complete = bool(completed_members) if group["rule"] == "any_complete" else (
            len(completed_members) == len(group["members"])
        )
        coverage_groups.append(
            {
                "groupId": group["groupId"],
                "rule": group["rule"],
                "members": group["members"],
                "completedMembers": completed_members,
                "coverageComplete": group_complete,
                "equivalenceEvidence": group["equivalenceEvidence"],
            }
        )
    groups_complete = all(
        row["coverageComplete"]
        for row in coverage_groups
        if next(
            group for group in config["coverageGroups"]
            if group["groupId"] == row["groupId"]
        ).get("required")
    )
    coverage_complete = required_ids.issubset(completed_ids) and groups_complete
    supplemental_failures = [
        row
        for row in source_runs
        if not row.get("searchCompleted")
        and not next(
            source
            for source in config["sources"]
            if source["sourceId"] == row["sourceId"]
        ).get("required")
        and next(
            source
            for source in config["sources"]
            if source["sourceId"] == row["sourceId"]
        ).get("degradedOnFailure")
    ]
    constrained_source_ids = sorted(
        str(row.get("sourceId") or "")
        for row in supplemental_failures
        if row.get("sourceId")
    )
    receipt_status = (
        "blocked"
        if not coverage_complete
        else "degraded"
        if supplemental_failures
        else "completed"
    )
    # A captcha-blocked supplemental source is not silently treated as a clean
    # scan.  It may, however, be released when the *configured* official
    # equivalent coverage groups have completed the complete query matrix.
    # This machine-readable assertion is consumed by the V2 release gate; a
    # generic ``degraded`` scan from any other channel remains blocking.
    release_eligible_with_constraint = bool(
        receipt_status == "degraded"
        and coverage_complete
        and constrained_source_ids
    )
    latest_dates = [
        row.get("publishDate") or ""
        for row in store_after.get("opportunities", [])
        if row.get("publishDate")
    ]
    artifact_paths = (raw_path, candidate_path, exclusion_path, STORE_PATH)
    receipt = {
        "schemaVersion": "1.0",
        "channel": "tender",
        "scanAsOf": scan_day,
        "slot": args.slot,
        "startedAt": started_at,
        "finishedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": receipt_status,
        "coverageComplete": coverage_complete,
        "releaseEligibility": {
            "eligible": release_eligible_with_constraint,
            "mode": (
                "official_equivalent_coverage_with_supplemental_source_constraint"
                if release_eligible_with_constraint
                else "none"
            ),
            "customerLabel": "已完成扫描，来源受限",
            "constrainedSourceIds": constrained_source_ids,
        },
        "networkVerified": any(
            row.get("healthProbe", {}).get("httpStatus")
            or any(query.get("httpStatus") for query in row.get("queries", []))
            for row in source_runs
        ),
        "sourceRuns": source_runs,
        "coverageGroups": coverage_groups,
        "searchTerms": config["keywordGroups"],
        "counts": {
            "existingProjectsBefore": len(store_before.get("opportunities", [])),
            "raw": len(raw_records),
            "candidate": len(matched),
            "verifiedForImport": sum(
                row.get("verificationStatus") == "official_body_verified" for row in matched
            ),
            "importedOrUpdated": len(imported),
            "excluded": len(exclusions),
            "projectsAfter": len(store_after.get("opportunities", [])),
        },
        "importedProjectIds": imported,
        "eventOnScanDate": any(
            row.get("publishedAt") == scan_day
            and row.get("verificationStatus") == "official_body_verified"
            for row in matched
        ),
        "latestEventDate": max(latest_dates or [""]),
        "inputSha256": sha256_json(
            {
                "config": config,
                "storeBefore": store_before,
                "date": scan_day,
                "slot": args.slot,
                "probeOnly": args.probe_only,
            }
        ),
        "configSha256": sha256_file(CONFIG_PATH),
        "scannerSha256": sha256_file(Path(__file__).resolve()),
        "eventStoreSha256": sha256_file(STORE_PATH),
        "artifactHashes": {
            path.relative_to(ROOT).as_posix(): sha256_file(path)
            for path in artifact_paths
        },
        "failureReasons": [
            f"{row['sourceId']}:{row.get('failureReason') or '未完成全文检索'}"
            for row in source_runs
            if not row.get("searchCompleted")
            and next(
                source
                for source in config["sources"]
                if source["sourceId"] == row["sourceId"]
            ).get("required")
        ] + [
            f"{row['groupId']}:官方等价覆盖组未完成"
            for row in coverage_groups
            if not row["coverageComplete"]
        ] + [
            f"{row['sourceId']}:补充来源受限，已由完整必需来源覆盖"
            for row in supplemental_failures
        ],
    }
    receipt_path = BASE_DIR / "scans" / f"scan-{scan_day}-{args.slot}.json"
    write_json(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if coverage_complete else 3


if __name__ == "__main__":
    raise SystemExit(main())
