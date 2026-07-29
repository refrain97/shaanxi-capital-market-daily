#!/usr/bin/env python3
"""Build the production V2 customer site from V2-owned canonical data."""
from __future__ import annotations

import argparse
import html
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "v2"
AS_OF = ""
LISTED_SOURCE_DATE = ""
PRIVATE_SOURCE_DATE = ""
CHANNEL_IMAGE_SOURCES: dict[str, str] = {}
CONTACT = "华泰证券西安锦业路证券营业部（西北分公司机构业务中心）"
EMAIL = "wangyue021243@htsc.com"
BUILD_SCHEMA = "v2-production-2"
READINESS_SLOT = "morning"


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def dated_source(directory: Path, pattern: str, requested: str, *, exact: bool = False) -> tuple[Path, str]:
    candidates: list[tuple[str, Path]] = []
    for path in directory.glob(pattern):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
        if match and match.group(1) <= requested:
            candidates.append((match.group(1), path))
    if exact:
        hit = next(((day, path) for day, path in candidates if day == requested), None)
        if not hit:
            raise FileNotFoundError(f"缺少 {requested} 的正式上市公司 curated 数据，V2 按失败关闭处理")
        return hit[1], hit[0]
    if not candidates:
        raise FileNotFoundError(f"{directory} 中没有不晚于 {requested} 的可用数据")
    day, path = max(candidates, key=lambda item: item[0])
    return path, day


def prepare_channel_images() -> None:
    """Validate the V2-owned channel artwork without reading V1 runtime files."""
    global CHANNEL_IMAGE_SOURCES
    result: dict[str, str] = {}
    for channel in ("listed", "private", "ma", "tender"):
        target = OUT / "assets" / f"channel-{channel}.webp"
        if not target.is_file():
            raise FileNotFoundError(f"缺少V2频道图片：{target.relative_to(ROOT)}")
        result[target.name] = target.relative_to(ROOT).as_posix()
    soe_target = OUT / "assets" / "channel-soe.png"
    if not soe_target.is_file():
        raise FileNotFoundError(f"缺少V2频道图片：{soe_target.relative_to(ROOT)}")
    result[soe_target.name] = soe_target.relative_to(ROOT).as_posix()
    CHANNEL_IMAGE_SOURCES = result


def esc(value: object) -> str:
    return html.escape(str(value or "—"))


def iso_date(value: object) -> str:
    """Return a customer-safe ISO date without exposing a technical timestamp."""
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else ""


def tender_constraint_release_eligible(receipt: dict) -> bool:
    """Mirror the release gate's sole permitted source-constrained state."""
    eligibility = receipt.get("releaseEligibility") or {}
    return bool(
        receipt.get("status") == "degraded"
        and receipt.get("coverageComplete")
        and receipt.get("networkVerified")
        and eligibility.get("eligible") is True
        and eligibility.get("mode")
        == "official_equivalent_coverage_with_supplemental_source_constraint"
        and eligibility.get("constrainedSourceIds")
    )


def cninfo_url(adjunct_url: str) -> str:
    value = str(adjunct_url or "").lstrip("/")
    return f"https://static.cninfo.com.cn/{value}" if value else ""


def ma_stage_text(project: dict) -> str:
    """Use the strict customer stage vocabulary; legal effectiveness is not delivery."""
    stage = project.get("stage") or ""
    status = str(project.get("statusText") or "")
    first = str(project.get("firstDisclosureText") or "")
    next_action = str(project.get("nextAction") or "")
    combined = f"{status} {first}"
    if stage == "terminated":
        return "终止"
    if stage == "completed":
        if any(word in combined for word in ("过户完成", "交割完成", "工商变更", "收款完成")):
            return "已完成交割"
        if any(word in next_action for word in ("交割", "过户", "付款", "工商变更")):
            return "生效条件达成"
        return "已完成交割"
    if "生效条件达成" in combined:
        return "生效条件达成"
    if stage == "in_progress":
        return "交割中"
    if stage == "signed_or_approved":
        return "审议" if any(word in combined for word in ("预案", "待股东会", "董事会")) else "协议签署"
    return "筹划" if stage == "planning" else "审议"


def ma_stage_group(stage_text: str) -> str:
    return stage_text


def ma_subject(title: str) -> str:
    """Prefer the acquirer/main transaction party over the target description."""
    parts = re.split(r"拟收购|收购|筹划|转让|出售|完成|引入|控股|终止", title, maxsplit=1)
    return parts[0].strip() or title


def customer_ma_importance(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"[，；。]?下一节点为[^。；]*[。；]?", "", text)
    text = re.sub(r"[^。；]*样本[^。；]*[。；]?", "", text)
    return text.strip("，；。 ")


def ma_verified_source(project: dict) -> dict:
    source = next(
        (
            row for row in project.get("sourceRecords", [])
            if row.get("url")
            and row.get("sourceQuality") == "exchange_or_regulator_original"
            and not row.get("requiresExactDocument")
        ),
        {},
    )
    if not source:
        return {}
    return {
        "sourceName": source.get("sourceName") or "公告原文",
        "url": source["url"],
        "title": source.get("title") or project["title"],
        "publishedAt": iso_date(source.get("publishedAt")),
    }


def ma_planned_next(project: dict, confirmed_date: str) -> tuple[str, str]:
    candidates = []
    for milestone in project.get("milestones") or []:
        at = iso_date(milestone.get("at"))
        label = str(milestone.get("label") or "")
        if at and confirmed_date and at > confirmed_date and any(
            word in label for word in ("观察", "计划", "预计", "股东会", "付款", "交割")
        ):
            candidates.append((at, label))
    return min(candidates) if candidates else ("", "")


def listed_company(row: dict, group: str) -> str:
    if row.get("company"):
        return row["company"]
    title = str(row.get("title") or "")
    parts = title.split("｜")
    return parts[-1] if group == "opportunities" or (parts and parts[0] in {"必看", "重点"}) else parts[0]


def load_listed_announcements() -> list[dict]:
    rows: dict[str, dict] = {}
    source_dir = ROOT / "v2" / "data" / "daily" / "listed"
    paths = []
    for path in source_dir.glob("cninfo-announcements-*.json"):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
        if match and LISTED_SOURCE_DATE <= match.group(1) <= AS_OF:
            paths.append(path)
    if not paths:
        exact = source_dir / f"cninfo-announcements-{LISTED_SOURCE_DATE}.json"
        if exact.exists():
            paths = [exact]
    for path in sorted(paths):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for value in payload.values():
            if not isinstance(value, list):
                continue
            for row in value:
                adjunct = row.get("adjunctUrl") or ""
                if not adjunct:
                    continue
                item = {
                    "company": row.get("_matchedCompanyName") or row.get("secName") or "",
                    "announcementTitle": row.get("announcementTitle") or "",
                    "publishedAt": iso_date(adjunct),
                    "sourceName": "巨潮资讯",
                    "sourceUrl": cninfo_url(adjunct),
                }
                rows[item["sourceUrl"]] = item
    return list(rows.values())


LISTED_SOURCE_KEYWORDS = {
    "中国西电": ("中标",),
    "康惠股份": ("算力服务合同",),
    "爱科赛博": ("回购股份",),
    "源杰科技": ("半年度业绩预告",),
    "标准股份": ("异常波动",),
    "珠海中富": ("累计诉讼",),
    "西安旅游": ("借款", "临时股东会"),
    "泰金新能": ("权益分派",),
    "广电网络": ("高级管理人员离任",),
    "莱特光电": ("审核中心意见落实函回复",),
    "西部证券": ("票面利率",),
    "科隆新材": ("权益变动", "现金管理"),
    "北方长龙": ("工商变更登记",),
    "航天电子": ("归还用于暂时补充流动资金",),
    "三角防务": ("减持计划期限届满",),
}


