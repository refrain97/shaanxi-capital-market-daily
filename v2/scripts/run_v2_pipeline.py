#!/usr/bin/env python3
"""Deterministic, self-contained V2 production orchestrator.

V2 owns the whole production path: source acquisition, original-document
verification, five-channel scanning, frozen-data build, page publication, and
daily-image delivery.  It must never read a same-day V1 output.  Every formal
run writes a terminal manifest, including blocked runs, so that a missing or
degraded source cannot be mistaken for a completed scan.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "v2"
SCRIPTS = V2 / "scripts"
TZ = ZoneInfo("Asia/Shanghai")
CHANNELS = ("listed", "private", "ma", "tender", "soe")
CODE_DIRS = (V2 / "scripts", V2 / "config", V2 / "tests")
# A generic ``degraded`` source is blocking.  The sole exception is a tender
# receipt that explicitly proves its configured official equivalent coverage
# while naming a constrained supplemental source.  This lets an externally
# captcha-protected supplemental endpoint be transparent to customers without
# downgrading the formal source contract.
ACCEPTED = {"completed", "no_new"}
SLOT_STARTS = {"morning": "05:30", "midday": "12:00", "closing": "17:00"}


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hashes() -> dict[str, str]:
    result: dict[str, str] = {}
    for directory in CODE_DIRS:
        for path in sorted(directory.rglob("*")):
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix in {".py", ".sh", ".json", ".md", ".txt"}
            ):
                result[path.relative_to(ROOT).as_posix()] = sha256(path)
    return result


def command(
    args: list[str],
    *,
    timeout: int,
    log_path: Path,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env={
                **os.environ,
                "TZ": "Asia/Shanghai",
                "PYTHONDONTWRITEBYTECODE": "1",
                **(extra_env or {}),
            },
            check=False,
        )
        output, return_code = completed.stdout, completed.returncode
    except subprocess.TimeoutExpired as error:
        output = (error.stdout or "") + f"\nTIMEOUT after {timeout}s\n"
        return_code = 124
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")
    return {
        "command": args,
        "returnCode": return_code,
        "elapsedSeconds": round(time.monotonic() - started, 3),
        "log": log_path.relative_to(ROOT).as_posix(),
    }


def input_command(channel: str, day: str, slot: str) -> tuple[list[str], int]:
    """Return the V2-owned acquisition command for a prepared channel."""
    if channel == "listed":
        editorial_brief = V2 / f"data/daily/listed/editorial-brief-{day}.json"
        editorial_args = (
            ["--editorial-brief", str(editorial_brief)]
            if editorial_brief.is_file()
            else []
        )
        return (
            [
                sys.executable,
                str(SCRIPTS / "prepare_listed_daily.py"),
                "--date",
                day,
                "--slot",
                slot,
                *editorial_args,
            ],
            1_800,
        )
    if channel == "private":
        return (
            [
                sys.executable,
                str(SCRIPTS / "fetch_private_funds.py"),
                "--date",
                day,
            ],
            2_400,
        )
    if channel == "soe":
        return (
            [
                sys.executable,
                str(SCRIPTS / "collect_soe_evidence.py"),
                "--date",
                day,
                "--slot",
                slot,
            ],
            600,
        )
    raise ValueError(f"unknown input channel: {channel}")


class FailedRunRollback:
    """Keep a blocked acquisition from replacing the last trusted baseline."""

    def __init__(self, day: str, slot: str) -> None:
        self.day = day
        self.slot = slot
        self.temp = tempfile.TemporaryDirectory(prefix="v2-production-rollback-")
        self.backup_root = Path(self.temp.name)
        self.existing: set[Path] = set()
        self.roots = [
            V2 / "data/daily",
            V2 / "data/scans",
            V2 / "data/readiness",
        ]
        self.fixed = [
            V2 / "data/production-data.json",
            V2 / "data/build-version.json",
            V2 / "assets/data.js",
            V2 / f"data/source/events/unified-{day[:4]}.json",
        ]
        self._capture()

    def _eligible(self, path: Path) -> bool:
        if path in self.fixed:
            return True
        if not path.is_file():
            return False
        return self.day in path.name or f"{self.day}-{self.slot}" in path.name

    def _capture(self) -> None:
        candidates = list(self.fixed)
        for root in self.roots:
            if root.is_dir():
                candidates.extend(path for path in root.rglob("*") if path.is_file())
        for path in candidates:
            if not self._eligible(path) or not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            target = self.backup_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            self.existing.add(relative)

    def restore(self) -> dict[str, Any]:
        removed: list[str] = []
        restored: list[str] = []
        for root in self.roots:
            if not root.is_dir():
                continue
            for path in list(root.rglob("*")):
                if not path.is_file() or not self._eligible(path):
                    continue
                relative = path.relative_to(ROOT)
                if relative not in self.existing:
                    path.unlink()
                    removed.append(relative.as_posix())
        for relative in sorted(self.existing):
            source = self.backup_root / relative
            target = ROOT / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            restored.append(relative.as_posix())
        return {"status": "restored", "restored": restored, "removed": removed}

    def close(self) -> None:
        self.temp.cleanup()


def tender_constraint_release_eligible(receipt: dict[str, Any]) -> bool:
    """Accept only the explicit, official-equivalence tender downgrade."""
    eligibility = receipt.get("releaseEligibility") or {}
    return bool(
        receipt.get("status") == "degraded"
        and receipt.get("coverageComplete")
        and receipt.get("networkVerified")
        and eligibility.get("eligible") is True
        and eligibility.get("mode")
        == "official_equivalent_coverage_with_supplemental_source_constraint"
        and eligibility.get("constrainedSourceIds")
    )


def release_acceptable(channel: str, result: dict[str, Any]) -> bool:
    """Return whether a channel result may cross the customer release gate."""
    if result.get("status") in ACCEPTED:
        return True
    return channel == "tender" and result.get("status") == "degraded" and bool(
        result.get("releaseEligible")
    )


def record_channel(
    day: str,
    slot: str,
    channel: str,
    status: str,
    result: str,
    evidence: list[Path],
    *,
    release_eligible: bool = False,
) -> dict[str, Any]:
    args = [
        sys.executable,
        str(SCRIPTS / "record_channel_scan.py"),
        "--date",
        day,
        "--slot",
        slot,
        "--channel",
        channel,
        "--status",
        status,
        "--result",
        result,
    ]
    for path in evidence:
        args.extend(["--evidence", path.relative_to(ROOT).as_posix()])
    if release_eligible:
        args.append("--release-eligible")
    return command(
        args,
        timeout=30,
        log_path=V2 / "data/runs/logs" / f"{day}-{slot}-record-{channel}.log",
    )


def prepare_input(channel: str, day: str, slot: str, log_dir: Path) -> dict[str, Any]:
    """Run one V2 input acquisition and retain its log in the formal run."""
    args, timeout = input_command(channel, day, slot)
    result = command(
        args,
        timeout=timeout,
        log_path=log_dir / f"input-{channel}.log",
    )
    return {
        "channel": channel,
        "status": "completed" if result["returnCode"] == 0 else "failed",
        "result": f"{channel}_v2_owned_input_preparation",
        "run": result,
    }


def validate_prepared_channel(day: str, channel: str, channel_slot: str) -> tuple[str, str, list[Path]]:
    if channel == "listed":
        curated = V2 / f"data/daily/listed/listed-official-{day}.json"
        announcements = V2 / f"data/daily/listed/cninfo-announcements-{day}.json"
        hkex = V2 / f"data/daily/listed/hkex-review-{day}.json"
        missing = [path for path in (curated, announcements, hkex) if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                "上市公司栏目缺少同日正式输入：" + ", ".join(
                    path.relative_to(ROOT).as_posix() for path in missing
                )
            )
        raw = load(announcements)
        summary = raw.get("_summary", {})
        if summary.get("errorCount"):
            raise ValueError(f"上市公司逐主体扫描存在 {summary['errorCount']} 个错误")
        if summary.get("companyUniverseCount") != 110:
            raise ValueError("上市公司扫描未覆盖110家正式观察池")
        curated_payload = load(curated)
        if curated_payload.get("date") != day:
            raise ValueError("上市公司 curated 输入日期不匹配")
        hkex_payload = load(hkex)
        if hkex_payload.get("date") != day:
            raise ValueError("港股 L2 复核日期不匹配")
        if hkex_payload.get("slot") != channel_slot:
            raise ValueError("港股 L2 复核时点不匹配")
        if hkex_payload.get("status") not in {"completed", "no_new"}:
            raise ValueError("港股L2复核未完成")
        if int(hkex_payload.get("companyCount") or 0) != 14:
            raise ValueError("港股 L2 复核未覆盖14家正式观察对象")
        count = int(summary.get("announcementCount") or 0)
        return (
            "completed" if count else "no_new",
            f"listed_primary_verified_{count}_announcements",
            [curated, announcements, hkex],
        )

    daily = V2 / f"data/daily/private/security-private-fund-daily-{day}.json"
    annual = V2 / "data/source/private/products-2026.json"
    universe = V2 / "data/source/private/universe.json"
    missing = [path for path in (daily, annual, universe) if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "私募栏目缺少同日正式输入：" + ", ".join(
                path.relative_to(ROOT).as_posix() for path in missing
            )
        )
    payload = load(daily)
    if payload.get("reportDate") != day:
        raise ValueError("私募日报日期不匹配")
    manager_count = int(payload.get("observationManagerCount") or 0)
    if manager_count != 92:
        raise ValueError(f"私募观察池数量异常：{manager_count}，期望92")
    new_count = sum(
        str(row.get("putOnRecordDate") or row.get("filingDate") or "").startswith(day)
        for row in payload.get("shaanxiOfficeProducts", [])
    )
    return (
        "completed" if new_count else "no_new",
        f"private_daily_verified_observation_pool_92_new_products_{new_count}",
        [daily, annual, universe],
    )


def scan_command(channel: str, day: str, slot: str) -> tuple[list[str], int]:
    if channel == "ma":
        return (
            [
                sys.executable,
                str(SCRIPTS / "refresh_ma_events.py"),
                "--date",
                day,
                "--slot",
                slot,
                "--verify-network",
            ],
            1_200,
        )
    if channel == "tender":
        return (
            [
                sys.executable,
                str(SCRIPTS / "refresh_tender_events.py"),
                "--date",
                day,
                "--slot",
                slot,
                "--timeout",
                "20",
            ],
            900,
        )
    return (
        [
            sys.executable,
            str(SCRIPTS / "refresh_soe_events.py"),
            "--date",
            day,
            "--slot",
            slot,
            "--verify-network",
        ],
        600,
    )


def receipt_path(channel: str, day: str, slot: str) -> Path:
    return V2 / f"data/source/{channel}/scans/scan-{day}-{slot}.json"


def reusable_receipt(channel: str, day: str, slot: str) -> dict[str, Any] | None:
    path = receipt_path(channel, day, slot)
    if not path.is_file():
        return None
    receipt = load(path)
    if (
        receipt.get("scanAsOf") != day
        or receipt.get("slot") != slot
        or receipt.get("status") not in {"completed", "degraded"}
        or not receipt.get("networkVerified")
    ):
        return None
    if channel in {"ma", "tender"}:
        if not receipt.get("coverageComplete"):
            return None
        scanner = SCRIPTS / f"refresh_{channel}_events.py"
        config = V2 / f"config/{channel}-sources.json"
        if (
            receipt.get("scannerSha256") != sha256(scanner)
            or receipt.get("configSha256") != sha256(config)
        ):
            return None
        for relative, expected in receipt.get("artifactHashes", {}).items():
            artifact = ROOT / relative
            if not artifact.is_file() or sha256(artifact) != expected:
                return None
    elif receipt.get("evidencePath"):
        evidence = ROOT / receipt["evidencePath"]
        if not evidence.is_file() or sha256(evidence) != receipt.get("evidenceSha256"):
            return None
    return receipt


def run_scanner(channel: str, day: str, slot: str, log_dir: Path) -> dict[str, Any]:
    cached = reusable_receipt(channel, day, slot)
    if cached is not None:
        status = (
            "degraded"
            if cached["status"] == "degraded"
            else "completed"
            if cached.get("eventOnScanDate")
            else "no_new"
        )
        path = receipt_path(channel, day, slot)
        return {
            "channel": channel,
            "status": status,
            "releaseEligible": tender_constraint_release_eligible(cached)
            if channel == "tender"
            else False,
            "result": f"{channel}_{cached['status']}_reused_verified_receipt",
            "receipt": path.relative_to(ROOT).as_posix(),
            "failureReasons": cached.get("failureReasons", []),
            "runs": [
                {
                    "command": ["reuse-verified-receipt", channel],
                    "returnCode": 0,
                    "elapsedSeconds": 0.0,
                    "log": "",
                }
            ],
        }
    args, timeout = scan_command(channel, day, slot)
    # Full re-runs are idempotent.  They protect the daily release from the
    # transient TLS/connection resets observed on the official property and
    # government platforms, while preserving a hard block after all retries.
    attempts = {"ma": 3, "tender": 2, "soe": 2}.get(channel, 1)
    runs = []
    for attempt in range(1, attempts + 1):
        run = command(
            args,
            timeout=timeout,
            log_path=log_dir / f"{channel}-attempt-{attempt}.log",
        )
        runs.append(run)
        path = receipt_path(channel, day, slot)
        receipt = load(path) if path.is_file() else {}
        coverage_ok = (
            bool(receipt.get("coverageComplete"))
            if channel in {"ma", "tender"}
            else bool(receipt.get("networkVerified"))
        )
        if (
            run["returnCode"] == 0
            and receipt.get("status") in {"completed", "degraded"}
            and coverage_ok
        ):
            break
        if attempt < attempts:
            time.sleep(min(3 * attempt, 6))
    path = receipt_path(channel, day, slot)
    receipt = load(path) if path.is_file() else {}
    coverage_ok = (
        bool(receipt.get("coverageComplete"))
        if channel in {"ma", "tender"}
        else bool(receipt.get("networkVerified"))
    )
    accepted = (
        receipt.get("scanAsOf") == day
        and receipt.get("slot") == slot
        and receipt.get("status") in {"completed", "degraded"}
        and coverage_ok
    )
    if not accepted:
        return {
            "channel": channel,
            "status": "failed",
            "result": "; ".join(receipt.get("failureReasons", []))
            or f"{channel}_scanner_failed",
            "receipt": path.relative_to(ROOT).as_posix() if path.is_file() else "",
            "runs": runs,
        }
    status = (
        "degraded"
        if receipt["status"] == "degraded"
        else "completed"
        if receipt.get("eventOnScanDate")
        else "no_new"
    )
    return {
        "channel": channel,
        "status": status,
        "releaseEligible": tender_constraint_release_eligible(receipt)
        if channel == "tender"
        else False,
        "result": (
            f"{channel}_{receipt['status']}_event_on_scan_date_"
            f"{str(bool(receipt.get('eventOnScanDate'))).lower()}"
        ),
        "receipt": path.relative_to(ROOT).as_posix(),
        "failureReasons": receipt.get("failureReasons", []),
        "runs": runs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="运行陕西资本市场日报V2唯一生产流水线")
    parser.add_argument("--date", default=datetime.now(TZ).date().isoformat())
    parser.add_argument("--slot", choices=("morning", "midday", "closing"), default="morning")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument(
        "--expected-start",
        help="计划时点 HH:MM；缺省按 morning/midday/closing 的正式时点判断",
    )
    parser.add_argument(
        "--max-start-lag-minutes",
        type=int,
        default=60,
        help="超过该时长的正式启动必须失败关闭，避免迟到运行伪装成定时早报",
    )
    parser.add_argument(
        "--run-kind",
        choices=("production", "diagnostic"),
        default="production",
        help="production 会更新正式运行清单；diagnostic 只写独立诊断清单。",
    )
    parser.add_argument(
        "--recovery-of",
        help=(
            "仅用于同日、同时点已阻断正式任务的完整补偿。"
            "补偿任务重新采集全部V2来源，清单明确保留原失败任务，不伪装为准点运行。"
        ),
    )
    parser.add_argument(
        "--skip-input-preparation",
        action="store_true",
        help="仅用于离线夹具/诊断；正式生产不得跳过V2原始来源采集",
    )
    parser.add_argument("--skip-channel-scans", action="store_true", help="仅用于离线门禁测试")
    parser.add_argument("--skip-tests", action="store_true", help="仅用于快速诊断")
    args = parser.parse_args()
    day = date.fromisoformat(args.date).isoformat()
    actual_started_at = datetime.now(TZ)
    recovery: dict[str, Any] | None = None
    if args.recovery_of:
        recovery_path = V2 / "data/runs" / f"run-{args.recovery_of}.json"
        if not recovery_path.is_file():
            raise SystemExit(f"找不到待补偿的正式运行清单：{args.recovery_of}")
        recovery_source = load(recovery_path)
        if args.run_kind != "production":
            raise SystemExit("补偿仅允许作为正式生产运行")
        if (
            recovery_source.get("status") != "blocked"
            or recovery_source.get("runKind") != "production"
            or recovery_source.get("date") != day
            or recovery_source.get("slot") != args.slot
        ):
            raise SystemExit("补偿目标必须是同日、同时点且已阻断的正式运行")
        recovery = {
            "ofRunId": args.recovery_of,
            "reason": "同日正式任务在数据冻结/发布前阻断后的完整补偿",
            "originalScheduledAt": recovery_source.get("scheduledAt", ""),
            "originalFailure": (recovery_source.get("sourceFailures") or [""])[-1],
        }
    # A recovery is a formally linked compensation, not a late attempt to
    # impersonate the original scheduled run.  Keep the original schedule in
    # ``recovery.originalScheduledAt`` while measuring this run from its actual
    # compensation start, even when the shell wrapper supplied 12:00/17:00.
    expected_start = (
        actual_started_at.strftime("%H:%M")
        if recovery
        else args.expected_start or SLOT_STARTS[args.slot]
    )
    try:
        scheduled_at = datetime.strptime(
            f"{day} {expected_start}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=TZ)
    except ValueError as error:
        raise SystemExit(f"无效 --expected-start：{expected_start}（应为 HH:MM）") from error
    start_lag_minutes = round(
        max(0.0, (actual_started_at - scheduled_at).total_seconds() / 60), 2
    )
    run_id = f"{day}-{args.slot}-{datetime.now(TZ).strftime('%H%M%S')}"
    run_path = V2 / f"data/runs/run-{run_id}.json"
    log_dir = V2 / "data/runs/logs" / run_id
    started = now()
    initial_hashes = code_hashes()
    stages: list[dict[str, Any]] = []
    channel_results: dict[str, dict[str, Any]] = {}
    status = "blocked"
    published_version = ""
    artifact_stage = ""
    online_verification: dict[str, Any] = {}
    delivery: dict[str, Any] = {"web": "not_started", "dailyImages": "not_created", "ima": "not_started"}
    source_failures: list[str] = []
    source_constraints: list[dict[str, Any]] = []

    manifest: dict[str, Any] = {
        "schemaVersion": "1.0",
        "runId": run_id,
        "runKind": args.run_kind,
        "date": day,
        "slot": args.slot,
        "status": "in_progress",
        "scheduledAt": scheduled_at.isoformat(timespec="seconds"),
        "actualStartedAt": actual_started_at.isoformat(timespec="seconds"),
        "startLagMinutes": start_lag_minutes,
        "maxStartLagMinutes": args.max_start_lag_minutes,
        "startedAt": started,
        "finishedAt": "",
        "stageTimings": stages,
        "channelReadiness": channel_results,
        "sourceFailures": source_failures,
        "sourceConstraints": source_constraints,
        "dataHashes": {},
        "publishedBuildVersion": "",
        "onlineVerification": online_verification,
        "delivery": delivery,
        "recovery": recovery,
        "inputPreparation": {},
        "qualityContract": {},
        "failedRunRollback": {"status": "armed"},
    }
    write(run_path, manifest)
    rollback = FailedRunRollback(day, args.slot)
    try:
        if args.run_kind == "production" and start_lag_minutes > args.max_start_lag_minutes:
            raise RuntimeError(
                f"正式运行启动滞后{start_lag_minutes}分钟，超过"
                f"{args.max_start_lag_minutes}分钟上限；不得以{args.slot}时点发布"
            )
        preflight_started = time.monotonic()
        if sys.version_info < (3, 11):
            raise RuntimeError("V2生产环境要求 Python 3.11+")
        required = [
            V2 / "config/source-contract.json",
            V2 / "config/production-quality-contract.json",
            SCRIPTS / "build_daily_v2.py",
            SCRIPTS / "validate_v2.py",
            SCRIPTS / "prepare_listed_daily.py",
            SCRIPTS / "fetch_private_funds.py",
            SCRIPTS / "collect_soe_evidence.py",
        ]
        missing = [path for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("生产脚本不完整：" + ",".join(map(str, missing)))
        stages.append(
            {
                "stage": "preflight",
                "status": "completed",
                "elapsedSeconds": round(time.monotonic() - preflight_started, 3),
            }
        )

        quality_contract = V2 / "config/production-quality-contract.json"
        manifest["qualityContract"] = {
            "path": quality_contract.relative_to(ROOT).as_posix(),
            "sha256": sha256(quality_contract),
            "owner": load(quality_contract).get("owner"),
            "standard": load(quality_contract).get("standard"),
        }

        if args.skip_input_preparation and args.run_kind == "production":
            raise RuntimeError("正式生产不得跳过V2原始来源采集")
        if not args.skip_input_preparation:
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {
                    pool.submit(prepare_input, channel, day, args.slot, log_dir): channel
                    for channel in ("listed", "private", "soe")
                }
                for future in as_completed(futures):
                    prepared = future.result()
                    channel = prepared["channel"]
                    manifest["inputPreparation"][channel] = prepared
                    stages.append(
                        {
                            "stage": f"acquire_{channel}",
                            "status": prepared["status"],
                            **prepared["run"],
                        }
                    )
                    if prepared["status"] != "completed":
                        raise RuntimeError(
                            f"{channel} V2原始来源采集失败，详见{prepared['run']['log']}"
                        )
        else:
            manifest["inputPreparation"] = {
                "mode": "fixture_or_diagnostic_skip",
                "reason": "not_allowed_for_production",
            }

        for channel in ("listed", "private"):
            prepared_started = time.monotonic()
            prepared_status, result, evidence = validate_prepared_channel(day, channel, args.slot)
            record = record_channel(
                day, args.slot, channel, prepared_status, result, evidence
            )
            if record["returnCode"] != 0:
                raise RuntimeError(f"{channel}栏目状态登记失败")
            channel_results[channel] = {
                "status": prepared_status,
                "result": result,
                "evidence": [path.relative_to(ROOT).as_posix() for path in evidence],
            }
            stages.append(
                {
                    "stage": f"prepare_{channel}",
                    "status": "completed",
                    "elapsedSeconds": round(time.monotonic() - prepared_started, 3),
                }
            )

        if not args.skip_channel_scans:
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {
                    pool.submit(run_scanner, channel, day, args.slot, log_dir): channel
                    for channel in ("ma", "tender", "soe")
                }
                for future in as_completed(futures):
                    result = future.result()
                    channel = result["channel"]
                    channel_results[channel] = result
                    record_channel(
                        day,
                        args.slot,
                        channel,
                        result["status"],
                        result["result"],
                        [ROOT / result["receipt"]] if result.get("receipt") else [],
                        release_eligible=bool(result.get("releaseEligible")),
                    )
                    stages.append(
                        {
                            "stage": f"scan_{channel}",
                            "status": result["status"],
                            "elapsedSeconds": round(
                                sum(row["elapsedSeconds"] for row in result["runs"]), 3
                            ),
                        }
                    )
                    if result["status"] == "failed":
                        source_failures.append(f"{channel}:{result['result']}")
                    elif result["status"] == "degraded":
                        if release_acceptable(channel, result):
                            source_constraints.append(
                                {
                                    "channel": channel,
                                    "customerLabel": "已完成扫描，来源受限",
                                    "reasons": result.get("failureReasons", []),
                                }
                            )
                        else:
                            source_failures.extend(
                                f"{channel}:{reason}"
                                for reason in result.get("failureReasons", [])
                            )
        else:
            scan_manifest = load(V2 / f"data/scans/{day}-{args.slot}.json")
            for channel in ("ma", "tender", "soe"):
                row = scan_manifest.get("channels", {}).get(channel, {})
                channel_results[channel] = row

        if any(
            not release_acceptable(channel, row)
            for channel, row in channel_results.items()
        ):
            raise RuntimeError("存在阻断栏目，构建停止")

        for name, cmd_args, timeout in (
            (
                "unified_store",
                [sys.executable, str(SCRIPTS / "build_unified_store.py"), "--date", day],
                180,
            ),
            (
                "readiness",
                [
                    sys.executable,
                    str(SCRIPTS / "write_v2_readiness.py"),
                    "--date",
                    day,
                    "--slot",
                    args.slot,
                ],
                180,
            ),
            (
                "build",
                [
                    sys.executable,
                    str(SCRIPTS / "build_daily_v2.py"),
                    "--date",
                    day,
                    "--slot",
                    args.slot,
                ],
                300,
            ),
            (
                "validate",
                [
                    sys.executable,
                    str(SCRIPTS / "validate_v2.py"),
                    "--date",
                    day,
                    "--slot",
                    args.slot,
                    *(["--skip-tests"] if args.skip_tests else []),
                ],
                900,
            ),
        ):
            result = command(
                cmd_args,
                timeout=timeout,
                log_path=log_dir / f"{name}.log",
            )
            stages.append({"stage": name, **result})
            if result["returnCode"] != 0:
                raise RuntimeError(f"{name}阶段失败，详见{result['log']}")

        readiness = load(V2 / f"data/readiness/v2-ready-{day}-{args.slot}.json")
        status = readiness["status"]
        if status != "ready":
            raise RuntimeError("V2质量门禁未达到 ready；禁止构建客户页面或发布")
        if args.publish:
            release_path = V2 / "data" / "releases" / day / "morning-release.json"
            artifact_args = [
                sys.executable,
                str(SCRIPTS / "daily_artifacts.py"),
                "prepare",
                "--date",
                day,
                "--slot",
                args.slot,
            ]
            if args.slot != "morning" and not release_path.is_file():
                artifact_args.append("--create-if-missing")
            artifacts = command(
                artifact_args,
                timeout=180,
                log_path=log_dir / "daily_artifacts_prepare.log",
            )
            stages.append({"stage": "daily_artifacts_prepare", **artifacts})
            if artifacts["returnCode"] != 0:
                raise RuntimeError(f"日图准备失败，详见{artifacts['log']}")
            artifact_result = load(ROOT / artifacts["log"])
            if artifact_result.get("created") and release_path.is_file():
                artifact_stage = (V2 / ".runtime" / "daily-images" / day).relative_to(ROOT).as_posix()
                delivery["dailyImages"] = "staged"
            publish = command(
                [
                    "sh",
                    str(SCRIPTS / "publish_v2_to_github_pages.sh"),
                    "--date",
                    day,
                    "--slot",
                    args.slot,
                    "--skip-build",
                    *( ["--archive-stage", artifact_stage] if artifact_stage else [] ),
                ],
                timeout=900,
                log_path=log_dir / "publish.log",
                extra_env={"V2_PUBLISH_AUTHORIZED": "1"},
            )
            stages.append({"stage": "publish", **publish})
            if publish["returnCode"] != 0:
                raise RuntimeError(f"publish阶段失败，详见{publish['log']}")
            published_version = load(V2 / "data/build-version.json").get("buildVersion", "")
            deployment = V2 / "data" / "deployment-verification.json"
            if not deployment.is_file():
                raise RuntimeError("发布未生成线上确认清单")
            online_verification.update(load(deployment))
            if online_verification.get("asOf") != day or not online_verification.get("v2", {}).get("confirmed"):
                raise RuntimeError("线上日期或版本确认失败")
            if artifact_stage and not online_verification.get("dailyImageArchive", {}).get("confirmed"):
                raise RuntimeError("线上日图归档确认失败")
            delivery["web"] = "published"
            if artifact_stage:
                mark = command(
                    [
                        sys.executable,
                        str(SCRIPTS / "daily_artifacts.py"),
                        "mark-web-published",
                        "--date",
                        day,
                        "--slot",
                        args.slot,
                    ],
                    timeout=60,
                    log_path=log_dir / "daily_artifacts_web_published.log",
                )
                stages.append({"stage": "daily_artifacts_web_published", **mark})
                if mark["returnCode"] != 0:
                    raise RuntimeError(f"日图网页归档标记失败，详见{mark['log']}")
                # The first deployment proves that image bytes are online.  The
                # second, metadata-only deployment makes the public archive
                # index say "published" only after that proof.
                metadata_publish = command(
                    [
                        "sh",
                        str(SCRIPTS / "publish_v2_to_github_pages.sh"),
                        "--date",
                        day,
                        "--slot",
                        args.slot,
                        "--skip-build",
                    ],
                    timeout=900,
                    log_path=log_dir / "publish_archive_metadata.log",
                    extra_env={"V2_PUBLISH_AUTHORIZED": "1"},
                )
                stages.append({"stage": "publish_archive_metadata", **metadata_publish})
                if metadata_publish["returnCode"] != 0:
                    raise RuntimeError(
                        f"日图归档索引发布失败，详见{metadata_publish['log']}"
                    )
                delivery["dailyImages"] = "published"
            # Image delivery is deliberately non-blocking.  Noon and closing
            # runs call the same queue even when no new daily image was made.
            ima = command(
                [
                    sys.executable,
                    str(SCRIPTS / "upload_v2_daily_images.py"),
                    "--date",
                    day,
                ],
                timeout=1_200,
                log_path=log_dir / "ima_delivery.log",
            )
            stages.append({"stage": "ima_delivery", **ima})
            if ima["returnCode"] == 0:
                ima_result = load(ROOT / ima["log"])
                delivery["ima"] = (
                    "completed"
                    if ima_result.get("attempted") and not ima_result.get("pendingRetry") and not ima_result.get("manualReview")
                    else "pending_retry"
                    if ima_result.get("pendingRetry")
                    else "needs_manual_duplicate_review"
                    if ima_result.get("manualReview")
                    else "no_pending_images"
                )
            else:
                # Never turn an already verified web release into a failed
                # release because a third-party upload is unavailable.
                delivery["ima"] = "pending_retry"
                source_failures.append("ima:delivery_command_failed_non_blocking")

        if code_hashes() != initial_hashes:
            raise RuntimeError("检测到生产运行期间代码/配置/测试文件发生变化")
    except Exception as error:  # always finalize the run manifest
        status = "blocked"
        source_failures.append(f"{type(error).__name__}:{error}")
        stages.append(
            {
                "stage": "pipeline",
                "status": "failed",
                "error": f"{type(error).__name__}: {error}",
                "traceback": traceback.format_exc(limit=8),
            }
        )
    finally:
        if status == "blocked" and delivery.get("web") != "published":
            manifest["failedRunRollback"] = rollback.restore()
            stages.append(
                {
                    "stage": "failed_run_rollback",
                    "status": "completed",
                    "restoredCount": len(manifest["failedRunRollback"]["restored"]),
                    "removedCount": len(manifest["failedRunRollback"]["removed"]),
                }
            )
        else:
            manifest["failedRunRollback"] = {
                "status": "not_required",
                "reason": (
                    "published_release"
                    if delivery.get("web") == "published"
                    else "run_ready"
                ),
            }
        rollback.close()
        hash_targets = [
            V2 / "data/source/events/unified-2026.json",
            V2 / "data/source/observation-pool.json",
            V2 / "data/production-data.json",
            V2 / "data/build-version.json",
        ]
        manifest.update(
            {
                "status": status,
                "finishedAt": now(),
                "stageTimings": stages,
                "channelReadiness": channel_results,
                "sourceFailures": source_failures,
                "sourceConstraints": source_constraints,
                "dataHashes": {
                    path.relative_to(ROOT).as_posix(): sha256(path)
                    for path in hash_targets
                    if path.is_file()
                },
                "publishedBuildVersion": published_version,
                "onlineVerification": online_verification,
                "delivery": delivery,
            }
        )
        write(run_path, manifest)
        latest = V2 / "data/runs/latest.json" if args.run_kind == "production" else V2 / "data/runs/latest-diagnostic.json"
        write(latest, manifest)
        if args.run_kind == "production":
            write(V2 / "data/runs/latest-production.json", manifest)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if status == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
