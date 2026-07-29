#!/usr/bin/env python3
"""Build V2's cross-channel observation pool and normalized event store."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def iso_date(value: Any) -> str:
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(value / 1000).date().isoformat()
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else ""


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "").strip() for part in parts)
    return f"{prefix}-{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def primary_source(
    name: str, title: str, url: str, published_at: str, quality: str
) -> dict:
    return {
        "sourceName": name,
        "title": title,
        "url": url,
        "publishedAt": iso_date(published_at),
        "sourceQuality": quality,
    }


def normalize_timeline(rows: list[dict]) -> list[dict]:
    deduped: dict[tuple[str, str], dict] = {}
    for row in rows:
        at = iso_date(row.get("at"))
        label = str(row.get("label") or "").strip()
        if at and label:
            deduped[(at, label)] = {
                "at": at,
                "label": label,
                "stageAfter": row.get("stageAfter") or "",
                "sourceIds": sorted(set(row.get("sourceIds") or [])),
            }
    return sorted(deduped.values(), key=lambda row: (row["at"], row["label"]))


def listed_events(contract: dict, day: str) -> list[dict]:
    daily = load(
        ROOT / contract["listedDailyDirectory"] / f"listed-official-{day}.json"
    )
    announcements = load(
        ROOT / contract["listedDailyDirectory"] / f"cninfo-announcements-{day}.json"
    )
    announcement_rows = [
        row
        for key, value in announcements.items()
        if not key.startswith("_") and isinstance(value, list)
        for row in value
        if isinstance(row, dict)
    ]
    by_id = {
        str(row.get("announcementId") or ""): row
        for row in announcement_rows
    }
    rows: list[tuple[str, dict]] = [
        (key, row)
        for key in ("risk_rows", "tiles", "capital_rows")
        for row in daily.get(key, [])
    ]
    rows.extend(
        ("fixed_columns", row)
        for group in daily.get("fixed_columns", [])
        for row in group.get("items", [])
    )
    result = []
    for group, row in rows:
        matter_id = re.sub(r"-fixed$", "", str(row.get("matter_id") or ""))
        announcement = by_id.get(matter_id, {})
        adjunct = str(announcement.get("adjunctUrl") or "").lstrip("/")
        source_url = f"https://static.cninfo.com.cn/{adjunct}" if adjunct else ""
        company = (
            row.get("company")
            or str(row.get("title") or "").split("｜", 1)[0]
            or announcement.get("secName")
            or ""
        )
        title = (
            announcement.get("announcementTitle")
            or row.get("event")
            or row.get("title")
            or matter_id
        )
        event_date = iso_date(announcement.get("announcementTime") or day)
        event_id = f"listed-{matter_id}" if matter_id else stable_id(
            "listed", company, title, event_date
        )
        result.append(
            {
                "eventId": event_id,
                "channel": "listed",
                "relatedEntities": [company],
                "shaanxiRelation": "V2上市公司正式观察池",
                "stage": group,
                "keyFacts": {
                    "title": title,
                    "summary": row.get("event")
                    or row.get("body")
                    or row.get("attention")
                    or "",
                },
                "primarySources": [
                    primary_source(
                        "巨潮资讯",
                        title,
                        source_url,
                        event_date,
                        "exchange_or_regulator_original",
                    )
                ] if source_url else [],
                "timeline": normalize_timeline(
                    [{"at": event_date, "label": title, "sourceIds": [matter_id]}]
                ),
                "scanAsOf": day,
                "latestEventDate": event_date,
                "sourceStatus": "verified" if source_url else "pending_primary_source",
            }
        )
    return list({row["eventId"]: row for row in result}.values())


def private_events(contract: dict, day: str) -> list[dict]:
    annual = load(ROOT / contract["privateAnnual"])
    daily = load(
        ROOT / contract["privateDailyDirectory"]
        / f"security-private-fund-daily-{day}.json"
    )
    rules = load(ROOT / contract["privateUniverse"])
    manager_tiers = {
        str(row.get("managerName") or ""): str(row.get("universeTier") or "PF1")
        for row in [
            *(rules.get("manualTerritorialTargets") or []),
            *(rules.get("relatedTargets") or []),
        ]
    }
    products = {
        str(row.get("fundNo") or ""): dict(row)
        for row in annual.get("products", [])
        if row.get("fundNo")
    }
    # The daily AMAC report contains a same-day, year-to-date query.  Merge it
    # into the immutable annual backfill instead of letting a stale backfill
    # erase a newly filed fund from the unified event store.
    for row in daily.get("shaanxiOfficeProducts", []):
        fund_no = str(row.get("fundNo") or "")
        if not fund_no:
            continue
        source_id = str(row.get("id") or "")
        products[fund_no] = {
            "fundNo": fund_no,
            "fundName": row.get("fundName") or "",
            "managerName": row.get("managerName") or "",
            "custodian": row.get("mandatorName") or row.get("custodian") or "",
            "filingDate": iso_date(row.get("putOnRecordDate")),
            "establishDate": iso_date(row.get("establishDate")),
            "universeTier": manager_tiers.get(str(row.get("managerName") or ""), "PF1"),
            "sourceUrl": (
                f"https://gs.amac.org.cn/amac-infodisc/res/pof/fund/{source_id}.html"
                if source_id else ""
            ),
        }
    result = []
    for row in products.values():
        if not row.get("fundNo") or not row.get("managerName") or not row.get("custodian"):
            # The daily quality gate reports this as a source failure.  Avoid
            # manufacturing an apparently verified event from an incomplete
            # AMAC row here.
            continue
        event_date = iso_date(row.get("filingDate"))
        result.append(
            {
                "eventId": f"private-{row['fundNo']}",
                "channel": "private",
                "relatedEntities": [
                    value for value in (row.get("managerName"), row.get("custodian")) if value
                ],
                "shaanxiRelation": row.get("universeTier") or "PF1",
                "stage": "fund_filed",
                "keyFacts": {
                    "fundName": row.get("fundName") or "",
                    "fundNo": row["fundNo"],
                    "managerName": row.get("managerName") or "",
                    "custodian": row.get("custodian") or "",
                    "establishDate": iso_date(row.get("establishDate")),
                },
                "primarySources": [
                    primary_source(
                        "中国证券投资基金业协会",
                        row.get("fundName") or row["fundNo"],
                        row.get("sourceUrl") or "",
                        event_date,
                        "regulator_original",
                    )
                ],
                "timeline": normalize_timeline(
                    [{"at": event_date, "label": "基金备案", "sourceIds": [row["fundNo"]]}]
                ),
                "scanAsOf": day,
                "latestEventDate": event_date,
                "sourceStatus": "verified",
            }
        )
    return result


def ma_events(contract: dict, day: str) -> list[dict]:
    source = load(ROOT / contract["maEvents"])
    result = []
    for row in source.get("projects", []):
        sources = [
            primary_source(
                item.get("sourceName") or "公告原文",
                item.get("title") or row["title"],
                item.get("url") or "",
                item.get("publishedAt") or "",
                item.get("sourceQuality") or "",
            )
            for item in row.get("sourceRecords", [])
            if item.get("url")
        ]
        confirmed_dates = [
            item["publishedAt"]
            for item in sources
            if item["publishedAt"] and not item.get("requiresExactDocument")
        ]
        timeline = normalize_timeline(row.get("milestones") or [])
        latest = max(confirmed_dates or [item["at"] for item in timeline] or [""])
        result.append(
            {
                "eventId": row["maProjectId"],
                "channel": "ma",
                "relatedEntities": [
                    value.strip()
                    for value in re.split(r"[；;]", row.get("partiesText") or "")
                    if value.strip()
                ],
                "shaanxiRelation": row.get("direction") or "",
                "stage": row.get("stage") or "",
                "keyFacts": {
                    "title": row["title"],
                    "amount": row.get("amountText") or "",
                    "industry": row.get("industry") or "",
                    "nextAction": row.get("nextAction") or "",
                    "entityType": row.get("entityType") or "",
                },
                "primarySources": sources,
                "timeline": timeline,
                "scanAsOf": day,
                "latestEventDate": latest,
                "sourceStatus": (
                    "verified"
                    if any(
                        item["sourceQuality"] == "exchange_or_regulator_original"
                        for item in sources
                    )
                    else "historical_pending"
                ),
            }
        )
    return result


def tender_events(contract: dict, day: str) -> list[dict]:
    source = load(ROOT / contract["tenderEvents"])
    result = []
    for row in source.get("opportunities", []):
        event_date = iso_date(row.get("publishDate"))
        sources = [
            primary_source(
                item.get("name") or "官方来源",
                row.get("projectName") or row["id"],
                item.get("url") or "",
                event_date,
                (
                    "official_public_disclosure"
                    if "官方" in str(row.get("sourceReliability") or "")
                    else "discovery_only"
                ),
            )
            for item in row.get("sources", [])
            if item.get("url")
        ]
        result.append(
            {
                "eventId": f"tender-{row['id']}",
                "channel": "tender",
                "relatedEntities": [row.get("buyer") or ""],
                "shaanxiRelation": row.get("location") or "陕西项目",
                "stage": row.get("stage") or "",
                "keyFacts": {
                    "title": row.get("projectName") or "",
                    "scale": row.get("projectScale") or "",
                    "deadlineOrOpening": row.get("deadlineOrOpening") or "",
                    "winnerStatus": row.get("winnerStatus") or "",
                },
                "primarySources": sources,
                "timeline": normalize_timeline(
                    [{"at": event_date, "label": row.get("stage") or "项目公告"}]
                ),
                "scanAsOf": day,
                "latestEventDate": event_date,
                "sourceStatus": (
                    "verified"
                    if any(item["sourceQuality"] == "official_public_disclosure" for item in sources)
                    else "historical_pending"
                ),
            }
        )
    return result


def soe_events(contract: dict, day: str) -> list[dict]:
    source = load(ROOT / contract["soeEvents"])
    result = []
    for row in source.get("records", []):
        event_date = iso_date(row.get("publishedAt"))
        result.append(
            {
                "eventId": row["candidateId"],
                "channel": "soe",
                "relatedEntities": row.get("entities") or [],
                "shaanxiRelation": "陕西国企及其资本、项目、产业动态",
                "stage": row.get("category") or "",
                "keyFacts": {"title": row.get("title") or ""},
                "primarySources": [
                    primary_source(
                        row.get("sourceName") or "官方来源",
                        row.get("title") or "",
                        row.get("sourceUrl") or "",
                        event_date,
                        row.get("sourceQuality") or "official_public_disclosure",
                    )
                ],
                "timeline": normalize_timeline(
                    [{"at": event_date, "label": row.get("title") or "公开动态"}]
                ),
                "scanAsOf": day,
                "latestEventDate": event_date,
                "sourceStatus": "verified" if row.get("sourceUrl") else "historical_pending",
            }
        )
    return result


def observation_pool(contract: dict, events: list[dict], day: str) -> dict:
    listed = load(ROOT / contract["listedUniverse"])
    private_daily = load(
        ROOT / contract["privateDailyDirectory"]
        / f"security-private-fund-daily-{day}.json"
    )
    private_rules = load(ROOT / contract["privateUniverse"])
    private_rows = [
        {
            "entityId": str(row.get("id") or row.get("registerNo") or ""),
            "legalName": row.get("managerName") or "",
            "displayName": row.get("managerName") or "",
            "tier": "PF1",
            "relation": "AMAC公示注册地或办公地在陕西",
        }
        for row in private_daily.get("raw", {}).get("shaanxiOfficeManagers", [])
    ]
    for row in [
        *private_rules.get("manualTerritorialTargets", []),
        *private_rules.get("relatedTargets", []),
    ]:
        private_rows.append(
            {
                "entityId": str(row["managerId"]),
                "legalName": row["managerName"],
                "displayName": row["managerName"],
                "tier": row["universeTier"],
                "relation": row["inclusionReason"],
            }
        )
    private_by_id = {row["entityId"]: row for row in private_rows}
    event_entities: dict[str, dict[str, dict]] = {"ma": {}, "tender": {}, "soe": {}}
    for event in events:
        if event["channel"] not in event_entities:
            continue
        for name in event["relatedEntities"]:
            if not name:
                continue
            event_entities[event["channel"]].setdefault(
                name,
                {
                    "entityId": stable_id(event["channel"], name),
                    "legalName": name,
                    "displayName": name,
                    "tier": "event-related",
                    "relation": event["shaanxiRelation"],
                },
            )
    return {
        "schemaVersion": "2.0",
        "owner": "V2",
        "scanAsOf": day,
        "channels": {
            "listed": [
                {
                    "entityId": row["entityId"],
                    "legalName": row["canonicalName"],
                    "displayName": row["canonicalName"],
                    "tier": row["universeTier"],
                    "relation": row["inclusionReason"],
                }
                for row in listed["entities"]
            ],
            "private": list(private_by_id.values()),
            **{
                channel: list(rows.values())
                for channel, rows in event_entities.items()
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    day = date.fromisoformat(args.date).isoformat()
    contract = load(ROOT / "v2/config/source-contract.json")
    builders = (
        listed_events,
        private_events,
        ma_events,
        tender_events,
        soe_events,
    )
    events = [row for builder in builders for row in builder(contract, day)]
    ids = [row["eventId"] for row in events]
    if len(ids) != len(set(ids)):
        raise ValueError("统一事件库存在重复 eventId")
    channels = {row["channel"] for row in events}
    if channels != {"listed", "private", "ma", "tender", "soe"}:
        raise ValueError(f"统一事件库栏目不完整：{sorted(channels)}")
    payload = {
        "schemaVersion": "2.0",
        "owner": "V2",
        "year": int(day[:4]),
        "scanAsOf": day,
        "generatedAt": f"{day}T00:00:00+08:00",
        "eventCount": len(events),
        "channelCounts": {
            channel: sum(row["channel"] == channel for row in events)
            for channel in sorted(channels)
        },
        "events": sorted(
            events,
            key=lambda row: (row["latestEventDate"], row["eventId"]),
            reverse=True,
        ),
    }
    event_target = ROOT / "v2/data/source/events/unified-2026.json"
    event_target.parent.mkdir(parents=True, exist_ok=True)
    event_target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pool = observation_pool(contract, events, day)
    pool_target = ROOT / "v2/data/source/observation-pool.json"
    pool_target.write_text(json.dumps(pool, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "scanAsOf": day,
                "eventCount": len(events),
                "channelCounts": payload["channelCounts"],
                "poolCounts": {
                    key: len(value) for key, value in pool["channels"].items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