def choose_listed_source(company: str, headline: str, text: str, announcements: list[dict]) -> dict:
    candidates = [row for row in announcements if row["company"] == company]
    if not candidates:
        return {}
    if len(candidates) == 1:
        best = candidates[0]
        return {
            **best,
            "sources": [{
                "sourceName": best["sourceName"],
                "sourceUrl": best["sourceUrl"],
                "announcementTitle": best["announcementTitle"],
            }],
            "sourceConfidence": "verified-single-company-announcement",
            "sourceKeyword": "唯一公司公告",
        }
    preferred = LISTED_SOURCE_KEYWORDS.get(company, ())
    scores = []
    row_text = re.sub(r"<[^>]+>", "", f"{headline} {text}")
    row_chars = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9%]", "", row_text)
    row_grams = {row_chars[index:index + 2] for index in range(max(0, len(row_chars) - 1))}
    for row in candidates:
        title = row["announcementTitle"]
        matched = [word for word in preferred if word in title and (word in text or len(preferred) == 1)]
        score = sum(100 if word in headline else 20 for word in matched)
        title_chars = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9%]", "", title.replace(company, ""))
        title_grams = {title_chars[index:index + 2] for index in range(max(0, len(title_chars) - 1))}
        overlap = len(row_grams & title_grams)
        score += overlap * 4
        scores.append((score, overlap, row["publishedAt"], matched, row))
    score, overlap, _, matched, best = max(scores, key=lambda item: (item[0], item[2]))
    if score < 8:
        return {}
    selected = [
        item[4]
        for item in scores
        if item[0] >= 8 and item[0] >= score * 0.55
    ]
    selected.sort(key=lambda item: (item["publishedAt"], item["sourceUrl"]), reverse=True)
    return {
        **best,
        "sources": [{
            "sourceName": source["sourceName"],
            "sourceUrl": source["sourceUrl"],
            "announcementTitle": source["announcementTitle"],
        } for source in selected],
        "sourceConfidence": "verified-company-and-topic",
        "sourceKeyword": matched[0] if matched else f"标题语义重合{overlap}",
    }


def attach_listed_sources(daily: dict) -> dict:
    announcements = load_listed_announcements()

    def curated_source(row: dict) -> dict:
        sources = [
            source
            for source in row.get("sources", [])
            if isinstance(source, dict) and source.get("sourceUrl")
        ]
        if not sources:
            return {}
        primary = sources[0]
        return {
            "sourceName": primary.get("sourceName") or "巨潮资讯",
            "sourceUrl": primary["sourceUrl"],
            "announcementTitle": primary.get("announcementTitle") or "",
            "publishedAt": row.get("publishedAt") or daily["date"],
            "sources": sources,
            "sourceConfidence": "verified-curated-matter-sources",
            "sourceKeyword": "V2精读事项来源组",
        }

    for group in ("opportunities", "risk_rows", "tiles", "capital_rows", "follow_items"):
        for row in daily.get(group, []):
            company = listed_company(row, group)
            source = curated_source(row) or choose_listed_source(
                company,
                str(row.get("title") or row.get("tag") or ""),
                " ".join(str(value) for value in row.values()),
                announcements,
            )
            row.update(source or {
                "publishedAt": daily["date"],
                "sourceName": "原始公告待核验",
                "sourceUrl": "",
                "announcementTitle": "",
                "sourceConfidence": "pending",
                "sourceKeyword": "",
            })
            if "sources" not in row:
                row["sources"] = ([{
                    "sourceName": row["sourceName"],
                    "sourceUrl": row["sourceUrl"],
                    "announcementTitle": row["announcementTitle"],
                }] if row.get("sourceUrl") else [])
    for column in daily.get("fixed_columns", []):
        for row in column.get("items", []):
            company = listed_company(row, "fixed_columns")
            source = curated_source(row) or choose_listed_source(
                company,
                str(row.get("title") or ""),
                " ".join(str(value) for value in row.values()),
                announcements,
            )
            row.update(source or {
                "publishedAt": daily["date"],
                "sourceName": "原始公告待核验",
                "sourceUrl": "",
                "announcementTitle": "",
                "sourceConfidence": "pending",
                "sourceKeyword": "",
            })
            if "sources" not in row:
                row["sources"] = ([{
                    "sourceName": row["sourceName"],
                    "sourceUrl": row["sourceUrl"],
                    "announcementTitle": row["announcementTitle"],
                }] if row.get("sourceUrl") else [])
    by_id = {
        re.search(r"/(\d+)\.PDF$", row["sourceUrl"]).group(1): row
        for row in announcements
        if re.search(r"/(\d+)\.PDF$", row["sourceUrl"])
    }

    def apply_exact(row: dict, ids: tuple[str, ...]) -> None:
        exact = [by_id[source_id] for source_id in ids]
        primary = exact[0]
        row.update({
            **primary,
            "sourceConfidence": "verified-exact-announcement",
            "sourceKeyword": "精确公告映射",
            "sources": [{
                "sourceName": source["sourceName"],
                "sourceUrl": source["sourceUrl"],
                "announcementTitle": source["announcementTitle"],
            } for source in exact],
        })

    # Prefer the stable announcement id carried by each curated row over
    # same-company semantic matching. This keeps a newly published announcement
    # from making an older, still-valid same-company row appear unmatched.
    exact_rows = [
        row
        for group in ("opportunities", "risk_rows", "tiles", "capital_rows", "follow_items")
        for row in daily.get(group, [])
    ] + [
        row
        for column in daily.get("fixed_columns", [])
        for row in column.get("items", [])
    ]
    for row in exact_rows:
        source_id = re.sub(r"-(?:fixed|follow)$", "", str(row.get("matter_id") or ""))
        if source_id in by_id:
            apply_exact(row, (source_id,))

    # Candidate-only exact mappings for rows that combine multiple same-company
    # announcements. These prevent a company-name fallback from appearing as a
    # fully verified topic match.
    exact_mappings = (
        ("capital_rows", "科隆新材", ("1225436726", "1225436773")),
        ("risk_rows", "西安旅游", ("1225435983", "1225435982")),
        ("fixed_columns", "西安旅游", ("1225435981",)),
    )
    for group, company, ids in exact_mappings:
        if not all(source_id in by_id for source_id in ids):
            continue
        pool = (
            [item for column in daily.get("fixed_columns", []) for item in column.get("items", [])]
            if group == "fixed_columns"
            else daily.get(group, [])
        )
        row = next(
            (
                item
                for item in pool
                if listed_company(item, group) == company
                or str(item.get("title") or "").startswith(company + "｜")
            ),
            None,
        )
        if row:
            apply_exact(row, ids)
    return daily


def listed_anchor(company: str) -> str:
    known = {
        "中国西电": "zhongguo-xidian",
        "康惠股份": "kanghui-gufen",
        "爱科赛博": "aikesaibo",
        "源杰科技": "yuanjie-keji",
        "泰金新能": "taijin-xinneng",
        "广电网络": "guangdian-wangluo",
        "莱特光电": "laite-guangdian",
        "科隆新材": "kelong-xincai",
        "三角防务": "sanjiao-fangwu",
    }
    return f"listed-detail-{known.get(company) or hashlib.sha1(company.encode('utf-8')).hexdigest()[:10]}"


def mark_listed_references(daily: dict) -> None:
    """Keep one full customer record for repeated events and link short references to it."""
    canonical_rows = [
        row
        for group in ("risk_rows", "tiles", "capital_rows")
        for row in daily.get(group, [])
        if not row.get("isReference")
    ] + [
        row
        for column in daily.get("fixed_columns", [])
        for row in column.get("items", [])
        if not row.get("isReference")
    ]
    canonical_by_matter = {
        str(row.get("matter_id") or ""): row
        for row in canonical_rows
        if row.get("matter_id")
    }
    for matter_id, row in canonical_by_matter.items():
        row["canonicalDetailId"] = (
            listed_anchor(str(row.get("company") or ""))
            + "-"
            + hashlib.sha1(matter_id.encode("utf-8")).hexdigest()[:8]
        )
    for group in ("opportunities", "follow_items"):
        for row in daily.get(group, []):
            referenced = canonical_by_matter.get(str(row.get("referenceMatterId") or row.get("matter_id") or ""))
            if referenced:
                row["isReference"] = True
                row["referenceAnchor"] = referenced["canonicalDetailId"]

    duplicate_groups = (
        ("中国西电", "capital_rows", ("opportunities", "tiles")),
        ("康惠股份", "risk_rows", ("opportunities",)),
        ("爱科赛博", "capital_rows", ("opportunities",)),
        ("源杰科技", "tiles", ("opportunities",)),
        ("泰金新能", "tiles", ("fixed_columns",)),
        ("广电网络", "tiles", ("fixed_columns",)),
    )

    def rows_for(group: str) -> list[dict]:
        if group == "fixed_columns":
            return [item for column in daily.get(group, []) for item in column.get("items", [])]
        return daily.get(group, [])

    for company, canonical_group, reference_groups in duplicate_groups:
        canonical = next(
            (row for row in rows_for(canonical_group) if listed_company(row, canonical_group) == company),
            None,
        )
        if not canonical:
            continue
        anchor = listed_anchor(company)
        canonical["canonicalDetailId"] = anchor
        for group in reference_groups:
            for row in rows_for(group):
                if listed_company(row, group) == company:
                    row["referenceAnchor"] = anchor
                    row["isReference"] = True
    # Compatibility overrides above may replace a canonical anchor after the
    # first reference pass.  Re-sync every layered 01/06 reference from the
    # canonical matter object so no link can retain a stale target.
    for group in ("opportunities", "follow_items"):
        for row in daily.get(group, []):
            referenced = canonical_by_matter.get(
                str(row.get("referenceMatterId") or row.get("matter_id") or "")
            )
            if referenced:
                row["referenceAnchor"] = referenced["canonicalDetailId"]
                row["isReference"] = True


