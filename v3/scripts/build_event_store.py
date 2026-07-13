#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/runtime/event-store.sqlite3"
INPUTS = {
    "dashboard": "data/sample/dashboard-2026-07-10.json",
    "ma_projects": "data/ma-projects/latest.json",
    "pre_ipo": "data/pre-ipo/latest.json",
    "private_fund": "data/private-fund/snapshots/latest.json",
    "tender": "data/tender/scans/latest.json",
    "listed_backfill": "data/backfill/listed/normalized-2026.json",
    "private_backfill": "data/backfill/private-fund/normalized-2026.json",
    "tender_backfill": "data/backfill/tender/merged-2026.json",
    "ma_backfill": "data/backfill/ma/normalized-2026.json",
    "equity_backfill": "data/backfill/equity-financing/normalized-2026.json",
    "soe_backfill": "data/backfill/soe/normalized-2026.json",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any, length: int | None = None) -> str:
    result = hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
    return result[:length] if length else result


def load(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class Store:
    def __init__(self, connection: sqlite3.Connection, seen_at: str) -> None:
        self.db = connection
        self.seen_at = seen_at

    def entity(self, entity_id: str, entity_type: str, name: str, **attributes: Any) -> None:
        region = attributes.pop("region", None)
        status = attributes.pop("status", None)
        self.db.execute(
            """INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(entity_id) DO UPDATE SET entity_type=excluded.entity_type,
               canonical_name=excluded.canonical_name, region=excluded.region,
               status=excluded.status, attributes_json=excluded.attributes_json,
               updated_at=excluded.updated_at""",
            (entity_id, entity_type, name, region, status, canonical(attributes), self.seen_at),
        )

    def source(self, source_id: str, record: dict[str, Any]) -> None:
        known = {"sourceType", "sourceName", "url", "sourceUrl", "title", "publishedAt", "fetchedAt", "sourceQuality"}
        attrs = {key: value for key, value in record.items() if key not in known}
        self.db.execute(
            """INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(source_id) DO UPDATE SET source_type=excluded.source_type,
               source_name=excluded.source_name, url=excluded.url, title=excluded.title,
               published_at=excluded.published_at, fetched_at=excluded.fetched_at,
               source_quality=excluded.source_quality, attributes_json=excluded.attributes_json""",
            (
                source_id,
                record.get("sourceType") or "web_record",
                record.get("sourceName"),
                record.get("url") or record.get("sourceUrl"),
                record.get("title"),
                record.get("publishedAt"),
                record.get("fetchedAt"),
                record.get("sourceQuality"),
                canonical(attrs),
            ),
        )

    def event(self, event: dict[str, Any], source_ids: Iterable[str] = (), timeline: Iterable[dict[str, Any]] = ()) -> None:
        event_id = str(event["eventId"])
        event_key = str(event.get("eventKey") or event_id)
        payload = canonical(event)
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.db.execute(
            """INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(event_id) DO UPDATE SET event_key=excluded.event_key,
               channel=excluded.channel, event_type=excluded.event_type,
               primary_entity_id=excluded.primary_entity_id, title=excluded.title,
               summary=excluded.summary, published_at=excluded.published_at,
               discovered_at=excluded.discovered_at, deadline_at=excluded.deadline_at,
               event_status=excluded.event_status, novelty_status=excluded.novelty_status,
               quality_status=excluded.quality_status, payload_hash=excluded.payload_hash,
               payload_json=excluded.payload_json, last_seen_at=excluded.last_seen_at""",
            (
                event_id, event_key, event["channel"], event["eventType"], event.get("primaryEntityId"),
                event["title"], event.get("summary"), event.get("publishedAt"), event.get("discoveredAt"),
                event.get("deadlineAt"), event.get("eventStatus"), event.get("noveltyStatus"),
                event.get("qualityStatus"), payload_hash, payload, self.seen_at, self.seen_at,
            ),
        )
        self.db.execute(
            "INSERT OR IGNORE INTO event_versions VALUES (?, ?, ?, ?)",
            (event_id, payload_hash, self.seen_at, payload),
        )
        for source_id in source_ids:
            self.db.execute("INSERT OR IGNORE INTO event_sources VALUES (?, ?, 'evidence')", (event_id, source_id))
        for item in timeline:
            timeline_id = f"tl-{digest([event_id, item.get('at'), item.get('label')], 20)}"
            self.db.execute(
                "INSERT OR IGNORE INTO event_timeline VALUES (?, ?, ?, ?, ?, ?)",
                (timeline_id, event_id, item.get("at"), item.get("label") or "节点", item.get("stageAfter"), canonical(item.get("sourceIds") or [])),
            )

    def candidate(self, item: dict[str, Any], channel: str, source_ids: Iterable[str]) -> None:
        candidate_id = str(item["candidateId"])
        payload = canonical(item)
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.db.execute(
            """INSERT INTO event_candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(candidate_id) DO UPDATE SET primary_entity_id=excluded.primary_entity_id,
               event_key_seed=excluded.event_key_seed, title=excluded.title,
               published_at=excluded.published_at, rm_category=excluded.rm_category,
               rm_subcategory=excluded.rm_subcategory, business_priority=excluded.business_priority,
               novelty_status=excluded.novelty_status, normalization_status=excluded.normalization_status,
               payload_hash=excluded.payload_hash, payload_json=excluded.payload_json, updated_at=excluded.updated_at""",
            (candidate_id, channel, item.get("primaryEntityId"), item.get("eventKeySeed") or candidate_id,
             item["title"], item.get("publishedAt"), item.get("rmCategory"), item.get("rmSubcategory"),
             item.get("businessPriority"), item.get("noveltyStatus") or "backfill",
             item.get("normalizationStatus") or "pending", payload_hash, payload, self.seen_at),
        )
        for source_id in source_ids:
            self.db.execute("INSERT OR IGNORE INTO candidate_sources VALUES (?, ?)", (candidate_id, source_id))


def import_dashboard(store: Store, data: dict[str, Any]) -> int:
    for entity in data.get("entities", []):
        known = {"entityId", "entityType", "canonicalName", "region", "status"}
        store.entity(entity["entityId"], entity["entityType"], entity["canonicalName"], **{k: v for k, v in entity.items() if k not in known}, region=entity.get("region"), status=entity.get("status"))
    for source in data.get("sources", []):
        store.source(source["sourceRecordId"], source)
    for event in data.get("events", []):
        store.event(event, event.get("sourceRecordIds", []), event.get("timeline", []))
    return len(data.get("events", []))


def import_ma(store: Store, data: dict[str, Any]) -> int:
    for project in data.get("projects", []):
        for source in project.get("sourceRecords", []):
            store.source(source["sourceRecordId"], source)
        milestones = project.get("milestones", [])
        published = milestones[0].get("at") if milestones else data.get("asOf")
        event = {
            "eventId": f"evt-{project['maProjectId']}", "eventKey": project["maProjectId"], "channel": "ma",
            "eventType": "ma_project", "title": project["title"], "summary": project.get("significance"),
            "publishedAt": published, "deadlineAt": next((m.get("at") for m in milestones if m.get("at") and str(m["at"]) > str(data.get("asOf", ""))[:10]), None),
            "eventStatus": project.get("stage"), "noveltyStatus": "tracked", "qualityStatus": project.get("sourceStatus"),
            "project": project,
        }
        store.event(event, [s["sourceRecordId"] for s in project.get("sourceRecords", [])], milestones)
    return len(data.get("projects", []))


def import_pre_ipo(store: Store, data: dict[str, Any]) -> int:
    count = 0
    for profile in data.get("profiles", []):
        entity_id = profile["enterpriseId"]
        store.entity(entity_id, "pre_ipo_enterprise", profile["name"], status=profile.get("listingStage"), reserveTier=profile.get("reserveTier"), reserveRank=profile.get("reserveRank"))
        for index, milestone in enumerate(profile.get("milestones", []), start=1):
            source_ids: list[str] = []
            if milestone.get("sourceUrl"):
                source_id = f"src-preipo-{digest(milestone['sourceUrl'], 20)}"
                store.source(source_id, {"sourceType": "authoritative_attachment", "sourceName": "上市后备或项目公开资料", "sourceUrl": milestone["sourceUrl"], "title": milestone.get("label"), "publishedAt": milestone.get("at"), "sourceQuality": profile.get("sourceStatus")})
                source_ids.append(source_id)
            event_id = f"evt-{entity_id}-{digest([index, milestone], 14)}"
            store.event({"eventId": event_id, "eventKey": event_id, "channel": "pre_ipo", "eventType": milestone.get("type") or "listing_progress", "primaryEntityId": entity_id, "title": f"{profile['name']}：{milestone.get('label')}", "summary": milestone.get("label"), "publishedAt": milestone.get("at"), "eventStatus": profile.get("listingStage"), "noveltyStatus": "tracked", "qualityStatus": profile.get("sourceStatus"), "milestone": milestone}, source_ids, [milestone])
            count += 1
    for financing in data.get("financingRecords", []):
        source_id = f"src-{financing['financingId']}"
        store.source(source_id, {"sourceType": "financing_disclosure", "sourceName": "企业公开信息", "sourceUrl": financing.get("sourceUrl"), "title": financing["financingId"], "publishedAt": financing.get("announcedAt"), "sourceQuality": financing.get("sourceQuality")})
        store.event({"eventId": f"evt-{financing['financingId']}", "eventKey": financing["financingId"], "channel": "equity_financing", "eventType": "financing_round", "primaryEntityId": financing.get("enterpriseId"), "title": f"股权融资：{financing.get('round')}", "summary": financing.get("amountText"), "publishedAt": financing.get("announcedAt"), "eventStatus": "disclosed", "noveltyStatus": "tracked", "qualityStatus": financing.get("verificationStatus"), "financing": financing}, [source_id])
        count += 1
    return count


def import_private(store: Store, data: dict[str, Any]) -> int:
    manager_ids: dict[str, str] = {}
    for manager in data.get("topManagers", []):
        manager_ids[manager["managerName"]] = manager["managerId"]
        store.entity(manager["managerId"], "private_fund_manager", manager["managerName"], status="active", registerNo=manager.get("registerNo"), officeProvince=manager.get("officeProvince"), activityScore=manager.get("activityScore"))
    count = 0
    for product in data.get("newProducts", []):
        manager_id = manager_ids.get(product.get("managerName", ""))
        event_id = f"evt-private-product-{product['fundNo']}"
        source_id = f"src-private-product-{product['fundNo']}"
        store.source(source_id, {"sourceType": "amac_filing", "sourceName": "中国证券投资基金业协会", "sourceUrl": product.get("sourceUrl"), "title": product.get("fundName"), "publishedAt": product.get("filingDate"), "sourceQuality": "official"})
        store.event({"eventId": event_id, "eventKey": event_id, "channel": "private_fund", "eventType": "new_fund_filing", "primaryEntityId": manager_id, "title": f"{product.get('managerName')}备案{product.get('fundName')}", "summary": f"托管人：{product.get('custodian') or '未披露'}", "publishedAt": product.get("filingDate"), "eventStatus": "filed", "noveltyStatus": "new", "qualityStatus": "verified", "product": product}, [source_id])
        count += 1
    for change in data.get("personnelChanges", []):
        event_id = f"evt-private-person-{digest(change, 20)}"
        store.event({"eventId": event_id, "eventKey": event_id, "channel": "private_fund", "eventType": "personnel_change", "primaryEntityId": manager_ids.get(change.get("managerName", "")), "title": change.get("title") or f"{change.get('managerName')}人员变化", "summary": change.get("note"), "publishedAt": change.get("at") or data.get("asOf"), "eventStatus": "changed", "noveltyStatus": "new", "qualityStatus": change.get("verificationStatus") or "pending", "change": change})
        count += 1
    return count


def import_tender(store: Store, data: dict[str, Any]) -> int:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in data.get("records", []):
        project_key = record.get("projectFingerprint") or f"record:{record['recordId']}"
        groups.setdefault(project_key, []).append(record)
    new_ids = set(data.get("newRecordIds", []))
    for project_key, records in groups.items():
        records.sort(key=lambda item: item.get("publishedAt") or item.get("discoveredAt") or "")
        latest = records[-1]
        source_ids: list[str] = []
        timeline: list[dict[str, Any]] = []
        for record in records:
            source_id = f"src-tender-{record['recordId']}"
            source_ids.append(source_id)
            store.source(source_id, {"sourceType": "official_tender_notice", "sourceName": record.get("sourceId"), "sourceUrl": record.get("sourceUrl"), "title": record.get("title"), "publishedAt": record.get("publishedAt"), "fetchedAt": record.get("discoveredAt"), "sourceQuality": record.get("sourceQuality")})
            timeline.append({"at": record.get("publishedAt") or record.get("discoveredAt"), "label": f"{record.get('stage') or '公告'}：{record.get('title') or '项目节点'}", "stageAfter": record.get("classification"), "sourceIds": [source_id]})
        event_id = f"evt-tender-{digest(project_key, 20)}"
        deadlines = [record["deadlineAt"] for record in records if record.get("deadlineAt")]
        store.event({"eventId": event_id, "eventKey": f"tender:{project_key}", "channel": "tender", "eventType": latest.get("stage") or "tender_notice", "title": latest.get("title") or "招投标项目", "summary": latest.get("contentExcerpt"), "publishedAt": records[0].get("publishedAt"), "discoveredAt": records[0].get("discoveredAt"), "deadlineAt": max(deadlines) if deadlines else None, "eventStatus": latest.get("classification"), "noveltyStatus": "new" if any(record["recordId"] in new_ids for record in records) else "tracked", "qualityStatus": latest.get("eligibilityStatus"), "projectFingerprint": project_key, "records": records}, source_ids, timeline)
    return len(groups)


def import_listed_backfill(store: Store, data: dict[str, Any], universe: dict[str, Any]) -> int:
    for entity in universe.get("entities", []):
        known = {"entityId", "canonicalName", "universeTier", "inclusionReason"}
        store.entity(entity["entityId"], "listed_company", entity["canonicalName"], status="active", universeTier=entity.get("universeTier"), inclusionReason=entity.get("inclusionReason"), **{k: v for k, v in entity.items() if k not in known})
    for source in data.get("sources", []):
        store.source(source["sourceRecordId"], {"sourceType": "official_announcement", "sourceName": "巨潮资讯", **source})
    for item in data.get("candidates", []):
        store.candidate({"candidateId": item["eventCandidateId"], **item}, "listed", item.get("sourceRecordIds", []))
    return len(data.get("candidates", []))


def import_private_backfill(store: Store, data: dict[str, Any]) -> int:
    count = 0
    for kind, items in (("new_fund_filing", data.get("products", [])), ("manager_registration", data.get("newManagers", [])), ("manager_cancellation", data.get("cancellations", []))):
        for item in items:
            manager_name = item.get("managerName") or "未知管理人"
            entity_id = f"private-{digest(manager_name, 18)}"
            store.entity(entity_id, "private_fund_manager", manager_name, status="tracked")
            identity = item.get("fundNo") or item.get("registerNo") or item.get("orgCode") or digest(item, 16)
            candidate_id = f"private-backfill-{kind}-{identity}"
            source_id = f"src-{candidate_id}"
            published_at = item.get("filingDate") or item.get("registerDate") or item.get("cancelDate")
            title = item.get("fundName") or f"{manager_name}{'登记' if kind == 'manager_registration' else '注销'}"
            store.source(source_id, {"sourceType": "amac_public_record", "sourceName": "中国证券投资基金业协会", "sourceUrl": item.get("sourceUrl"), "title": title, "publishedAt": published_at, "sourceQuality": "official"})
            store.candidate({"candidateId": candidate_id, "primaryEntityId": entity_id, "eventKeySeed": f"{kind}:{identity}", "title": title, "publishedAt": published_at, "noveltyStatus": "backfill", "normalizationStatus": "source_verified_diff_pending", "record": item}, "private_fund", [source_id])
            count += 1
    return count


def import_tender_backfill(store: Store, data: dict[str, Any]) -> int:
    source_ids_by_record: dict[str, str] = {}
    for record in data.get("records", []):
        source_id = f"src-tender-backfill-{digest(record['recordId'], 20)}"
        source_ids_by_record[record["recordId"]] = source_id
        store.source(source_id, {"sourceType": "official_tender_notice", "sourceName": record.get("sourceId"), "sourceUrl": record.get("sourceUrl"), "title": record.get("title"), "publishedAt": record.get("publishedAt"), "fetchedAt": record.get("discoveredAt"), "sourceQuality": record.get("sourceQuality"), "discoveryMode": "backfill"})
    for project in data.get("projects", []):
        source_ids = [source_ids_by_record[record_id] for record_id in project.get("sourceRecordIds", []) if record_id in source_ids_by_record]
        store.candidate({"candidateId": project["candidateId"], "eventKeySeed": f"tender:{project['projectFingerprint']}", "title": project["title"], "publishedAt": project.get("firstPublishedAt"), "rmCategory": "金融招投标", "rmSubcategory": project.get("latestStage"), "businessPriority": "focus", "noveltyStatus": "backfill", "normalizationStatus": project.get("normalizationStatus"), "project": project}, "tender", source_ids)
    return len(data.get("projects", []))


def import_ma_backfill(store: Store, data: dict[str, Any]) -> int:
    for source in data.get("sources", []):
        store.source(source["sourceRecordId"], {"sourceType": "official_announcement", "sourceName": "巨潮资讯", **source})
    for project in data.get("projects", []):
        store.candidate({"candidateId": project["candidateId"], "primaryEntityId": project.get("primaryEntityId"), "eventKeySeed": project.get("eventKeySeed"), "title": project["title"], "publishedAt": project.get("firstPublishedAt"), "rmCategory": "资本运作", "rmSubcategory": "并购重组", "businessPriority": "focus", "noveltyStatus": "backfill", "normalizationStatus": project.get("normalizationStatus"), "project": project}, "ma", project.get("sourceRecordIds", []))
    return len(data.get("projects", []))


def import_equity_backfill(store: Store, data: dict[str, Any]) -> int:
    count = 0
    for item in data.get("milestones", []):
        if not item.get("sourceUrl"):
            continue
        source_ids: list[str] = []
        source_id = f"src-preipo-backfill-{digest(item['sourceUrl'], 20)}"
        store.source(source_id, {"sourceType": "listing_progress", "sourceName": "上市后备或交易所公开资料", "sourceUrl": item["sourceUrl"], "title": item["title"], "publishedAt": item.get("publishedAt"), "sourceQuality": item.get("sourceQuality")})
        source_ids.append(source_id)
        store.candidate({"candidateId": item["candidateId"], "primaryEntityId": item.get("primaryEntityId"), "eventKeySeed": f"preipo:{item.get('primaryEntityId')}:{item.get('eventType')}:{item.get('publishedAt')}", "title": f"{item.get('enterpriseName')}：{item.get('title')}", "publishedAt": item.get("publishedAt"), "rmCategory": "拟上市与股权融资", "rmSubcategory": item.get("eventType"), "businessPriority": "focus" if item.get("eventType") in {"hearing", "listed"} else "standard", "noveltyStatus": "backfill", "normalizationStatus": item.get("normalizationStatus"), "milestone": item}, "pre_ipo", source_ids)
        count += 1
    for financing in data.get("financingRecords", []):
        source_id = f"src-equity-backfill-{digest(financing.get('sourceUrl'), 20)}"
        store.source(source_id, {"sourceType": "financing_disclosure", "sourceName": "企业或投资机构公开信息", "sourceUrl": financing.get("sourceUrl"), "title": financing["financingId"], "publishedAt": financing.get("announcedAt"), "sourceQuality": financing.get("sourceQuality")})
        store.candidate({"candidateId": f"equity-backfill-{financing['financingId']}", "primaryEntityId": financing.get("enterpriseId"), "eventKeySeed": financing["financingId"], "title": f"股权融资：{financing.get('round')}", "publishedAt": financing.get("announcedAt"), "rmCategory": "拟上市与股权融资", "rmSubcategory": "股权融资", "businessPriority": "focus", "noveltyStatus": "backfill", "normalizationStatus": financing.get("verificationStatus"), "financing": financing}, "equity_financing", [source_id])
        count += 1
    return count


def import_soe_backfill(store: Store, data: dict[str, Any]) -> int:
    for item in data.get("records", []):
        source_id = f"src-{item['candidateId']}"
        store.source(source_id, {"sourceType": "sasac_or_group_site", "sourceName": item.get("sourceName"), "sourceUrl": item.get("sourceUrl"), "title": item["title"], "publishedAt": item.get("publishedAt"), "sourceQuality": item.get("sourceQuality")})
        store.candidate({"candidateId": item["candidateId"], "eventKeySeed": f"soe:{digest(item.get('sourceUrl'), 20)}", "title": item["title"], "publishedAt": item.get("publishedAt"), "rmCategory": "国企动态", "rmSubcategory": item.get("category"), "businessPriority": "focus" if item.get("category") in {"资本金融", "项目资产"} else "standard", "noveltyStatus": "backfill", "normalizationStatus": item.get("normalizationStatus"), "record": item}, "soe", [source_id])
    return len(data.get("records", []))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or update the V3 persistent event store.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    db_path = Path(args.db).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    seen_at = now_iso()
    run_id = f"event-store-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript((ROOT / "storage/schema.sql").read_text(encoding="utf-8"))
        connection.execute("INSERT INTO ingest_runs(run_id, started_at, status) VALUES (?, ?, 'RUNNING')", (run_id, seen_at))
        store = Store(connection, seen_at)
        connection.execute("DELETE FROM candidate_sources")
        connection.execute("DELETE FROM event_candidates")
        datasets = {name: load(path) for name, path in INPUTS.items()}
        for name, relative in INPUTS.items():
            payload = datasets[name]
            content_hash = digest(payload)
            snapshot_id = f"raw-{name}-{content_hash[:20]}"
            data_as_of = payload.get("meta", {}).get("asOf") if name == "dashboard" else payload.get("asOf") or payload.get("endDate") or payload.get("generatedAt")
            connection.execute("INSERT OR IGNORE INTO raw_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)", (snapshot_id, name, relative, content_hash, data_as_of, seen_at, canonical(payload)))
        universe = load("data/listed/universe.json")
        event_count = sum((import_dashboard(store, datasets["dashboard"]), import_ma(store, datasets["ma_projects"]), import_pre_ipo(store, datasets["pre_ipo"]), import_private(store, datasets["private_fund"]), import_tender(store, datasets["tender"])))
        candidate_count = sum((
            import_listed_backfill(store, datasets["listed_backfill"], universe),
            import_private_backfill(store, datasets["private_backfill"]),
            import_tender_backfill(store, datasets["tender_backfill"]),
            import_ma_backfill(store, datasets["ma_backfill"]),
            import_equity_backfill(store, datasets["equity_backfill"]),
            import_soe_backfill(store, datasets["soe_backfill"]),
        ))
        connection.execute("INSERT OR REPLACE INTO metadata VALUES ('schema_version', '1')")
        connection.execute("INSERT OR REPLACE INTO metadata VALUES ('last_successful_run', ?)", (run_id,))
        connection.execute("UPDATE ingest_runs SET finished_at=?, status='PASS', dataset_count=?, event_count=? WHERE run_id=?", (now_iso(), len(datasets), event_count, run_id))
        connection.commit()
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("raw_snapshots", "entities", "sources", "events", "event_versions", "event_timeline", "event_candidates")}
        summary = {"schemaVersion": "1", "runId": run_id, "status": "PASS", "database": str(db_path.relative_to(ROOT)), "counts": counts, "channelCounts": dict(connection.execute("SELECT channel, COUNT(*) FROM events GROUP BY channel ORDER BY channel")), "candidateChannelCounts": dict(connection.execute("SELECT channel, COUNT(*) FROM event_candidates GROUP BY channel ORDER BY channel")), "importedCandidateCount": candidate_count, "generatedAt": now_iso()}
        (ROOT / "data/runtime/event-store-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        connection.rollback()
        print(f"event store build failed: {exc}", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
