#!/usr/bin/env python3
"""Collect same-day V2 SOE evidence from the reviewed official source registry."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "v2"
CONFIG = V2 / "config/soe-sources.json"
EVIDENCE_DIR = V2 / "data/source/soe/evidence"
TZ = ZoneInfo("Asia/Shanghai")
DATE_RE = re.compile(r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})")
ANCHOR_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def visible(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.I | re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def fetch(url: str) -> tuple[str, bytes]:
    request = Request(url, headers={"User-Agent": "Shaanxi-Capital-Market-V2-SOE/2.0"})
    with urlopen(request, timeout=35) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        return response.geturl(), response.read(4_000_000)


def normalized_date(match: re.Match[str]) -> str:
    return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"


def candidates(list_url: str, raw: bytes, day: str) -> list[tuple[str, str]]:
    html = raw.decode("utf-8", errors="replace")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in ANCHOR_RE.finditer(html):
        before = re.sub(r"<[^>]+>", " ", html[max(0, match.start() - 450):match.end()])
        if day not in {normalized_date(item) for item in DATE_RE.finditer(before)}:
            continue
        title = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", match.group(2)))).strip()
        url = urljoin(list_url, unescape(match.group(1)))
        if len(title) < 6 or url in seen or not url.startswith(("https://", "http://")):
            continue
        seen.add(url)
        result.append((title, url))
    return result


def collect_source(source: dict[str, Any], day: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    final_url, raw = fetch(str(source["url"]))
    listing = visible(raw)
    found: list[dict[str, Any]] = []
    for title, article_url in candidates(final_url, raw, day):
        final_article, article_raw = fetch(article_url)
        text = visible(article_raw)
        if title[:12] not in text or day not in {normalized_date(item) for item in DATE_RE.finditer(text)}:
            continue
        found.append({
            "publishedAt": day,
            "entities": [source["entity"]],
            "title": title,
            "category": source["category"],
            "sourceName": source["sourceName"],
            "sourceUrl": final_article,
            "sourceQuality": "issuer_original" if "集团" in source["sourceName"] or "财金" in source["sourceName"] else "official_public_disclosure",
            "expectedTitleContains": title[:18],
            "expectedDate": day,
            "verificationNote": text[:360],
        })
    dates = [normalized_date(item) for item in DATE_RE.finditer(listing)]
    coverage = {
        "sourceName": source["sourceName"], "url": final_url, "httpStatus": 200,
        "responseSha256": digest(raw), "newestObservedDate": max(dates) if dates else "",
    }
    return coverage, found


def main() -> int:
    parser = argparse.ArgumentParser(description="采集V2国企动态官方证据批次")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slot", choices=("morning", "midday", "closing"), default="morning")
    args = parser.parse_args()
    day = date.fromisoformat(args.date).isoformat()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    coverage, records = [], []
    for source in config.get("sources") or []:
        item, found = collect_source(source, day)
        coverage.append(item)
        records.extend(found)
    unique = {row["sourceUrl"]: row for row in records}
    records = sorted(unique.values(), key=lambda row: (row["publishedAt"], row["sourceUrl"]), reverse=True)
    payload = {
        "schemaVersion": "2.0", "channel": "soe", "scanAsOf": day, "slot": args.slot,
        "generatedAt": datetime.now(TZ).isoformat(timespec="seconds"),
        "purpose": "V2官方来源注册表自动扫描与原文复核",
        "migrationReference": {"runtimeInput": False},
        "scanConclusion": {
            "eventOnScanDate": bool(records),
            "latestVerifiedEventDate": records[0]["publishedAt"] if records else "",
            "summary": "全部已登记官方来源完成请求；客户事项均回到原文页面核验。",
        },
        "sourceCoverage": {"coverageComplete": len(coverage) == len(config.get("sources") or []), "sources": coverage},
        "records": records,
        "rejectedCandidates": [],
    }
    path = EVIDENCE_DIR / f"verified-{day}-{args.slot}.json"
    write(path, payload)
    print(json.dumps({"status": "completed", "evidence": path.relative_to(ROOT).as_posix(), "records": len(records), "sources": len(coverage)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