def home_highlights(
    listed_daily: dict,
    products: list[dict],
    ma_projects: list[dict],
    *,
    ma_event_on_scan_date: bool,
) -> list[dict]:
    """Build the four fixed-category homepage cards from the current snapshot."""
    importance = {"必看": 0, "重点": 1}
    listed_candidates = sorted(
        listed_daily.get("opportunities", []),
        key=lambda row: (
            -(int((row.get("publishedAt") or "0000-00-00").replace("-", ""))),
            importance.get(str(row.get("title") or "").split("｜")[0], 9),
        ),
    )
    selected, seen = [], set()
    for row in listed_candidates:
        company = listed_company(row, "opportunities")
        if company in seen:
            continue
        seen.add(company)
        selected.append(row)
        if len(selected) == 2:
            break
    listed_cards = [
        {
            "category": "上市公司",
            "mode": "latest-specific",
            "title": row["title"],
            "body": row["body"],
            "date": row["publishedAt"],
            "href": f"listed.html#{row.get('referenceAnchor') or row.get('canonicalDetailId') or listed_anchor(listed_company(row, 'opportunities'))}",
            "company": listed_company(row, "opportunities"),
            "sortBasis": "公告日期倒序，同日按重要度排序",
        }
        for row in selected
    ]
    if len(listed_cards) != 2:
        raise ValueError("homepage requires two listed-company opportunity cards")

    today_products = [row for row in products if row["filingDate"] == AS_OF]
    latest_product = (today_products or products)[0]
    if today_products:
        private_card = {
            "category": "证券私募",
            "mode": "today-specific",
            "title": f"今日新备案｜{latest_product['fundName']}",
            "body": f"管理人：{latest_product['managerName']}。",
            "date": latest_product["filingDate"],
            "href": f"private.html#fund-{latest_product['fundNo']}",
        }
    else:
        private_card = {
            "category": "证券私募",
            "mode": "annual-with-latest",
            "title": f"全年备案 {len(products)} 只",
            "body": f"最近一只：{latest_product['fundName']}；管理人：{latest_product['managerName']}。",
            "date": latest_product["filingDate"],
            "href": f"private.html#fund-{latest_product['fundNo']}",
        }

    verified_ma = [row for row in ma_projects if row["sourceVerified"]]
    # The homepage may call an M&A item “today's progress” only when the
    # dedicated same-slot scanner both found it and wrote it into the verified
    # event store.  A historical record whose date happens to equal ``AS_OF``
    # must not override a truthful ``no_new`` scan state.
    today_ma = (
        [row for row in verified_ma if row["eventDate"] == AS_OF]
        if ma_event_on_scan_date
        else []
    )
    latest_ma = (today_ma or verified_ma)[0]
    if today_ma:
        ma_card = {
            "category": "收并购",
            "mode": "today-specific",
            "title": f"今日新进展｜{latest_ma['title']}",
            "body": f"{latest_ma['stageText']}。{latest_ma['progress']}",
            "date": latest_ma["eventDate"],
            "href": f"ma.html#{latest_ma['id']}",
        }
    else:
        ma_card = {
            "category": "收并购",
            "mode": "annual-with-latest",
            "title": f"全年收并购项目 {len(ma_projects)} 个",
            "body": f"最近已核验项目：{latest_ma['title']}；{latest_ma['stageText']}。",
            "date": latest_ma["eventDate"],
            "href": f"ma.html#{latest_ma['id']}",
        }
    return [*listed_cards, private_card, ma_card]


def classify_listed_business(text: str, taxonomy: dict) -> dict:
    ordered = [
        {**tag, "rmCategory": category["name"], "targetObjects": category["targetObjects"]}
        for category in taxonomy["categories"]
        for tag in category["tags"]
    ]
    if "回购" in text and "注销" not in text:
        return next(item for item in ordered if item["name"] == "股份回购")
    if "回购注销" in text:
        return next(item for item in ordered if item["name"] == "回购注销")
    found = next((item for item in ordered if any(keyword in text for keyword in item["keywords"])), None)
    if found:
        return found
    fallbacks = (
        (("中标", "合同"), "重大合同"),
        (("业绩预告", "营业收入", "净利润"), "业绩预告"),
        (("权益分派", "现金红利"), "分红"),
        (("股东会", "董事会"), "章程治理"),
    )
    for needles, tag_name in fallbacks:
        if any(needle in text for needle in needles):
            return next(item for item in ordered if item["name"] == tag_name)
    return {
        "name": "综合事项",
        "rmCategory": "综合事项",
        "businessPriority": "standard",
        "targetObjects": ["董秘办"],
        "keywords": [],
    }


def annotate_listed_daily(daily: dict, taxonomy: dict) -> dict:
    groups = (
        ("opportunities", lambda row: f"{row.get('title', '')} {row.get('body', '')}", lambda row: row.get("title", "").split("｜")[0]),
        ("risk_rows", lambda row: f"{row.get('company', '')} {row.get('event', '')} {row.get('tag', '')}", lambda row: "内容重要"),
        ("tiles", lambda row: f"{row.get('title', '')} {row.get('body', '')}", lambda row: "内容重要"),
        ("capital_rows", lambda row: f"{row.get('company', '')} {row.get('numbersHtml', '')} {row.get('attention', '')}", lambda row: "内容重要"),
        ("follow_items", lambda row: f"{row.get('title', '')} {row.get('body', '')}", lambda row: "重点跟踪"),
    )
    for key, text_fn, importance_fn in groups:
        for row in daily.get(key, []):
            classified = classify_listed_business(re.sub(r"<[^>]+>", "", text_fn(row)), taxonomy)
            row["business"] = {
                "category": classified["rmCategory"],
                "subcategory": classified["name"],
                "priority": classified["businessPriority"],
                "targets": classified["targetObjects"],
                "contentImportance": importance_fn(row),
            }
    for group in daily.get("fixed_columns", []):
        for row in group.get("items", []):
            classified = classify_listed_business(f"{row.get('title', '')} {row.get('body', '')}", taxonomy)
            row["business"] = {
                "category": classified["rmCategory"],
                "subcategory": classified["name"],
                "priority": classified["businessPriority"],
                "targets": classified["targetObjects"],
                "contentImportance": "固定披露",
            }
    for row in daily.get("follow_items", []):
        row["title"] = re.sub(r"｜看", "｜关注", row.get("title") or "")
        row["body"] = re.sub(r"^看", "关注", row.get("body") or "")
    return daily


def add_listed_canonical_details(daily: dict) -> list[dict]:
    """Attach stable anchors to one canonical detail row per current focus company."""
    row_groups = [
        ("section-04", daily.get("capital_rows", [])),
        ("section-05", [item for group in daily.get("fixed_columns", []) for item in group.get("items", [])]),
        ("section-02", daily.get("risk_rows", [])),
        ("section-03", daily.get("tiles", [])),
        ("section-01", daily.get("opportunities", [])),
    ]
    follow_rows = daily.get("follow_items", [])
    result = []
    seen: set[str] = set()
    for follow in follow_rows:
        company = listed_company(follow, "follow_items")
        if not company or company in seen:
            continue
        seen.add(company)
        detail = None
        section_id = ""
        for candidate_section, candidates in row_groups:
            detail = next(
                (
                    row
                    for row in candidates
                    if listed_company(
                        row,
                        "opportunities" if candidate_section == "section-01"
                        else "fixed_columns" if candidate_section == "section-05"
                        else "",
                    ) == company
                    or row.get("company") == company
                    or str(row.get("title") or "").startswith(company + "｜")
                ),
                None,
            )
            if detail:
                section_id = candidate_section
                break
        if not detail:
            continue
        anchor_id = detail.get("canonicalDetailId") or listed_anchor(company)
        detail["canonicalDetailId"] = anchor_id
        result.append(
            {
                "company": company,
                "anchorId": anchor_id,
                "sourceSection": section_id,
                "business": detail.get("business") or {},
                "followText": follow.get("body") or "",
            }
        )
        if len(result) == 4:
            break
    if not result:
        raise ValueError("当前上市日报没有可跳转的重点公司")
    daily["focusCompanies"] = result
    return result


