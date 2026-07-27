#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START_DATE = "2026-01-01"


def main() -> int:
    source = json.loads((ROOT / "data/pre-ipo/latest.json").read_text(encoding="utf-8"))
    milestones = []
    for profile in source.get("profiles", []):
        for item in profile.get("milestones", []):
            if (item.get("at") or "") < START_DATE:
                continue
            milestones.append({
                "candidateId": f"preipo-backfill-{profile['enterpriseId']}-{item.get('type')}-{item.get('at')}",
                "primaryEntityId": profile["enterpriseId"],
                "enterpriseName": profile["name"],
                "reserveTier": profile.get("reserveTier"),
                "listingStage": profile.get("listingStage"),
                "publishedAt": item.get("at"),
                "eventType": item.get("type"),
                "title": item.get("label"),
                "sourceUrl": item.get("sourceUrl"),
                "sourceQuality": profile.get("sourceStatus"),
                "noveltyStatus": "backfill",
                "normalizationStatus": "source_verified" if item.get("sourceUrl") else "source_missing",
            })
    financing = [item for item in source.get("financingRecords", []) if (item.get("announcedAt") or "") >= START_DATE]
    output = {
        "schemaVersion": "0.1",
        "channel": "equity_financing",
        "novelty": "backfill",
        "period": {"startDate": START_DATE, "endDate": datetime.now(timezone.utc).date().isoformat()},
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "BASELINE_NORMALIZED_FINANCING_SCAN_PENDING",
        "limits": ["A档80家已逐家建档；B/C档仅有官方数量，未取得权威企业明细不得补造", "融资事件目前仅纳入已取得官方来源的记录，逐企年度扫描仍在进行"],
        "summary": {
            "officialReserveTotalCount": source.get("reserveTotalCount"),
            "profileCount": len(source.get("profiles", [])),
            "aTierProfileCount": sum(item.get("reserveTier") == "A" for item in source.get("profiles", [])),
            "milestoneCount": len(milestones),
            "verifiedFinancingCount": sum(item.get("verificationStatus") == "verified" for item in financing),
            "missingSourceMilestoneCount": sum(not item.get("sourceUrl") for item in milestones),
        },
        "milestones": milestones,
        "financingRecords": financing,
    }
    target = ROOT / "data/backfill/equity-financing/normalized-2026.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
