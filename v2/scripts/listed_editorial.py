#!/usr/bin/env python3
"""V2 listed-company editorial selection and customer-copy quality gates.

The official announcement inventory remains complete and auditable, but only
matter-level, source-backed conclusions leave this module.  PDF paragraphs are
never used as customer copy.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Iterable


FORBIDDEN_CUSTOMER_PATTERNS = (
    r"邮编[：:]",
    r"传真(?:/Fax)?[：:]",
    r"律师事务所",
    r"法律意见书",
    r"本公司及(?:董事会|监事会).*保证",
    r"没有虚假记载、?误导性陈述",
    r"本报告依据.*评估准则",
    r"资产评估报告第?\s*\d+\s*页",
    r"目\s*录",
    r"证券代码[：:]",
    r"股票代码[：:]",
    r"公告编号[：:]",
)
MOJIBAKE_MARKERS = ("�", "█", "▒", "▓", "Ã", "Â", "â€", "ï¿½", "ʫ", "ʮ̡", "ཫ", "ԫ", "", "")
BOILERPLATE_PATTERNS = FORBIDDEN_CUSTOMER_PATTERNS + (
    r"保荐机构（主承销商）",
    r"关于.+?之(?:补充)?法律意见书",
    r"关于.+?资产评估报告",
    r"重要内容提示",
    r"以下简称",
    r"单位[：:]股",
    r"根据《中华人民共和国",
    r"相关法律法规",
    r"第\s*\d+\s*页",
    r"二[〇○零一二三四五六七八九]{3}年",
    r"注册地址",
    r"办公地址",
)
LOW_VALUE_TITLE_PATTERNS = (
    r"法律意见书",
    r"资产评估报告$",
    r"审计报告$",
    r"上市保荐书$",
    r"发行保荐书$",
    r"补充法律意见书",
)
MATERIAL_TERMS = (
    "问询", "立案", "警示", "诉讼", "仲裁", "亏损", "盈利预警", "担保", "授信",
    "增资", "收购", "出售", "资产置换", "股权转让", "回购", "减持", "权益变动",
    "发行", "募资", "可转债", "股权激励", "激励", "归属", "辞职", "中标", "合同", "业绩",
)
RISK_TERMS = ("问询", "立案", "警示", "诉讼", "仲裁", "亏损", "盈利预警", "担保", "冻结", "终止评级")
CAPITAL_TERMS = ("增资", "收购", "出售", "资产置换", "股权转让", "回购", "减持", "权益变动", "发行", "募资", "可转债")


def normalize_pdf_text(value: str) -> str:
    text = str(value or "").replace("\u3000", " ").replace("\ufeff", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"(?<=[A-Za-z])\s+(?=[A-Za-z])", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def text_quality_report(value: str) -> dict[str, Any]:
    raw = str(value or "")
    compact = "".join(char for char in raw if not char.isspace())
    total = max(1, len(compact))
    controls = sum(ord(char) < 32 and char not in "\t\n\r" for char in raw)
    replacements = sum(raw.count(marker) for marker in MOJIBAKE_MARKERS)
    readable = sum(
        "\u4e00" <= char <= "\u9fff"
        or char.isascii()
        or char in "，。；：、（）《》【】“”‘’—…％·"
        for char in compact
    )
    chinese = sum("\u4e00" <= char <= "\u9fff" for char in compact)
    latin = sum(char.isascii() and (char.isalpha() or char.isdigit()) for char in compact)
    abnormal_runs = re.findall(r"[^\u4e00-\u9fffA-Za-z0-9，。；：、（）《》【】“”‘’—…％%.,:;()\-_/]{4,}", compact)
    broken_spacing = len(re.findall(r"[\u4e00-\u9fff]\s+[\u4e00-\u9fff]\s+[\u4e00-\u9fff]", raw))
    reasons: list[str] = []
    if len(compact) < 80:
        reasons.append("text_too_short")
    if controls:
        reasons.append("control_characters")
    if replacements:
        reasons.append("replacement_or_mojibake_markers")
    if readable / total < 0.82:
        reasons.append("readable_character_ratio")
    if (chinese + latin) / total < 0.46:
        reasons.append("language_character_ratio")
    if len(abnormal_runs) > 1:
        reasons.append("continuous_abnormal_symbols")
    if broken_spacing > max(8, len(raw) // 260):
        reasons.append("broken_cjk_spacing")
    return {
        "eligible": not reasons,
        "reasons": reasons,
        "metrics": {
            "characters": len(compact),
            "readableRatio": round(readable / total, 4),
            "languageRatio": round((chinese + latin) / total, 4),
            "controlCharacters": controls,
            "mojibakeMarkers": replacements,
            "abnormalRuns": len(abnormal_runs),
            "brokenCjkSpacing": broken_spacing,
        },
    }


def clean_customer_text(value: str) -> str:
    text = normalize_pdf_text(re.sub(r"<[^>]+>", "", str(value or "")))
    text = re.sub(r"\s+([，。；：、）])", r"\1", text)
    text = re.sub(r"([（])\s+", r"\1", text)
    text = re.sub(r"^\s*[\d一二三四五六七八九十]+[、.．]\s*", "", text)
    return text.strip(" ，；。") + ("。" if text.strip(" ，；。") else "")


def trim_sentence(value: str, maximum: int, minimum: int = 0) -> str:
    text = clean_customer_text(value)
    if len(text) <= maximum:
        return text
    clipped = text[:maximum].rstrip("，；：、。")
    boundary = max(clipped.rfind("；"), clipped.rfind("，"))
    if boundary >= minimum:
        clipped = clipped[:boundary]
    return clipped.rstrip("，；：、。") + "。"


def split_sentences(value: str) -> list[str]:
    text = normalize_pdf_text(value)
    return [
        clean_customer_text(item)
        for item in re.split(r"(?<=[。；！？])", text)
        if len(normalize_pdf_text(item)) >= 12
    ]


def is_boilerplate(value: str) -> bool:
    return any(re.search(pattern, value, flags=re.I) for pattern in BOILERPLATE_PATTERNS)


def customer_copy_is_clean(value: str) -> bool:
    text = str(value or "")
    return not (
        any(re.search(pattern, text, flags=re.I) for pattern in FORBIDDEN_CUSTOMER_PATTERNS)
        or any(marker in text for marker in MOJIBAKE_MARKERS)
        or re.search(r"[\u4e00-\u9fff]\s+[\u4e00-\u9fff]\s+[\u4e00-\u9fff]", text)
    )


def matter_type(title: str, text: str) -> str:
    title_rules = (
        (("资产置换",), "资产置换"),
        (("限制性股票激励", "激励对象名单", "归属结果"), "股权激励"),
        (("首次回购", "回购股份"), "股份回购"),
        (("担保", "授信"), "担保授信"),
        (("到期兑付", "可转债兑付"), "可转债兑付"),
        (("信用评级", "终止评级"), "信用评级"),
        (("向特定对象发行", "募集说明书"), "再融资"),
        (("股东会",), "股东会"),
        (("增资",), "对外投资"),
        (("股权转让", "挂牌"), "股权转让"),
        (("保荐代表人",), "中介变更"),
        (("辞职",), "治理变动"),
        (("盈利预警", "业绩预告"), "业绩预告"),
    )
    for needles, label in title_rules:
        if any(needle in title for needle in needles):
            return label
    value = f"{title} {text}"
    for needles, label in (
        (("资产置换",), "资产置换"),
        (("限制性股票激励", "激励对象名单"), "股权激励"),
        (("担保", "授信"), "担保授信"),
        (("回购",), "股份回购"),
        (("可转债", "兑付"), "可转债兑付"),
        (("向特定对象发行", "募集说明书"), "再融资"),
        (("增资",), "对外投资"),
        (("股权转让", "挂牌"), "股权转让"),
    ):
        if any(needle in value for needle in needles):
            return label
    return "经营治理"


def business_subcategory(kind: str) -> str:
    return {
        "资产置换": "资产交易",
        "股权激励": "股权激励",
        "再融资": "再融资",
        "股东会": "章程治理",
        "股份回购": "股份回购",
        "担保授信": "担保与授信",
        "可转债兑付": "债券兑付",
        "信用评级": "信用风险",
        "对外投资": "对外投资",
        "股权转让": "股权转让",
        "治理变动": "高管与治理",
        "中介变更": "持续督导",
        "业绩预告": "业绩预告",
    }.get(kind, "综合事项")


def stable_group_key(company: str, title: str, text: str) -> str:
    kind = matter_type(title, text)
    if kind == "股权激励" and ("名单" in title or "核查" in title):
        key = "激励名单核查"
    elif kind == "资产置换":
        key = "资产置换"
    elif kind == "再融资":
        key = "向特定对象发行"
    elif kind == "股东会":
        meeting = re.search(r"(20\d{2}年)?第[一二三四五六七八九十\d]+次临时股东会", title + text)
        key = meeting.group(0) if meeting else "股东会"
    elif kind == "担保授信":
        key = "担保授信"
    elif kind in {"可转债兑付", "信用评级"} and "科华转债" in title + text:
        key = "科华转债到期"
    else:
        key = kind
    return f"{company}|{key}"


def score_matter(rows: list[dict[str, Any]]) -> int:
    value = " ".join(f"{row.get('title', '')} {row.get('fullText', '')[:3000]}" for row in rows)
    score = sum(4 for term in MATERIAL_TERMS if term in value)
    score += min(5, len(re.findall(r"\d+(?:[.,]\d+)?(?:亿元|万元|%|股|张|元)", value)))
    if any(term in value for term in RISK_TERMS):
        score += 5
    if all(any(re.search(pattern, str(row.get("title") or "")) for pattern in LOW_VALUE_TITLE_PATTERNS) for row in rows):
        score -= 9
    return score


def importance_label(rows: list[dict[str, Any]]) -> str:
    score = score_matter(rows)
    return "必看" if score >= 13 else "重点" if score >= 8 else "关注"


def select_sentences(rows: list[dict[str, Any]], maximum: int = 2) -> list[str]:
    title_terms = {
        term
        for row in rows
        for term in re.findall(r"[\u4e00-\u9fff]{2,6}", str(row.get("title") or ""))
        if term not in {"有限公司", "股份", "公告", "关于", "公司"}
    }
    candidates: list[tuple[int, str]] = []
    for row in rows:
        for sentence in split_sentences(str(row.get("fullText") or row.get("excerpt") or "")):
            if is_boilerplate(sentence) or not customer_copy_is_clean(sentence):
                continue
            score = sum(term in sentence for term in MATERIAL_TERMS) * 4
            score += sum(term in sentence for term in title_terms)
            score += min(4, len(re.findall(r"\d+(?:[.,]\d+)?(?:亿元|万元|%|股|张|元|个月|日)", sentence)))
            if 30 <= len(sentence) <= 180:
                score += 2
            candidates.append((score, sentence))
    selected: list[str] = []
    for _, sentence in sorted(candidates, key=lambda item: (item[0], len(item[1])), reverse=True):
        fingerprint = re.sub(r"\W", "", sentence)[:36]
        if fingerprint and all(fingerprint not in re.sub(r"\W", "", item) for item in selected):
            selected.append(sentence)
        if len(selected) == maximum:
            break
    return selected


def next_step_for(kind: str) -> str:
    return {
        "资产置换": "后续关注协议签署、资产交割及关联交易执行情况。",
        "股权激励": "后续关注授予或归属条件、登记数量及费用影响。",
        "再融资": "后续关注交易所审核、证监会注册及募投落地。",
        "股东会": "后续关注已通过议案执行及相关工商或资金安排。",
        "股份回购": "后续关注回购进度、成交区间及后续用途。",
        "担保授信": "后续关注实际提款、担保余额和偿债安排。",
        "可转债兑付": "后续关注摘牌、股本变动及债务结构变化。",
        "信用评级": "后续关注债券摘牌后的融资安排与信用变化。",
        "对外投资": "后续关注股东会审议、出资节奏和项目回报。",
        "股权转让": "后续关注正式挂牌、受让方和交易价格。",
        "治理变动": "后续关注补选安排和治理衔接。",
        "中介变更": "后续关注持续督导交接及存续项目安排。",
        "业绩预告": "后续关注正式业绩、减值及现金流变化。",
    }.get(kind, "后续关注正式公告中的关键节点和数字变化。")


def summarize_matter(rows: list[dict[str, Any]]) -> tuple[str, str]:
    kind = matter_type(str(rows[0].get("title") or ""), " ".join(str(row.get("fullText") or "")[:1200] for row in rows))
    picked = select_sentences(rows, maximum=2)
    conclusion = trim_sentence("".join(picked) or str(rows[0].get("title") or ""), 118, 48)
    if not customer_copy_is_clean(conclusion):
        conclusion = trim_sentence(str(rows[0].get("title") or ""), 72)
    why = next_step_for(kind)
    return conclusion, why


def common_fields(matter: dict[str, Any]) -> dict[str, Any]:
    return {
        "matter_id": matter["matter_id"],
        "company": matter["company"],
        "matterType": matter["matterType"],
        "businessSubcategory": matter["businessSubcategory"],
        "importance": matter["importance"],
        "conclusion": matter["conclusion"],
        "whyImportant": matter["whyImportant"],
        "publishedAt": matter["publishedAt"],
        "sourceName": matter["sourceName"],
        "sourceUrl": matter["sourceUrl"],
        "announcementTitle": matter["announcementTitle"],
        "sources": matter["sources"],
    }


def build_matters(evidence: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence:
        grouped[stable_group_key(str(row["company"]), str(row["title"]), str(row.get("fullText") or ""))].append(row)
    matters: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        rows.sort(key=lambda row: (str(row.get("publishedAt") or ""), str(row.get("matter_id") or "")), reverse=True)
        if score_matter(rows) < 3:
            continue
        company = str(rows[0]["company"])
        joined = " ".join(f"{row.get('title', '')} {row.get('fullText', '')[:1200]}" for row in rows)
        kind = matter_type(str(rows[0]["title"]), joined)
        conclusion, why = summarize_matter(rows)
        source_rows = [
            {
                "sourceName": "巨潮资讯",
                "sourceUrl": str(row["sourceUrl"]),
                "announcementTitle": str(row["title"]),
                "announcementId": str(row["matter_id"]),
            }
            for row in rows
        ]
        matter_id = "listed-matter-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:14]
        matters.append({
            "matter_id": matter_id,
            "company": company,
            "matterType": kind,
            "businessSubcategory": business_subcategory(kind),
            "importance": importance_label(rows),
            "conclusion": conclusion,
            "whyImportant": why,
            "publishedAt": max(str(row.get("publishedAt") or "") for row in rows),
            "sourceName": "巨潮资讯",
            "sourceUrl": source_rows[0]["sourceUrl"],
            "announcementTitle": source_rows[0]["announcementTitle"],
            "sources": source_rows,
            "sourceAnnouncementIds": [row["announcementId"] for row in source_rows],
            "score": score_matter(rows),
        })
    matters.sort(
        key=lambda row: (
            str(row["publishedAt"]),
            {"必看": 3, "重点": 2, "关注": 1}[row["importance"]],
            int(row["score"]),
        ),
        reverse=True,
    )
    return matters


def homepage_body(matter: dict[str, Any]) -> str:
    if matter.get("homeSummary"):
        return clean_customer_text(str(matter["homeSummary"]))
    value = f"{matter['conclusion'].rstrip('。')}；{matter['whyImportant']}"
    return trim_sentence(value, 90, 58)


def assemble_editorial_report(
    *,
    day: str,
    matters: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    raw_summary: dict[str, Any],
    hkex_company_count: int,
) -> dict[str, Any]:
    if len(matters) < 2:
        raise ValueError("通过文本质量与事项筛选的上市公司重点不足，拒绝生成客户稿")
    risk = [
        row for row in matters
        if row.get("mainSection") == "risk"
        or (not row.get("mainSection") and row["matterType"] in {"业绩预告", "担保授信", "信用评级", "再融资"})
    ]
    capital = [
        row for row in matters
        if row.get("mainSection") == "capital"
        or (not row.get("mainSection") and row["matterType"] in {"资产置换", "股份回购", "可转债兑付", "对外投资", "股权转让"})
    ]
    governance = [
        row for row in matters
        if row.get("mainSection") == "governance"
        or (not row.get("mainSection") and row["matterType"] in {"股东会", "股权激励", "治理变动", "中介变更"})
    ]
    used = {row["matter_id"] for row in risk[:4] + capital[:5] + governance[:6]}
    dynamic = [
        row for row in matters
        if row.get("mainSection") == "dynamic"
        or (not row.get("mainSection") and row["matter_id"] not in used)
    ][:4]
    used.update(row["matter_id"] for row in dynamic)
    dynamic = (dynamic + [row for row in matters if row["matter_id"] not in used])[:4]
    headline = [row for row in matters if row["importance"] in {"必看", "重点"}][:4]
    if len(headline) < 2:
        headline = matters[:4]

    opportunities = [
        {
            **common_fields(row),
            "title": f"{row['importance']}｜{row['company']}",
            "body": homepage_body(row),
            "isReference": True,
            "referenceMatterId": row["matter_id"],
        }
        for row in headline
    ]
    risk_rows = [
        {
            **common_fields(row),
            "event": row["conclusion"],
            "tag": row["businessSubcategory"],
            "tagClass": "risk" if row["matterType"] in {"业绩预告", "担保授信", "信用评级"} else "watch",
        }
        for row in risk[:4]
    ]
    tiles = [
        {
            **common_fields(row),
            "title": f"{row['company']}｜{row['matterType']}",
            "body": row["conclusion"],
        }
        for row in dynamic[:4]
    ]
    capital_rows = [
        {
            **common_fields(row),
            "numbersHtml": row["conclusion"],
            "attention": row["whyImportant"],
        }
        for row in capital[:5]
    ]
    fixed_items = [
        {
            **common_fields(row),
            "title": f"{row['company']}｜{row['matterType']}",
            "body": row["conclusion"],
        }
        for row in governance[:6]
    ]
    midpoint = (len(fixed_items) + 1) // 2
    fixed_columns = [
        {"title": "A. 股东会与治理", "items": fixed_items[:midpoint]},
        {"title": "B. 激励与固定披露", "items": fixed_items[midpoint:]},
    ]
    follow_items = [
        {
            **common_fields(row),
            "title": f"{row['company']}｜关注{row['businessSubcategory']}",
            "body": row["whyImportant"],
            "isReference": True,
            "referenceMatterId": row["matter_id"],
        }
        for row in matters[:6]
    ]
    company_count = len({str(row["company"]) for row in evidence})
    return {
        "schemaVersion": "2.1",
        "date": day,
        "template": "v2-listed-v1-editorial",
        "editorialPolicy": "select_then_summarize_matter_level",
        "subtitle": (
            f"{day}｜逐主体检索{raw_summary.get('companyUniverseCount', 0)}家正式观察池，"
            f"{raw_summary.get('announcementCount', 0)}条公告、{company_count}家发布公告公司"
        ),
        "kpis": [
            {"num": f"{raw_summary.get('announcementCount', 0)}条", "label": "巨潮逐主体检索公告"},
            {"num": f"{company_count}家", "label": "窗口内发布公告公司"},
            {"num": f"{len(matters)}项", "label": "合并去重后的客户事项"},
            {"num": f"{len(rejected)}条", "label": "文本不合格或原文不可用候选"},
        ],
        "opportunities": opportunities,
        "risk_rows": risk_rows,
        "tiles": tiles,
        "capital_rows": capital_rows,
        "fixed_columns": fixed_columns,
        "follow_items": follow_items,
        "matterIndex": matters,
        "sourceEvidence": evidence,
        "rejectedCandidates": rejected,
        "evidenceArchiveCollapsedByDefault": True,
        "hkexOfficialReviewCompanyCount": hkex_company_count,
    }


def build_editorial_report(
    *,
    day: str,
    evidence: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    raw_summary: dict[str, Any],
    hkex_company_count: int,
) -> dict[str, Any]:
    return assemble_editorial_report(
        day=day,
        matters=build_matters(evidence),
        evidence=evidence,
        rejected=rejected,
        raw_summary=raw_summary,
        hkex_company_count=hkex_company_count,
    )


def build_editorial_report_from_brief(
    *,
    day: str,
    brief: dict[str, Any],
    evidence: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    raw_summary: dict[str, Any],
    hkex_company_count: int,
) -> dict[str, Any]:
    """Bind a maintenance editorial repair to already quality-checked sources."""
    if brief.get("date") != day or brief.get("policy") != "frozen_official_sources_editorial_repair":
        raise ValueError("上市公司维护编辑清单日期或策略标识错误")
    evidence_by_id = {str(row.get("matter_id") or ""): row for row in evidence}
    matters: list[dict[str, Any]] = []
    used_source_ids: set[str] = set()
    for position, row in enumerate(brief.get("matters") or []):
        source_ids = [str(value) for value in row.get("sourceAnnouncementIds") or []]
        if not source_ids or any(source_id not in evidence_by_id for source_id in source_ids):
            raise ValueError(f"维护编辑事项引用了不存在或文本不合格的官方公告：{source_ids}")
        if any(source_id in used_source_ids for source_id in source_ids):
            raise ValueError(f"同一官方公告重复进入多个客户事项：{source_ids}")
        used_source_ids.update(source_ids)
        conclusion = clean_customer_text(str(row.get("conclusion") or ""))
        why = clean_customer_text(str(row.get("whyImportant") or ""))
        if not 24 <= len(conclusion) <= 120 or not 18 <= len(why) <= 90:
            raise ValueError(f"维护编辑事项摘要长度不合格：{row.get('company')}")
        if not customer_copy_is_clean(conclusion + why):
            raise ValueError(f"维护编辑事项包含页眉页脚、乱码或异常空格：{row.get('company')}")
        source_rows = [
            {
                "sourceName": "巨潮资讯",
                "sourceUrl": str(evidence_by_id[source_id]["sourceUrl"]),
                "announcementTitle": str(evidence_by_id[source_id]["title"]),
                "announcementId": source_id,
            }
            for source_id in source_ids
        ]
        matter_key = str(row.get("matterKey") or f"{row.get('company')}|{row.get('matterType')}")
        matter_id = "listed-matter-" + hashlib.sha1(matter_key.encode("utf-8")).hexdigest()[:14]
        kind = str(row.get("matterType") or "")
        home_summary = clean_customer_text(str(row.get("homeSummary") or ""))
        if home_summary and not 35 <= len(home_summary) <= 90:
            raise ValueError(f"维护编辑事项首页摘要长度不合格：{row.get('company')}={len(home_summary)}")
        if home_summary and not customer_copy_is_clean(home_summary):
            raise ValueError(f"维护编辑事项首页摘要包含页眉页脚、乱码或异常空格：{row.get('company')}")
        matters.append({
            "matter_id": matter_id,
            "company": str(row.get("company") or ""),
            "matterType": kind,
            "businessSubcategory": str(row.get("businessSubcategory") or business_subcategory(kind)),
            "importance": str(row.get("importance") or "关注"),
            "conclusion": conclusion,
            "whyImportant": why,
            "publishedAt": max(str(evidence_by_id[source_id].get("publishedAt") or day) for source_id in source_ids),
            "sourceName": "巨潮资讯",
            "sourceUrl": source_rows[0]["sourceUrl"],
            "announcementTitle": source_rows[0]["announcementTitle"],
            "sources": source_rows,
            "sourceAnnouncementIds": source_ids,
            "score": int(row.get("score") or (100 - position)),
            "mainSection": str(row.get("mainSection") or ""),
            "homeSummary": home_summary,
        })
    matters.sort(
        key=lambda row: (
            str(row["publishedAt"]),
            {"必看": 3, "重点": 2, "关注": 1}.get(str(row["importance"]), 0),
            int(row["score"]),
        ),
        reverse=True,
    )
    report = assemble_editorial_report(
        day=day,
        matters=matters,
        evidence=evidence,
        rejected=rejected,
        raw_summary=raw_summary,
        hkex_company_count=hkex_company_count,
    )
    report["editorialPolicy"] = "frozen_official_sources_select_then_human_style_summary"
    report["editorialRepairId"] = str(brief.get("repairId") or "")
    return report
