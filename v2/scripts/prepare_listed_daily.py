#!/usr/bin/env python3
"""Prepare V2's self-contained listed-company daily inputs.

This replaces the former manual hand-off of CNINFO raw data, HKEX review and
editorial JSON.  It deliberately publishes only facts for which the official
PDF was fetched and text-extracted; an unavailable original document is a
candidate, never customer copy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from pypdf import PdfReader

from listed_editorial import (
    build_editorial_report,
    build_editorial_report_from_brief,
    normalize_pdf_text,
    text_quality_report,
)
from listed_universe import V2_UNIVERSE_PATH, load_listed_universe


ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "v2"
TZ = ZoneInfo("Asia/Shanghai")
HKEX_REGISTRY = V2 / "config/hkex-issuers.json"
HKEX_ENDPOINT = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
CNINFO_STATIC = "https://static.cninfo.com.cn/"

OPPORTUNITY_TERMS = ("中标", "合同", "订单", "融资", "发行", "增资", "收购", "投资")
RISK_TERMS = ("诉讼", "仲裁", "亏损", "风险", "担保", "终止", "减持", "冻结", "异常")
CAPITAL_TERMS = ("增资", "收购", "转让", "发行", "募", "债", "回购", "担保", "授信", "股东", "减持")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def previous_trade_day(day: date) -> date:
    cursor = day - timedelta(days=1)
    while cursor.weekday() >= 5:
        cursor -= timedelta(days=1)
    return cursor


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u3000", " ")).strip()


def day_from_timestamp(value: Any) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(int(value) / 1000, tz=TZ).date().isoformat()


def official_url(row: dict[str, Any]) -> str:
    value = str(row.get("adjunctUrl") or "").lstrip("/")
    return CNINFO_STATIC + value if value else ""


def fetch_bytes(url: str, *, timeout: int = 45) -> tuple[str, bytes]:
    """Fetch an official source without treating one TLS reset as source loss."""
    errors: list[str] = []
    for attempt in range(4):
        request = Request(url, headers={"User-Agent": "Shaanxi-Capital-Market-V2/2.0"})
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.geturl(), response.read(12_000_000)
        except Exception as error:
            errors.append(f"urllib#{attempt + 1}:{type(error).__name__}:{error}")
            if attempt < 3:
                time.sleep(1 + attempt)

    completed = subprocess.run(
        [
            "curl",
            "--location",
            "--fail",
            "--silent",
            "--show-error",
            "--http1.1",
            "--retry",
            "3",
            "--retry-all-errors",
            "--retry-delay",
            "1",
            "--connect-timeout",
            "15",
            "--max-time",
            str(timeout),
            "--user-agent",
            "Shaanxi-Capital-Market-V2/2.0",
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout + 15,
        check=False,
    )
    if completed.returncode == 0 and completed.stdout:
        return url, completed.stdout[:12_000_000]
    errors.append(
        f"curl:{completed.returncode}:"
        f"{completed.stderr.decode('utf-8', errors='replace')[-500:]}"
    )
    raise RuntimeError("正式来源多通道取证失败：" + " | ".join(errors))


def extract_with_pdfkit(raw: bytes) -> str:
    """Use macOS PDFKit only as an isolated fallback; the PDF is auto-deleted."""
    swift = Path("/usr/bin/swift")
    if not swift.is_file():
        return ""
    script = (
        'import Foundation; import PDFKit; '
        'let p=ProcessInfo.processInfo.environment["V2_PDF_PATH"]!; '
        'if let d=PDFDocument(url: URL(fileURLWithPath:p)) { print(d.string ?? "") }'
    )
    with tempfile.TemporaryDirectory(prefix="v2-listed-pdf-") as directory:
        pdf_path = Path(directory) / "official.pdf"
        pdf_path.write_bytes(raw)
        completed = subprocess.run(
            [str(swift), "-e", script],
            env={**os.environ, "V2_PDF_PATH": str(pdf_path)},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
            check=False,
        )
        return completed.stdout if completed.returncode == 0 else ""


def hkex_equivalent_pdf(row: dict[str, Any]) -> tuple[str, bytes, str] | None:
    """Locate the same L2 disclosure on HKEX when the CNINFO mirror is unreadable."""
    if str(row.get("_companyMarket") or "").upper() != "HK":
        return None
    security_code = str(row.get("secCode") or "").zfill(5)
    registry = json.loads(HKEX_REGISTRY.read_text(encoding="utf-8"))
    issuer = next(
        (item for item in registry.get("issuers", []) if str(item.get("securityCode") or "") == security_code),
        None,
    )
    if not issuer:
        return None
    announcement_day = day_from_timestamp(row.get("announcementTime"))
    compact = announcement_day.replace("-", "")
    params = {
        "sortDir": "0", "sortByOptions": "DateTime", "category": "0", "market": "SEHK",
        "stockId": str(issuer["stockId"]), "documentType": "-1",
        "fromDate": compact, "toDate": compact, "title": "",
    }
    _, response = fetch_bytes(f"{HKEX_ENDPOINT}?{urlencode(params)}")
    payload = json.loads(response.decode("utf-8"))
    records = json.loads(payload.get("result") or "[]")
    pdf_records = [item for item in records if item.get("FILE_TYPE") == "PDF" and item.get("FILE_LINK")]
    if len(pdf_records) != 1:
        return None
    pdf_url = "https://www1.hkexnews.hk" + str(pdf_records[0]["FILE_LINK"])
    final_url, raw = fetch_bytes(pdf_url)
    return final_url, raw, str(pdf_records[0].get("NEWS_ID") or "")


def pdf_excerpt(row: dict[str, Any], day: str) -> dict[str, Any]:
    source_url = official_url(row)
    if not source_url:
        raise ValueError("公告缺少正式PDF地址")
    announcement_id = str(row.get("announcementId") or "")
    if not announcement_id:
        raise ValueError("公告缺少稳定announcementId")
    final_url, raw = fetch_bytes(source_url)
    reader = PdfReader(BytesIO(raw))
    text = normalize_pdf_text(" ".join((page.extract_text() or "") for page in reader.pages[:40]))
    quality = text_quality_report(text)
    parser = "pypdf"
    discovery_url = final_url
    discovery_pdf_sha = digest(raw)
    hkex_news_id = ""
    if not quality["eligible"]:
        alternate = hkex_equivalent_pdf(row)
        if alternate:
            final_url, raw, hkex_news_id = alternate
            alternate_text = extract_with_pdfkit(raw)
            if alternate_text:
                text = normalize_pdf_text(alternate_text)
                quality = text_quality_report(text)
                parser = "pdfkit"
    if not quality["eligible"]:
        raise ValueError("公告PDF文本质量门禁失败：" + ",".join(quality["reasons"]))
    sentences = [clean_text(item) for item in re.split(r"(?<=[。；])", text) if clean_text(item)]
    title = clean_text(str(row.get("announcementTitle") or ""))
    signals = [item for item in sentences if any(term in item for term in CAPITAL_TERMS + RISK_TERMS)]
    selected = (signals or sentences)[:2]
    excerpt = "".join(selected)
    if len(excerpt) > 230:
        excerpt = excerpt[:229].rstrip("，；。") + "。"
    return {
        "sourceUrl": final_url,
        "pdfSha256": digest(raw),
        "textSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "parser": parser,
        "discoverySourceUrl": discovery_url,
        "discoveryPdfSha256": discovery_pdf_sha,
        "hkexNewsId": hkex_news_id,
        "excerpt": excerpt or title,
        "fullText": text,
        "textQuality": quality,
    }


def run_cninfo(start: str, end: str) -> Path:
    output = V2 / "data" / "daily" / "listed" / f"cninfo-announcements-{end}.json"
    command = [
        sys.executable,
        str(V2 / "scripts" / "fetch_listed_announcements.py"),
        "--start-date", start,
        "--end-date", end,
        "--companies", str(V2_UNIVERSE_PATH),
        "--output", str(output),
    ]
    completed = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"CNINFO逐主体检索失败：{completed.stdout[-2000:]}")
    return output


def hkex_review(day: str, slot: str) -> Path:
    registry = json.loads(HKEX_REGISTRY.read_text(encoding="utf-8"))
    universe = {str(row.get("securityCode") or "").split(".")[0].zfill(5) for row in load_listed_universe(V2_UNIVERSE_PATH) if row.get("market") == "HK"}
    issuers = registry.get("issuers") or []
    if {str(row.get("securityCode") or "") for row in issuers} != universe:
        raise ValueError("HKEX注册表与V2 L2正式观察池不一致")
    compact = day.replace("-", "")
    reviews: list[dict[str, Any]] = []
    for issuer in issuers:
        params = {
            "sortDir": "0", "sortByOptions": "DateTime", "category": "0", "market": "SEHK",
            "stockId": str(issuer["stockId"]), "documentType": "-1", "fromDate": compact,
            "toDate": compact, "title": "",
        }
        url = f"{HKEX_ENDPOINT}?{urlencode(params)}"
        final_url, raw = fetch_bytes(url)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        records = payload.get("searchResult") or payload.get("records") or payload.get("data") or []
        if not isinstance(records, list):
            records = []
        reviews.append({
            **issuer,
            "httpStatus": 200,
            "recordCount": len(records),
            "responseSha256": digest(raw),
            "requestUrl": final_url,
            "records": records[:30],
        })
        time.sleep(0.12)
    path = V2 / "data" / "daily" / "listed" / f"hkex-review-{day}.json"
    payload = {
        "schemaVersion": "2.0", "channel": "listed", "date": day, "slot": slot,
        "scannedAt": datetime.now(TZ).isoformat(timespec="seconds"),
        "source": HKEX_ENDPOINT, "queryMethod": registry["queryMethod"], "status": "completed",
        "companyCount": len(reviews), "announcementCount": sum(row["recordCount"] for row in reviews), "reviews": reviews,
    }
    write(path, payload)
    return path


def attach_hkex_summary(raw_path: Path, hkex_path: Path) -> None:
    """Bind the independent HKEX receipt into the CNINFO scan provenance.

    The M&A scanner consumes the CNINFO receipt as its listed-company coverage
    proof.  Linking the hash-checked HKEX receipt here makes the 14 L2 checks
    part of the same V2 acquisition record instead of a manual sidecar.
    """
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    review = json.loads(hkex_path.read_text(encoding="utf-8"))
    summary = raw.setdefault("_summary", {})
    summary["hkexOfficialReview"] = {
        "status": review.get("status"),
        "companyCount": review.get("companyCount"),
        "announcementCount": review.get("announcementCount"),
        "slot": review.get("slot"),
        "path": hkex_path.relative_to(ROOT).as_posix(),
        "sha256": digest(hkex_path.read_bytes()),
    }
    write(raw_path, raw)


def classify(title: str) -> str:
    if any(term in title for term in RISK_TERMS):
        return "risk"
    if any(term in title for term in CAPITAL_TERMS):
        return "capital"
    if any(term in title for term in OPPORTUNITY_TERMS):
        return "opportunity"
    return "dynamic"


def curated_daily(day: str, raw_path: Path, hkex_path: Path, editorial_brief_path: Path | None = None) -> Path:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    rows = [item for key, value in raw.items() if not key.startswith("_") and isinstance(value, list) for item in value if isinstance(item, dict)]
    evidence: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for row in rows:
        try:
            proof = pdf_excerpt(row, day)
            title = clean_text(str(row.get("announcementTitle") or ""))
            evidence.append({
                "matter_id": str(row["announcementId"]), "company": str(row.get("_matchedCompanyName") or row.get("secName") or ""),
                "title": title, "publishedAt": day_from_timestamp(row.get("announcementTime")) or day,
                "kind": classify(title), "body": proof["excerpt"], **proof,
            })
        except Exception as error:  # fail closed only for customer inclusion; raw remains auditable.
            failures.append({
                "announcementId": str(row.get("announcementId") or ""),
                "company": str(row.get("_matchedCompanyName") or row.get("secName") or ""),
                "title": clean_text(str(row.get("announcementTitle") or "")),
                "sourceUrl": official_url(row),
                "status": "pending_manual_verification",
                "discoveryStatus": "official_announcement_found_text_extraction_failed",
                "customerDisposition": "excluded_from_customer_highlights_pending_reliable_text",
                "error": f"{type(error).__name__}:{error}",
            })
    evidence.sort(key=lambda item: (item["publishedAt"], item["matter_id"]), reverse=True)
    hkex = json.loads(hkex_path.read_text(encoding="utf-8"))
    report_args = {
        "day": day,
        "evidence": evidence,
        "rejected": failures,
        "raw_summary": raw.get("_summary", {}),
        "hkex_company_count": int(hkex.get("companyCount") or 0),
    }
    if editorial_brief_path:
        brief = json.loads(editorial_brief_path.read_text(encoding="utf-8"))
        curated = build_editorial_report_from_brief(brief=brief, **report_args)
        curated["editorialBriefPath"] = editorial_brief_path.relative_to(ROOT).as_posix()
        curated["editorialBriefSha256"] = digest(editorial_brief_path.read_bytes())
    else:
        curated = build_editorial_report(**report_args)
    curated["sourceEvidence"] = [
        {key: value for key, value in row.items() if key != "fullText"}
        for row in evidence
    ]
    curated["sourceAcquisitionStatus"] = {
        "officialAnnouncementsDiscovered": len(rows),
        "reliableTextExtracted": len(evidence),
        "officialAnnouncementTextExtractionFailed": len(failures),
        "hasPendingOfficialTextVerification": bool(failures),
    }
    curated["rawPath"] = raw_path.relative_to(ROOT).as_posix()
    curated["hkexPath"] = hkex_path.relative_to(ROOT).as_posix()
    if rows and not evidence:
        raise ValueError("当日存在公告但没有可提取的正式PDF正文，拒绝生成客户精读稿")
    path = V2 / "data" / "daily" / "listed" / f"listed-official-{day}.json"
    write(path, curated)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="准备V2上市公司原文精读输入")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slot", choices=("morning", "midday", "closing"), default="morning")
    parser.add_argument("--start-date")
    parser.add_argument(
        "--reuse-frozen-raw",
        action="store_true",
        help="维护模式：复用同日已冻结的 CNINFO/HKEX 回执，仅补取其列明的官方 PDF 并重建客户稿",
    )
    parser.add_argument(
        "--editorial-brief",
        help="维护模式专用：仅可与 --reuse-frozen-raw 同用，按官方公告ID绑定精选结论",
    )
    args = parser.parse_args()
    day = date.fromisoformat(args.date)
    start = args.start_date or previous_trade_day(day).isoformat()
    if args.reuse_frozen_raw:
        raw_path = V2 / "data" / "daily" / "listed" / f"cninfo-announcements-{day.isoformat()}.json"
        hkex_path = V2 / "data" / "daily" / "listed" / f"hkex-review-{day.isoformat()}.json"
        if not raw_path.is_file() or not hkex_path.is_file():
            raise FileNotFoundError("维护重建缺少同日冻结的 CNINFO 或 HKEX 回执")
    else:
        raw_path = run_cninfo(start, day.isoformat())
        hkex_path = hkex_review(day.isoformat(), args.slot)
        attach_hkex_summary(raw_path, hkex_path)
    brief_path = Path(args.editorial_brief).resolve() if args.editorial_brief else None
    curated_path = curated_daily(day.isoformat(), raw_path, hkex_path, brief_path)
    print(json.dumps({"status": "completed", "date": day.isoformat(), "raw": raw_path.relative_to(ROOT).as_posix(), "hkex": hkex_path.relative_to(ROOT).as_posix(), "curated": curated_path.relative_to(ROOT).as_posix()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
