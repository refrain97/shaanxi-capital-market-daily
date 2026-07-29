#!/usr/bin/env python3
"""Create V2's strict, channel-level customer-release readiness manifest.

The manifest is intentionally a release gate, not a dashboard.  A generic
degraded source, stale input, missing original evidence, or divergence from
the V2 quality contract blocks publication.  The only exception is the tender
source contract's explicit official-equivalent coverage assertion; it remains
visible to customers as a source constraint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

from scanner_common import verify_receipt_artifacts


ROOT = Path(__file__).resolve().parents[2]
CHANNELS = ("listed", "private", "ma", "tender", "soe")
ACCEPTED_CHANNEL_STATUSES = {"completed", "no_new"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tender_constraint_release_eligible(receipt: dict) -> bool:
    eligibility = receipt.get("releaseEligibility") or {}
    return bool(
        receipt.get("status") == "degraded"
        and receipt.get("coverageComplete")
        and receipt.get("networkVerified")
        and eligibility.get("eligible") is True
        and eligibility.get("mode")
        == "official_equivalent_coverage_with_supplemental_source_constraint"
        and eligibility.get("constrainedSourceIds")
    )


def channel_release_eligible(channel: str, row: dict, tender_receipt: dict) -> bool:
    if row.get("status") in ACCEPTED_CHANNEL_STATUSES:
        return True
    return bool(
        channel == "tender"
        and row.get("status") == "degraded"
        and row.get("releaseEligible") is True
        and tender_constraint_release_eligible(tender_receipt)
    )


def dedicated_scan_failures(
    channel: str,
    receipt: dict,
    receipt_path: Path,
    event_path: Path,
    day: str,
    slot: str,
) -> list[str]:
    failures = []
    if not receipt_path.is_file():
        return [f"{channel}_dedicated_scan_missing"]
    if receipt.get("scanAsOf") != day or receipt.get("slot") != slot:
        failures.append(f"{channel}_dedicated_scan_wrong_slot")
    if (
        receipt.get("status") not in {"completed", "degraded"}
        or not receipt.get("coverageComplete")
    ):
        failures.append(f"{channel}_dedicated_scan_incomplete")
    if not receipt.get("networkVerified"):
        failures.append(f"{channel}_dedicated_scan_not_network_verified")
    if receipt.get("eventStoreSha256") != file_sha256(event_path):
        failures.append(f"{channel}_event_store_hash_mismatch")
    artifact_errors = verify_receipt_artifacts(ROOT, receipt)
    if artifact_errors:
        failures.append(
            f"{channel}_scan_artifact_invalid:" + ",".join(artifact_errors)
        )
    return failures


def listed_quality_failures(curated: dict, raw: dict, contract: dict, day: str) -> list[str]:
    rules = contract["channels"]["listed"]
    failures: list[str] = []
    summary = raw.get("_summary", {})
    required_total = int(rules["requiredUniverse"]["total"])
    if int(summary.get("companyUniverseCount") or 0) != required_total:
        failures.append("listed_universe_drift")
    if int(summary.get("errorCount") or 0):
        failures.append("listed_subject_scan_error")
    if curated.get("date") != day:
        failures.append("listed_curated_date_mismatch")
    evidence = curated.get("sourceEvidence") or []
    evidence_by_id = {str(row.get("matter_id") or ""): row for row in evidence}
    if len(evidence_by_id) != len(evidence):
        failures.append("listed_duplicate_matter_id")
    for matter_id, row in evidence_by_id.items():
        if not matter_id or not row.get("sourceUrl", "").startswith("https://"):
            failures.append("listed_source_url_missing")
            break
        if not row.get("pdfSha256") or not row.get("textSha256") or not row.get("excerpt"):
            failures.append("listed_pdf_evidence_incomplete")
            break
    customer_rows = [
        row
        for key in ("opportunities", "risk_rows", "tiles", "capital_rows", "follow_items")
        for row in curated.get(key, [])
    ] + [
        row
        for group in curated.get("fixed_columns", [])
        for row in group.get("items", [])
    ]
    for row in customer_rows:
        matter_id = str(row.get("matter_id") or "")
        normalized = matter_id.removesuffix("-follow").removesuffix("-fixed")
        if not normalized or normalized not in evidence_by_id:
            failures.append("listed_customer_row_without_pdf_primary")
            break
    return sorted(set(failures))


def private_quality_failures(daily: dict, contract: dict, day: str) -> list[str]:
    rules = contract["channels"]["private"]
    failures: list[str] = []
    if daily.get("reportDate") != day:
        failures.append("private_daily_date_mismatch")
    if int(daily.get("observationManagerCount") or 0) != int(rules["requiredObservationManagers"]):
        failures.append("private_observation_pool_drift")
    for row in daily.get("shaanxiOfficeProducts") or []:
        if not row.get("fundNo") or not row.get("managerName"):
            failures.append("private_product_identity_incomplete")
            break
        if not (row.get("mandatorName") or row.get("custodian")):
            failures.append("private_product_custodian_incomplete")
            break
    return sorted(set(failures))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--slot", choices=("morning", "midday", "closing"), default="morning")
    args = parser.parse_args()
    day = date.fromisoformat(args.date).isoformat()
    contract = load(ROOT / "v2/config/source-contract.json")
    quality_contract_path = ROOT / "v2/config/production-quality-contract.json"
    quality_contract = load(quality_contract_path)
    scan_path = ROOT / f"v2/data/scans/{day}-{args.slot}.json"
    if not scan_path.exists() and args.slot == "morning":
        scan_path = ROOT / f"v2/data/scans/{day}.json"
    scan = load(scan_path)
    checks = {
        "listedDaily": ROOT / f"v2/data/daily/listed/listed-official-{day}.json",
        "listedAnnouncements": ROOT / f"v2/data/daily/listed/cninfo-announcements-{day}.json",
        "listedHkexReview": ROOT / f"v2/data/daily/listed/hkex-review-{day}.json",
        "privateDaily": ROOT / f"v2/data/daily/private/security-private-fund-daily-{day}.json",
        "maEvents": ROOT / contract["maEvents"],
        "maScanReceipt": (
            ROOT / contract["maScanDirectory"] / f"scan-{day}-{args.slot}.json"
        ),
        "tenderEvents": ROOT / contract["tenderEvents"],
        "tenderScanReceipt": (
            ROOT / contract["tenderScanDirectory"] / f"scan-{day}-{args.slot}.json"
        ),
        "soeEvents": ROOT / contract["soeEvents"],
        "soeScanReceipt": (
            ROOT
            / contract["soeScanDirectory"]
            / f"scan-{day}-{args.slot}.json"
        ),
        "eventStore": ROOT / contract["eventStore"],
        "observationPool": ROOT / contract["observationPool"],
        "qualityContract": quality_contract_path,
    }
    missing = [name for name, path in checks.items() if not path.is_file()]
    ma = load(checks["maEvents"])
    listed_daily = load(checks["listedDaily"]) if checks["listedDaily"].is_file() else {}
    listed_announcements = load(checks["listedAnnouncements"]) if checks["listedAnnouncements"].is_file() else {}
    listed_hkex = load(checks["listedHkexReview"]) if checks["listedHkexReview"].is_file() else {}
    private_daily = load(checks["privateDaily"]) if checks["privateDaily"].is_file() else {}
    ma_scan = load(checks["maScanReceipt"]) if checks["maScanReceipt"].is_file() else {}
    tender_scan = (
        load(checks["tenderScanReceipt"])
        if checks["tenderScanReceipt"].is_file()
        else {}
    )
    soe_scan = load(checks["soeScanReceipt"]) if checks["soeScanReceipt"].is_file() else {}
    event_store = load(checks["eventStore"]) if checks["eventStore"].is_file() else {}
    observation_pool = load(checks["observationPool"]) if checks["observationPool"].is_file() else {}
    channel_status = {}
    for channel in CHANNELS:
        row = scan.get("channels", {}).get(channel, {})
        ready = row.get("scanAsOf") == day and channel_release_eligible(
            channel, row, tender_scan
        )
        channel_status[channel] = {**row, "ready": ready}
    listed_ma = [row for row in ma["projects"] if row.get("entityType") == "listed"]
    listed_ma_missing = [
        row["maProjectId"]
        for row in listed_ma
        if not any(
            source.get("sourceQuality") == "exchange_or_regulator_original"
            and source.get("url")
            for source in row.get("sourceRecords", [])
        )
    ]
    failures = []
    if missing:
        failures.append("missing_inputs:" + ",".join(missing))
    if scan.get("status") not in {"completed", "completed_with_source_constraint"}:
        failures.append("scan_not_completed")
    if not all(row["ready"] for row in channel_status.values()):
        failures.append("channel_scan_incomplete")
    if (
        listed_hkex.get("date") != day
        or listed_hkex.get("slot") != args.slot
        or listed_hkex.get("status") not in {"completed", "no_new"}
        or int(listed_hkex.get("companyCount") or 0)
        != int(quality_contract["channels"]["listed"]["requiredUniverse"]["hkexL2"])
    ):
        failures.append("listed_hkex_review_incomplete")
    failures.extend(listed_quality_failures(listed_daily, listed_announcements, quality_contract, day))
    failures.extend(private_quality_failures(private_daily, quality_contract, day))
    if (
        soe_scan.get("scanAsOf") != day
        or soe_scan.get("slot") != args.slot
        or soe_scan.get("status") != "completed"
        or not soe_scan.get("networkVerified")
    ):
        failures.append("soe_dedicated_scan_not_verified")
    soe_evidence_path = ROOT / str(soe_scan.get("evidencePath") or "")
    soe_evidence = load(soe_evidence_path) if soe_evidence_path.is_file() else {}
    registry = load(ROOT / "v2/config/soe-sources.json")
    if (
        not soe_evidence.get("sourceCoverage", {}).get("coverageComplete")
        or len(soe_evidence.get("sourceCoverage", {}).get("sources", []))
        != len(registry.get("sources", []))
    ):
        failures.append("soe_official_source_registry_incomplete")
    failures.extend(
        dedicated_scan_failures(
            "ma",
            ma_scan,
            checks["maScanReceipt"],
            checks["maEvents"],
            day,
            args.slot,
        )
    )
    tender_constraint = tender_constraint_release_eligible(tender_scan)
    if tender_scan.get("status") == "degraded" and not tender_constraint:
        failures.append("tender_degraded_without_official_equivalent_coverage")
    failures.extend(
        dedicated_scan_failures(
            "tender",
            tender_scan,
            checks["tenderScanReceipt"],
            checks["tenderEvents"],
            day,
            args.slot,
        )
    )
    if listed_ma_missing:
        failures.append("listed_ma_missing_primary:" + ",".join(listed_ma_missing))
    if event_store.get("scanAsOf") != day:
        failures.append("event_store_not_current")
    if set(event_store.get("channelCounts", {})) != set(CHANNELS):
        failures.append("event_store_channels_incomplete")
    listed_event_pending = [
        row.get("eventId", "")
        for row in event_store.get("events", [])
        if row.get("channel") == "listed" and row.get("sourceStatus") != "verified"
    ]
    if listed_event_pending:
        failures.append("listed_events_missing_primary:" + ",".join(listed_event_pending))
    if observation_pool.get("scanAsOf") != day:
        failures.append("observation_pool_not_current")
    if set(observation_pool.get("channels", {})) != set(CHANNELS):
        failures.append("observation_pool_channels_incomplete")
    publish_status = "blocked" if failures else "ready"
    payload = {
        "schemaVersion": "2.0",
        "owner": "V2",
        "date": day,
        "slot": args.slot,
        "status": publish_status,
        "channels": channel_status,
        "checks": {name: path.relative_to(ROOT).as_posix() for name, path in checks.items()},
        "qualityContract": {
            "path": quality_contract_path.relative_to(ROOT).as_posix(),
            "sha256": file_sha256(quality_contract_path),
            "standard": quality_contract.get("standard"),
        },
        "ma": {
            "projectCount": len(ma["projects"]),
            "primaryVerified": ma.get("officialSourceProjectCount", 0),
            "historicalExactDocumentBacklog": ma.get("sourceBackfillCount", 0),
            "listedMissingPrimary": listed_ma_missing,
            "scanReceipt": (
                checks["maScanReceipt"].relative_to(ROOT).as_posix()
                if checks["maScanReceipt"].is_file()
                else ""
            ),
            "coverageComplete": bool(ma_scan.get("coverageComplete")),
            "networkVerified": bool(ma_scan.get("networkVerified")),
            "sourceRuns": ma_scan.get("sourceRuns", []),
        },
        "tender": {
            "scanReceipt": (
                checks["tenderScanReceipt"].relative_to(ROOT).as_posix()
                if checks["tenderScanReceipt"].is_file()
                else ""
            ),
            "coverageComplete": bool(tender_scan.get("coverageComplete")),
            "networkVerified": bool(tender_scan.get("networkVerified")),
            "sourceRuns": tender_scan.get("sourceRuns", []),
            "sourceConstraint": (
                tender_scan.get("releaseEligibility", {})
                if tender_constraint
                else {}
            ),
        },
        "sourceConstraints": (
            [{"channel": "tender", **tender_scan.get("releaseEligibility", {})}]
            if tender_constraint
            else []
        ),
        "soe": {
            "scanReceipt": (
                checks["soeScanReceipt"].relative_to(ROOT).as_posix()
                if checks["soeScanReceipt"].is_file()
                else ""
            ),
            "latestVerifiedEventDate": soe_scan.get("latestVerifiedEventDate", ""),
            "eventOnScanDate": soe_scan.get("eventOnScanDate"),
            "networkVerified": bool(soe_scan.get("networkVerified")),
        },
        "unifiedStore": {
            "eventCount": event_store.get("eventCount", 0),
            "channelCounts": event_store.get("channelCounts", {}),
            "poolCounts": {
                channel: len(rows)
                for channel, rows in observation_pool.get("channels", {}).items()
            },
            "listedEventsMissingPrimary": listed_event_pending,
        },
        "failures": failures,
    }
    target = ROOT / f"v2/data/readiness/v2-ready-{day}-{args.slot}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
