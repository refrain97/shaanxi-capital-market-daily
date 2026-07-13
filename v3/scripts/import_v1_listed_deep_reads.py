#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from html import unescape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
V1_ROOT = REPO_ROOT / "v1/陕西省上市公司日报v1"
CURATED_DIR = V1_ROOT / "data/curated"
OUTPUT_DIR = V1_ROOT / "outputs"
TARGET = ROOT / "data/listed/deep-reads-v1-2026.json"
OFFICIAL_NAME = re.compile(r"listed-official-(2026-\d{2}-\d{2})\.json$")
SECTION_PRIORITY = {"02": 0, "04": 1, "03": 2, "05": 3, "01": 4}
EVIDENCE_PRIORITY = {
    "PDF正文数字已核验": 4,
    "PDF正文已命中": 3,
    "PDF已抽取待核": 2,
    "仅标题待核": 1,
}


def plain(value: object) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return re.sub(r"\s+", " ", unescape(text)).strip()


def company_from_title(title: str) -> str:
    parts = [part.strip() for part in re.split(r"[｜|]", plain(title)) if part.strip()]
    if not parts:
        return ""
    if parts[0] in {"必看", "重点", "次重点", "观察"} and len(parts) > 1:
        return parts[1]
    return parts[0]


def load_workbench(report_date: str) -> list[dict[str, str]]:
    path = OUTPUT_DIR / f"shaanxi-listed-vr-workbench-{report_date}.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def add_entry(groups: dict[tuple[str, str], list[dict]], report_date: str, company: str, entry: dict) -> None:
    company = plain(company)
    if company:
        groups[(report_date, company)].append(entry)


def curated_entries(report_date: str, payload: dict, groups: dict[tuple[str, str], list[dict]]) -> dict[str, dict]:
    annotations: dict[str, dict] = defaultdict(dict)
    for item in payload.get("opportunities", []):
        company = company_from_title(item.get("title", ""))
        annotations[company]["opportunity"] = {
            "title": plain(item.get("title")),
            "body": plain(item.get("body")),
        }

    for item in payload.get("risk_rows", []):
        company = plain(item.get("company"))
        add_entry(groups, report_date, company, {
            "section": "02",
            "sectionName": "重大事项与风险公告",
            "title": f"{company}｜{plain(item.get('tag')) or '风险事项'}",
            "summary": plain(item.get("event")),
            "judgement": "风险事项，需持续核验公告进展和处置结果。",
        })

    for item in payload.get("tiles", []):
        title = plain(item.get("title"))
        add_entry(groups, report_date, company_from_title(title), {
            "section": "03",
            "sectionName": "上市公司动态",
            "title": title,
            "summary": plain(item.get("body")),
            "judgement": "值得业务跟进的公司进展。",
        })

    for item in payload.get("capital_rows", []):
        company = plain(item.get("company"))
        add_entry(groups, report_date, company, {
            "section": "04",
            "sectionName": "股东变动与资本运作",
            "title": f"{company}｜资本运作与股东事项",
            "summary": plain(item.get("numbersHtml")),
            "judgement": plain(item.get("attention")),
        })

    for column in payload.get("fixed_columns", []):
        column_name = plain(column.get("title"))
        for item in column.get("items", []):
            title = plain(item.get("title"))
            add_entry(groups, report_date, company_from_title(title), {
                "section": "05",
                "sectionName": column_name or "治理与固定披露",
                "title": title,
                "summary": plain(item.get("body")),
                "judgement": "固定披露已按正文提取关键人员、议案、数字或结果。",
            })

    for item in payload.get("follow_items", []):
        company = company_from_title(item.get("title", ""))
        annotations[company]["nextAction"] = plain(item.get("body"))
        annotations[company]["followTitle"] = plain(item.get("title"))
    return annotations


