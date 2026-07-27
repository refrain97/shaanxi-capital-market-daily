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
    {"code": "002185.SZ", "name": "华天科技", "relationType": "operating_base", "reason": "西安核心生产基地及总部管理子公司"},
    {"code": "600089.SH", "name": "特变电工", "relationType": "operating_base", "reason": "西安重资产制造与研发项目"},
    {"code": "600212.SH", "name": "绿能慧充", "relationType": "operating_base", "reason": "西安全资子公司及研发制造基地"},
    {"code": "600184.SH", "name": "光电股份", "relationType": "headquarters_office", "reason": "总部及主要办公地址在西安"},
    {"code": "002140.SZ", "name": "东华科技", "relationType": "strategic_shareholding", "reason": "陕煤集团为第二大股东并持股20.79%", "relatedHoldingPct": 20.79},
    {"code": "002246.SZ", "name": "北化股份", "relationType": "group_industry_affiliation", "reason": "西安惠安为同一控股集团产业主体并持股5.49%", "relatedHoldingPct": 5.49},
    {"code": "300527.SZ", "name": "ST应急", "relationType": "group_industry_affiliation", "reason": "西安705所为控股集团体系内主体并间接持股1.97%", "relatedHoldingPct": 1.97},
    {"code": "600879.SH", "name": "航天电子", "relationType": "group_industry_affiliation", "reason": "陕西导航与陕西苍松为同一控股集团产业主体，合计持股2.98%", "relatedHoldingPct": 2.98},
    {"code": "300110.SZ", "name": "华仁药业", "relationType": "controlling_shareholding", "reason": "西安曲江天授健康投资为第一大股东并持股20.00%", "relatedHoldingPct": 20.00},
    {"code": "000659.SZ", "name": "珠海中富", "relationType": "controlling_shareholding", "reason": "陕西新丝路进取一号为第一大股东并持股15.71%", "relatedHoldingPct": 15.71},
    {"code": "002022.SZ", "name": "科华生物", "relationType": "control_rights", "reason": "西安致同直接持股5.00%，叠加表决权委托后控制15.64%表决权并形成公司控制", "relatedHoldingPct": 5.00, "relatedVotingPct": 15.64},
]

EXCLUDED_L3 = [
    {"canonicalName": "比亚迪", "reason": "用户明确排除"},
    {"canonicalName": "海格通信", "reason": "用户明确排除"},
    {"canonicalName": "彤程新材", "reason": "陕西煤业仅财务持股2.95%，无陕西经营、控制或产业协同证据"},
    {"canonicalName": "北方铜业", "reason": "西安高科建材仅持股1.52%，未形成控制或实质经营联系"},
    {"canonicalName": "广誉远", "reason": "西安东盛当前持股仅0.90%，主要为历史关系"},
    {"canonicalName": "佳力奇", "reason": "西安基金载体合计持股约3.68%，属于财务投资"},
    {"canonicalName": "金天钛业", "reason": "陕西合伙基金持股2.15%，无经营、控制或治理证据"},
    {"canonicalName": "明阳电路", "reason": "仅自然人股东西安学习任职履历，不构成公司级实质关联"},
    {"canonicalName": "菲林格尔", "reason": "陕西信托产品为财务持股且不谋求控制，不能按持股比例自动纳入"},
]


def main() -> None:
    existing_by_code: dict[str, dict[str, Any]] = {}
    if OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        existing_by_code = {item["securityCode"]: item for item in existing.get("entities", [])}
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
        "cninfoQueryCode": item["code"],
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
        "cninfoOrgId": existing_by_code.get(code, {}).get("cninfoOrgId"),
        "cninfoQueryCode": existing_by_code.get(code, {}).get("cninfoQueryCode"),
    } for code, name, reason, address in L2]
    l3 = [{
        "entityId": f"listed-{item['code'].lower().replace('.', '-')}",
        "canonicalName": item["name"],
        "securityCode": item["code"],
        "market": item["code"].split(".")[-1],
        "universeTier": "L3",
        "relationType": item["relationType"],
        "relationStrength": "material",
        "monitoringPriority": "important",
        "inclusionReason": item["reason"],
        "relatedHoldingPct": item.get("relatedHoldingPct"),
        "relatedVotingPct": item.get("relatedVotingPct"),
        "sourceAsOf": "2026-07-22",
        "sourceType": "西安关联上市公司线索池+定期报告逐家复核",
        "cninfoOrgId": existing_by_code.get(item["code"], {}).get("cninfoOrgId"),
        "cninfoQueryCode": existing_by_code.get(item["code"], {}).get("cninfoQueryCode"),
    } for item in L3]
    entities = l1 + l2 + l3
    codes = [item["securityCode"] for item in entities]
    if len(codes) != len(set(codes)):
        raise ValueError("listed universe contains duplicate security codes across tiers")
    excluded_names = {item["canonicalName"] for item in EXCLUDED_L3}
    if any(item["canonicalName"] in excluded_names for item in l3):
        raise ValueError("excluded L3 company entered the universe")
    payload = {
        "schemaVersion": "0.1",
        "asOf": date.today().isoformat(),
        "counts": {"total": len(entities), "L1": len(l1), "L2": len(l2), "L3": len(l3)},
        "retrievalCoverage": {
            "cninfoCompanyCount": len(l1),
            "hkexCompanyCount": sum(bool(item.get("cninfoOrgId")) for item in l2),
            "l3CninfoCompanyCount": sum(bool(item.get("cninfoOrgId")) for item in l3),
            "resolvedSubjectCount": sum(bool(item.get("cninfoOrgId")) for item in entities),
            "note": f"{len(entities)}家观察主体已解析巨潮证券主数据标识；L1仍须随陕西证监局最新名录刷新，港股公告须以HKEX披露易作最终完整性复核。"
        },
        "inclusionRules": {
            "L1": "陕西证监局最新辖区上市公司名录且上市状态有效",
            "L2": "总部、主要办公地或主要经营管理主体明确在陕西，逐家回源",
            "L3": "陕西实质经营基地/总部，或陕西主体形成控制、重大持股、公司治理或同一控股集团产业关系；逐家人工准入",
            "automaticExclusions": ["仅低比例财务持股", "仅信托或基金产品持股", "仅自然人学习任职履历", "仅一般项目或销售关系"]
        },
        "excluded": EXCLUDED_L3,
        "entities": entities,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
