#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def write(relative: str, payload: dict) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def title_score(title: str) -> int:
    score = 0
    if any(word in title for word in ("公告", "预案", "草案", "报告书")):
        score += 8
    if any(word in title for word in ("进展", "计划", "结果", "完成", "终止")):
        score += 3
    if "摘要" in title:
        score -= 2
    if any(word in title for word in ("核查意见", "法律意见", "独立意见", "保荐书", "专项报告", "说明")):
        score -= 8
    return score


def is_supporting_title(title: str) -> bool:
    return any(word in title for word in (
        "核查意见", "法律意见", "独立意见", "保荐书", "专项核查", "董事会关于", "监事会关于",
    )) and not any(word in title for word in ("公告", "预案", "草案", "报告书"))


def lifecycle_status(titles: list[str]) -> tuple[str, str]:
    text = " ".join(titles)
    closed_words = (
        "实施完毕", "实施完成", "回购结果", "回购完成", "终止", "取消", "期限届满",
        "到期赎回", "解除质押", "解除冻结", "上市流通", "注销完成", "归属结果",
        "行权结果", "授予登记完成", "完成过户", "完成非交易过户", "完成工商变更",
        "发行结果", "回购注销实施", "完成换届",
    )
    if any(word in text for word in closed_words):
        return "archived", "标题含明确完成、终止或结果节点"
    return "active", "尚未出现明确结束节点"


def build_listed_workspace() -> dict:
    normalized = load("data/backfill/listed/normalized-2026.json")
    universe = load("data/listed/universe.json")
    sources = {item["sourceRecordId"]: item for item in normalized["sources"]}
    focus = [item for item in normalized["candidates"] if item.get("businessPriority") == "focus"]
    groups: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for item in focus:
        date = item["publishedAt"][:10]
        key = (item["primaryEntityId"], item["rmCategory"], item["rmSubcategory"], date)
        groups[key].append(item)

    matters = []
    for (entity_id, category, subcategory, date), candidates in groups.items():
        if all(is_supporting_title(item["title"]) for item in candidates):
            continue
        ranked = sorted(candidates, key=lambda item: (title_score(item["title"]), item["title"]), reverse=True)
        primary = ranked[0]
        source_rows = []
        seen_urls = set()
        for candidate in ranked:
            for source_id in candidate.get("sourceRecordIds", []):
                source = sources.get(source_id)
                if not source or source.get("url") in seen_urls:
                    continue
                seen_urls.add(source.get("url"))
                source_rows.append({
                    "title": source.get("title") or candidate["title"],
                    "url": source.get("url"),
                    "sourceQuality": source.get("sourceQuality", "official"),
                })
        source = sources.get(primary.get("sourceRecordIds", [None])[0], {})
        status, status_reason = lifecycle_status([item["title"] for item in candidates])
        matters.append({
            "matterId": f"{entity_id}:{subcategory}:{date}",
            "entityId": entity_id,
            "companyName": source.get("canonicalName", entity_id),
            "securityCode": source.get("securityCode", ""),
            "universeTier": source.get("universeTier", ""),
            "publishedAt": primary["publishedAt"],
            "rmCategory": category,
            "rmSubcategory": subcategory,
            "title": primary["title"],
            "targetObjects": primary.get("targetObjects", []),
            "workspaceStatus": status,
            "statusReason": status_reason,
            "sourceCount": len(source_rows),
            "sources": source_rows,
            "normalizationStatus": primary.get("normalizationStatus"),
        })

    matters.sort(key=lambda item: (item["publishedAt"], item["companyName"]), reverse=True)
    tier_stats = []
    for tier in ("L1", "L2", "L3"):
        tier_sources = [item for item in normalized["sources"] if item.get("universeTier") == tier]
        tier_stats.append({
            "tier": tier,
            "subjectCount": len({item["entityId"] for item in tier_sources}),
            "announcementCount": len(tier_sources),
        })
    retrieved_subjects = len({item["entityId"] for item in normalized["sources"]})
    deep_read_path = ROOT / "data/listed/deep-reads-v1-2026.json"
    deep_reads = json.loads(deep_read_path.read_text(encoding="utf-8")) if deep_read_path.exists() else None
    return {
        "schemaVersion": "0.1",
        "year": 2026,
        "asOf": normalized["endDate"],
        "generatedAt": normalized["generatedAt"],
        "universe": {
            "targetCount": universe["counts"]["total"],
            "retrievedSubjectCount": retrieved_subjects,
            "retrievalRate": round(retrieved_subjects / universe["counts"]["total"], 4),
            "tierStats": tier_stats,
            "announcementCount": len(normalized["sources"]),
            "focusCandidateCount": len(focus),
            "matterCount": len(matters),
            "activeMatterCount": sum(item["workspaceStatus"] == "active" for item in matters),
            "archivedMatterCount": sum(item["workspaceStatus"] == "archived" for item in matters),
            "qualityNote": universe["retrievalCoverage"]["note"],
        },
        "matters": matters,
        "deepRead": deep_reads,
    }