def split_values(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[、,，]", value or "") if item.strip()]


def split_numbers(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[、;；]", value or "") if item.strip()]


def split_targets(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"\s*/\s*|[、,，]", value or "") if item.strip()]


def extract_key_numbers(*values: str) -> list[str]:
    pattern = re.compile(
        r"(?<![\d.])[-+]?\d[\d,]*(?:\.\d+)?\s*"
        r"(?:亿元|万元|元/股|万股|亿股|个百分点|%|元|股|人|家|项|个月)"
    )
    result = []
    for value in values:
        for match in pattern.findall(plain(value)):
            normalized = re.sub(r"\s+", "", match)
            if normalized not in result:
                result.append(normalized)
    return result


def preferred_business_views(primary: dict) -> list[str]:
    text = f"{primary['title']} {primary['summary']}"
    if any(word in text for word in ("诉讼", "监管", "问询", "警示", "风险", "整改", "执行受理")):
        return ["风险沟通", "资本运作"]
    if any(word in text for word in ("业绩", "净利润", "分红", "年报", "半年度", "季报")):
        return ["业绩与分红"]
    if any(word in text for word in ("减持", "增持", "权益变动", "质押", "拍卖", "解禁")):
        return ["股东服务"]
    if any(word in text for word in ("授信", "担保", "现金管理", "贷款", "融资租赁")):
        return ["资金与财务"]
    if any(word in text for word in ("重组", "收购", "发行股份", "定增", "可转债", "回购")):
        return ["资本运作"]
    if primary["section"] == "05":
        return ["治理关系"]
    if primary["section"] == "03":
        return ["经营与产业", "业绩与分红"]
    if primary["section"] == "04":
        return ["资本运作", "股东服务", "资金与财务"]
    return ["风险沟通", "资本运作"]


def fallback_business_judgement(primary: dict, preferred_views: list[str]) -> str:
    templates = {
        "资本运作": "跟踪交易作价、审批进度、资金用途和后续资本运作节点。",
        "股东服务": "跟踪股东实施节奏、持股变化、资金安排和披露节点。",
        "资金与财务": "跟踪授信、担保敞口、资金成本和现金流影响。",
        "治理关系": "更新关键联系人和治理节点，跟踪后续审议或任职结果。",
        "风险沟通": "跟踪监管、诉讼、整改或风险处置进展，并核验对经营和财务的影响。",
        "业绩与分红": "跟踪业绩兑现、利润驱动、分红安排和投资者沟通节点。",
        "经营与产业": "跟踪经营影响、项目落地、产能变化和现金流传导。",
    }
    return templates.get(preferred_views[0], primary["judgement"])


def lifecycle_status(text: str, next_action: str) -> tuple[str, str]:
    if next_action:
        return "active", "V1精读已设置下一跟踪动作"
    closed_words = (
        "实施完毕", "已完成", "完成过户", "登记完成", "终止", "取消", "到期赎回",
        "审议通过", "离任生效", "辞职报告", "解除质押", "上市流通",
    )
    if any(word in text for word in closed_words):
        return "archived", "正文显示该节点已经完成或终止"
    return "active", "正文已精读，后续节点尚未形成明确结束结论"


def main() -> int:
    curated_files = []
    for path in sorted(CURATED_DIR.glob("listed-official-2026-*.json")):
        match = OFFICIAL_NAME.fullmatch(path.name)
        if match:
            curated_files.append((match.group(1), path))
    if not curated_files:
        if TARGET.exists():
            print(json.dumps({"status": "SKIP", "reason": "V1 source tree unavailable; retained published deep-read artifact"}, ensure_ascii=False))
            return 0
        raise SystemExit("No V1 listed official curated files found")

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    annotations_by_day: dict[str, dict[str, dict]] = {}
    workbench_by_day: dict[str, list[dict[str, str]]] = {}
    for report_date, path in curated_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        annotations_by_day[report_date] = curated_entries(report_date, payload, groups)
        workbench_by_day[report_date] = load_workbench(report_date)

    deep_reads = []
    for (report_date, company), entries in groups.items():
        entries = sorted(entries, key=lambda item: SECTION_PRIORITY[item["section"]])
        primary = entries[0]
        annotations = annotations_by_day.get(report_date, {}).get(company, {})
        rows = [row for row in workbench_by_day.get(report_date, []) if plain(row.get("company")) == company]
        rows.sort(key=lambda row: (int(row.get("score") or 0), row.get("readDecision") == "必须精读"), reverse=True)
        evidence_rows = [row for row in rows if row.get("hasText") == "是" and row.get("url")]
        if not evidence_rows:
            evidence_rows = [row for row in rows if row.get("url")]

        sources = []
        seen_urls = set()
        for row in evidence_rows:
            url = row.get("url") or ""
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            sources.append({
                "announcementId": row.get("announcementId"),
                "publishedAt": row.get("date"),
                "title": plain(row.get("title")),
                "url": url,
                "evidenceLevel": row.get("evidenceLevel"),
            })

        categories = []
        tags = []
        follow_targets = []
        for row in rows:
            for value in split_values(row.get("businessViews", "")):
                if value not in categories:
                    categories.append(value)
            for value in split_values(row.get("secondaryTags", "")):
                if value not in tags:
                    tags.append(value)
            for target in split_targets(plain(row.get("followTarget"))):
                if target not in follow_targets:
                    follow_targets.append(target)

        evidence_level = max(
            (row.get("evidenceLevel") or "仅标题待核" for row in rows),
            key=lambda value: EVIDENCE_PRIORITY.get(value, 0),
            default="仅标题待核",
        )
        next_action = plain(annotations.get("nextAction"))
        if not next_action:
            next_action = next((
                entry["judgement"] for entry in entries
                if entry["judgement"] and any(word in entry["judgement"] for word in ("跟踪", "需看", "后续", "等待", "关注"))
            ), "")
        opportunity = annotations.get("opportunity", {})
        curated_number_texts = [
            opportunity.get("body", ""),
            primary["summary"],
            next_action,
            *(entry["summary"] for entry in entries[1:]),
        ]
        verified_numbers = extract_key_numbers(*curated_number_texts)
        preferred_views = preferred_business_views(primary)
        matched_row = next((
            row for preferred in preferred_views for row in rows
            if preferred in split_values(row.get("businessViews", "")) and plain(row.get("businessAction"))
        ), None)
        if not verified_numbers and matched_row:
            verified_numbers = [
                value for value in split_numbers(matched_row.get("numbers", ""))
                if not re.fullmatch(r"\d{1,4}年|\d{1,2}日", value)
            ]
        business_judgement = plain(matched_row.get("businessAction")) if matched_row else fallback_business_judgement(primary, preferred_views)
        combined_text = " ".join([primary["title"], primary["summary"], primary["judgement"], next_action])
        status, status_reason = lifecycle_status(combined_text, next_action)
        company_slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", company)
        published_dates = [source["publishedAt"] for source in sources if source.get("publishedAt")]
        supporting = []
        for entry in entries[1:]:
            if entry["summary"] and entry["summary"] != primary["summary"]:
                supporting.append({
                    "section": entry["section"],
                    "sectionName": entry["sectionName"],
                    "title": entry["title"],
                    "summary": entry["summary"],
                })
        deep_reads.append({
            "deepReadId": f"v1-deep-read-{report_date}-{company_slug}",
            "reportDate": report_date,
            "publishedAt": max(published_dates) if published_dates else report_date,
            "companyName": company,
            "securityCode": rows[0].get("code") if rows else "",
            "title": primary["title"],
            "summary": primary["summary"],
            "importanceNote": plain(opportunity.get("body")),
            "businessJudgement": business_judgement,
            "nextAction": next_action,
            "followTargets": follow_targets,
            "primarySection": primary["section"],
            "primarySectionName": primary["sectionName"],
            "rmCategories": categories,
            "rmSubcategories": tags,
            "verifiedNumbers": verified_numbers[:12],
            "supportingInsights": supporting,
            "workspaceStatus": status,
            "statusReason": status_reason,
            "readStatus": "v1_pdf_deep_read",
            "evidenceLevel": evidence_level,
            "pdfTextEvidenceCount": sum(row.get("hasText") == "是" for row in rows),
            "sourceCount": len(sources),
            "sources": sources,
        })

    deep_reads.sort(key=lambda item: (item["reportDate"], item["companyName"]), reverse=True)
    report_dates = sorted({item["reportDate"] for item in deep_reads})
    latest_date = report_dates[-1]
    payload = {
        "schemaVersion": "0.1",
        "source": "V1上市公司精读正式JSON、VR选题台与PDF正文证据",
        "coverageStart": report_dates[0],
        "coverageEnd": latest_date,
        "reportCount": len(curated_files),
        "deepReadItemCount": len(deep_reads),
        "latestReportDate": latest_date,
        "latestItemCount": sum(item["reportDate"] == latest_date for item in deep_reads),
        "pdfVerifiedItemCount": sum(item["evidenceLevel"] == "PDF正文数字已核验" for item in deep_reads),
        "activeItemCount": sum(item["workspaceStatus"] == "active" for item in deep_reads),
        "archivedItemCount": sum(item["workspaceStatus"] == "archived" for item in deep_reads),
        "backfillGap": {
            "start": "2026-01-01",
            "end": "2026-05-20",
            "status": "pending_pdf_deep_read",
            "note": "该区间已有全量检索和标题候选，但尚未达到V1 PDF正文精读发布标准。",
        },
        "items": deep_reads,
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "reports": payload["reportCount"],
        "deepReads": payload["deepReadItemCount"],
        "latestDate": latest_date,
        "latestItems": payload["latestItemCount"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
