#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main() -> int:
    listed = load("data/listed/workspace-2026.json")
    private = load("data/private-fund/workspace-2026.json")
    universe = listed["universe"]
    assert universe["targetCount"] == 117
    assert universe["retrievedSubjectCount"] == 117
    assert universe["retrievalRate"] == 1.0
    assert {item["tier"]: item["subjectCount"] for item in universe["tierStats"]} == {"L1": 85, "L2": 14, "L3": 18}
    assert universe["matterCount"] == len(listed["matters"])
    assert universe["activeMatterCount"] + universe["archivedMatterCount"] == len(listed["matters"])
    assert all(item["workspaceStatus"] in {"active", "archived"} for item in listed["matters"])
    assert all(item["sources"] and item["sourceCount"] == len(item["sources"]) for item in listed["matters"])

    quarters = private["quarters"]
    assert [item["quarter"] for item in quarters] == ["Q1", "Q2", "Q3", "Q4"]
    assert sum(item["productCount"] for item in quarters) == private["summary"]["productCount"]
    assert all(item["productCount"] == len(item["products"]) for item in quarters)
    assert all(product["filingDate"].startswith("2026-") for item in quarters for product in item["products"])
    print(json.dumps({
        "listedRetrieved": universe["retrievedSubjectCount"],
        "listedMatters": universe["matterCount"],
        "privateProducts": private["summary"]["productCount"],
        "status": "PASS",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
