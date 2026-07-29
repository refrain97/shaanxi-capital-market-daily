#!/usr/bin/env python3
"""Shared loader for the V2-owned listed-company observation universe."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
SOURCE_CONTRACT_PATH = REPO_ROOT / "v2" / "config" / "source-contract.json"


def _contract_path(key: str) -> Path:
    contract = json.loads(SOURCE_CONTRACT_PATH.read_text(encoding="utf-8"))
    return REPO_ROOT / str(contract[key])


V2_UNIVERSE_PATH = _contract_path("listedUniverse")


def _normalized_entity(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": str(entity.get("cninfoQueryCode") or "").strip(),
        "name": str(entity.get("canonicalName") or "").strip(),
        "orgId": str(entity.get("cninfoOrgId") or "").strip(),
        "market": str(entity.get("market") or "").strip(),
        "universeTier": str(entity.get("universeTier") or "").strip(),
        "inclusionReason": str(entity.get("inclusionReason") or "").strip(),
        "securityCode": str(entity.get("securityCode") or "").strip(),
        "entityId": str(entity.get("entityId") or "").strip(),
        "sourceAsOf": str(entity.get("sourceAsOf") or "").strip(),
    }


def _normalized_legacy_entity(entity: dict[str, Any]) -> dict[str, Any]:
    row = dict(entity)
    row.setdefault("universeTier", "L1")
    row.setdefault("inclusionReason", "陕西辖区A股")
    row.setdefault("securityCode", f"{row.get('code', '')}.{row.get('market', '')}")
    row.setdefault("entityId", "")
    row.setdefault("sourceAsOf", "2026-03-31")
    return row


def load_listed_universe(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the V2 universe object or a compatible legacy list for import tooling."""
    source = path or V2_UNIVERSE_PATH
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("entities"), list):
        rows = [_normalized_entity(row) for row in payload["entities"] if isinstance(row, dict)]
    elif isinstance(payload, list):
        rows = [_normalized_legacy_entity(row) for row in payload if isinstance(row, dict)]
    else:
        raise ValueError(f"unsupported listed-company universe format: {source}")

    required = ("code", "name", "orgId", "market", "universeTier")
    for index, row in enumerate(rows):
        missing = [key for key in required if not str(row.get(key) or "").strip()]
        if missing:
            raise ValueError(f"company #{index} missing fields {missing}: {row}")

    entity_keys = [(row["market"], row["code"]) for row in rows]
    if len(entity_keys) != len(set(entity_keys)):
        raise ValueError(f"duplicate market/code entries in listed-company universe: {source}")
    return rows


def universe_counts(rows: list[dict[str, Any]] | None = None) -> dict[str, int]:
    entities = rows if rows is not None else load_listed_universe()
    tiers = Counter(str(row.get("universeTier") or "") for row in entities)
    markets = Counter(str(row.get("market") or "") for row in entities)
    return {
        "total": len(entities),
        "L1": tiers["L1"],
        "L2": tiers["L2"],
        "L3": tiers["L3"],
        "SH": markets["SH"],
        "SZ": markets["SZ"],
        "BJ": markets["BJ"],
        "HK": markets["HK"],
    }
