#!/usr/bin/env python3
"""Shared deterministic helpers for V2 MA and tender scanners."""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


TENDER_STAGE_RULES = (
    ("terminated", re.compile(r"终止|流标|废标")),
    ("award", re.compile(r"(?:中标|成交)(?:结果|公告|公示)|中标通知")),
    ("candidate", re.compile(r"候选人")),
    ("change", re.compile(r"更正|变更|澄清|答疑")),
    ("announcement", re.compile(r"招标|采购|遴选|选聘|征集|比选|资格预审")),
)

MA_STAGE_RULES = (
    ("terminated", re.compile(r"终止|取消|不再推进")),
    ("completed", re.compile(r"交割完成|交易完成|过户完成|工商变更完成|完成收购")),
    ("signed_or_approved", re.compile(r"签署|协议|获批|审议通过|同意")),
    ("in_progress", re.compile(r"进展|交割|工商变更|审核|问询|回复")),
    ("announced", re.compile(r"预案|草案|提示性公告|筹划|收购|出售|股权转让|增资")),
)

MA_SUBSTANTIVE_RULES = (
    ("发行股份购买资产", re.compile(r"发行股份购买资产")),
    ("重大资产重组", re.compile(r"重大资产重组")),
    ("控制权变更", re.compile(r"控制权(?:变更|转让|收购)|取得.{0,20}控制权")),
    ("股权转让", re.compile(r"股权(?:转让|收购|出售|受让|交易)|(?:转让|收购|出售|受让).{0,20}股权")),
    ("股份转让", re.compile(r"股份(?:转让|收购|出售|受让)|(?:转让|收购|出售|受让).{0,20}股份")),
    ("企业产权转让", re.compile(r"(?:企业|公司|整体)产权(?:转让|交易)|(?:转让|受让).{0,20}(?:企业|公司|整体)产权")),
    ("增资", re.compile(r"增资(?:扩股|引战)?")),
    ("企业或业务收购", re.compile(
        r"(?:拟|筹划|完成)?收购(?:事项|项目|计划|方案|交易|"
        r".{0,20}(?:公司|企业|业务|经营性资产|资产组|股权|股份|控制权))|"
        r"(?:公司|企业|业务|经营性资产|资产组|股权|股份|控制权).{0,20}收购"
    )),
    ("企业或业务出售", re.compile(
        r"出售.{0,20}(?:公司|企业|业务|经营性资产|资产组|股权|股份|控制权)|"
        r"(?:公司|企业|业务|经营性资产|资产组|股权|股份|控制权).{0,20}出售"
    )),
    ("购买企业或业务", re.compile(
        r"购买.{0,20}(?:公司|企业|业务|经营性资产|资产组|股权|股份|控制权)"
    )),
    ("企业合并", re.compile(r"吸收合并|(?:公司|企业)(?:之间)?合并")),
)

MA_LIFECYCLE_RULES = (
    ("完成", re.compile(r"完成")),
    ("终止", re.compile(r"终止|中止|终结|取消")),
    ("交割", re.compile(r"交割")),
    ("工商变更", re.compile(r"工商变更")),
    ("交易", re.compile(r"交易|成交")),
    ("过户", re.compile(r"过户")),
    ("进展", re.compile(r"进展")),
)


def canonical_json(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    )


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_json(payload: Any) -> str:
    return sha256_bytes(canonical_json(payload))


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def normalize_title(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"^[【\[][^】\]]+[】\]]", "", text)
    text = re.sub(
        r"(公开)?招标公告|采购公告|遴选公告|选聘公告|征集公告|比选公告|"
        r"中标候选人公示|中标结果(?:公告|公示)|成交结果(?:公告|公示)|"
        r"更正公告|变更公告|澄清公告|终止公告|流标公告|废标公告|"
        r"关于|进展公告|提示性公告",
        "",
        text,
    )
    return re.sub(r"[\s，。；：、【】\[\]（）()《》<>“”\"'·—_-]+", "", text).lower()


def stable_project_id(prefix: str, title: str, buyer: str = "") -> str:
    normalized = f"{normalize_title(title)}|{normalize_title(buyer)}"
    return f"{prefix}-{hashlib.sha1(normalized.encode('utf-8')).hexdigest()[:20]}"


def infer_tender_stage(text: str) -> str:
    for stage, pattern in TENDER_STAGE_RULES:
        if pattern.search(text or ""):
            return stage
    return "pending"


def infer_ma_stage(text: str) -> str:
    for stage, pattern in MA_STAGE_RULES:
        if pattern.search(text or ""):
            return stage
    return "pending"


