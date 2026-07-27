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
UNIVERSE_PATH = ROOT / "data/listed/universe.json"
OFFICIAL_NAME = re.compile(r"listed-official-(2026-\d{2}-\d{2})\.json$")
SECTION_PRIORITY = {"02": 0, "04": 1, "03": 2, "05": 3, "01": 4}
EVIDENCE_PRIORITY = {
    "PDF正文数字已核验": 4,
    "PDF正文已命中": 3,
    "PDF已抽取待核": 2,
    "仅标题待核": 1,
}
EVENT_RULES = [
    ("litigation", "诉讼仲裁", ("诉讼", "仲裁")),
    ("abnormal_move", "异常波动", ("异常波动",)),
    ("major_contract", "重大合同", ("算力服务合同", "重大合同", "签署合同")),
    ("performance", "业绩预告", ("业绩预告", "营业收入", "归母净利润")),
    ("refinancing", "再融资", ("可转债募集资金", "募投项目", "募集说明书")),
    ("convertible_bond", "可转债兑付", ("可转债兑付", "转债将按", "到期兑付", "摘牌")),
    ("product_registration", "产品注册", ("医疗器械注册证", "注册证", "获证")),
    ("lockup_release", "限售股上市流通", ("限售股", "上市流通", "解除限售")),
    ("operations_project", "产销与项目进展", ("产销", "厂房主体封顶", "武汉项目", "生产线")),
    ("voting_agreement", "一致行动安排", ("一致行动", "表决安排")),
    ("write_off", "应收款项核销", ("核销应收", "应收账款及其他应收款", "坏账准备")),
    ("dividend", "权益分派", ("权益分派", "现金红利", "除权除息")),
    ("incentive", "股权激励", ("激励对象", "回购注销", "限制性股票")),
    ("debt_financing", "债务融资", ("中期票据", "超短期融资券", "短期融资券", "债务融资工具", "接受注册")),
    ("related_loan", "关联借款", ("借款展期", "展期年利率", "控股股东借款")),
    ("guarantee", "担保", ("连带责任保证", "担保总额", "对外担保", "提供担保")),
    ("ownership_change", "股东权益变动", ("权益变动", "减持", "持股比例由")),
    ("cash_management", "现金管理", ("现金管理", "闲置募集资金", "理财产品")),
    ("pledge", "股份质押", ("解除质押", "剩余质押", "股份质押")),
    ("share_increase", "股东增持", ("增持计划", "首次增持", "本次增持")),
    ("shareholder_meeting", "股东会与治理", ("临时股东会", "年度股东会", "召开股东会", "股东会将审议", "补选")),
    ("bond_issue", "债券发行", ("公司债券", "发行规模", "票面利率")),
]


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


def event_key(text: str) -> tuple[str, str]:
    text = plain(text)
    for key, label, keywords in EVENT_RULES:
        if any(keyword in text for keyword in keywords):
            return key, label
    return "general", "重要事项"


def split_entry(company: str, entry: dict) -> list[tuple[str, dict]]:
    summary = plain(entry.get("summary"))
    clauses = [plain(value) for value in re.split(r"；", summary) if plain(value)]
    clause_keys = [event_key(clause) for clause in clauses]
    for index, detected in enumerate(clause_keys):
        if detected[0] != "general":
            continue
        replacement = next((value for value in clause_keys[index + 1:] if value[0] != "general"), None)
        if replacement is None:
            replacement = next((value for value in reversed(clause_keys[:index]) if value[0] != "general"), None)
        clause_keys[index] = replacement or event_key(f"{entry.get('title', '')} {clauses[index]}")
    if any(key == "refinancing" for key, _ in clause_keys) and "可转债" in f"{entry.get('title', '')} {summary}":
        clause_keys = [("refinancing", "再融资") if key == "bond_issue" else (key, label) for key, label in clause_keys]
    unique_keys = {key for key, _ in clause_keys}
    if len(clauses) < 2 or len(unique_keys) < 2:
        key, label = event_key(f"{entry.get('title', '')} {summary}")
        single_item = dict(entry)
        if key != "general" and "资本运作与股东事项" in plain(single_item.get("title")):
            single_item["title"] = f"{company}｜{label}"
        return [(key, single_item)]

    results = []
    for clause, (key, label) in zip(clauses, clause_keys):
        split_item = dict(entry)
        split_item["title"] = f"{company}｜{label}"
        split_item["summary"] = re.sub(r"^(同日|公司另披露|公司同步提示)", "", clause).strip("，， ")
        results.append((key, split_item))
    return results


