#!/usr/bin/env python3
"""Validate the isolated V2 runtime and execute its production test suite."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "v2"
RUNTIME_ROOT_FILES = (
    "index.html", "listed.html", "private.html", "ma.html", "tender.html", "soe.html",
)
RUNTIME_DIRS = ("assets", "data")
PUBLISH_DIRS = ("assets",)
PUBLISH_DATA_FILES = ("data/production-data.json", "data/build-version.json")
EXCLUDED_DIRS = ("scripts", "tests", "docs", "陕西省上市公司日报v2")
LISTED_FORBIDDEN_CUSTOMER_PATTERNS = (
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
LISTED_MOJIBAKE_MARKERS = ("�", "█", "▒", "▓", "Ã", "Â", "â€", "ï¿½", "ʫ", "ʮ̡", "ཫ", "ԫ")


def listed_customer_rows(daily: dict) -> list[dict]:
    rows = [
        row
        for key in ("opportunities", "risk_rows", "tiles", "capital_rows", "follow_items")
        for row in daily.get(key, [])
        if isinstance(row, dict)
    ]
    rows.extend(
        row
        for group in daily.get("fixed_columns", [])
        if isinstance(group, dict)
        for row in group.get("items", [])
        if isinstance(row, dict)
    )
    return rows


def validate_listed_customer_quality(data: dict) -> None:
    daily = data.get("listed", {}).get("daily", {})
    if daily.get("template") != "v2-listed-v1-editorial":
        raise ValueError("上市公司客户稿未使用 V1 标准的 V2 精读模板")
    rows = listed_customer_rows(daily)
    if not rows:
        raise ValueError("上市公司客户稿没有精选事项")
    customer_texts: list[str] = []
    seen_main: set[str] = set()
    for row in rows:
        text = " ".join(
            str(row.get(key) or "")
            for key in ("title", "body", "company", "event", "tag", "numbersHtml", "attention")
        )
        plain = re.sub(r"<[^>]+>", "", text)
        customer_texts.append(plain)
        if any(re.search(pattern, plain, flags=re.I) for pattern in LISTED_FORBIDDEN_CUSTOMER_PATTERNS):
            raise ValueError(f"上市公司客户稿泄漏 PDF 模板或页眉页脚：{plain[:80]}")
        if any(marker in plain for marker in LISTED_MOJIBAKE_MARKERS):
            raise ValueError(f"上市公司客户稿包含乱码标记：{plain[:80]}")
        if re.search(r"[\u4e00-\u9fff]\s+[\u4e00-\u9fff]\s+[\u4e00-\u9fff]", plain):
            raise ValueError(f"上市公司客户稿包含异常中文断词空格：{plain[:80]}")
        if len(plain) > 360:
            raise ValueError(f"上市公司客户稿出现全文式长段落：{plain[:80]}")
        matter_id = str(row.get("matter_id") or "")
        if not matter_id:
            raise ValueError("上市公司客户事项缺少稳定 matter_id")
        if not row.get("isReference") and matter_id in seen_main:
            raise ValueError(f"上市公司同一事项重复进入多个主栏目：{matter_id}")
        if not row.get("isReference"):
            seen_main.add(matter_id)
        required = ("company", "matterType", "businessSubcategory", "importance", "conclusion", "whyImportant")
        if any(not row.get(key) for key in required):
            raise ValueError(f"上市公司客户事项缺少结构化字段：{matter_id}")
    for row in daily.get("opportunities", []):
        body = str(row.get("body") or "")
        if not 35 <= len(body) <= 95:
            raise ValueError(f"首页候选摘要长度不合格：{row.get('matter_id')}={len(body)}")
    source_ids: set[str] = set()
    for row in daily.get("sourceEvidence", []):
        source_id = str(row.get("matter_id") or "")
        if source_id and source_id in source_ids:
            raise ValueError(f"上市公司证据库公告 ID 重复：{source_id}")
        source_ids.add(source_id)
        for forbidden_path_key in ("pdfPath", "textPath"):
            if row.get(forbidden_path_key):
                raise ValueError(f"上市公司证据库不得依赖长期本地原文路径：{forbidden_path_key}")
    rejected = daily.get("rejectedCandidates", [])
    for row in rejected:
        if (
            row.get("status") != "pending_manual_verification"
            or row.get("discoveryStatus") != "official_announcement_found_text_extraction_failed"
            or row.get("customerDisposition") != "excluded_from_customer_highlights_pending_reliable_text"
            or not row.get("sourceUrl")
        ):
            raise ValueError("正式公告正文解析失败未以待核验状态明确记录")
    acquisition = daily.get("sourceAcquisitionStatus") or {}
    if int(acquisition.get("officialAnnouncementTextExtractionFailed") or 0) != len(rejected):
        raise ValueError("正式公告正文解析失败数量与待核验清单不一致")
    if bool(acquisition.get("hasPendingOfficialTextVerification")) != bool(rejected):
        raise ValueError("上市公司正式公告解析待核验状态不一致")
    for text in customer_texts:
        abnormal = sum(
            not (
                "\u4e00" <= char <= "\u9fff"
                or char.isascii()
                or char in "，。；：、（）《》【】“”‘’—…％"
            )
            for char in text
            if not char.isspace()
        )
        if abnormal > max(2, len(text) // 40):
            raise ValueError(f"上市公司客户稿异常字符比例过高：{text[:80]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--slot", choices=("morning", "midday", "closing"), default="morning")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    data = json.loads((OUT / "data" / "production-data.json").read_text(encoding="utf-8"))
    if data["asOf"] != args.date:
        raise ValueError(f"生产快照日期 {data['asOf']} 与验证日期 {args.date} 不一致")
    if data.get("scanAsOf") != args.date or data.get("scanSlot") != args.slot:
        raise ValueError("生产快照与本次扫描日期/时点不一致")
    if data.get("readiness", {}).get("status") != "ready":
        raise ValueError("V2栏目就绪清单未达到严格 ready")
    if not all(row.get("ready") for row in data["readiness"]["channels"].values()):
        raise ValueError("存在未完成扫描的栏目")
    validate_listed_customer_quality(data)
    if any(
        row.get("date") != args.date
        for row in (
            {"date": data["scanAsOf"]},
            {"date": json.loads((ROOT / data["sources"]["eventStore"]).read_text(encoding="utf-8"))["scanAsOf"]},
            {"date": json.loads((ROOT / data["sources"]["observationPool"]).read_text(encoding="utf-8"))["scanAsOf"]},
        )
    ):
        raise ValueError("统一事件库或观察池不是当日版本")
    ma = data["ma"]
    if (
        ma["sourceCoverage"]["total"] < 25
        or ma["sourceCoverage"]["linked"] + ma["sourceCoverage"]["historicalExactDocumentBacklog"]
        != ma["sourceCoverage"]["total"]
    ):
        raise ValueError("收并购项目数量或原始来源复核口径不完整")
    if any(
        not row.get("sourceUrl")
        for row in ma["projects"]
        if row.get("entityType") == "listed"
    ):
        raise ValueError("上市公司收并购项目存在缺失交易所原文")
    if any(
        not str(row["path"]).startswith("v2/")
        for row in data["build"]["inputs"]
    ):
        raise ValueError("V2构建输入仍依赖V1/V3运行路径")
    quality = data.get("readiness", {}).get("qualityContract", {})
    if not quality.get("sha256") or quality.get("standard") != "v1-source-and-editorial-quality":
        raise ValueError("V2构建缺少已锁定的V1质量标准合同")
    soe = data["soe"]
    if (
        soe["scanAsOf"] != args.date
        or soe["scanSlot"] != args.slot
        or not soe["networkVerified"]
        or soe["latestRecordDate"] > args.date
    ):
        raise ValueError("SOE专用扫描回执或事件日期不合格")
    for name in RUNTIME_ROOT_FILES:
        if not (OUT / name).is_file():
            raise FileNotFoundError(name)
    for name in RUNTIME_DIRS:
        if not (OUT / name).is_dir():
            raise FileNotFoundError(name)
    for retired in ("images", "share"):
        if (OUT / retired).exists():
            raise ValueError(f"已停用分享目录仍存在：{retired}")
    if (OUT / "data" / "share-images.json").exists():
        raise ValueError("已停用分享图清单仍存在")
    for page in RUNTIME_ROOT_FILES:
        text = (OUT / page).read_text(encoding="utf-8")
        if "陕西资本市场日报 V2" not in text or "PREVIEW" in text:
            raise ValueError(f"{page} 的生产标识不合格")
        if f'data-build-version="{data["build"]["version"]}"' not in text:
            raise ValueError(f"{page} 的构建版本不一致")
    if not args.skip_tests:
        subprocess.run(
            ["python3", "-m", "unittest", "discover", "-s", "v2/tests", "-p", "test_*.py", "-v"],
            cwd=ROOT,
            check=True,
        )
    result = {
        "status": "ok",
        "asOf": data["asOf"],
        "buildVersion": data["build"]["version"],
        "pages": len(RUNTIME_ROOT_FILES),
        "retiredShareImages": 0,
        "scanSlot": args.slot,
        "sourceCoverage": {
            "listed": data["listed"]["sourceCoverage"],
            "ma": data["ma"]["sourceCoverage"],
        },
        "publishWhitelist": {
            "rootFiles": list(RUNTIME_ROOT_FILES),
            "directories": list(PUBLISH_DIRS),
            "dataFiles": list(PUBLISH_DATA_FILES),
            "excluded": list(EXCLUDED_DIRS),
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