def private_candidate_overlay() -> tuple[list[dict], list[dict], list[dict]]:
    """Candidate-only evidence overlay; the formal V2 private universe is not mutated."""
    pf1 = (
        ("candidate-pf1-hanzhong-linyuan", "汉中林园投资基金管理合伙企业（有限合伙）", "P1069402", "重庆市"),
        ("candidate-pf1-xian-baishi", "西安柏石私募基金管理有限公司", "P1069047", "浙江省"),
        ("candidate-pf1-xian-aerfa", "西安阿而法私募基金管理合伙企业（有限合伙）", "P1063733", "广东省"),
        ("candidate-pf1-xian-litian", "西安力天私募基金管理有限公司", "P1064879", "上海市"),
        ("candidate-pf1-xian-jiushang", "西安久上基金管理有限公司", "P1065633", "四川省"),
        ("candidate-pf1-xian-guozi", "西安国子资本管理有限公司", "P1065741", "广东省"),
    )
    included = [
        {
            "id": manager_id,
            "name": name,
            "registerNo": register_no,
            "registerProvince": "陕西省",
            "officeProvince": office_province,
            "officeAddress": "",
            "tier": "PF1",
            "relationType": "shaanxi_registered",
            "relationStrength": "direct",
            "relationGroup": "direct_local",
            "relation": "工商主体注册在陕西",
            "relationLabel": "陕西注册",
            "status": "公开证据确认纳入",
            "filingCount": 0,
            "latestFiling": "",
            "detailUrl": "",
            "evidence": [
                {
                    "type": "陕西辖区名录",
                    "fact": "陕西证监局截至2025-07-31辖区私募基金管理人名录确认；AMAC登记号与异地办公省按候选核验口径记录",
                    "url": "https://www.csrc.gov.cn/shaanxi/c104633/c7575055/content.shtml",
                }
            ],
        }
        for manager_id, name, register_no, office_province in pf1
    ]
    included.extend(
        [
        {
            "id": "candidate-pf2-shanghai-zhuozhu",
            "name": "上海卓铸私募基金管理有限公司",
            "registerNo": "P1027840",
            "registerProvince": "上海市",
            "officeProvince": "上海市",
            "officeAddress": "",
            "tier": "PF2",
            "relation": "上海注册及AMAC办公地在上海；公司官网持续公开西安办公室，且西安分公司真实存续，按陕西实质经营分支强关联纳入",
            "relationLabel": "上海注册 / 上海AMAC办公 / 西安持续办公+存续分公司 / PF2强关联",
            "relationType": "xian_active_branch",
            "relationStrength": "substantive",
            "relationGroup": "substantive_operation_or_equity",
            "status": "公开证据确认纳入",
            "filingCount": 0,
            "latestFiling": "",
            "detailUrl": "",
            "evidence": [
                {
                    "type": "公司官网持续办公信息",
                    "publishedAt": "2023-05-19",
                    "registerNo": "P1027840",
                    "xianOfficeAddress": "陕西省西安市高新区锦业路12号迈科中心1203室",
                    "companyStatement": "以西安为中心，由上海辐射全国",
                    "url": "https://www.zhuozhuinvest.com/website/w/h",
                    "factBoundary": "公司官网证明西安持续办公信息，不代表AMAC公示办公地已变更至陕西",
                },
                {
                    "type": "工商分公司",
                    "entity": "上海卓铸私募基金管理有限公司西安分公司",
                    "establishedAt": "2024-07-12",
                    "address": "陕西省西安市未央区大明宫商业街3楼5号",
                    "unifiedSocialCreditCode": "91610112MADQBNQU84",
                    "factBoundary": "该证据证明西安实质分支，不代表AMAC办公地已变更至陕西",
                }
            ],
        },
        {
            "id": "candidate-pf2-tianyou",
            "name": "添佑私募基金管理（上海）有限公司",
            "registerNo": "P1018901",
            "registerProvince": "上海市",
            "officeProvince": "云南省",
            "officeAddress": "昆明市（AMAC办公地）",
            "tier": "PF2",
            "relation": "上海注册/昆明办公；当前陕西产业股东合计40%，且历史控股陕西平台",
            "relationLabel": "上海注册 / 昆明办公 / 陕西股权关系 / PF2强关联",
            "relationType": "current_shaanxi_shareholders_and_historical_shaanxi_platform",
            "relationStrength": "substantive",
            "relationGroup": "substantive_operation_or_equity",
            "status": "公开证据确认纳入",
            "filingCount": 0,
            "latestFiling": "",
            "detailUrl": "",
            "evidence": [
                {
                    "type": "主体身份",
                    "unifiedSocialCreditCode": "91310000342390344H",
                    "amacOrgNoLegacy": "34239034-4",
                    "registerNo": "P1018901",
                },
                {
                    "type": "当前股权",
                    "effectiveAt": "2026-07-08",
                    "fact": "陈磊40%、柏晋20%、吴静20%、陈成学20%；柏晋与陈成学合计40%构成当前陕西产业股东关系",
                    "shaanxiShareholders": [
                        {"name": "柏晋", "share": "20%", "relationship": "长期持股/担任西安恒信集团有限责任公司法人及多家陕西企业职务"},
                        {"name": "陈成学", "share": "20%", "relationship": "持有/任职陕西恒优佳程并任西安牟牟农业科技法人"},
                    ],
                },
                {
                    "type": "历史陕西控股主体",
                    "entity": "陕西陕易购供应链管理有限公司",
                    "unifiedSocialCreditCode": "91610581MA6YDM4PXE",
                    "registeredPlace": "陕西韩城",
                    "historicalShare": "60%",
                    "currentStatus": "已注销",
                },
            ],
        },
        {
            "id": "candidate-pf2-longquan-yunfeng",
            "name": "龙泉云锋私募基金管理有限公司",
            "registerNo": "P1073744",
            "registerProvince": "浙江省",
            "officeProvince": "河南省",
            "officeAddress": "郑州市（AMAC办公地）",
            "tier": "PF2",
            "relation": "陕西省证券投资基金业协会正式会员；未发现陕西注册、办公或分公司",
            "relationLabel": "协会会员观察（非陕西注册/办公）",
            "relationType": "shaanxi_industry_association_member",
            "relationStrength": "institutional",
            "relationGroup": "association_member",
            "status": "公开证据确认纳入",
            "filingCount": 0,
            "latestFiling": "",
            "detailUrl": "",
            "evidence": [
                {
                    "type": "协会会员",
                    "fact": "2025-08-29成为陕西省证券投资基金业协会第18批正式会员",
                    "url": "https://www.amas.org.cn/show/1280.html",
                },
                {
                    "type": "高管履历",
                    "fact": "法人/总经理刘斌2013—2016年任西安领汇优选投资管理有限公司投资经理；仅履历不足以纳入PF2",
                },
            ],
        },
        {
            "id": "candidate-pf2-suzhou-shuirunshanhe",
            "name": "苏州水润山禾私募基金管理有限公司",
            "registerNo": "P1064295",
            "registerProvince": "江苏省",
            "officeProvince": "重庆市",
            "officeAddress": "重庆市（AMAC办公地）",
            "tier": "PF2",
            "relation": "同一统一社会信用代码主体以曾用名加入陕西省证券投资基金业协会；未发现陕西注册、办公或分公司",
            "relationLabel": "协会会员观察（非陕西注册/办公）",
            "relationType": "shaanxi_industry_association_member",
            "relationStrength": "institutional",
            "relationGroup": "association_member",
            "status": "公开证据确认纳入",
            "filingCount": 0,
            "latestFiling": "",
            "detailUrl": "",
            "evidence": [
                {
                    "type": "协会会员",
                    "fact": "曾用名深圳前海云水梅花资本管理有限公司于2023-08-23成为陕西省证券投资基金业协会第12批正式会员",
                    "url": "https://www.amas.org.cn/show/674.html",
                },
                {
                    "type": "同一主体延续",
                    "unifiedSocialCreditCode": "91440300335117358H",
                    "fact": "更名前后统一社会信用代码未变",
                }
            ],
        },
        ]
    )
    return included, [], []


def custodian_label(name: str) -> str:
    labels = {
        "招商证券股份有限公司": "招商证券",
        "中信证券股份有限公司": "中信证券",
        "华泰证券股份有限公司": "华泰证券",
        "中信建投证券股份有限公司": "中信建投",
        "光大证券股份有限公司": "光大证券",
        "国泰海通证券股份有限公司": "国泰海通",
        "兴业证券股份有限公司": "兴业证券",
        "中国银河证券股份有限公司": "中国银河",
        "华福证券股份有限公司": "华福证券",
        "国信证券股份有限公司": "国信证券",
        "国元证券股份有限公司": "国元证券",
        "广发证券股份有限公司": "广发证券",
        "浙商证券股份有限公司": "浙商证券",
        "财通证券股份有限公司": "财通证券",
        "中国国际金融股份有限公司": "中金公司",
    }
    return labels.get(name, name)


