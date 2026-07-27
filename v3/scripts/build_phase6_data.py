#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}-{hashlib.sha1(value.encode('utf-8')).hexdigest()[:14]}"


def main() -> None:
    dashboard = load("data/sample/dashboard-2026-07-10.json")
    private = load("data/private-fund/snapshots/latest.json")
    ma = load("data/ma-projects/latest.json")
    preipo = load("data/pre-ipo/latest.json")
    tender = load("data/tender/scans/latest.json")

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    def add_node(node_id: str, node_type: str, name: str, **extra: Any) -> str:
        existing = nodes.get(node_id, {})
        nodes[node_id] = {**existing, "nodeId": node_id, "nodeType": node_type, "name": name, **extra}
        return node_id

    def add_edge(source: str, target: str, relation: str, evidence_type: str, at: str | None = None, source_url: str | None = None, **extra: Any) -> None:
        key = f"{source}|{target}|{relation}|{at or ''}"
        edge_id = stable_id("rel", key)
        edges[edge_id] = {"edgeId": edge_id, "sourceNodeId": source, "targetNodeId": target, "relationType": relation, "evidenceType": evidence_type, "at": at, "sourceUrl": source_url, **extra}

    for entity in dashboard["entities"]:
        add_node(entity["entityId"], entity["entityType"], entity["canonicalName"], region=entity.get("region"), securityCode=entity.get("securityCode"), sourceScope="dashboard")

    event_by_id = {item["eventId"]: item for item in dashboard["events"]}
    for event in dashboard["events"]:
        add_node(event["eventId"], "event", event["title"], status=event["eventStatus"], channel=event["channel"], sourceScope="dashboard")
        add_edge(event["primaryEntityId"], event["eventId"], "has_event", "normalized_event", event["publishedAt"][:10])

    manager_ids: dict[str, str] = {}
    for manager in private["topManagers"]:
        manager_id = manager.get("managerId") or stable_id("manager", manager["managerName"])
        manager_ids[manager["managerName"]] = manager_id
        add_node(manager_id, "private_manager", manager["managerName"], registerNo=manager["registerNo"], rank=manager["rank"], sourceScope="amac")
        for person in manager["executives"]:
            person_id = stable_id("person", person["name"])
            add_node(person_id, "person", person["name"], sourceScope="amac")
            add_edge(manager_id, person_id, "executive", "amac_manager_detail", private["sourceReportDate"], manager["detailUrl"], role=person["role"])
        for shareholder in manager["shareholders"]:
            holder_id = stable_id("holder", shareholder["name"])
            add_node(holder_id, "shareholder", shareholder["name"], sourceScope="amac")
            add_edge(holder_id, manager_id, "shareholder_of", "amac_manager_detail", private["sourceReportDate"], manager["detailUrl"], ratio=shareholder["ratio"])

    for product in private["newProducts"]:
        manager_id = manager_ids.get(product["managerName"]) or stable_id("manager", product["managerName"])
        add_node(manager_id, "private_manager", product["managerName"], sourceScope="amac")
        product_id = f"fund-{product['fundNo'].lower()}"
        custodian_id = stable_id("custodian", product["custodian"])
        add_node(product_id, "private_product", product["fundName"], fundNo=product["fundNo"], sourceScope="amac")
        add_node(custodian_id, "custodian", product["custodian"], sourceScope="amac")
        add_edge(manager_id, product_id, "manages", "amac_fund_filing", product["filingDate"], product["sourceUrl"])
        add_edge(product_id, custodian_id, "custodied_by", "amac_fund_filing", product["filingDate"], product["sourceUrl"])

    project_by_title: dict[str, str] = {}
    for project in ma["projects"]:
        project_by_title[project["title"]] = project["maProjectId"]
        add_node(project["maProjectId"], "ma_project", project["title"], stage=project["stage"], sourceStatus=project["sourceStatus"], sourceScope="ma_project")

    for profile in preipo["profiles"]:
        add_node(profile["enterpriseId"], "preipo_enterprise", profile["name"], reserveTier=profile["reserveTier"], listingStage=profile["listingStage"], securityCode=profile.get("securityCode"), sourceScope="preipo")
        for milestone in profile["milestones"]:
            if milestone["type"] == "ma_progress" and milestone["label"] in project_by_title:
                add_edge(profile["enterpriseId"], project_by_title[milestone["label"]], "linked_ma_project", "project_timeline", milestone["at"], milestone.get("sourceUrl"))

    for financing in preipo["financingRecords"]:
        for investor in financing["investors"]:
            investor_id = stable_id("investor", investor)
            add_node(investor_id, "investor", investor, sourceScope="official_investor")
            add_edge(investor_id, financing["enterpriseId"], "invested_in", financing["sourceQuality"], financing["announcedAt"], financing["sourceUrl"], round=financing["round"], amountText=financing["amountText"])

    relation_counts = Counter(edge["relationType"] for edge in edges.values())
    node_counts = Counter(node["nodeType"] for node in nodes.values())
    network = {
        "schemaVersion": "0.1",
        "asOf": max(dashboard["meta"]["asOf"], private["sourceReportDate"], ma["asOf"], preipo["asOf"]),
        "summary": {"nodeCount": len(nodes), "edgeCount": len(edges), "nodeTypeCounts": dict(sorted(node_counts.items())), "relationTypeCounts": dict(sorted(relation_counts.items()))},
        "nodes": sorted(nodes.values(), key=lambda item: (item["nodeType"], item["name"])),
        "edges": sorted(edges.values(), key=lambda item: (item["relationType"], item["sourceNodeId"], item["targetNodeId"])),
    }

    month_series: dict[str, Counter[str]] = {
        "events": Counter(), "maMilestones": Counter(), "reserveMilestones": Counter(), "privateFilings": Counter(), "financing": Counter()
    }
    for event in dashboard["events"]:
        month_series["events"][event["publishedAt"][:7]] += 1
    for project in ma["projects"]:
        for milestone in project["milestones"]:
            if milestone.get("at"):
                month_series["maMilestones"][milestone["at"][:7]] += 1
    for profile in preipo["profiles"]:
        for milestone in profile["milestones"]:
            if milestone["type"] == "reserve_list":
                month_series["reserveMilestones"][milestone["at"][:7]] += 1
    for product in private["newProducts"]:
        month_series["privateFilings"][product["filingDate"][:7]] += 1
    for financing in preipo["financingRecords"]:
        month_series["financing"][financing["announcedAt"][:7]] += 1

    annual = {
        "schemaVersion": "0.1",
        "year": 2026,
        "asOf": network["asOf"],
        "metrics": {
            "normalizedEvents": len(dashboard["events"]),
            "listedDailyItems": dashboard["listedDaily"]["effectiveEventCount"],
            "maProjects": ma["projectCount"],
            "maActiveProjects": ma["stageCounts"]["planning"] + ma["stageCounts"]["signed_or_approved"] + ma["stageCounts"]["in_progress"],
            "privateManagers": private["summary"]["managerCount"],
            "privateYtdProducts": private["summary"]["ytdProductCount"],
            "reserveEnterprises": preipo["reserveTotalCount"],
            "aTierProfiles": preipo["tierCounts"]["A"],
            "verifiedFinancing": len(preipo["financingRecords"]),
            "tenderScannedRecords": tender["summary"]["recordCount"],
            "activeTenderOpportunities": tender["summary"]["activeOpportunityCount"],
        },
        "monthlySeries": {name: [{"month": f"2026-{month:02d}", "count": values.get(f"2026-{month:02d}", 0)} for month in range(1, 13)] for name, values in month_series.items()},
        "dataBoundaries": [
            "各指标保持独立业务口径，不相加生成总事件数。",
            "证券私募全年备案数来自V1 AMAC快照；月序列仅统计已进入V3差异记录的备案。",
            "上市后备530家为名录总量；逐家档案当前覆盖A档80家。",
            "招投标扫描数是扫描记录，不等于有效机会。",
        ],
    }

    (ROOT / "data/relationships").mkdir(parents=True, exist_ok=True)
    (ROOT / "data/annual").mkdir(parents=True, exist_ok=True)
    (ROOT / "data/relationships/latest.json").write_text(json.dumps(network, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "data/annual/2026.json").write_text(json.dumps(annual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"nodeCount": len(nodes), "edgeCount": len(edges), "annualMetrics": annual["metrics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
