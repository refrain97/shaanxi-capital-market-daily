#!/usr/bin/env python3
"""Verify and merge a V2-owned SOE evidence batch into the annual event store."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
from datetime import date
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "v2/data/source/soe/events-2026.json"
EVIDENCE_DIR = ROOT / "v2/data/source/soe/evidence"
SCAN_DIR = ROOT / "v2/data/source/soe/scans"
ALLOWED_CATEGORIES = {"资本金融", "项目资产", "风险治理", "产业经营", "综合动态"}
# Evidence collection occasionally uses a natural-language synonym.  Normalize
# only known, reviewed aliases before validation; unknown labels still fail
# closed and cannot silently enter the customer taxonomy.
CATEGORY_ALIASES = {"资本运作": "资本金融"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def stable_id(url: str) -> str:
    return "soe-v2-" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]


def visible_text(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def fetch_and_verify(row: dict) -> dict:
    request = Request(row["sourceUrl"], headers={"User-Agent": "Mozilla/5.0 V2-SOE-Verifier"})
    with urlopen(request, timeout=20, context=ssl.create_default_context()) as response:
        raw = response.read(1_500_000)
        status = response.status
    if status != 200:
        raise ValueError(f"SOE原文HTTP异常：{row['sourceUrl']} -> {status}")
    text = visible_text(raw)
    mode = row.get("verificationMode", "content")
    if mode == "content":
        for expected in (row["expectedTitleContains"], row["expectedDate"]):
            if expected and expected not in text:
                raise ValueError(f"SOE原文证据不匹配：{row['sourceUrl']} 缺少 {expected}")
    elif mode != "official_account_url_preserved_from_migration":
        raise ValueError(f"未知SOE核验模式：{mode}")
    return {
        "url": row["sourceUrl"],
        "httpStatus": status,
        "verificationMode": mode,
        "titleEvidence": row.get("expectedTitleContains", ""),
        "dateEvidence": row.get("expectedDate", ""),
    }


def validate_batch(batch: dict, day: str, slot: str) -> None:
    if batch.get("channel") != "soe":
        raise ValueError("SOE证据批次栏目错误")
    if batch.get("scanAsOf") != day or batch.get("slot") != slot:
        raise ValueError("SOE证据批次日期或时点不匹配")
    if batch.get("migrationReference", {}).get("runtimeInput") is not False:
        raise ValueError("迁移参考不得成为V2日常运行输入")
    urls: set[str] = set()
    for row in batch.get("records", []):
        row["category"] = CATEGORY_ALIASES.get(str(row.get("category") or ""), row.get("category"))
        date.fromisoformat(row["publishedAt"])
        if row["publishedAt"] > day:
            raise ValueError("SOE事件日期不得晚于扫描日期")
        if row["category"] not in ALLOWED_CATEGORIES:
            raise ValueError(f"未知SOE分类：{row['category']}")
        if not row.get("entities") or not row.get("title") or not row.get("sourceUrl"):
            raise ValueError("SOE事件缺少主体、标题或原文")
        if row["sourceUrl"] in urls:
            raise ValueError(f"SOE证据批次原文重复：{row['sourceUrl']}")
        urls.add(row["sourceUrl"])


def main() -> int:
    parser = argparse.ArgumentParser(description="刷新V2自有国企动态事件库")
    parser.add_argument("--date", required=True)
    parser.add_argument("--slot", choices=("morning", "midday", "closing"), default="morning")
    parser.add_argument("--evidence")
    parser.add_argument(
        "--verify-network",
        action="store_true",
        help="重新请求每条官方原文并校验标题/日期；自动化正式扫描应启用",
    )
    args = parser.parse_args()
    day = date.fromisoformat(args.date).isoformat()
    evidence_path = (
        ROOT / args.evidence
        if args.evidence
        else EVIDENCE_DIR / f"verified-{day}-{args.slot}.json"
    )
    if not evidence_path.is_file():
        raise FileNotFoundError(
            f"缺少V2 SOE专用证据批次：{evidence_path.relative_to(ROOT)}；"
            "不能只凭record_channel_scan声明扫描完成"
        )
    batch = load(evidence_path)
    validate_batch(batch, day, args.slot)
    checks = [
        fetch_and_verify(row)
        if args.verify_network
        else {
            "url": row["sourceUrl"],
            "httpStatus": "recorded",
            "verificationMode": row.get("verificationMode", "content"),
            "titleEvidence": row.get("expectedTitleContains", ""),
            "dateEvidence": row.get("expectedDate", ""),
        }
        for row in batch["records"]
    ]

    store = load(STORE)
    by_url = {
        row.get("sourceUrl"): row
        for row in store.get("records", [])
        if row.get("sourceUrl")
    }
    for row in batch["records"]:
        by_url[row["sourceUrl"]] = {
            "candidateId": stable_id(row["sourceUrl"]),
            "publishedAt": row["publishedAt"],
            "entities": row["entities"],
            "title": row["title"],
            "category": row["category"],
            "sourceName": row["sourceName"],
            "sourceUrl": row["sourceUrl"],
            "sourceQuality": row["sourceQuality"],
            "noveltyStatus": "verified_v2_import",
            "normalizationStatus": "official_source_verified",
            "verificationEvidence": evidence_path.relative_to(ROOT).as_posix(),
            **({"correctionNote": row["correctionNote"]} if row.get("correctionNote") else {}),
            **({"verificationNote": row["verificationNote"]} if row.get("verificationNote") else {}),
        }
    records = sorted(
        by_url.values(),
        key=lambda row: (row.get("publishedAt", ""), row.get("candidateId", "")),
    )
    dates = [row["publishedAt"] for row in records if row.get("publishedAt")]
    entities = {
        entity
        for row in records
        for entity in row.get("entities", [])
    }
    store.update(
        {
            "schemaVersion": "1.0",
            "channel": "soe",
            "novelty": "backfill_and_v2_verified_imports",
            "period": {"startDate": min(dates), "endDate": max(dates)},
            "generatedAt": f"{day}T00:00:00+08:00",
            "scanAsOf": day,
            "lastScanEvidence": evidence_path.relative_to(ROOT).as_posix(),
            "status": "PARTIAL_HISTORY_WITH_CURRENT_OFFICIAL_SCAN",
            "limits": [
                "当前事件库最早记录为2026-05-21，不能据此声明1月至5月20日全量",
                "新增事项须经V2专用证据批次和原始官方链接核验后入库"
            ],
            "summary": {
                "recordCount": len(records),
                "earliestPublishedAt": min(dates),
                "latestPublishedAt": max(dates),
                "entityCount": len(entities),
                "verifiedImportCount": sum(
                    row.get("noveltyStatus") == "verified_v2_import" for row in records
                ),
            },
            "records": records,
        }
    )
    write(STORE, store)
    receipt = {
        "schemaVersion": "1.0",
        "channel": "soe",
        "scanAsOf": day,
        "slot": args.slot,
        "status": "completed",
        "eventOnScanDate": batch["scanConclusion"]["eventOnScanDate"],
        "latestVerifiedEventDate": max(dates),
        "importedOrReverified": len(batch["records"]),
        "rejectedCandidates": batch.get("rejectedCandidates", []),
        "evidencePath": evidence_path.relative_to(ROOT).as_posix(),
        "evidenceSha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        "networkVerified": args.verify_network,
        "sourceChecks": checks,
    }
    receipt_path = SCAN_DIR / f"scan-{day}-{args.slot}.json"
    write(receipt_path, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
