#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the V3 persistent event store.")
    parser.add_argument("--db", default=str(ROOT / "data/runtime/event-store.sqlite3"))
    args = parser.parse_args()
    connection = sqlite3.connect(Path(args.db))
    errors: list[str] = []
    try:
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            errors.append(f"foreign key violations: {len(foreign_keys)}")
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("raw_snapshots", "entities", "sources", "events", "event_versions", "event_timeline")}
        if counts["raw_snapshots"] < 5:
            errors.append("all five source datasets must have immutable snapshots")
        if counts["events"] < 100:
            errors.append("event migration is unexpectedly incomplete")
        missing_versions = connection.execute("SELECT COUNT(*) FROM events e LEFT JOIN event_versions v ON v.event_id=e.event_id WHERE v.event_id IS NULL").fetchone()[0]
        if missing_versions:
            errors.append(f"events without versions: {missing_versions}")
        duplicate_keys = connection.execute("SELECT COUNT(*) FROM (SELECT event_key FROM events GROUP BY event_key HAVING COUNT(*) > 1)").fetchone()[0]
        if duplicate_keys:
            errors.append(f"duplicate event keys: {duplicate_keys}")
        required_channels = {"listed", "ma", "pre_ipo", "private_fund", "tender"}
        channels = {row[0] for row in connection.execute("SELECT DISTINCT channel FROM events")}
        missing_channels = required_channels - channels
        if missing_channels:
            errors.append(f"missing channels: {sorted(missing_channels)}")
        result = {"status": "FAIL" if errors else "PASS", "counts": counts, "channels": sorted(channels), "errors": errors}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
