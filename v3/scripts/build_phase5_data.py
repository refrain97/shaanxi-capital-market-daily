#!/usr/bin/env python3
"""Build Phase 5 M&A projects and pre-IPO enterprise profiles from verified local assets."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
V3_ROOT = Path(__file__).resolve().parents[1]
CASE_SCRIPT = ROOT / "v1/陕西省收并购日报v1/scripts/render_shaanxi_ma_cases.py"
DASHBOARD_PATH = V3_ROOT / "data/sample/dashboard-2026-07-10.json"
RESERVE_PATH = V3_ROOT / "data/reference/2026-sx-listing-reserve-a-tier.json"


def load_cases() -> list[tuple[str, ...]]:
    tree = ast.parse(CASE_SCRIPT.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "cases" for target in node.targets):
            return ast.literal_eval(node.value)
    raise RuntimeError("cases assignment not found")


def project_id(title: str) -> str:
    normalized = re.sub(r"^\d+\s*", "", title)
    normalized = re.sub(r"[\s｜|/]+", "", normalized)
    return "ma-" + hashlib.sha256(normalized.encode()).hexdigest()[:16]


def stage_from_status(value: str) -> str:
    if any(word in value for word in ("终止", "失败")):
        return "terminated"
    if any(word in value for word in ("完成", "过户", "工商变更", "生效条件达成")):
        return "completed"
    if any(word in value for word in ("签协议", "董事会通过", "草案", "预案", "股东会")):
        return "signed_or_approved"
    if any(word in value for word in ("筹划", "意向", "停牌", "提示", "问询")):
        return "planning"
    return "in_progress"


def milestones_from_text(text: str, status: str) -> list[dict[str, Any]]:
    milestones = []
    for index, part in enumerate(re.split(r"[；;]", text)):
        part = part.strip()
        if not part:
            continue
        full = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", part)
        short = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})日", part)
        if full:
            at = f"{full.group(1)}-{int(full.group(2)):02d}-{int(full.group(3)):02d}"
        elif short:
            at = f"2026-{int(short.group(1)):02d}-{int(short.group(2)):02d}"
        else:
            at = None
        milestones.append({"milestoneId": f"m-{index + 1}", "at": at, "label": part, "stageAfter": stage_from_status(status), "sourceIds": []})
    return milestones


def latest_milestone_at(project: dict[str, Any]) -> str:
    dates = [item["at"] for item in project["milestones"] if item.get("at")]
    return max(dates) if dates else "0000-00-00"


def upsert_dashboard_listing(dashboard: dict[str, Any]) -> None:
    entity = next(item for item in dashboard["entities"] if item["entityId"] == "ent-maikeaote")
    entity.update({
        "entityType": "listed_company",
        "canonicalName": "陕西麦科奥特医药科技股份有限公司",
        "aliases": ["麦科奥特", "麦科医药-B"],
        "region": "陕西",
        "securityCode": "02335.HK",
        "universeTier": "L1",
    })

    source_id = "src-maikeaote-listing"
    if not any(item["sourceRecordId"] == source_id for item in dashboard["sources"]):
        dashboard["sources"].append({
            "sourceRecordId": source_id,
            "sourceType": "exchange_official",
            "sourceName": "香港交易所",
            "url": "https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/HKSCC/2026/ce_HKSCC_SKA_186_2026.pdf",
            "title": "Stock Admission - New Listing of Securities (2335)",
            "publishedAt": "2026-06-22T00:00:00+08:00",
            "fetchedAt": "2026-07-12T11:00:00+08:00",
            "sourceQuality": "official",
        })

    event = next(item for item in dashboard["events"] if item["eventId"] == "evt-20260611-maikeaote-hearing")
    event.update({
        "title": "陕西麦科奥特完成港交所主板上市",
        "summary": "麦科奥特6月11日通过聆讯，6月24日以2335.HK在港交所主板上市；同一上市进程更新为完成。",
        "lastCheckedAt": "2026-07-12T11:00:00+08:00",
        "eventStatus": "completed",
        "noveltyStatus": "progress",
        "sourceRecordIds": ["src-maikeaote-hearing", source_id],
        "metrics": [{"label": "上市阶段", "value": "已上市"}, {"label": "证券代码", "value": "02335.HK"}],
        "timeline": [
            {"at": "2026-06-11", "label": "通过港交所聆讯"},
            {"at": "2026-06-24", "label": "港交所主板挂牌上市，代码2335.HK"},
        ],
    })
    evidence = next(item for item in dashboard["evidence"] if item["evidenceId"] == "evd-maikeaote")
    evidence.update({"sourceRecordId": source_id, "value": "2026-06-24在港交所上市，证券代码02335.HK"})
    signal = next(item for item in dashboard["signals"] if item["signalId"] == "sig-maikeaote")
    signal.update({
        "headline": "麦科奥特已完成港股上市",
        "whyItMatters": "上市节点已完成，后续转入陕西港股上市公司持续跟踪。",
        "signalStatus": "completed",
        "actionable": False,
        "reasoning": "香港交易所新上市证券记录确认6月24日挂牌。",
    })
    lead = next(item for item in dashboard["leads"] if item["leadId"] == "lead-maikeaote")
    lead.update({
        "opportunityType": "港股上市后服务",
        "rationale": "港股上市节点已经完成，原上市进度线索已转化。",
        "nextAction": "转入上市公司持续服务，跟踪上市后公告、融资和股东事项。",
        "leadStatus": "converted",
        "confidence": "high",
    })
    for snapshot in dashboard["snapshots"]:
        snapshot["activeSignalIds"] = [item for item in snapshot["activeSignalIds"] if item != "sig-maikeaote"]


def main() -> None:
    dashboard = json.loads(DASHBOARD_PATH.read_text())
    reserve = json.loads(RESERVE_PATH.read_text())
    source_lookup = {item["sourceRecordId"]: item for item in dashboard["sources"]}
    ma_events = [item for item in dashboard["events"] if item["channel"] == "ma"]
    legacy_cases = load_cases()
    projects = []

    for case in legacy_cases:
        title, dimension, status, _, _, date_text, direction, parties, amount_text, industry, significance, next_action = case
        clean_title = re.sub(r"^\d+\s*", "", title)
        project = {
            "maProjectId": project_id(title),
            "title": clean_title,
            "dimension": dimension,
            "stage": stage_from_status(status),
            "statusText": status,
            "firstDisclosureText": date_text,
            "direction": direction,
            "partiesText": parties,
            "amountText": amount_text,
            "industry": industry,
            "significance": significance,
            "nextAction": next_action,
            "milestones": milestones_from_text(date_text, status),
            "sourceRecords": [],
            "sourceStatus": "needs_source_backfill",
            "legacyOrigin": "V1 deterministic renderer",
        }
        if "陕鼓动力" in clean_title:
            event = next(item for item in ma_events if "陕鼓动力" in item["title"])
            sources = [source_lookup[source_id] for source_id in event["sourceRecordIds"]]
            project["sourceRecords"] = sources
            project["sourceStatus"] = "official"
            project["milestones"] = [{"milestoneId": f"m-{index+1}", "at": node["at"], "label": node["label"], "stageAfter": event["eventStatus"], "sourceIds": event["sourceRecordIds"]} for index, node in enumerate(event["timeline"])]
        projects.append(project)

    rainbow = next(item for item in ma_events if "彩虹股份" in item["title"])
    rainbow_sources = [source_lookup[source_id] for source_id in rainbow["sourceRecordIds"]]
    projects.append({
        "maProjectId": "ma-rainbow-hongyang-minority-2026",
        "title": rainbow["title"],
        "dimension": "已上市公司",
        "stage": "signed_or_approved",
        "statusText": "协议签署/待交割",
        "firstDisclosureText": "2026-07-07公告",
        "direction": "陕西上市公司收购控股子公司少数股权",
        "partiesText": "彩虹股份；虹阳显示33.4204%少数股权",
        "amountText": "以公告原文为准",
        "industry": "显示面板",
        "significance": rainbow["summary"],
        "nextAction": "跟踪7月20日付款、贷款提款、工商变更和交割。",
        "milestones": [{"milestoneId": f"m-{index+1}", "at": node["at"], "label": node["label"], "stageAfter": rainbow["eventStatus"], "sourceIds": rainbow["sourceRecordIds"]} for index, node in enumerate(rainbow["timeline"])],
        "sourceRecords": rainbow_sources,
        "sourceStatus": "official",
        "legacyOrigin": None,
    })

    projects.sort(key=lambda item: (latest_milestone_at(item), item["title"]), reverse=True)
    ma_output = {
        "schemaVersion": "0.1",
        "asOf": "2026-07-12T11:00:00+08:00",
        "projectCount": len(projects),
        "officialSourceProjectCount": sum(item["sourceStatus"] == "official" for item in projects),
        "sourceBackfillCount": sum(item["sourceStatus"] != "official" for item in projects),
        "stageCounts": {stage: sum(item["stage"] == stage for item in projects) for stage in sorted({item["stage"] for item in projects})},
        "projects": projects,
    }

    reserve_profiles = [{
        "enterpriseId": "preipo-" + hashlib.sha256(item["name"].encode()).hexdigest()[:16],
        "name": item["name"],
        "reserveRank": item["rank"],
        "reserveTier": item["tier"],
        "listingStage": "reserve_A",
        "latestMilestone": "入选2026年度A档省级上市后备企业",
        "latestMilestoneAt": reserve["publishedAt"],
        "financingStatus": "not_disclosed",
        "milestones": [{"at": reserve["publishedAt"], "type": "reserve_list", "label": "入选2026年度A档省级上市后备企业", "sourceUrl": reserve["sourceUrl"]}],
        "sourceStatus": "authoritative_attachment",
    } for item in reserve["companies"]]
    profile_by_name = {item["name"]: item for item in reserve_profiles}
    for project in projects:
        for name in ("西安紫光国芯半导体股份有限公司", "西安中科西光航天科技集团有限公司", "西安奇芯光电科技有限公司"):
            if name.split("有限公司")[0].replace("西安", "")[:4] in project["title"] and name in profile_by_name:
                milestone_at = latest_milestone_at(project)
                profile_by_name[name]["milestones"].append({"at": milestone_at, "type": "ma_progress", "label": project["title"], "sourceUrl": project["sourceRecords"][0]["url"] if project["sourceRecords"] else None})
                if milestone_at > profile_by_name[name]["latestMilestoneAt"]:
                    profile_by_name[name]["latestMilestone"] = project["title"]
                    profile_by_name[name]["latestMilestoneAt"] = milestone_at

    reserve_profiles.append({
        "enterpriseId": "ent-maikeaote",
        "name": "陕西麦科奥特医药科技股份有限公司",
        "reserveRank": None,
        "reserveTier": "graduated",
        "listingStage": "listed_hk",
        "securityCode": "02335.HK",
        "latestMilestone": "港交所主板挂牌上市",
        "latestMilestoneAt": "2026-06-24",
        "financingStatus": "ipo_completed",
        "milestones": [
            {"at": "2026-06-11", "type": "hearing", "label": "通过港交所聆讯", "sourceUrl": source_lookup["src-maikeaote-hearing"]["url"]},
            {"at": "2026-06-24", "type": "listed", "label": "港交所主板挂牌上市，代码2335.HK", "sourceUrl": "https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/HKSCC/2026/ce_HKSCC_SKA_186_2026.pdf"},
        ],
        "sourceStatus": "official",
    })

    preipo_output = {
        "schemaVersion": "0.1",
        "asOf": "2026-07-12T11:00:00+08:00",
        "reserveYear": 2026,
        "reserveTotalCount": reserve["totalCount"],
        "tierCounts": reserve["tierCounts"],
        "priorityProfileCount": len(reserve_profiles),
        "aTierTranscribedCount": len(reserve["companies"]),
        "graduatedCount": sum(item["reserveTier"] == "graduated" for item in reserve_profiles),
        "profiles": reserve_profiles,
        "financingRecords": [
            {
                "financingId": "fin-maikeaote-preipo-202606",
                "enterpriseId": "ent-maikeaote",
                "round": "IPO基石投资",
                "amountText": "2.5亿元",
                "investors": ["陕西省科创母基金直投份额", "西安高新金融控股集团"],
                "announcedAt": "2026-06-24",
                "sourceUrl": "https://www.ca-ht.com/show/1273",
                "sourceQuality": "official_investor",
                "verificationStatus": "verified"
            }
        ],
        "source": {
            "issuer": reserve["issuer"],
            "documentNo": reserve["documentNo"],
            "publishedAt": reserve["publishedAt"],
            "url": reserve["sourceUrl"],
            "transcriptionStatus": reserve["transcriptionStatus"],
        },
    }

    ma_dir = V3_ROOT / "data/ma-projects"
    preipo_dir = V3_ROOT / "data/pre-ipo"
    ma_dir.mkdir(parents=True, exist_ok=True)
    preipo_dir.mkdir(parents=True, exist_ok=True)
    (ma_dir / "latest.json").write_text(json.dumps(ma_output, ensure_ascii=False, indent=2) + "\n")
    (preipo_dir / "latest.json").write_text(json.dumps(preipo_output, ensure_ascii=False, indent=2) + "\n")
    upsert_dashboard_listing(dashboard)
    DASHBOARD_PATH.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "maProjectCount": ma_output["projectCount"],
        "maOfficialSourceCount": ma_output["officialSourceProjectCount"],
        "maBackfillCount": ma_output["sourceBackfillCount"],
        "reserveTotalCount": preipo_output["reserveTotalCount"],
        "priorityProfileCount": preipo_output["priorityProfileCount"],
        "financingRecordCount": len(preipo_output["financingRecords"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
