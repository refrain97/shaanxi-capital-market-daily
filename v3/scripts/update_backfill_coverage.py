#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main() -> int:
    coverage_path = ROOT / "data/backfill/coverage-2026.json"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    tender = load("data/backfill/tender/merged-2026.json")
    ma = load("data/backfill/ma/normalized-2026.json")
    equity = load("data/backfill/equity-financing/normalized-2026.json")
    soe = load("data/backfill/soe/normalized-2026.json")
    coverage["endDate"] = datetime.now(timezone.utc).date().isoformat()
    coverage["generatedAt"] = datetime.now(timezone.utc).isoformat()
    coverage["channels"]["tender"] = {"status": tender["status"], **tender["summary"], "limits": tender["limits"]}
    coverage["channels"]["ma"] = {"status": ma["status"], **ma["summary"], "limits": ma["limits"]}
    coverage["channels"]["equity_financing"] = {"status": equity["status"], **equity["summary"], "limits": equity["limits"]}
    coverage["channels"]["soe"] = {"status": soe["status"], **soe["summary"], "limits": soe["limits"]}
    coverage_path.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(coverage["channels"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
