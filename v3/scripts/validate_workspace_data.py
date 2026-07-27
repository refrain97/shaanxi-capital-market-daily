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
    universe_payload = load("data/listed/universe.json")
    active_names = {item["canonicalName"] for item in universe_payload["entities"]}
    universe = listed["universe"]
    assert universe["targetCount"] == 110
    assert universe["retrievedSubjectCount"] == 110
    assert universe["retrievalRate"] == 1.0
    assert {item["tier"]: item["subjectCount"] for item in universe["tierStats"]} == {"L1": 85, "L2": 14, "L3": 11}
    excluded_names = {"彤程新材", "北方铜业", "广誉远", "佳力奇", "金天钛业", "明阳电路", "菲林格尔"}
    assert not any(item["companyName"] in excluded_names for item in listed["matters"])
    assert universe["matterCount"] == len(listed["matters"])
    assert universe["activeMatterCount"] + universe["archivedMatterCount"] == len(listed["matters"])
    assert all(item["workspaceStatus"] in {"active", "archived"} for item in listed["matters"])
    assert all(item["sources"] and item["sourceCount"] == len(item["sources"]) for item in listed["matters"])
    deep_read = listed.get("deepRead")
    assert deep_read and deep_read["deepReadItemCount"] == len(deep_read["items"])
    assert deep_read["latestItemCount"] == sum(item["reportDate"] == deep_read["latestReportDate"] for item in deep_read["items"])
    assert all(item["companyName"] in active_names for item in deep_read["items"])
    assert len({item["deepReadId"] for item in deep_read["items"]}) == len(deep_read["items"])
    assert deep_read["latestReportDate"] == max(item["reportDate"] for item in deep_read["items"])
    assert deep_read["backfillGap"]["status"] == "pending_pdf_deep_read"
    assert all(item["readStatus"] == "v1_pdf_deep_read" for item in deep_read["items"])
    assert all(item["summary"] and item["businessJudgement"] for item in deep_read["items"])
    assert all(item["sourceCount"] == len(item["sources"]) for item in deep_read["items"])
    assert all(isinstance(item["verifiedNumbers"], list) for item in deep_read["items"])
    assert all(isinstance(item["followTargets"], list) for item in deep_read["items"])
    assert not any(number == "-2.20%" for item in deep_read["items"] for number in item["verifiedNumbers"])
    latest_items = [item for item in deep_read["items"] if item["reportDate"] == deep_read["latestReportDate"]]
    assert all(item["sourceCount"] > 0 for item in latest_items)
    latest_titles = {item["title"] for item in latest_items}
    assert {"科华生物｜可转债兑付", "科华生物｜产品注册"} <= latest_titles
    assert {"西安奕材-U｜产销与项目进展", "西安奕材-U｜限售股上市流通"} <= latest_titles
    assert {"科隆新材｜股东权益变动", "科隆新材｜现金管理"} <= latest_titles
    assert any(item["companyName"] == "陕鼓动力" and "9亿元" in item["verifiedNumbers"] for item in latest_items)

    quarters = private["quarters"]
    assert [item["quarter"] for item in quarters] == ["Q1", "Q2", "Q3", "Q4"]
    assert sum(item["productCount"] for item in quarters) == private["summary"]["productCount"]
    assert all(item["productCount"] == len(item["products"]) for item in quarters)
    assert all(product["filingDate"].startswith("2026-") for item in quarters for product in item["products"])
    print(json.dumps({
        "listedRetrieved": universe["retrievedSubjectCount"],
        "listedMatters": universe["matterCount"],
        "listedDeepReads": deep_read["deepReadItemCount"],
        "privateProducts": private["summary"]["productCount"],
        "status": "PASS",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