def quarter_of(date_text: str) -> str:
    month = int(date_text[5:7])
    return f"Q{(month - 1) // 3 + 1}"


def build_private_workspace() -> dict:
    normalized = load("data/backfill/private-fund/normalized-2026.json")
    products = sorted(normalized["products"], key=lambda item: item["filingDate"], reverse=True)
    quarter_products: dict[str, list[dict]] = {f"Q{index}": [] for index in range(1, 5)}
    for product in products:
        quarter_products[quarter_of(product["filingDate"])].append(product)

    labels = {"Q1": "第一季度", "Q2": "第二季度", "Q3": "第三季度", "Q4": "第四季度"}
    ranges = {
        "Q1": "01.01 - 03.31", "Q2": "04.01 - 06.30",
        "Q3": "07.01 - 09.30", "Q4": "10.01 - 12.31",
    }
    quarters = []
    for quarter in ("Q1", "Q2", "Q3", "Q4"):
        rows = quarter_products[quarter]
        quarters.append({
            "quarter": quarter,
            "label": labels[quarter],
            "dateRange": ranges[quarter],
            "productCount": len(rows),
            "managerCount": len({item["managerName"] for item in rows}),
            "custodianCount": len({item["custodian"] for item in rows}),
            "products": rows,
        })

    manager_counts = Counter(item["managerName"] for item in products)
    custodian_counts = Counter(item["custodian"] for item in products)
    monthly_counts = Counter(item["filingDate"][:7] for item in products)
    return {
        "schemaVersion": "0.1",
        "year": 2026,
        "asOf": normalized["endDate"],
        "generatedAt": normalized["generatedAt"],
        "summary": {
            "productCount": len(products),
            "managerCount": len(manager_counts),
            "custodianCount": len(custodian_counts),
            "activeQuarterCount": sum(bool(rows) for rows in quarter_products.values()),
            "latestFilingDate": products[0]["filingDate"] if products else None,
            "topManager": {"name": manager_counts.most_common(1)[0][0], "count": manager_counts.most_common(1)[0][1]} if manager_counts else None,
            "topCustodian": {"name": custodian_counts.most_common(1)[0][0], "count": custodian_counts.most_common(1)[0][1]} if custodian_counts else None,
            "coverageStatus": normalized["coverage"]["status"],
        },
        "quarters": quarters,
        "managerRanking": [{"name": name, "count": count} for name, count in manager_counts.most_common()],
        "custodianRanking": [{"name": name, "count": count} for name, count in custodian_counts.most_common()],
        "monthlySeries": [{"month": f"{month:02d}", "count": monthly_counts.get(f"2026-{month:02d}", 0)} for month in range(1, 13)],
    }


def main() -> int:
    listed = build_listed_workspace()
    private = build_private_workspace()
    write("data/listed/workspace-2026.json", listed)
    write("data/private-fund/workspace-2026.json", private)
    print(json.dumps({
        "listedMatters": len(listed["matters"]),
        "listedRetrieved": listed["universe"]["retrievedSubjectCount"],
        "privateProducts": private["summary"]["productCount"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
