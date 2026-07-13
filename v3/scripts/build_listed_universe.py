#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
L1_PATH = PROJECT / "v1/陕西省上市公司日报v1/data/shaanxi-companies-cninfo-2026-03-31.json"
OUTPUT = ROOT / "data/listed/universe.json"

L2 = [
    ("0438.HK", "彩虹新能源", "陕西办公地", "陕西省咸阳市高新技术产业开发区星火大道3号C6"),
    ("2335.HK", "麦科医药-B", "陕西办公地", "陕西省西安市长安区协同创新港6号楼"),
    ("2418.HK", "德银天下", "陕西办公地", "陕西省西安市经济技术开发区泾渭新城西金路西段29号"),
    ("1354.HK", "经发物业", "陕西办公地", "陕西省西安市经济技术开发区凤城二路51号"),
    ("8227.HK", "海天天线", "陕西办公地", "陕西省西安市高新技术产业开发区硕士路25号"),
    ("2233.HK", "西部水泥", "陕西办公地", "陕西省西安市长安区航天基地神舟四路336号"),
    ("6162.HK", "天瑞汽车内饰", "陕西办公地", "陕西省西安市经济技术开发区泾渭新城渭华路北段6号"),
    ("1771.HK", "新丰泰集团", "陕西办公地", "陕西省西安市浐灞生态区北辰大道欧亚一路1555号"),
    ("8631.HK", "申港控股", "陕西办公地", "陕西省西安市灞桥区长乐东路华夏世纪广场A座2301室"),
    ("2367.HK", "巨子生物", "陕西办公地", "陕西省西安市长安区上林苑七路1855号"),
    ("0162.HK", "世纪金花", "主要业务在陕西", None),
    ("0620.HK", "大唐西市", "主要业务在陕西", None),
    ("0346.HK", "延长石油国际", "主要业务在陕西", None),
    ("0997.HK", "普汇中金国际", "主要业务在陕西", None),
]

L3 = [
    ("002185.SZ", "华天科技", "强", None),
    ("600089.SH", "特变电工", "强", None),
    ("600212.SH", "绿能慧充", "强", None),
    ("600184.SH", "光电股份", "强", None),
    ("002140.SZ", "东华科技", "强且持股大于10%", 20.79),
    ("002246.SZ", "北化股份", "强", None),
    ("603650.SH", "彤程新材", "强", None),
    ("300527.SZ", "ST应急", "强", None),
    ("600879.SH", "航天电子", "强", None),
    ("000737.SZ", "北方铜业", "强", None),
    ("600771.SH", "广誉远", "强", None),
    ("300110.SZ", "华仁药业", "强且持股大于10%", 20.00),
    ("000659.SZ", "珠海中富", "强且持股大于10%", 15.71),
    ("002022.SZ", "科华生物", "强", None),
    ("301586.SZ", "佳力奇", "强", None),
    ("688750.SH", "金天钛业", "强", None),
    ("300739.SZ", "明阳电路", "强", None),
    ("603226.SH", "菲林格尔", "持股大于10%", 14.00),
]


def main() -> None:
    l1_raw: list[dict[str, Any]] = json.loads(L1_PATH.read_text(encoding="utf-8"))
    l1 = [{
        "entityId": f"listed-{item['code']}-{item['market'].lower()}",
        "canonicalName": item["name"],
        "securityCode": f"{item['code']}.{item['market']}",
        "market": item["market"],
        "universeTier": "L1",
        "inclusionReason": "陕西辖区A股",
        "sourceAsOf": "2026-03-31",
        "cninfoOrgId": item["orgId"],
    } for item in l1_raw]
    l2 = [{
        "entityId": f"listed-{code.lower().replace('.', '-')}",
        "canonicalName": name,
        "securityCode": code,
        "market": "HK",
        "universeTier": "L2",
        "inclusionReason": reason,
        "officeAddress": address,
        "sourceAsOf": "2026-07-13",
        "sourceType": "Wind筛选+iFinD上市状态复核",
    } for code, name, reason, address in L2]
    l3 = [{
        "entityId": f"listed-{code.lower().replace('.', '-')}",
        "canonicalName": name,
        "securityCode": code,
        "market": code.split(".")[-1],
        "universeTier": "L3",
        "inclusionReason": reason,
        "relatedHoldingPct": holding,
        "sourceAsOf": "2026-06-16",
        "sourceType": "西安关联上市公司线索池",
    } for code, name, reason, holding in L3]
    entities = l1 + l2 + l3
    codes = [item["securityCode"] for item in entities]
    if len(codes) != len(set(codes)):
        raise ValueError("listed universe contains duplicate security codes across tiers")
    if any(item["canonicalName"] in {"比亚迪", "海格通信"} for item in l3):
        raise ValueError("excluded L3 company entered the universe")
    payload = {
        "schemaVersion": "0.1",
        "asOf": date.today().isoformat(),
        "counts": {"total": len(entities), "L1": len(l1), "L2": len(l2), "L3": len(l3)},
        "retrievalCoverage": {
            "cninfoCompanyCount": len(l1),
            "hkexCompanyCount": 0,
            "l3CninfoCompanyCount": 0,
            "note": "当前CNINFO日抓取仍只覆盖L1；L2和L3已进入跟踪池但尚未接入日公告适配器。"
        },
        "excluded": [
            {"canonicalName": "比亚迪", "reason": "用户明确排除"},
            {"canonicalName": "海格通信", "reason": "用户明确排除"}
        ],
        "entities": entities,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
