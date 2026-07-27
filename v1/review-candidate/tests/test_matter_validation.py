#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "validate_v1_outputs.py"
spec = importlib.util.spec_from_file_location("v1_validator", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


def main() -> int:
    west = "中国西电下属14家子公司中标国家电网项目41.2893亿元"
    assert module.matter_topics(west) == {"contract"}
    duplicate_west = [
        {"section": "02", "matter_id": "explicit:cninfo-123", "label": "中国西电", "text": west},
        {"section": "03", "matter_id": "explicit:cninfo-123", "label": "中国西电", "text": west},
    ]
    try:
        module.validate_matter_records(duplicate_west)
    except ValueError:
        pass
    else:
        raise AssertionError("same China XD matter_id across two narrative homes must fail")

    allowed_west = duplicate_west[:1] + [
        {"section": "04", "matter_id": "explicit:cninfo-123", "label": "中国西电", "text": "41.2893亿元"},
        {"section": "06", "matter_id": "explicit:cninfo-123", "label": "中国西电", "text": "跟踪合同与回款"},
    ]
    assert module.validate_matter_records(allowed_west) == []
    fallback_a = module.matter_identity({}, "中国西电", "国家电网项目中标", "2026-07-23 中标公告")
    fallback_b = module.matter_identity({}, "中国西电", "国家电网项目中标", "2026-07-23 中标公告")
    assert fallback_a == fallback_b and fallback_a.startswith("fallback:")

    kelong_merged = "科隆新材股东减持1,368,395股；闲置募集资金现金管理余额13,500万元"
    assert module.matter_topics(kelong_merged) == {"shareholder_change", "cash_management"}
    merged_diagnostics = module.validate_matter_records([
        {"section": "03", "matter_id": "explicit:kelong-merged", "label": "科隆新材", "text": kelong_merged}
    ])
    assert merged_diagnostics and "diagnostic only" in merged_diagnostics[0]

    kelong_share = "科隆新材股东减持1,368,395股，持股比例降至5%"
    kelong_cash = "科隆新材闲置资金现金管理未到期余额13,500万元"
    assert module.matter_topics(kelong_share) == {"shareholder_change"}
    assert module.matter_topics(kelong_cash) == {"cash_management"}
    assert module.validate_matter_records([
        {"section": "02", "matter_id": "explicit:kelong-share", "label": "科隆新材", "text": kelong_share},
        {"section": "03", "matter_id": "explicit:kelong-cash", "label": "科隆新材", "text": kelong_cash},
    ]) == []
    print("matter validation regression: PASS (China XD dedup; Kelong split)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
