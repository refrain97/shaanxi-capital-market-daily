#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOE_ROOT = ROOT.parent / "soe-radar"


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", value))).strip(" ·")


def main() -> int:
    records: dict[str, dict] = {}
    input_files = sorted(SOE_ROOT.glob("2026-*.html"))
    section_pattern = re.compile(r"<section class='column'>.*?<h2>(.*?)</h2>.*?<ol>(.*?)</ol></section>", re.S)
    item_pattern = re.compile(
        r"<li><div class='meta'><span>(20\d{2}-\d{2}-\d{2})</span><span>(.*?)</span></div>"
        r"<a href='([^']+)'>(.*?)</a><div class='source'>来源：(.*?)</div></li>", re.S
    )
    for file in input_files:
        text = file.read_text(encoding="utf-8")
        for category_raw, body in section_pattern.findall(text):
            category = clean(category_raw)
            for published_at, entity_raw, url_raw, title_raw, source_raw in item_pattern.findall(body):
                url = html.unescape(url_raw)
                record_id = hashlib.sha256(url.encode()).hexdigest()[:20]
                records[record_id] = {
                    "candidateId": f"soe-backfill-{record_id}",
                    "publishedAt": published_at,
                    "entities": [item.strip() for item in clean(entity_raw).split("；") if item.strip()],
                    "title": clean(title_raw),
                    "category": category,
                    "sourceName": clean(source_raw),
                    "sourceUrl": url,
                    "sourceQuality": "official_or_group_site",
                    "noveltyStatus": "backfill",
                    "normalizationStatus": "existing_output_source_link_preserved",
                }
    items = sorted(records.values(), key=lambda item: (item["publishedAt"], item["title"]))
    output = {
        "schemaVersion": "0.1",
        "channel": "soe",
        "novelty": "backfill",
        "period": {"startDate": "2026-01-01", "endDate": datetime.now(timezone.utc).date().isoformat()},
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "PARTIAL_EXISTING_OUTPUTS_NO_JAN_JUN_ARCHIVE",
        "limits": ["现有国企网页只保留7月5日起的发布文件，无法据此声明1月至6月全量", "当前回收的是页面中仍保留且带来源链接的事项，后续需按国资委及集团官网重扫"],
        "summary": {
            "inputFileCount": len(input_files),
            "recordCount": len(items),
            "earliestPublishedAt": items[0]["publishedAt"] if items else None,
            "latestPublishedAt": items[-1]["publishedAt"] if items else None,
            "entityCount": len({entity for item in items for entity in item["entities"]}),
        },
        "records": items,
    }
    target = ROOT / "data/backfill/soe/normalized-2026.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
