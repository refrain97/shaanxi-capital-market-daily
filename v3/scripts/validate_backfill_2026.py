#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    coverage = json.loads((ROOT / "data/backfill/coverage-2026.json").read_text(encoding="utf-8"))
    if coverage.get("startDate") != "2026-01-01":
        errors.append("backfill must start on 2026-01-01")
    listed = json.loads((ROOT / "data/backfill/listed/normalized-2026.json").read_text(encoding="utf-8"))
    universe = json.loads((ROOT / "data/listed/universe.json").read_text(encoding="utf-8"))
    target_count = universe["counts"]["total"]
    active_entity_ids = {item["entityId"] for item in universe["entities"]}
    if listed["coverage"]["subjectCount"] != target_count or listed["coverage"]["resolvedSubjectCount"] != target_count:
        errors.append(f"listed backfill must resolve all {target_count} active subjects")
    if any(item.get("entityId") not in active_entity_ids for item in listed["sources"]):
        errors.append("listed backfill contains sources outside the active universe")
    source_ids = {item["sourceRecordId"] for item in listed["sources"]}
    if len(source_ids) != len(listed["sources"]):
        errors.append("listed source IDs must be unique")
    if any(not set(item["sourceRecordIds"]).issubset(source_ids) for item in listed["candidates"]):
        errors.append("listed candidate references missing source")
    if any(item.get("noveltyStatus") != "backfill" for item in listed["candidates"]):
        errors.append("historical listed candidates must be marked backfill")
    raw_files = sorted((ROOT / "data/backfill/listed/raw").glob("cninfo-*.json"))
    if not raw_files or any(json.loads(path.read_text(encoding="utf-8"))["summary"]["errorCount"] for path in raw_files):
        errors.append("listed raw chunks are missing or contain errors")

    private = json.loads((ROOT / "data/backfill/private-fund/normalized-2026.json").read_text(encoding="utf-8"))
    fund_numbers = [item["fundNo"] for item in private["products"]]
    if len(fund_numbers) != len(set(fund_numbers)) or any(not value for value in fund_numbers):
        errors.append("private-fund products require unique fund numbers")
    if any(not item.get("sourceUrl", "").startswith("https://gs.amac.org.cn/") for item in private["products"] + private["cancellations"]):
        errors.append("private-fund backfill records require AMAC sources")
    if private["coverage"]["limitHit"] and "LIMITED" not in private["coverage"]["status"]:
        errors.append("AMAC limit must remain visible in status")
    if not any(item.get("managerName") == "深圳抱朴容易私募证券基金管理有限公司" and item.get("universeTier") == "PF2" for item in private["products"]):
        errors.append("private-fund backfill must include approved PF2 products")

    tender = json.loads((ROOT / "data/backfill/tender/merged-2026.json").read_text(encoding="utf-8"))
    if tender["summary"]["sourceCount"] < 2 or tender["summary"]["projectCount"] < 10:
        errors.append("tender backfill requires two sources and grouped project timelines")
    if tender["summary"]["announcementMissingCount"] and "REVIEW_PENDING" not in tender["status"]:
        errors.append("tender announcement gaps must remain visible in status")
    if any(project.get("noveltyStatus") != "backfill" for project in tender["projects"]):
        errors.append("historical tender projects must be marked backfill")

    ma = json.loads((ROOT / "data/backfill/ma/normalized-2026.json").read_text(encoding="utf-8"))
    if ma["summary"]["announcementCandidateCount"] < ma["summary"]["projectCandidateCount"] or not ma.get("sources"):
        errors.append("M&A backfill must retain sources and dedupe announcement candidates")

    equity = json.loads((ROOT / "data/backfill/equity-financing/normalized-2026.json").read_text(encoding="utf-8"))
    if equity["summary"]["officialReserveTotalCount"] != 530 or equity["summary"]["aTierProfileCount"] != 80:
        errors.append("pre-IPO official reserve counts must remain intact")
    if any(item.get("verificationStatus") != "verified" or not item.get("sourceUrl", "").startswith("https://") for item in equity["financingRecords"]):
        errors.append("equity financing records require verified HTTPS sources")

    soe = json.loads((ROOT / "data/backfill/soe/normalized-2026.json").read_text(encoding="utf-8"))
    if not soe["status"].startswith("PARTIAL_") or any(not item.get("sourceUrl", "").startswith(("http://", "https://")) for item in soe["records"]):
        errors.append("SOE history gap must stay visible and retained records require sources")

    result = {"status": "FAIL" if errors else "PASS", "listedSources": len(listed["sources"]), "listedCandidates": len(listed["candidates"]), "privateProducts": len(private["products"]), "privateCancellations": len(private["cancellations"]), "tenderProjects": len(tender["projects"]), "maProjects": len(ma["projects"]), "preIpoMilestones": len(equity["milestones"]), "soeRecords": len(soe["records"]), "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
