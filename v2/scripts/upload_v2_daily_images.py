#!/usr/bin/env python3
"""Non-blocking IMA delivery and retry queue for V2 daily image editions."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "v2"
INDEX_PATH = V2 / "data" / "daily-image-archive.json"
RELEASES = V2 / "data" / "releases"
STAGING = V2 / ".runtime" / "daily-images"
TZ = ZoneInfo("Asia/Shanghai")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def record_path(day: str, channel: str) -> Path:
    return RELEASES / day / "ima" / f"{channel}.json"


def entry_file(entry: dict[str, Any]) -> Path:
    return STAGING / str(entry["date"]) / str(entry["channel"]) / str(entry["date"])[:4] / str(entry["fileName"])


def prune_empty(path: Path) -> None:
    while path != STAGING and path.exists():
        try:
            path.rmdir()
        except OSError:
            return
        path = path.parent


def purge_day_staging(day: str) -> None:
    """Keep retry state in frozen data, never in a persistent PNG cache."""
    try:
        if datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d") != day:
            raise ValueError
    except ValueError as error:
        raise ValueError(f"非法日图暂存日期：{day}") from error
    target = STAGING / day
    if target.is_dir():
        shutil.rmtree(target)


def restore(day: str) -> None:
    result = subprocess.run(
        [sys.executable, str(V2 / "scripts" / "daily_artifacts.py"), "restore", "--date", day],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode:
        raise RuntimeError(result.stdout.strip()[-500:])


def set_release_status(day: str, states: list[str]) -> None:
    path = RELEASES / day / "morning-release.json"
    if not path.is_file():
        return
    release = load(path)
    index = load(INDEX_PATH)
    by_channel = {entry.get("channel"): entry for rows in index.get("channels", {}).values() for entry in rows if entry.get("date") == day}
    for image in release.get("imageFiles", []):
        entry = by_channel.get(image.get("channel"))
        if entry:
            image["ima"] = entry.get("ima", {})
            image["webStatus"] = entry.get("webStatus", image.get("webStatus"))
    release["imaStatus"] = "completed" if states and all(state == "completed" for state in states) else "pending_retry"
    release["imaUpdatedAt"] = now()
    write(path, release)


def main() -> int:
    parser = argparse.ArgumentParser(description="补传 V2 已发布日图至 IMA；失败不影响网页发布")
    parser.add_argument("--date", help="仅处理该日期；缺省时处理全部待补传 V2 日图")
    args = parser.parse_args()
    if not INDEX_PATH.is_file():
        print(json.dumps({"attempted": 0, "status": "no_index"}, ensure_ascii=False))
        return 0
    config = load(V2 / "config" / "ima.json")
    knowledge_base = os.environ.get("IMA_KNOWLEDGE_BASE_ID") or config.get("defaultKnowledgeBaseId")
    if config.get("status") != "active" or not knowledge_base:
        print(json.dumps({"attempted": 0, "status": "not_configured"}, ensure_ascii=False))
        return 0
    index = load(INDEX_PATH)
    candidates = [
        entry
        for rows in index.get("channels", {}).values()
        for entry in rows
        if entry.get("origin") == "v2"
        and entry.get("webStatus") == "published"
        and (not args.date or entry.get("date") == args.date)
        and entry.get("ima", {}).get("status") not in {"completed", "not_applicable", "needs_manual_duplicate_review"}
    ]
    candidates.sort(key=lambda item: (str(item.get("date")), str(item.get("channel"))))
    summary: dict[str, Any] = {"attempted": 0, "completed": 0, "pendingRetry": 0, "manualReview": 0, "results": []}
    date_states: dict[str, list[str]] = {}
    touched_days = ({str(args.date)} if args.date else set()) | {str(entry["date"]) for entry in candidates}
    for entry in candidates:
        summary["attempted"] += 1
        file_path = entry_file(entry)
        try:
            if not file_path.is_file():
                restore(str(entry["date"]))
            if not file_path.is_file():
                raise FileNotFoundError("冻结快照复原后仍找不到临时日图")
            completed = subprocess.run(
                [
                    "node", str(V2 / "scripts" / "upload_ima_v2_image.cjs"),
                    "--file", str(file_path), "--name", str(entry["fileName"]), "--kb", str(knowledge_base),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
                env={**os.environ, "TZ": "Asia/Shanghai"},
            )
            payload = json.loads((completed.stdout.strip().splitlines() or ["{}"])[-1])
            upload_status = str(payload.get("status") or "failed")
            record = {
                "date": entry["date"], "channel": entry["channel"], "fileName": entry["fileName"],
                "sha256": entry["sha256"], "status": upload_status,
                "verification": payload.get("verification", ""), "attemptedAt": now(),
            }
            if upload_status in {"completed", "already_exists"}:
                entry["ima"] = {"status": "completed", "uploadedAt": now(), "verification": payload.get("verification", "exact_file_name")}
                record["status"] = "completed"
                write(record_path(str(entry["date"]), str(entry["channel"])), record)
                summary["completed"] += 1
                date_states.setdefault(str(entry["date"]), []).append("completed")
            elif upload_status == "needs_manual_duplicate_review":
                entry["ima"] = {"status": "needs_manual_duplicate_review", "updatedAt": now()}
                write(record_path(str(entry["date"]), str(entry["channel"])), record)
                summary["manualReview"] += 1
                date_states.setdefault(str(entry["date"]), []).append("needs_manual_duplicate_review")
            else:
                entry["ima"] = {"status": "pending_retry", "lastError": str(payload.get("message") or payload.get("verification") or "IMA 未完成确认")[:300], "updatedAt": now()}
                write(record_path(str(entry["date"]), str(entry["channel"])), record)
                summary["pendingRetry"] += 1
                date_states.setdefault(str(entry["date"]), []).append("pending_retry")
            summary["results"].append({"date": entry["date"], "channel": entry["channel"], "status": entry["ima"]["status"]})
        except Exception as error:
            entry["ima"] = {"status": "pending_retry", "lastError": str(error)[:300], "updatedAt": now()}
            write(record_path(str(entry["date"]), str(entry["channel"])), {
                "date": entry["date"], "channel": entry["channel"], "fileName": entry["fileName"],
                "sha256": entry["sha256"], "status": "pending_retry", "attemptedAt": now(),
            })
            summary["pendingRetry"] += 1
            date_states.setdefault(str(entry["date"]), []).append("pending_retry")
            summary["results"].append({"date": entry["date"], "channel": entry["channel"], "status": "pending_retry"})
        finally:
            # Pending IMA delivery is reconstructible from the immutable
            # snapshot.  Do not turn a transient upload issue into a local
            # image library.
            file_path.unlink(missing_ok=True)
            prune_empty(file_path.parent)
    for day in touched_days:
        purge_day_staging(day)
    index["updatedAt"] = now()
    write(INDEX_PATH, index)
    for day in touched_days:
        states = [
            str(entry.get("ima", {}).get("status"))
            for rows in index.get("channels", {}).values()
            for entry in rows
            if entry.get("origin") == "v2" and entry.get("date") == day
        ]
        normalized = ["completed" if state == "completed" else "pending_retry" for state in states]
        set_release_status(day, normalized)
    print(json.dumps(summary, ensure_ascii=False))
    # Delivery is explicitly non-blocking. The caller reads the per-item status.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
