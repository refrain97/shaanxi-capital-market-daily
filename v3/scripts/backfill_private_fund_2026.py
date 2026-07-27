#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
V1_DATA = REPO / "v1/陕西省证券私募日报v1/data"
UNIVERSE_CONFIG = ROOT / "config/private-fund-universe.json"
TZ = ZoneInfo("Asia/Shanghai")


def date_from_ms(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(int(value) / 1000, TZ).date().isoformat()


def is_shaanxi_manager(item: dict[str, Any]) -> bool:
    detail = item.get("detail") or {}
    text = " ".join(str(value or "") for value in (
        item.get("registerProvince"), item.get("officeProvince"), item.get("registerAddress"), item.get("officeAddress"),
        detail.get("registerAddress"), detail.get("officeAddress"),
    ))
    return "陕西" in text or "西安" in text


def load_latest(end: date) -> tuple[Path, dict[str, Any]]:
    candidates = []
    for path in V1_DATA.glob("security-private-fund-daily-*.json"):
        try:
            value = date.fromisoformat(path.stem.removeprefix("security-private-fund-daily-"))
        except ValueError:
            continue
        if value <= end:
            candidates.append((value, path))
    if not candidates:
        raise RuntimeError("no V1 AMAC snapshot available at or before end date")
    path = max(candidates)[1]
    return path, json.loads(path.read_text(encoding="utf-8"))


def in_range(value: str | None, start: date, end: date) -> bool:
    return bool(value and start <= date.fromisoformat(value) <= end)


def merge_coverage(channel: dict[str, Any], start: date, end: date) -> None:
    path = ROOT / "data/backfill/coverage-2026.json"
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schemaVersion": "0.1", "channels": {}}
    payload["startDate"] = start.isoformat()
    payload["endDate"] = end.isoformat()
    payload["generatedAt"] = datetime.now(TZ).isoformat()
    payload.setdefault("channels", {})["private_fund"] = channel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill 2026 Shaanxi securities private-fund records from AMAC snapshots.")
    parser.add_argument("--start-date", default="2026-01-01")
    parser.add_argument("--end-date", default=date.today().isoformat())
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)
    source_path, source = load_latest(end)
    universe_config = json.loads(UNIVERSE_CONFIG.read_text(encoding="utf-8"))
    related_names = {item["managerName"] for item in universe_config["relatedTargets"]}

    products = []
    product_rows = list(source.get("shaanxiOfficeProducts", []))
    product_rows.extend(
        item for item in source.get("raw", {}).get("allSecurityProductsInShaanxiWindow", [])
        if item.get("managerName") in related_names
    )
    seen_fund_nos = set()
    for item in product_rows:
        if item.get("fundNo") in seen_fund_nos:
            continue
        seen_fund_nos.add(item.get("fundNo"))
        filing_date = date_from_ms(item.get("putOnRecordDate"))
        if not in_range(filing_date, start, end):
            continue
        products.append({
            "fundNo": item.get("fundNo"), "fundName": item.get("fundName"), "managerName": item.get("managerName"),
            "custodian": item.get("mandatorName"), "filingDate": filing_date, "establishDate": date_from_ms(item.get("establishDate")),
            "universeTier": "PF2" if item.get("managerName") in related_names else "PF1",
            "sourceUrl": f"https://gs.amac.org.cn/amac-infodisc/res/pof/fund/{item.get('url')}", "sourceQuality": "official",
        })
    managers = []
    for item in source.get("nationalYearAdditions", []):
        register_date = date_from_ms(item.get("registerDate"))
        if is_shaanxi_manager(item) and in_range(register_date, start, end):
            managers.append({"registerNo": item.get("registerNo"), "managerName": item.get("managerName"), "registerDate": register_date, "registerProvince": item.get("registerProvince"), "officeProvince": item.get("officeProvince"), "sourceUrl": item.get("detailUrl"), "sourceQuality": "official"})
    cancellations = []
    for item in source.get("nationalYearCancellations", []):
        cancel_date = date_from_ms(item.get("cancelDate"))
        manager_type = str((item.get("detail") or {}).get("managerType") or "")
        if is_shaanxi_manager(item) and "证券" in manager_type and in_range(cancel_date, start, end):
            cancellations.append({"managerName": item.get("orgName"), "orgCode": item.get("orgCode"), "cancelDate": cancel_date, "cancelType": item.get("statusName"), "managerType": manager_type, "sourceUrl": item.get("detailUrl"), "sourceQuality": "official"})

    limited = bool(source.get("yearCancelDetailLimitHit"))
    output = {
        "schemaVersion": "0.1", "startDate": start.isoformat(), "endDate": end.isoformat(), "generatedAt": datetime.now(TZ).isoformat(),
        "sourceSnapshot": str(source_path.relative_to(REPO)), "sourceReportDate": source.get("reportDate"),
        "coverage": {"status": "PRODUCTS_COMPLETE_CANCELLATIONS_LIMITED" if limited else "RAW_COMPLETE", "productCount": len(products), "territorialProductCount": sum(item["universeTier"] == "PF1" for item in products), "relatedProductCount": sum(item["universeTier"] == "PF2" for item in products), "newManagerCount": len(managers), "cancellationCount": len(cancellations), "yearCancellationDetailChecked": source.get("yearCancelDetailChecked"), "yearCancellationDetailTotal": source.get("yearCancelDetailTotalInWindow"), "limitHit": limited},
        "products": sorted(products, key=lambda item: (item["filingDate"], item["fundNo"])),
        "newManagers": sorted(managers, key=lambda item: (item["registerDate"], item["registerNo"] or "")),
        "cancellations": sorted(cancellations, key=lambda item: (item["cancelDate"], item["managerName"])),
    }
    output_path = ROOT / "data/backfill/private-fund/normalized-2026.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    merge_coverage({**output["coverage"], "sourceReportDate": source.get("reportDate"), "errors": []}, start, end)
    print(json.dumps(output["coverage"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