def add_entry(groups: dict[tuple[str, str, str], list[dict]], report_date: str, company: str, entry: dict) -> None:
    company = plain(company)
    if company:
        for key, split_item in split_entry(company, entry):
            groups[(report_date, company, key)].append(split_item)


def curated_entries(report_date: str, payload: dict, groups: dict[tuple[str, str, str], list[dict]]) -> dict[str, dict]:
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
        body = plain(item.get("body"))
        parts = [plain(value) for value in re.split(r"，?(?:以及|并关注)|；", body) if plain(value)]
        detected_parts = [(event_key(part)[0], part) for part in parts if event_key(part)[0] != "general"]
        if len({key for key, _ in detected_parts}) > 1:
            for key, part in detected_parts:
                action = part if part.startswith(("跟踪", "关注")) else f"关注{part}"
                annotations[company].setdefault("matterActions", {})[key] = action
        else:
            key, _ = event_key(f"{item.get('title', '')} {body}")
            annotations[company].setdefault("matterActions", {})[key] = body
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
        r"(?<![\d.%])[-+]?\d[\d,]*(?:\.\d+)?\s*"
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
    if any(word in text for word in ("一致行动", "表决安排", "减持", "增持", "权益变动", "质押", "拍卖", "解禁")):
        return ["股东服务"]
    if any(word in text for word in ("核销应收", "坏账准备", "授信", "担保", "现金管理", "借款", "贷款", "债务融资", "中期票据", "融资租赁")):
        return ["资金与财务"]
    if any(word in text for word in ("激励对象", "回购注销", "限制性股票")):
        return ["激励与员工"]
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
        "资本运作": "关注审核、发行或交割进度，以及资金用途和资本结构变化。",
        "股东服务": "关注股东实施节奏、持股比例变化及后续披露。",
        "资金与财务": "关注融资成本、担保敞口、资金使用效率及现金流影响。",
        "治理关系": "关注人员变动、审议结果及治理衔接。",
        "激励与员工": "关注回购注销、授予归属、股份支付费用及员工持股变化。",
        "风险沟通": "关注监管、诉讼或风险处置进展，以及对经营和财务的影响。",
        "业绩与分红": "关注业绩最终确认、增长驱动、现金流及分红安排。",
        "经营与产业": "关注项目落地、产能兑现、订单执行及现金流贡献。",
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

    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    active_names = {plain(item.get("canonicalName")) for item in universe.get("entities", [])}
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    annotations_by_day: dict[str, dict[str, dict]] = {}
    workbench_by_day: dict[str, list[dict[str, str]]] = {}
    for report_date, path in curated_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        annotations_by_day[report_date] = curated_entries(report_date, payload, groups)
        workbench_by_day[report_date] = load_workbench(report_date)

    deep_reads = []
    for (report_date, company, matter_key), entries in groups.items():
        if company not in active_names:
            continue
        entries = sorted(entries, key=lambda item: SECTION_PRIORITY[item["section"]])
        primary = entries[0]
        annotations = annotations_by_day.get(report_date, {}).get(company, {})
        company_rows = [row for row in workbench_by_day.get(report_date, []) if plain(row.get("company")) == company]
        rows = [row for row in company_rows if event_key(f"{row.get('title', '')} {row.get('secondaryTags', '')}")[0] == matter_key]
        if not rows:
            rows = company_rows if len({key for date, name, key in groups if date == report_date and name == company}) == 1 else []
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
                if value != "未归类" and value not in categories:
                    categories.append(value)
            for value in split_values(row.get("secondaryTags", "")):
                if value != "未归类" and value not in tags:
                    tags.append(value)
            for target in split_targets(plain(row.get("followTarget"))):
                if target not in follow_targets:
                    follow_targets.append(target)

        evidence_level = max(
            (row.get("evidenceLevel") or "仅标题待核" for row in rows),
            key=lambda value: EVIDENCE_PRIORITY.get(value, 0),
            default="仅标题待核",
        )
        next_action = plain(annotations.get("matterActions", {}).get(matter_key))
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
            if split_values(row.get("businessViews", ""))[:1] == [preferred] and plain(row.get("businessAction"))
        ), None)
        if not verified_numbers and matched_row:
            verified_numbers = [
                value for value in split_numbers(matched_row.get("numbers", ""))
                if not re.fullmatch(r"\d{1,4}年|\d{1,2}日", value)
                and value != f"{plain(matched_row.get('code'))}股"
            ]
        business_judgement = fallback_business_judgement(primary, preferred_views)
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
            "deepReadId": f"listed-deep-read-{report_date}-{company_slug}-{matter_key}",
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
        "source": "上市公司正式精读与公告原文",
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