def find_object(value: object, key: str, expected: str) -> dict | None:
    if isinstance(value, dict):
        if value.get(key) == expected:
            return value
        for child in value.values():
            found = find_object(child, key, expected)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_object(child, key, expected)
            if found:
                return found
    return None


TENDER_SHORT_TITLES = {
    "SX-STB-2026-001": "标准化债券第三方服务机构项目",
    "SX-STB-2026-002": "科创债主承销商项目",
    "SX-STB-2026-003": "2026年海外债券承销商采购",
    "SX-STB-2026-004": "中期票据发行承销商遴选",
    "SX-STB-2026-005": "2026年公司债券主承销商选聘",
}


def tender_latest_date(row: dict) -> str:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("stage", "deadlineOrOpening", "winnerStatus", "publishDate")
    )
    dates = re.findall(r"2026-\d{2}-\d{2}", text)
    return max(dates) if dates else row["publishDate"]


def tender_status_group(row: dict) -> str:
    text = f"{row.get('stage', '')} {row.get('winnerStatus', '')}"
    if any(word in text for word in ("中标", "结果", "候选")):
        return "已出结果"
    if row.get("deadlineOrOpening") and iso_date(row["deadlineOrOpening"]) >= AS_OF:
        return "今日可参与机会"
    return "正在推进"


def private_contract_managers(private_daily: dict, private_rules: dict) -> list[dict]:
    """Build the current formal pool from V2's live AMAC result plus reviewed targets."""
    rows = []
    for item in private_daily.get("raw", {}).get("shaanxiOfficeManagers", []):
        rows.append({
            **item,
            "managerId": str(item.get("id") or item.get("registerNo") or ""),
            "universeTier": "PF1",
            "relationType": "registered_or_office_in_shaanxi",
            "relationStrength": "direct",
            "relationGroup": "direct_local",
            "inclusionReason": "AMAC当前公示的注册地或办公地在陕西省",
            "relationEvidence": [],
            "detailUrl": (
                f"https://gs.amac.org.cn/amac-infodisc/res/pof/manager/{item.get('url')}"
                if item.get("url") else ""
            ),
        })
    for target in [
        *private_rules.get("manualTerritorialTargets", []),
        *private_rules.get("relatedTargets", []),
    ]:
        rows.append({
            "managerId": str(target["managerId"]),
            "managerName": target["managerName"],
            "registerNo": target["registerNo"],
            "registerProvince": target.get("currentRegisterProvince") or "",
            "officeProvince": target.get("currentOfficeProvince") or "",
            "universeTier": target["universeTier"],
            "relationType": target["relationType"],
            "relationStrength": target["relationStrength"],
            "relationGroup": target.get("relationGroup") or (
                "direct_local" if target["universeTier"] == "PF1" else "other"
            ),
            "inclusionReason": target["inclusionReason"],
            "relationEvidence": target.get("evidence", []),
            "detailUrl": target.get("managerDetailUrl") or "",
        })
    by_register_no = {}
    for row in rows:
        key = row.get("registerNo") or row.get("managerName")
        by_register_no.setdefault(key, row)
    return list(by_register_no.values())


def private_relation_label(row: dict) -> str:
    register_short = str(row.get("registerProvince") or "").removesuffix("省").removesuffix("市")
    office_short = str(row.get("officeProvince") or "").removesuffix("省").removesuffix("市")
    if row["universeTier"] == "PF1":
        if row.get("registerProvince") == "陕西省" and row.get("officeProvince") != "陕西省":
            return f"陕西注册 / {office_short}办公"
        if row.get("registerProvince") != "陕西省" and row.get("officeProvince") == "陕西省":
            return f"{register_short}注册 / 陕西办公"
        return "陕西注册 / 陕西办公"
    relation_type = str(row.get("relationType") or "")
    if "抱朴容易" in row["managerName"]:
        return "广东注册 / 西安办公分部 / PF2强关联"
    if relation_type == "xian_active_branch":
        return f"{register_short}注册 / {office_short}AMAC办公 / 西安持续办公+存续分公司 / PF2强关联"
    if relation_type == "current_shaanxi_shareholders_and_historical_shaanxi_platform":
        return f"{register_short}注册 / {office_short}办公 / 陕西股权关系 / PF2强关联"
    if row.get("relationGroup") == "association_member":
        return "协会会员观察（非陕西注册/办公）"
    return f"{register_short}注册 / 陕西重要关联"


def private_product_overlay(private_daily: dict, manager_tiers: dict[str, str], source_path: Path) -> list[dict]:
    """Union all V2 YTD observations so later API result drift cannot erase filings."""
    raw_dir = source_path.parent
    by_fund_no = {}
    source_by_fund_no = {}
    for path in sorted(raw_dir.glob("security-private-fund-daily-*.json")):
        match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
        if not match or match.group(1) > AS_OF:
            continue
        snapshot = private_daily if path == source_path else json.loads(path.read_text(encoding="utf-8"))
        source_rows = list(snapshot.get("shaanxiOfficeProducts", []))
        source_rows.extend(
            row
            for row in snapshot.get("raw", {}).get("allSecurityProductsInShaanxiWindow", [])
            if row.get("managerName") in manager_tiers
        )
        for row in source_rows:
            fund_no = str(row.get("fundNo") or "")
            if not fund_no or not row.get("putOnRecordDate"):
                continue
            by_fund_no.setdefault(fund_no, row)
            source_by_fund_no.setdefault(fund_no, path)
    products = []
    for fund_no, row in by_fund_no.items():
        filing_date = datetime.utcfromtimestamp(row["putOnRecordDate"] / 1000).date().isoformat()
        establish_date = (
            datetime.utcfromtimestamp(row["establishDate"] / 1000).date().isoformat()
            if row.get("establishDate") else ""
        )
        products.append(
            {
                "fundNo": fund_no,
                "fundName": row["fundName"],
                "managerName": row["managerName"],
                "custodian": row.get("mandatorName") or "",
                "filingDate": filing_date,
                "establishDate": establish_date,
                "universeTier": manager_tiers.get(row["managerName"], "PF1"),
                "sourceUrl": f"https://gs.amac.org.cn/amac-infodisc/res/pof/fund/{row['id']}.html",
                "sourceQuality": "amac-official-current-pool",
                "sourcePath": source_by_fund_no[fund_no].relative_to(ROOT).as_posix(),
            }
        )
    return products


