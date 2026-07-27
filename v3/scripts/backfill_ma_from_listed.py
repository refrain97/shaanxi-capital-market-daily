#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
START_DATE = "2026-01-01"
END_DATE = datetime.now(timezone.utc).date().isoformat()


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def stage_for(title: str) -> str:
    if "终止" in title:
        return "terminated"
    if "问询" in title and "回复" in title:
        return "inquiry_response"
    if "复牌" in title:
        return "plan_disclosed"
    if "停牌" in title:
        return "planning"
    if "报告书" in title or "预案" in title:
        return "plan_disclosed"
    if "进展" in title or "价格及发行数量调整" in title:
        return "in_progress"
    if "筹划" in title or "拟参与" in title:
        return "planning"
    return "supporting_document"


def timeline_role(title: str) -> str:
    support = re.compile(
        r"核查意见|董事会关于|会计师事务所|资产评估有限公司|财务报告|审计报告|评估报告|"
        r"审核报告|持续督导|业绩承诺|募集资金|解除限售|投资者说明会|相关主体不存在|符合《"
    )
    return "supporting_document" if support.search(title) else "milestone"


def main() -> int:
    listed = load("data/backfill/listed/normalized-2026.json")
    universe = load("data/listed/universe.json")
    entity_names = {item["entityId"]: item["canonicalName"] for item in universe["entities"]}
    sources = {item["sourceRecordId"]: item for item in listed["sources"]}
    candidates = [item for item in listed["candidates"] if item.get("rmSubcategory") == "并购重组"]
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in candidates:
        grouped[item["primaryEntityId"]].append(item)

    projects = []
    for entity_id, items in sorted(grouped.items()):
        items.sort(key=lambda item: (item.get("publishedAt") or "", item["title"]))
        documents = []
        milestones_by_key: dict[tuple[str, str], dict] = {}
        for item in items:
            role = timeline_role(item["title"])
            stage = stage_for(item["title"])
            source_ids = item.get("sourceRecordIds", [])
            document = {
                "candidateId": item["eventCandidateId"],
                "at": item.get("publishedAt"),
                "title": item["title"],
                "role": role,
                "stage": stage,
                "sourceRecordIds": source_ids,
                "sourceUrls": [sources[source_id].get("url") for source_id in source_ids if source_id in sources],
            }
            documents.append(document)
            if role == "milestone":
                key = ((item.get("publishedAt") or "")[:10], stage)
                previous = milestones_by_key.get(key)
                if previous is None or len(item["title"]) < len(previous["title"]):
                    milestones_by_key[key] = document
        milestones = sorted(milestones_by_key.values(), key=lambda item: item["at"] or "")
        projects.append({
            "candidateId": f"ma-backfill-{entity_id}",
            "eventKeySeed": f"ma:{entity_id}:2026",
            "primaryEntityId": entity_id,
            "companyName": entity_names.get(entity_id, entity_id),
            "title": f"{entity_names.get(entity_id, entity_id)} 2026年并购重组事项",
            "firstPublishedAt": items[0].get("publishedAt"),
            "latestPublishedAt": items[-1].get("publishedAt"),
            "latestStage": milestones[-1]["stage"] if milestones else "source_gap",
            "milestoneCount": len(milestones),
            "supportingDocumentCount": sum(item["role"] == "supporting_document" for item in documents),
            "sourceRecordIds": sorted({source_id for item in items for source_id in item.get("sourceRecordIds", [])}),
            "noveltyStatus": "backfill",
            "normalizationStatus": "timeline_grouped_pdf_review_pending" if milestones else "source_gap_primary_announcement_missing",
            "milestones": milestones,
            "documents": documents,
        })

    output = {
        "schemaVersion": "0.1",
        "channel": "ma",
        "novelty": "backfill",
        "period": {"startDate": START_DATE, "endDate": END_DATE},
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "DEDUPED_TIMELINES_BODY_REVIEW_PENDING",
        "limits": ["当前项目按活动上市公司主体池初聚类，交易标的仍需公告正文确认", "不在当前活动主体公告范围内的场外并购另行回补"],
        "summary": {
            "announcementCandidateCount": len(candidates),
            "projectCandidateCount": len(projects),
            "milestoneCount": sum(item["milestoneCount"] for item in projects),
            "supportingDocumentCount": sum(item["supportingDocumentCount"] for item in projects),
            "sourceGapProjectCount": sum(item["latestStage"] == "source_gap" for item in projects),
        },
        "sources": [sources[source_id] for source_id in sorted({source_id for item in candidates for source_id in item.get("sourceRecordIds", [])}) if source_id in sources],
        "projects": projects,
    }
    target = ROOT / "data/backfill/ma/normalized-2026.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
