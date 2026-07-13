#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Asia/Shanghai")


def load(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def run_step(name: str, command: list[str]) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    result = subprocess.run(command, cwd=ROOT.parent, text=True, capture_output=True)
    finished = datetime.now(timezone.utc)
    return {
        "name": name,
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "startedAt": started.isoformat(),
        "finishedAt": finished.isoformat(),
        "durationSeconds": round((finished - started).total_seconds(), 3),
        "command": command,
        "outputTail": (result.stdout + result.stderr)[-3000:],
    }


def as_date(value: str) -> datetime.date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(TZ).date()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the V3 morning or closing validation pipeline without rewriting source dates.")
    parser.add_argument("--slot", choices=("morning", "midday", "closing"), required=True)
    args = parser.parse_args()
    now = datetime.now(TZ)
    run_id = f"v3-{now:%Y%m%d-%H%M%S}-{args.slot}"
    lock_path = ROOT / "data/runs/.run.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print("another V3 run is active", file=sys.stderr)
        return 2

    try:
        os.write(lock_fd, run_id.encode("ascii"))
        os.close(lock_fd)
        python = str(ROOT.parent / ".venv/bin/python")
        steps = [
            run_step("build_listed_universe", [python, "v3/scripts/build_listed_universe.py"]),
            run_step("build_phase5", [python, "v3/scripts/build_phase5_data.py"]),
            run_step("build_phase6", [python, "v3/scripts/build_phase6_data.py"]),
            run_step("build_event_store", [python, "v3/scripts/build_event_store.py"]),
            run_step("validate_event_store", [python, "v3/scripts/validate_event_store.py"]),
            run_step("validate_dashboard", ["node", "v3/scripts/validate_data.mjs"]),
            run_step("validate_listed_business_taxonomy", ["node", "v3/scripts/validate_listed_business_taxonomy.mjs"]),
            run_step("validate_listed_universe", ["node", "v3/scripts/validate_listed_universe.mjs"]),
            run_step("validate_tender_runtime", ["node", "v3/scripts/validate_tender_runtime.mjs"]),
            run_step("validate_tender_classifier", ["node", "v3/scripts/validate_tender_classifier.mjs"]),
            run_step("validate_private_fund", ["node", "v3/scripts/validate_private_fund.mjs"]),
            run_step("validate_phase5", ["node", "v3/scripts/validate_phase5.mjs"]),
            run_step("validate_phase6", ["node", "v3/scripts/validate_phase6.mjs"]),
        ]
        inputs = {
            "dashboard": load("data/sample/dashboard-2026-07-10.json")["meta"]["asOf"],
            "privateFund": load("data/private-fund/snapshots/latest.json")["sourceReportDate"],
            "maProjects": load("data/ma-projects/latest.json")["asOf"],
            "preIpo": load("data/pre-ipo/latest.json")["asOf"],
            "tenderRuntime": load("data/tender/scans/latest.json")["generatedAt"],
        }
        input_health = [{"dataset": name, "dataAsOf": value, "status": "CURRENT" if as_date(value) == now.date() else "STALE", "ageDays": (now.date() - as_date(value)).days} for name, value in inputs.items()]
        failed = [step["name"] for step in steps if step["status"] != "PASS"]
        stale = [item["dataset"] for item in input_health if item["status"] == "STALE"]
        quality = "FAIL" if failed else "PASS_WITH_STALE_INPUT" if stale else "PASS"
        record = {
            "schemaVersion": "0.1",
            "runId": run_id,
            "slot": args.slot,
            "runMode": "parallel_prototype",
            "startedAt": steps[0]["startedAt"],
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "qualityResult": quality,
            "failedSteps": failed,
            "staleDatasets": stale,
            "inputHealth": input_health,
            "steps": steps,
            "note": "运行时点不覆盖数据时点；STALE输入保持可见，V1生产未被修改。",
        }
        run_path = ROOT / f"data/runs/{run_id}.json"
        latest_path = ROOT / f"data/runs/latest-{args.slot}.json"
        content = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        run_path.write_text(content, encoding="utf-8")
        latest_path.write_text(content, encoding="utf-8")
        print(json.dumps({"runId": run_id, "qualityResult": quality, "failedSteps": failed, "staleDatasets": stale}, ensure_ascii=False, indent=2))
        return 1 if failed else 0
    finally:
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
