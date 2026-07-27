#!/usr/bin/env python3
"""Build the V3 Shaanxi securities private-fund intelligence snapshot from V1 data."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
V3_ROOT = Path(__file__).resolve().parents[1]
V1_PRIVATE = ROOT / "v1/陕西省证券私募日报v1"
AMAC_SCRIPT = V1_PRIVATE / "scripts/amac_security_private_daily.py"
UNIVERSE_CONFIG = V3_ROOT / "config/private-fund-universe.json"


def load_amac_module():
    spec = importlib.util.spec_from_file_location("v1_amac_private", AMAC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {AMAC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--previous-date")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--refresh-details", action="store_true")
    return parser.parse_args()


def available_snapshot_dates() -> list[str]:
    dates = []
    for path in (V1_PRIVATE / "data").glob("security-private-fund-daily-*.json"):
        value = path.stem.removeprefix("security-private-fund-daily-")
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            continue
        dates.append(value)
    return sorted(set(dates))


def load_v1(day: str) -> dict[str, Any]:
    path = V1_PRIVATE / "data" / f"security-private-fund-daily-{day}.json"
    return json.loads(path.read_text())


def load_universe_config() -> dict[str, Any]:
    return json.loads(UNIVERSE_CONFIG.read_text(encoding="utf-8"))


def dedupe_products(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_fund_no: dict[str, dict[str, Any]] = {}
    for item in items:
        fund_no = str(item.get("fundNo") or "")
        if fund_no:
            by_fund_no[fund_no] = item
    return list(by_fund_no.values())


def observed_products(snapshot: dict[str, Any], related_names: set[str]) -> list[dict[str, Any]]:
    territorial = snapshot.get("shaanxiOfficeProducts", [])
    # V1 keeps the full Jan-1-to-report-date national product window under this
    # legacy key; shaanxiOfficeProducts is the location-filtered subset.
    national = snapshot.get("raw", {}).get("allSecurityProductsInShaanxiWindow", [])
    related = [item for item in national if item.get("managerName") in related_names]
    return dedupe_products([*territorial, *related])


def related_manager_row(amac: Any, target: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    error = None
    try:
        payload = amac.post_json(
            "/pof/manager/query",
            {"keyword": target["managerName"]},
            page=0,
            referer=amac.MANAGER_REFERER,
        )
        candidates = payload.get("content") or []
        row = next(
            (item for item in candidates if item.get("registerNo") == target["registerNo"]),
            None,
        )
        if row is None:
            raise RuntimeError("AMAC manager query did not return the configured registerNo")
    except Exception as exc:  # preserve the approved target when AMAC is temporarily unavailable
        error = str(exc)
        row = {
            "id": target["managerId"],
            "managerName": target["managerName"],
            "registerNo": target["registerNo"],
            "url": f"{target['managerId']}.html",
            "registerProvince": target.get("currentRegisterProvince"),
            "officeProvince": target.get("currentOfficeProvince"),
            "fundCount": 0,
        }
    row = dict(row)
    row.update({
        "universeTier": target["universeTier"],
        "relationType": target["relationType"],
        "relationStrength": target["relationStrength"],
        "monitoringPriority": target["dailyPriority"],
        "inclusionReason": target["inclusionReason"],
        "relationEvidence": target.get("evidence", []),
    })
    return row, error


def product_date(item: dict[str, Any]) -> str | None:
    value = item.get("putOnRecordDate")
    if not value:
        return None
    return dt.datetime.fromtimestamp(int(value) / 1000, dt.UTC).date().isoformat()


def manager_score(manager: dict[str, Any], products: list[dict[str, Any]], as_of: dt.date) -> tuple[int, dict[str, Any]]:
    total_products = int(manager.get("fundCount") or 0)
    dated = [product_date(item) for item in products]
    dated = [value for value in dated if value]
    latest = max(dated) if dated else None
    recency = 0
    if latest:
        age = (as_of - dt.date.fromisoformat(latest)).days
        recency = 12 if age <= 30 else 6 if age <= 90 else 0
    score = min(total_products, 40) * 2 + len(products) * 10 + recency
    return score, {
        "totalProductCount": total_products,
        "ytdNewProductCount": len(products),
        "latestFilingDate": latest,
        "components": {"stockProducts": min(total_products, 40) * 2, "ytdFilings": len(products) * 10, "recency": recency},
    }


def main() -> None:
    args = parse_args()
    available_dates = available_snapshot_dates()
    if not available_dates:
        raise RuntimeError("no V1 private-fund snapshots are available")
    args.date = args.date or available_dates[-1]
    if args.previous_date is None:
        previous_dates = [value for value in available_dates if value < args.date]
        if not previous_dates:
            raise RuntimeError(f"no comparable snapshot exists before {args.date}")
        args.previous_date = previous_dates[-1]
    current = load_v1(args.date)
    previous = load_v1(args.previous_date)
    universe_config = load_universe_config()
    as_of = dt.date.fromisoformat(args.date)
    amac = load_amac_module()
    territorial_managers = [{
        **item,
        "universeTier": "PF1",
        "relationType": "registered_or_office_in_shaanxi",
        "relationStrength": "direct",
        "monitoringPriority": "important",
        "inclusionReason": "AMAC当前公示的注册地或办公地在陕西省",
        "relationEvidence": [],
    } for item in current["raw"]["shaanxiOfficeManagers"]]
    related_rows = []
    universe_errors = []
    for target in universe_config["relatedTargets"]:
        row, error = related_manager_row(amac, target)
        related_rows.append(row)
        if error:
            universe_errors.append({"managerName": target["managerName"], "error": error})
    managers_by_register_no = {item.get("registerNo"): item for item in territorial_managers}
    for item in related_rows:
        managers_by_register_no.setdefault(item.get("registerNo"), item)
    managers = list(managers_by_register_no.values())
    related_names = {item["managerName"] for item in universe_config["relatedTargets"]}
    products = observed_products(current, related_names)
    previous_products = observed_products(previous, related_names)
    products_by_manager: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in products:
        products_by_manager[item.get("managerName", "")].append(item)

    ranking = []
    for manager in managers:
        score, evidence = manager_score(manager, products_by_manager[manager["managerName"]], as_of)
        ranking.append((score, evidence, manager))
    ranking.sort(key=lambda item: (-item[0], -item[1]["ytdNewProductCount"], -item[1]["totalProductCount"], item[2]["managerName"]))
    top = ranking[: args.top]

    output_dir = V3_ROOT / "data/private-fund/snapshots"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{args.date}.json"
    previous_snapshot_path = output_dir / f"{args.previous_date}.json"
    previous_snapshot = json.loads(previous_snapshot_path.read_text()) if previous_snapshot_path.exists() else None
    cached = json.loads(output_path.read_text()) if output_path.exists() and not args.refresh_details else None
    detail_cache = {item["registerNo"]: item for item in (cached or {}).get("topManagers", [])}
    top_managers = []
    detail_errors = []

    for rank, (score, score_evidence, manager) in enumerate(top, 1):
        cached_manager = detail_cache.get(manager.get("registerNo"))
        if cached_manager:
            enriched = cached_manager
        else:
            try:
                row = amac.enrich_manager(manager)
                enriched = {
                    "managerId": str(row.get("id") or row.get("registerNo")),
                    "managerName": row["managerName"],
                    "registerNo": row.get("registerNo"),
                    "registerProvince": row.get("registerProvince"),
                    "officeProvince": row.get("officeProvince"),
                    "officeCity": row.get("officeCity"),
                    "officeAddress": row.get("detail", {}).get("officeAddress") or row.get("officeAddress"),
                    "detailUrl": row.get("detailUrl"),
                    "scaleRange": row.get("detail", {}).get("scaleRange"),
                    "employeeCount": int(row.get("detail", {}).get("employeeCount") or 0),
                    "qualifiedCount": int(row.get("detail", {}).get("qualifiedCount") or 0),
                    "actualController": row.get("detail", {}).get("actualController"),
                    "executives": row.get("detail", {}).get("executives", []),
                    "workHistory": row.get("detail", {}).get("workHistory", []),
                    "shareholders": row.get("detail", {}).get("shareholders", []),
                    "teamSummary": row.get("teamSummary"),
                }
                time.sleep(0.12)
            except Exception as exc:  # keep the ranking usable while exposing coverage failure
                enriched = {
                    "managerId": str(manager.get("id") or manager.get("registerNo")),
                    "managerName": manager["managerName"],
                    "registerNo": manager.get("registerNo"),
                    "registerProvince": manager.get("registerProvince"),
                    "officeProvince": manager.get("officeProvince"),
                    "officeCity": manager.get("officeCity"),
                    "officeAddress": manager.get("officeAddress"),
                    "detailUrl": None,
                    "scaleRange": None,
                    "employeeCount": None,
                    "qualifiedCount": None,
                    "actualController": None,
                    "executives": [],
                    "workHistory": [],
                    "shareholders": [],
                    "teamSummary": "AMAC详情页本轮抓取失败。",
                }
                detail_errors.append({"managerName": manager["managerName"], "error": str(exc)})
        enriched.update({
            "rank": rank,
            "activityScore": score,
            "scoreEvidence": score_evidence,
            "universeTier": manager["universeTier"],
            "relationType": manager["relationType"],
            "relationStrength": manager["relationStrength"],
            "monitoringPriority": manager["monitoringPriority"],
            "inclusionReason": manager["inclusionReason"],
            "relationEvidence": manager.get("relationEvidence", []),
        })
        top_managers.append(enriched)

    previous_fund_nos = {item.get("fundNo") for item in previous_products}
    new_products = []
    for item in products:
        if item.get("fundNo") in previous_fund_nos:
            continue
        manager_name = item.get("managerName", "")
        earlier_count = sum(1 for old in previous_products if old.get("managerName") == manager_name)
        new_products.append({
            "fundNo": item.get("fundNo"),
            "fundName": item.get("fundName"),
            "managerName": manager_name,
            "custodian": item.get("mandatorName") or "未披露",
            "filingDate": product_date(item),
            "establishDate": dt.datetime.fromtimestamp(int(item["establishDate"]) / 1000, dt.UTC).date().isoformat() if item.get("establishDate") else None,
            "sourceUrl": f"https://gs.amac.org.cn/amac-infodisc/res/pof/fund/{item.get('url')}",
            "reactivationCandidate": earlier_count == 0,
            "reactivationReason": "年内此前未见该管理人备案，本次出现首只产品；仅为重新活跃候选，需结合更长历史确认。" if earlier_count == 0 else None,
            "businessFit": ["product_account_opening", "custody_outsourcing"],
        })

    custodian_counter = Counter(item.get("mandatorName") or "未披露" for item in products)
    custodian_rows = [{"custodian": name, "productCount": count} for name, count in custodian_counter.most_common()]
    manager_custodians = []
    for manager_name, items in products_by_manager.items():
        counts = Counter(item.get("mandatorName") or "未披露" for item in items)
        for custodian, count in counts.items():
            manager_custodians.append({"managerName": manager_name, "custodian": custodian, "productCount": count, "evidenceType": "AMAC公开托管人字段"})
    manager_custodians.sort(key=lambda item: (-item["productCount"], item["managerName"], item["custodian"]))

    location_observations = []
    for manager in managers:
        register_province = manager.get("registerProvince")
        office_province = manager.get("officeProvince")
        if register_province == office_province:
            continue
        direction = "office_in_shaanxi" if office_province == "陕西省" else "registered_in_shaanxi"
        location_observations.append({
            "managerName": manager["managerName"],
            "registerProvince": register_province,
            "officeProvince": office_province,
            "direction": direction,
            "classification": "location_observation",
            "note": "当前注册地址与办公地异省；没有历史地址差异证据，不得直接表述为迁入或迁出。",
        })

    personnel_count = sum(1 for item in top_managers if item.get("executives"))
    personnel_changes = []
    if previous_snapshot:
        previous_manager_map = {item["registerNo"]: item for item in previous_snapshot.get("topManagers", [])}
        for item in top_managers:
            old = previous_manager_map.get(item["registerNo"])
            if not old:
                continue
            old_people = {(person["name"], person["role"]) for person in old.get("executives", [])}
            new_people = {(person["name"], person["role"]) for person in item.get("executives", [])}
            for name, role in sorted(new_people - old_people):
                personnel_changes.append({"registerNo": item["registerNo"], "managerName": item["managerName"], "changeType": "executive_added", "personName": name, "role": role, "evidenceUrl": item["detailUrl"]})
            for name, role in sorted(old_people - new_people):
                personnel_changes.append({"registerNo": item["registerNo"], "managerName": item["managerName"], "changeType": "executive_removed", "personName": name, "role": role, "evidenceUrl": item["detailUrl"]})
            for field in ("employeeCount", "qualifiedCount"):
                if old.get(field) != item.get(field):
                    personnel_changes.append({"registerNo": item["registerNo"], "managerName": item["managerName"], "changeType": f"{field}_changed", "before": old.get(field), "after": item.get(field), "evidenceUrl": item["detailUrl"]})
    comparison_status = "compared" if previous_snapshot else "baseline_created"
    manager_universe = [{
        "managerId": str(item.get("id") or item.get("registerNo")),
        "managerName": item["managerName"],
        "registerNo": item.get("registerNo"),
        "registerProvince": item.get("registerProvince"),
        "officeProvince": item.get("officeProvince"),
        "universeTier": item["universeTier"],
        "relationType": item["relationType"],
        "relationStrength": item["relationStrength"],
        "monitoringPriority": item["monitoringPriority"],
        "inclusionReason": item["inclusionReason"],
        "relationEvidence": item.get("relationEvidence", []),
        "detailUrl": amac.absolutize(item.get("url", ""), "manager"),
    } for item in managers]
    territorial_count = sum(item["universeTier"] == "PF1" for item in manager_universe)
    related_count = sum(item["universeTier"] == "PF2" for item in manager_universe)
    snapshot = {
        "schemaVersion": "0.1",
        "snapshotId": f"private-fund-{args.date}",
        "asOf": f"{args.date}T23:59:59+08:00",
        "sourceReportDate": current["reportDate"],
        "previousSnapshotDate": args.previous_date,
        "scope": "PF1为注册地或办公地在陕西省的证券私募；PF2为经官方材料逐家确认的陕西强关联证券私募。两层均按重要观察对象监测，统计时分列。",
        "summary": {
            "managerCount": len(manager_universe),
            "observationManagerCount": len(manager_universe),
            "territorialManagerCount": territorial_count,
            "relatedManagerCount": related_count,
            "ytdProductCount": len(products),
            "newProductCount": len(new_products),
            "topManagerCount": len(top_managers),
            "personnelCoveredCount": personnel_count,
            "detailErrorCount": len(detail_errors),
            "locationObservationCount": len(location_observations),
            "personnelComparisonStatus": comparison_status,
        },
        "rankingMethod": {
            "formula": "min(存量产品数,40)*2 + 年内备案数*10 + 备案新鲜度(30天内12/90天内6)",
            "purpose": "用于公开信息活跃度排序，不代表管理规模、投资能力或业绩排名。",
        },
        "universeRules": universe_config,
        "managerUniverse": manager_universe,
        "topManagers": top_managers,
        "newProducts": new_products,
        "custodianSummary": custodian_rows,
        "managerCustodianRelations": manager_custodians,
        "personnelChanges": personnel_changes,
        "personnelBaselineNote": "这是首个逐家详情快照；没有上一期人员详情，不输出人员新增、离任或跳槽结论。下一次同口径快照后才计算差异。" if not previous_snapshot else f"已与{args.previous_date}同口径V3详情快照比较；仅输出AMAC公示字段差异。",
        "locationObservations": location_observations,
        "businessTaxonomy": [
            {"code": "product_account_opening", "name": "产品开户"},
            {"code": "custody_outsourcing", "name": "托管外包"},
            {"code": "special_mandate_reduction", "name": "特委减持"},
            {"code": "otc_derivatives", "name": "场外衍生品"},
            {"code": "b_share_funding", "name": "B份额"},
            {"code": "performance_allocation", "name": "业绩切分"},
        ],
        "source": {
            "name": "中国证券投资基金业协会信息公示系统",
            "managerListUrl": "https://gs.amac.org.cn/amac-infodisc/res/pof/manager/managerList.html",
            "fundListUrl": "https://gs.amac.org.cn/amac-infodisc/res/pof/fund/index.html",
            "v1CurrentFile": str(V1_PRIVATE / "data" / f"security-private-fund-daily-{args.date}.json"),
            "v1PreviousFile": str(V1_PRIVATE / "data" / f"security-private-fund-daily-{args.previous_date}.json"),
            "capturedAt": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds"),
        },
        "universeErrors": universe_errors,
        "detailErrors": detail_errors,
    }
    output_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    (output_dir / "latest.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output_path), **snapshot["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
