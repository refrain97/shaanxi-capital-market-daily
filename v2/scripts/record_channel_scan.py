#!/usr/bin/env python3
"""Record truthful per-channel scan completion for one V2 automation slot."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHANNELS = ("listed", "private", "ma", "tender", "soe")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--slot", choices=("morning", "midday", "closing"), required=True)
    parser.add_argument("--channel", choices=CHANNELS, required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument(
        "--status",
        choices=("completed", "no_new", "degraded", "failed"),
        default="completed",
    )
    parser.add_argument(
        "--release-eligible",
        action="store_true",
        help="仅限已证明官方等价覆盖的受限栏目；不能把普通 degraded 放行",
    )
    parser.add_argument("--evidence", action="append", default=[])
    args = parser.parse_args()
    day = date.fromisoformat(args.date).isoformat()
    path = ROOT / f"v2/data/scans/{day}-{args.slot}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {
            "schemaVersion": "2.0",
            "date": day,
            "slot": args.slot,
            "status": "in_progress",
            "channels": {},
        }
    )
    payload["channels"][args.channel] = {
        "status": args.status,
        "scanAsOf": day,
        "result": args.result,
        "evidence": sorted(set(args.evidence)),
        "releaseEligible": bool(args.release_eligible),
    }
    rows = [payload["channels"].get(name, {}) for name in CHANNELS]
    values = [row.get("status") for row in rows]
    releasable = [
        value in {"completed", "no_new"}
        or (value == "degraded" and row.get("releaseEligible") is True)
        for value, row in zip(values, rows)
    ]
    payload["status"] = (
        "failed" if "failed" in values
        else "completed_with_source_constraint"
        if all(releasable) and "degraded" in values
        else "completed" if all(releasable)
        else "in_progress"
    )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if args.status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