def tender_keyword_match(text: str, config: dict) -> dict:
    clean = re.sub(r"\s+", " ", text or "")
    excluded = [term for term in config.get("exclusionKeywords", []) if term in clean]
    groups = {
        name: [term for term in terms if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", clean, re.I)]
        for name, terms in config["keywordGroups"].items()
    }
    substantive = bool(groups["products"] or groups["services"])
    lifecycle = bool(groups["actions"]) or infer_tender_stage(clean) in {
        "change", "candidate", "award", "terminated"
    }
    matched = substantive and lifecycle and not excluded
    return {
        "matched": matched,
        "groups": groups,
        "excludedKeywords": excluded,
        "reason": (
            "matched_financing_or_securities_service"
            if matched
            else "excluded_non_capital_market_procurement"
            if excluded
            else "missing_product_or_service_keyword"
            if not substantive
            else "missing_procurement_lifecycle_keyword"
        ),
    }


def ma_keyword_match(text: str, config: dict) -> dict:
    clean = re.sub(r"\s+", " ", text or "")
    substantive = [
        label for label, pattern in MA_SUBSTANTIVE_RULES if pattern.search(clean)
    ]
    lifecycle = [
        label for label, pattern in MA_LIFECYCLE_RULES if pattern.search(clean)
    ]
    configured = [
        term for term in config.get("eventKeywords", []) if term in clean
    ]
    matched = bool(substantive)
    return {
        "matched": matched,
        "matchedKeywords": substantive,
        "substantiveSignals": substantive,
        "lifecycleSignals": lifecycle,
        "configuredKeywordHits": configured,
        "reason": (
            "matched_substantive_ma_signal"
            if matched
            else "lifecycle_without_substantive_ma_signal"
            if lifecycle
            else "no_substantive_ma_signal"
        ),
    }


def extract_ma_facts(text: str) -> dict:
    """Conservative structured extraction; empty fields remain pending review."""
    clean = re.sub(r"\s+", " ", text or "")
    amounts = list(
        dict.fromkeys(
            match.group(0)
            for match in re.finditer(
                r"(?:人民币)?\d+(?:,\d{3})*(?:\.\d+)?(?:亿元|万元|元)", clean
            )
        )
    )
    ratios = list(
        dict.fromkeys(
            match.group(0)
            for match in re.finditer(r"\d+(?:\.\d+)?%", clean)
        )
    )
    return {
        "amounts": amounts,
        "equityRatios": ratios,
        "amountStatus": "extracted_requires_context_review" if amounts else "pending_original_text",
        "ratioStatus": "extracted_requires_context_review" if ratios else "pending_original_text",
    }


def _dedupe(rows: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    found: dict[tuple[str, ...], dict] = {}
    for row in rows:
        key = tuple(str(row.get(field) or "") for field in key_fields)
        found[key] = deepcopy(row)
    return sorted(found.values(), key=lambda row: tuple(str(row.get(k) or "") for k in key_fields))


def merge_ma_project(existing: dict, candidate: dict) -> dict:
    """Append an official MA source/milestone without replacing a legacy project id."""
    result = deepcopy(existing)
    source = deepcopy(candidate["sourceRecord"])
    milestone = deepcopy(candidate["milestone"])
    result["sourceRecords"] = _dedupe(
        [*result.get("sourceRecords", []), source], ("url", "publishedAt", "title")
    )
    result["milestones"] = _dedupe(
        [*result.get("milestones", []), milestone], ("at", "label", "stageAfter")
    )
    latest = max(
        result["milestones"],
        key=lambda row: (str(row.get("at") or ""), str(row.get("label") or "")),
    )
    result["stage"] = latest.get("stageAfter") or result.get("stage")
    return result


def merge_tender_project(existing: dict, candidate: dict) -> dict:
    result = deepcopy(existing)
    result["projectFingerprint"] = candidate["projectFingerprint"]
    result["sourceRecords"] = _dedupe(
        [*result.get("sourceRecords", []), candidate["sourceRecord"]],
        ("url", "publishedAt", "title"),
    )
    result["milestones"] = _dedupe(
        [*result.get("milestones", []), candidate["milestone"]],
        ("at", "stage", "title"),
    )
    latest = max(
        result["milestones"],
        key=lambda row: (str(row.get("at") or ""), str(row.get("title") or "")),
    )
    result["stageCode"] = latest.get("stage") or result.get("stageCode") or "pending"
    return result


def verify_receipt_artifacts(root: Path, receipt: dict) -> list[str]:
    errors: list[str] = []
    for relative, expected in sorted(receipt.get("artifactHashes", {}).items()):
        path = root / relative
        if not path.is_file():
            errors.append(f"missing:{relative}")
        elif sha256_file(path) != expected:
            errors.append(f"hash_mismatch:{relative}")
    return errors