def normalize() -> dict:
    source_contract = load("v2/config/source-contract.json")
    listed_universe = load(source_contract["listedUniverse"])
    listed_taxonomy = load(source_contract["listedTaxonomy"])
    listed_path = (
        ROOT / source_contract["listedDailyDirectory"]
        / f"listed-official-{LISTED_SOURCE_DATE}.json"
    )
    listed_daily = json.loads(listed_path.read_text(encoding="utf-8"))
    if listed_daily.get("date") != LISTED_SOURCE_DATE:
        raise ValueError("上市公司源文件名与数据日期不一致")
    # V2 correction: PDF extraction contains an unverified "AAsti"
    # token. Preserve the confirmed bond rating AA and omit the malformed issuer
    # rating until a clean source field is available.
    for row in listed_daily.get("capital_rows", []):
        if row.get("company") == "莱特光电":
            row["numbersHtml"] = re.sub(
                r"主体信用等级<b>AAsti</b>、",
                "",
                row.get("numbersHtml") or "",
            )
    listed_daily = annotate_listed_daily(listed_daily, listed_taxonomy)
    listed_daily = attach_listed_sources(listed_daily)
    mark_listed_references(listed_daily)
    listed_focus_companies = add_listed_canonical_details(listed_daily)
    private_backfill = load(source_contract["privateAnnual"])
    private_rules = load(source_contract["privateUniverse"])
    private_daily_path = (
        ROOT / source_contract["privateDailyDirectory"]
        / f"security-private-fund-daily-{PRIVATE_SOURCE_DATE}.json"
    )
    private_daily = json.loads(private_daily_path.read_text(encoding="utf-8"))
    private_snapshot = {
        "topManagers": private_daily.get("raw", {}).get("shaanxiOfficeManagers", [])
    }
    ma_source = load(source_contract["maEvents"])
    ma_scan_path = (
        ROOT
        / source_contract["maScanDirectory"]
        / f"scan-{AS_OF}-{READINESS_SLOT}.json"
    )
    tender_scan_path = (
        ROOT
        / source_contract["tenderScanDirectory"]
        / f"scan-{AS_OF}-{READINESS_SLOT}.json"
    )
    for channel, scan_path, event_path in (
        ("MA", ma_scan_path, ROOT / source_contract["maEvents"]),
        ("tender", tender_scan_path, ROOT / source_contract["tenderEvents"]),
    ):
        if not scan_path.is_file():
            raise FileNotFoundError(f"缺少V2 {channel}专用扫描回执：{scan_path.relative_to(ROOT)}")
        receipt = json.loads(scan_path.read_text(encoding="utf-8"))
        status_ok = (
            receipt.get("status") == "completed"
            if channel == "MA"
            else receipt.get("status") == "completed"
            or tender_constraint_release_eligible(receipt)
        )
        if (
            receipt.get("scanAsOf") != AS_OF
            or receipt.get("slot") != READINESS_SLOT
            or not status_ok
            or not receipt.get("coverageComplete")
            or not receipt.get("networkVerified")
            or receipt.get("eventStoreSha256")
            != hashlib.sha256(event_path.read_bytes()).hexdigest()
        ):
            raise ValueError(f"V2 {channel}专用扫描回执日期、覆盖或事件库哈希不合格")
    # Keep the dedicated receipt available to the homepage renderer.  The
    # renderer must use the scan outcome, rather than a historical event date,
    # when deciding whether an M&A card can say "今日新进展".
    ma_scan = json.loads(ma_scan_path.read_text(encoding="utf-8"))
    soe_source = load(source_contract["soeEvents"])
    soe_scan_path = (
        ROOT
        / source_contract["soeScanDirectory"]
        / f"scan-{AS_OF}-{READINESS_SLOT}.json"
    )
    if not soe_scan_path.is_file():
        raise FileNotFoundError(
            f"缺少V2 SOE专用扫描回执：{soe_scan_path.relative_to(ROOT)}"
        )
    soe_scan = json.loads(soe_scan_path.read_text(encoding="utf-8"))
    if (
        soe_scan.get("scanAsOf") != AS_OF
        or soe_scan.get("slot") != READINESS_SLOT
        or soe_scan.get("status") != "completed"
    ):
        raise ValueError("V2 SOE专用扫描回执日期、时点或状态不匹配")
    tender_catalog = load(source_contract["tenderEvents"])
    history = {"listedArchive": []}
    readiness_path = (
        ROOT / source_contract["readinessDirectory"]
        / f"v2-ready-{AS_OF}-{READINESS_SLOT}.json"
    )
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    if (
        readiness.get("status") != "ready"
        or readiness.get("date") != AS_OF
    ):
        raise ValueError(f"V2栏目就绪清单未通过：{readiness_path.relative_to(ROOT)}")

    listed_entities = []
    for row in listed_universe["entities"]:
        listed_entities.append(
            {
                "id": row["entityId"],
                "name": row["canonicalName"],
                "code": row["securityCode"],
                "exchange": {"SZ": "深交所", "SH": "上交所", "BJ": "北交所", "HK": "港交所"}.get(row.get("market"), row.get("market") or "—"),
                "tier": row["universeTier"],
                "relation": row["inclusionReason"],
                "industry": row.get("industry") or "",
                "reason": row["inclusionReason"],
                "sourceAsOf": row.get("sourceAsOf") or listed_universe["asOf"],
            }
        )

    manager_universe = private_contract_managers(private_daily, private_rules)
    manager_tiers = {row["managerName"]: row["universeTier"] for row in manager_universe}
    products = list(private_backfill["products"])
    annual_fund_nos = {row["fundNo"] for row in products}
    for product in private_product_overlay(private_daily, manager_tiers, private_daily_path):
        if product["fundNo"] not in annual_fund_nos:
            products.append(product)
            annual_fund_nos.add(product["fundNo"])
    products.sort(key=lambda x: (x["filingDate"], x["fundNo"]), reverse=True)
    product_by_manager: dict[str, list[dict]] = {}
    for row in products:
        product_by_manager.setdefault(row["managerName"], []).append(row)
    top_by_id = {
        str(x.get("managerId") or x.get("id") or ""): x
        for x in private_snapshot.get("topManagers", [])
    }
    top_by_register_no = {x.get("registerNo"): x for x in private_snapshot.get("topManagers", [])}
    private_managers = []
    for row in manager_universe:
        detail = top_by_id.get(str(row["managerId"]), {}) or top_by_register_no.get(row.get("registerNo"), {})
        filings = product_by_manager.get(row["managerName"], [])
        private_managers.append(
            {
                "id": row["managerId"],
                "name": row["managerName"],
                "registerNo": row.get("registerNo") or "",
                "registerProvince": row.get("registerProvince") or "",
                "officeProvince": row.get("officeProvince") or "",
                "officeAddress": detail.get("officeAddress") or "",
                "tier": row["universeTier"],
                "relationType": row.get("relationType") or "",
                "relationStrength": row.get("relationStrength") or "",
                "relationGroup": row.get("relationGroup") or "",
                "relation": row["inclusionReason"],
                "relationLabel": private_relation_label(row),
                "status": "协会当前公示在册",
                "filingCount": len(filings),
                "latestFiling": filings[0]["filingDate"] if filings else "",
                "detailUrl": row.get("detailUrl") or "",
                "evidence": row.get("relationEvidence", []),
            }
        )
    pending_evidence = []
    excluded_evidence = []
    private_managers.sort(key=lambda row: (row["tier"], row["name"]))
    for manager in private_managers:
        filings = product_by_manager.get(manager["name"], [])
        manager["filingCount"] = len(filings)
        manager["latestFiling"] = filings[0]["filingDate"] if filings else ""
    manager_counts = Counter(row["tier"] for row in private_managers)
    pf2_relation_counts = Counter(
        row.get("relationGroup") or "other" for row in private_managers if row["tier"] == "PF2"
    )
    manager_relation_by_name = {x["name"]: x["relationLabel"] for x in private_managers}
    for product in products:
        product["relationLabel"] = manager_relation_by_name.get(product["managerName"], "")
        product["custodianLabel"] = custodian_label(product.get("custodian") or "")

    ma_projects = []
    for row in ma_source["projects"]:
        source = ma_verified_source(row)
        confirmed_date = iso_date(source.get("publishedAt"))
        planned_date, planned_label = ma_planned_next(row, confirmed_date)
        stage_text = ma_stage_text(row)
        ma_projects.append(
            {
                "id": row["maProjectId"],
                "title": row["title"],
                "subject": ma_subject(row["title"]),
                "dimension": row.get("dimension") or "",
                "entityType": row.get("entityType") or "",
                "eventDate": confirmed_date,
                "updatedAt": confirmed_date,
                "reportedDate": max(re.findall(r"2026-\d{2}-\d{2}", str(row.get("firstDisclosureText") or "")), default=""),
                "plannedNextDate": planned_date,
                "plannedNextLabel": planned_label,
                "stage": row["stage"],
                "stageText": stage_text,
                "stageGroup": ma_stage_group(stage_text),
                "amount": row.get("amountText") or "未披露",
                "industry": row.get("industry") or "",
                "matter": row.get("direction") or row["title"],
                "fact": row.get("direction") or row["title"],
                "importance": customer_ma_importance(row.get("significance")),
                "progress": customer_ma_importance(row.get("significance")),
                "nextStep": row.get("nextAction") or "",
                "sourceName": source.get("sourceName") or "待补原始来源",
                "sourceUrl": source.get("url") or "",
                "sourceTitle": source.get("title") or "",
                "sourceVerified": bool(source.get("url") and confirmed_date),
                "sourceStatus": "verified" if source.get("url") and confirmed_date else "pending",
                "sourceReviewStatus": row.get("sourceReviewStatus") or "pending_primary_source",
            }
        )
    ma_projects.sort(key=lambda x: (x["sourceVerified"], x["eventDate"] or x["reportedDate"], x["title"]), reverse=True)

    target_year = int(AS_OF[:4])
    target_month = int(AS_OF[5:7])
    private_annual_months = {
        f"{target_year}-{month:02d}": sum(
            x["filingDate"].startswith(f"{target_year}-{month:02d}") for x in products
        )
        for month in range(1, target_month + 1)
    }
    custodian_counts = Counter(x["custodian"] for x in products)
    custodian_stats = [
        {"name": name, "label": custodian_label(name), "count": count}
        for name, count in sorted(custodian_counts.items(), key=lambda item: (-item[1], custodian_label(item[0])))
    ]
    listed_archive = list(history.get("listedArchive", []))

    tender_projects = [
        {
            "id": row["id"],
            "title": TENDER_SHORT_TITLES[row["id"]],
            "formalTitle": row["projectName"],
            "purchaser": row["buyer"],
            "publishDate": row["publishDate"],
            "latestProgressDate": tender_latest_date(row),
            "opportunityType": row["opportunityType"],
            "stage": row["stage"],
            "statusGroup": tender_status_group(row),
            "deadlineOrOpening": row.get("deadlineOrOpening") or "",
            "winnerStatus": row["winnerStatus"],
            "projectScale": row.get("projectScale") or "未披露",
            "winningOrCandidateUnits": row.get("winningOrCandidateUnits") or [],
            "sourceName": (row.get("sources") or [{}])[0].get("name") or "公开来源",
            "sourceUrl": (row.get("sources") or [{}])[0].get("url") or "",
        }
        for row in tender_catalog["opportunities"]
    ]
    tender_projects.sort(key=lambda row: (row["latestProgressDate"], row["id"]), reverse=True)
    if len(tender_projects) != tender_catalog["summary"]["confirmedPublishedIn2026"]:
        raise ValueError("tender project catalog count does not match its confirmed-project summary")
    tender_pending = [{
        "id": "SX-STB-PENDING-2026-001",
        "title": "陕西金资公司债主承销商及联席主承销商项目",
        "formalTitle": "陕西金资2026年面向专业投资者公开发行公司债券选定主承销商和联席主承销商项目",
        "purchaser": "陕西金融资产管理股份有限公司",
        "latestProgressDate": "2026-07-02",
        "opportunityType": "公司债券主承销商、联席主承销商",
        "statusGroup": "待回源线索",
        "stage": "中标结果公示线索",
        "projectScale": "待官方正文核验",
        "winningOrCandidateUnits": [],
        "winnerStatus": "完整中标人、承销费率、服务期和招标编号待官方正文回源核验",
        "sourceName": "待回源观察",
        "sourceUrl": "",
    }]

    soe_records = [
        row
        for row in soe_source["records"]
        if iso_date(row.get("publishedAt")) and iso_date(row.get("publishedAt")) <= AS_OF
    ]
    if not soe_records:
        raise ValueError("V2 SOE事件库在页面日期前没有可用记录")
    soe_records.sort(
        key=lambda row: (iso_date(row.get("publishedAt")), row.get("candidateId", "")),
        reverse=True,
    )
    soe_latest_date = iso_date(soe_records[0]["publishedAt"])
    soe_focus_records = soe_records[:5]
    soe_category_order = ("资本金融", "项目资产", "风险治理", "产业经营", "综合动态")
    soe_category_records = {
        category: [row for row in soe_records if row.get("category") == category][:5]
        for category in soe_category_order
    }
    listed_content_rows = [
        (key, row)
        for key in ("opportunities", "risk_rows", "tiles", "capital_rows", "follow_items")
        for row in listed_daily.get(key, [])
    ] + [
        ("fixed_columns", row)
        for group in listed_daily.get("fixed_columns", [])
        for row in group.get("items", [])
    ]
    listed_unmatched = [
        {
            "group": group,
            "company": listed_company(row, group),
            "title": row.get("title") or row.get("event") or "",
        }
        for group, row in listed_content_rows
        if not row.get("sourceUrl")
    ]

    return {
        "schemaVersion": "2.2",
        "asOf": AS_OF,
        "pageDate": AS_OF,
        "year": target_year,
        "scanAsOf": readiness["date"],
        "scanSlot": readiness["slot"],
        "sourceAsOf": {
            "listed": LISTED_SOURCE_DATE,
            "privateProducts": PRIVATE_SOURCE_DATE,
            "privateUniverse": PRIVATE_SOURCE_DATE,
            "ma": iso_date(ma_source.get("eventAsOf") or ma_source.get("asOf")),
            "tender": max((row["latestProgressDate"] for row in tender_projects), default=""),
            "soe": soe_latest_date,
        },
        "build": {
            "script": "v2/scripts/build_daily_v2.py",
            "mode": "repeatable-derived-artifact",
            "schema": BUILD_SCHEMA,
            "readiness": readiness_path.relative_to(ROOT).as_posix(),
            "notice": "本快照由列示规范数据与结构化证据稳定生成。",
        },
        "readiness": {
            "status": readiness["status"],
            "slot": readiness["slot"],
            "date": readiness["date"],
            "channels": readiness["channels"],
            "failures": readiness.get("failures", []),
            # The customer snapshot retains the immutable quality-contract
            # identity used for this build.  It is metadata for the release
            # validator, not customer-facing copy.
            "qualityContract": readiness.get("qualityContract", {}),
            "sourceConstraints": readiness.get("sourceConstraints", []),
        },
        "rules": {
            "year": "eventDate 所在自然年；仅展示结构化源中真实存在的年份",
            "eventDate": "私募取备案日期；收并购仅取有可访问原始来源确认的公告或实际进展日期",
            "updatedAt": "当前记录最近一次可核验公开进展日期",
        },
        "sources": {
            "channelImages": CHANNEL_IMAGE_SOURCES,
            "sourceContract": "v2/config/source-contract.json",
            "listedUniverse": source_contract["listedUniverse"],
            "listedDaily": listed_path.relative_to(ROOT).as_posix(),
            "listedBusinessTaxonomy": source_contract["listedTaxonomy"],
            "privateAnnual": source_contract["privateAnnual"],
            "privateUniverse": (
                private_daily_path.relative_to(ROOT).as_posix()
                + " + "
                + source_contract["privateUniverse"]
            ),
            "privateProductEvidence": sorted({row.get("sourcePath", "") for row in products if row.get("sourcePath")}),
            "maAnnual": source_contract["maEvents"],
            "maScanEvidence": ma_scan_path.relative_to(ROOT).as_posix(),
            "soeAnnual": source_contract["soeEvents"],
            "soeScanEvidence": soe_scan_path.relative_to(ROOT).as_posix(),
            "tenderAnnualProjects": source_contract["tenderEvents"],
            "tenderScanEvidence": tender_scan_path.relative_to(ROOT).as_posix(),
            "eventStore": source_contract["eventStore"],
            "observationPool": source_contract["observationPool"],
        },
        "homeHighlights": home_highlights(
            listed_daily,
            products,
            ma_projects,
            ma_event_on_scan_date=bool(ma_scan.get("eventOnScanDate")),
        ),
        "listed": {
            "pageDate": AS_OF,
            "sourceAsOf": LISTED_SOURCE_DATE,
            "latestEventDate": max(
                (iso_date(row.get("publishedAt")) for _, row in listed_content_rows),
                default="",
            ),
            "isAsOfFallback": LISTED_SOURCE_DATE != AS_OF,
            "counts": listed_universe["counts"],
            "entities": listed_entities,
            "excluded": listed_universe.get("excluded", []),
            "daily": listed_daily,
            "focusCompanies": listed_focus_companies,
            "sourceCoverage": {
                "total": len(listed_content_rows),
                "linked": sum(bool(row.get("sourceUrl")) for _, row in listed_content_rows),
                "unmatched": listed_unmatched,
            },
            "archive": listed_archive,
            "businessTaxonomy": {
                "priorityMeaning": listed_taxonomy["priorityMeaning"],
                "focusTags": [
                    {"category": category["name"], "name": tag["name"], "targets": category["targetObjects"]}
                    for category in listed_taxonomy["categories"]
                    for tag in category["tags"]
                    if tag["businessPriority"] == "focus"
                ],
            },
        },
        "private": {
            "pageDate": AS_OF,
            "sourceAsOf": PRIVATE_SOURCE_DATE,
            "latestEventDate": max((row["filingDate"] for row in products), default=""),
            "universeAsOf": PRIVATE_SOURCE_DATE,
            "summary": private_backfill["coverage"],
            "rules": private_rules,
            "managers": private_managers,
            "managerCounts": {
                "total": len(private_managers),
                "PF1": manager_counts["PF1"],
                "PF2": manager_counts["PF2"],
                "PF2Substantive": pf2_relation_counts["substantive_operation_or_equity"],
                "PF2Association": pf2_relation_counts["association_member"],
            },
            "pendingEvidence": pending_evidence,
            "excludedEvidence": excluded_evidence,
            "products": products,
            "custodianStats": custodian_stats,
            "annualMonthCounts": private_annual_months,
        },
        "ma": {
            "pageDate": AS_OF,
            "sourceAsOf": iso_date(ma_source.get("eventAsOf") or ma_source.get("asOf")),
            "scanAsOf": readiness["date"],
            "projects": ma_projects,
            "verifiedProjects": [row for row in ma_projects if row["sourceVerified"]],
            "pendingProjects": [row for row in ma_projects if not row["sourceVerified"]],
            "sourceCoverage": {
                "linked": sum(row["sourceVerified"] for row in ma_projects),
                "total": len(ma_projects),
                "reviewed": ma_source.get("projectCount", len(ma_projects)),
                "historicalExactDocumentBacklog": ma_source.get("sourceBackfillCount", 0),
            },
        },
        "soe": {
            "pageDate": AS_OF,
            "sourceAsOf": soe_latest_date,
            "scanAsOf": soe_scan["scanAsOf"],
            "scanSlot": soe_scan["slot"],
            "scanStatus": soe_scan["status"],
            "eventOnScanDate": bool(soe_scan.get("eventOnScanDate")),
            "scanEvidence": soe_scan_path.relative_to(ROOT).as_posix(),
            "networkVerified": bool(soe_scan.get("networkVerified")),
            "available": True,
            "summary": soe_source["summary"],
            "limits": soe_source["limits"],
            "customerBoundary": "当前可查询的国企历史记录最早到2026-05-21；更早记录尚未完成系统回补，不能据此视为年初以来全量。",
            "latestRecordDate": soe_latest_date,
            "focusRecords": soe_focus_records,
            "categoryRecords": soe_category_records,
            "categoryOrder": list(soe_category_order),
            "recordCount": len(soe_records),
            "rejectedCandidateCount": len(soe_scan.get("rejectedCandidates", [])),
            "isAsOfFallback": soe_latest_date != AS_OF,
        },
        "tender": {
            "pageDate": AS_OF,
            "sourceAsOf": max((row["latestProgressDate"] for row in tender_projects), default=""),
            "scanAsOf": readiness["date"],
            "isAsOfFallback": True,
            "annualSummary": tender_catalog["summary"],
            "projectCountBasis": "按独立项目计数；同一项目的公告、更正、候选与中标阶段不重复计项",
            "projects": tender_projects,
            "pending": tender_pending,
        },
    }


def shell(page: str, title: str, build_version: str) -> str:
    nav = [
        ("index", "首页"),
        ("listed", "上市公司"),
        ("private", "证券私募"),
        ("ma", "收并购"),
        ("tender", "金融招投标"),
        ("soe", "国企动态"),
    ]
    links = ""
    for key, label in nav:
        current = 'aria-current="page"' if key == page else ""
        href = key + ".html"
        links += f'<a {current} href="{href}">{label}</a>'
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#17395c"><meta name="v2-build-version" content="{build_version}"><title>{esc(title)}｜陕西资本市场日报 V2</title>
<link rel="icon" href="data:,">
<link rel="stylesheet" href="assets/styles.css?v={build_version}"></head>
<body data-page="{page}" data-build-version="{build_version}"><div class="edition">陕西资本市场日报 V2</div>
<header class="site-head"><a class="brand" href="index.html"><span>陕西资本市场</span><b>日报 V2</b></a>
<button class="nav-toggle" type="button" aria-label="展开导航">目录</button><nav>{links}</nav></header>
<main id="app"><div class="loading">正在载入日报…</div></main>
<footer class="site-footer"><section><b>客户联系</b><p>{CONTACT}<br><a href="mailto:{EMAIL}">{EMAIL}</a></p></section>
<section><b>使用说明</b><p>来源链接随事项列示。公开信息仅供交流，不构成投资建议或交易邀请；请以监管部门及公告原文为准。</p></section>
<button class="copy" type="button">复制本页链接</button></footer>
<script src="assets/app.js?v={build_version}"></script></body></html>"""


def source_fingerprints() -> list[dict]:
    contract = load("v2/config/source-contract.json")
    soe_receipt_path = ROOT / contract["soeScanDirectory"] / f"scan-{AS_OF}-{READINESS_SLOT}.json"
    soe_receipt = json.loads(soe_receipt_path.read_text(encoding="utf-8"))
    soe_evidence_relative = str(soe_receipt.get("evidencePath") or "")
    if not soe_evidence_relative:
        raise ValueError("SOE 当前时点扫描回执缺少正式取证路径")
    files = [
        ROOT / "v2" / "config" / "source-contract.json",
        ROOT / "v2" / "config" / "production-quality-contract.json",
        ROOT / contract["listedUniverse"],
        ROOT / contract["listedTaxonomy"],
        ROOT / contract["listedDailyDirectory"] / f"listed-official-{LISTED_SOURCE_DATE}.json",
        ROOT / contract["listedDailyDirectory"] / f"cninfo-announcements-{LISTED_SOURCE_DATE}.json",
        ROOT / contract["privateAnnual"],
        ROOT / contract["privateUniverse"],
        ROOT / contract["privateDailyDirectory"] / f"security-private-fund-daily-{PRIVATE_SOURCE_DATE}.json",
        ROOT / contract["maEvents"],
        ROOT / contract["maSources"],
        ROOT / contract["maScanDirectory"] / f"scan-{AS_OF}-{READINESS_SLOT}.json",
        ROOT / contract["soeEvents"],
        soe_receipt_path,
        ROOT / soe_evidence_relative,
        ROOT / contract["tenderEvents"],
        ROOT / contract["tenderSources"],
        ROOT / contract["tenderScanDirectory"] / f"scan-{AS_OF}-{READINESS_SLOT}.json",
        ROOT / contract["eventStore"],
        ROOT / contract["observationPool"],
        ROOT / contract["readinessDirectory"] / f"v2-ready-{AS_OF}-{READINESS_SLOT}.json",
        Path(__file__).resolve(),
        ROOT / "v2" / "scripts" / "refresh_soe_events.py",
        ROOT / "v2" / "scripts" / "refresh_ma_events.py",
        ROOT / "v2" / "scripts" / "refresh_tender_events.py",
        ROOT / "v2" / "scripts" / "scanner_common.py",
    ] + [ROOT / source for source in CHANNEL_IMAGE_SOURCES.values()]
    result = []
    for path in files:
        if path.exists():
            result.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    return sorted(result, key=lambda item: item["path"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建陕西资本市场日报 V2")
    parser.add_argument(
        "--date",
        default=datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
        help="页面日期，格式 YYYY-MM-DD；默认 Asia/Shanghai 当天",
    )
    parser.add_argument(
        "--allow-listed-fallback",
        action="store_true",
        help="仅供人工历史预览：允许上市公司回退至最近正式 curated；自动化不得启用",
    )
    parser.add_argument(
        "--slot",
        choices=("morning", "midday", "closing"),
        default="morning",
        help="本次扫描时点；构建只接受同日期、同时点且状态为 ready 的 V2 就绪清单",
    )
    return parser.parse_args()


def main() -> int:
    global AS_OF, LISTED_SOURCE_DATE, PRIVATE_SOURCE_DATE, READINESS_SLOT
    args = parse_args()
    AS_OF = date.fromisoformat(args.date).isoformat()
    READINESS_SLOT = args.slot
    _, LISTED_SOURCE_DATE = dated_source(
        ROOT / "v2" / "data" / "daily" / "listed",
        "listed-official-*.json",
        AS_OF,
        exact=not args.allow_listed_fallback,
    )
    _, PRIVATE_SOURCE_DATE = dated_source(
        ROOT / "v2" / "data" / "daily" / "private",
        "security-private-fund-daily-*.json",
        AS_OF,
    )
    for retired in (OUT / "images", OUT / "share"):
        if retired.exists():
            shutil.rmtree(retired)
    retired_manifest = OUT / "data" / "share-images.json"
    if retired_manifest.exists():
        retired_manifest.unlink()
    for path in (OUT / "data", OUT / "assets"):
        path.mkdir(parents=True, exist_ok=True)
    prepare_channel_images()
    data = normalize()
    data["build"]["inputs"] = source_fingerprints()
    version_input = (
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"".join(path.read_bytes() for path in sorted((OUT / "assets").iterdir()) if path.is_file())
    )
    build_version = hashlib.sha256(version_input).hexdigest()[:12]
    data["build"]["version"] = build_version
    (OUT / "data" / "production-data.json").write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / "data" / "build-version.json").write_text(
        json.dumps({"asOf": AS_OF, "buildVersion": build_version}, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    pages = {
        "index.html": ("index", "陕西资本市场动态"),
        "listed.html": ("listed", "陕西上市公司早报"),
        "private.html": ("private", "陕西证券私募年度库"),
        "ma.html": ("ma", "陕西收并购年度库"),
        "tender.html": ("tender", "陕西金融招投标日报"),
        "soe.html": ("soe", "陕西国企动态早报"),
    }
    for filename, (page, title) in pages.items():
        (OUT / filename).write_text(shell(page, title, build_version), encoding="utf-8")
    print(
        json.dumps(
            {
                "asOf": AS_OF,
                "buildVersion": build_version,
                "pages": len(pages),
                "listed": data["listed"]["counts"],
                "privateAnnual": len(data["private"]["products"]),
                "maAnnual": len(data["ma"]["projects"]),
                "soeLatestEvent": data["soe"]["latestRecordDate"],
                "soeScanAsOf": data["soe"]["scanAsOf"],
                "privatePool": Counter(x["tier"] for x in data["private"]["managers"]),
            },
            ensure_ascii=False,
            default=dict,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
