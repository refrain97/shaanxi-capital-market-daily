#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "v2/scripts"
FIXTURES = ROOT / "v2/tests/fixtures"
sys.path.insert(0, str(SCRIPTS))

from scanner_common import (  # noqa: E402
    extract_ma_facts,
    infer_ma_stage,
    infer_tender_stage,
    ma_keyword_match,
    merge_ma_project,
    merge_tender_project,
    sha256_file,
    stable_project_id,
    tender_keyword_match,
    verify_receipt_artifacts,
    write_json,
)


def automation_toml_fields(path: Path) -> dict:
    """Parse the flat fields used by Codex automation TOML without extra deps."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    fields = {}
    for key in (
        "id", "name", "prompt", "status", "rrule", "model",
        "reasoning_effort", "notification_policy",
    ):
        raw = next(
            (line.split(" = ", 1)[1] for line in lines if line.startswith(f"{key} = ")),
            None,
        )
        if raw is None:
            raise AssertionError(f"{path}: missing {key}")
        fields[key] = json.loads(raw)
    project = re.search(r'project_id = "([^"]+)"', text)
    if not project:
        raise AssertionError(f"{path}: missing project_id")
    fields["project_id"] = project.group(1)
    return fields


class ChannelScannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tender_config = json.loads(
            (ROOT / "v2/config/tender-sources.json").read_text(encoding="utf-8")
        )
        cls.ma_config = json.loads(
            (ROOT / "v2/config/ma-sources.json").read_text(encoding="utf-8")
        )
        spec = importlib.util.spec_from_file_location(
            "refresh_tender_events_test", SCRIPTS / "refresh_tender_events.py"
        )
        cls.tender_scanner = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(cls.tender_scanner)
        ma_spec = importlib.util.spec_from_file_location(
            "refresh_ma_events_test", SCRIPTS / "refresh_ma_events.py"
        )
        cls.ma_scanner = importlib.util.module_from_spec(ma_spec)
        assert ma_spec.loader
        ma_spec.loader.exec_module(cls.ma_scanner)

    def test_tender_stage_and_keyword_classification(self) -> None:
        self.assertEqual(infer_tender_stage("中标候选人公示"), "candidate")
        self.assertEqual(infer_tender_stage("中标结果公告"), "award")
        self.assertEqual(infer_tender_stage("更正公告"), "change")
        self.assertEqual(infer_tender_stage("终止公告"), "terminated")
        match = tender_keyword_match("公司债主承销商选聘公告", self.tender_config)
        self.assertTrue(match["matched"])
        excluded = tender_keyword_match("银行物业采购公告", self.tender_config)
        self.assertFalse(excluded["matched"])
        self.assertEqual(excluded["reason"], "excluded_non_capital_market_procurement")

    def test_ma_stage_and_false_completion_exclusion(self) -> None:
        self.assertEqual(infer_ma_stage("股权收购交割完成公告"), "completed")
        self.assertEqual(infer_ma_stage("重大资产重组终止公告"), "terminated")
        self.assertTrue(
            ma_keyword_match("关于收购某公司股权的公告", self.ma_config)["matched"]
        )
        self.assertFalse(
            ma_keyword_match("临床试验完成数据库锁定", self.ma_config)["matched"]
        )
        facts = extract_ma_facts("拟以19.16亿元收购33.4204%股权")
        self.assertEqual(facts["amounts"], ["19.16亿元"])
        self.assertEqual(facts["equityRatios"], ["33.4204%"])

    def test_ma_substantive_and_lifecycle_fixture_cases(self) -> None:
        fixture = json.loads(
            (
                ROOT / "v2/tests/fixtures/ma-keyword-cases.json"
            ).read_text(encoding="utf-8")
        )
        for row in fixture["cases"]:
            with self.subTest(row["name"]):
                audit = ma_keyword_match(row["text"], self.ma_config)
                self.assertEqual(audit["matched"], row["matched"])
                if not row["matched"] and any(
                    term in row["text"]
                    for term in ("完成", "终止", "交易", "成交")
                ):
                    self.assertEqual(
                        audit["reason"],
                        "lifecycle_without_substantive_ma_signal",
                    )

    def test_xbcq_physical_asset_scope_and_cross_category_deduplication(self) -> None:
        physical = ma_keyword_match(
            "一宗土地使用权挂牌交易完成", self.ma_config
        )
        physical = self.ma_scanner.xbcq_scope_audit(
            "中国某股份有限公司一宗土地使用权", "土地资产", physical
        )
        self.assertFalse(physical["matched"])
        self.assertEqual(
            physical["reason"], "excluded_single_physical_asset_disposal"
        )
        equity = ma_keyword_match(
            "某公司25%股权 股权转让", self.ma_config
        )
        equity = self.ma_scanner.xbcq_scope_audit(
            "某公司25%股权", "股权转让", equity
        )
        self.assertTrue(equity["matched"])

        base = {
            "recordId": "ma-sx-property-exchanges:same-record",
            "title": "某公司25%股权",
            "sourceUrl": "https://www.xbcq.com/project/same-record",
            "publishedAt": "2026-07-27",
            "industry": "股权转让",
            "discoveredCategories": ["股权转让"],
            "listAndDetailEvidence": {"detailSha256": "a" * 64},
        }
        duplicate = {
            **base,
            "recordId": "ma-sx-property-exchanges:alternate-record",
            "industry": "资产综合",
            "discoveredCategories": ["资产综合"],
            "listAndDetailEvidence": {"detailSha256": "a" * 64},
        }
        deduped = self.ma_scanner.dedupe_ma_records([base, duplicate])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(
            deduped[0]["discoveredCategories"], ["股权转让", "资产综合"]
        )
        self.assertEqual(len(deduped[0]["discoveryEvidence"]), 2)

    def test_ma_candidate_does_not_become_formal_event_flag(self) -> None:
        pending = [{"publishedAt": "2026-07-27", "recordId": "candidate-1"}]
        store = {
            "projects": [
                {
                    "maProjectId": "ma-existing",
                    "sourceRecords": [
                        {"publishedAt": "2026-07-18", "url": "https://example.com"}
                    ],
                }
            ]
        }
        candidate_on_date, event_on_date = self.ma_scanner.scan_date_flags(
            store, [], pending, "2026-07-27"
        )
        self.assertTrue(candidate_on_date)
        self.assertFalse(event_on_date)

    def test_stage_changes_share_stable_tender_project_id(self) -> None:
        announcement = stable_project_id(
            "tender-project", "某公司债主承销商选聘项目招标公告", "陕西某集团"
        )
        result = stable_project_id(
            "tender-project", "某公司债主承销商选聘项目中标结果公告", "陕西某集团"
        )
        self.assertEqual(announcement, result)

    def test_ma_timeline_merge_is_idempotent_and_preserves_project_id(self) -> None:
        project = {
            "maProjectId": "ma-legacy-001",
            "stage": "announced",
            "sourceRecords": [],
            "milestones": [],
        }
        candidate = {
            "sourceRecord": {
                "sourceRecordId": "src-1",
                "sourceName": "巨潮资讯",
                "sourceQuality": "exchange_or_regulator_original",
                "publishedAt": "2026-07-27",
                "title": "收购进展公告",
                "url": "https://static.cninfo.com.cn/example.pdf",
            },
            "milestone": {
                "milestoneId": "m-1",
                "at": "2026-07-27",
                "label": "收购进展公告",
                "stageAfter": "in_progress",
                "sourceIds": ["src-1"],
            },
        }
        once = merge_ma_project(project, candidate)
        twice = merge_ma_project(once, candidate)
        self.assertEqual(once, twice)
        self.assertEqual(twice["maProjectId"], "ma-legacy-001")
        self.assertEqual((len(twice["sourceRecords"]), len(twice["milestones"])), (1, 1))

    def test_tender_stage_merge_is_idempotent(self) -> None:
        project = {
            "id": "SX-STB-2026-001",
            "sourceRecords": [],
            "milestones": [],
        }
        candidate = {
            "projectFingerprint": "tender-project-abc",
            "sourceRecord": {
                "url": "https://example.gov.cn/result",
                "publishedAt": "2026-07-27",
                "title": "中标结果公告",
            },
            "milestone": {
                "at": "2026-07-27",
                "stage": "award",
                "title": "中标结果公告",
            },
        }
        once = merge_tender_project(project, candidate)
        twice = merge_tender_project(once, candidate)
        self.assertEqual(once, twice)
        self.assertEqual(twice["stageCode"], "award")

    def test_receipt_hashes_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact.json"
            write_json(artifact, {"value": 1})
            receipt = {"artifactHashes": {"artifact.json": sha256_file(artifact)}}
            self.assertEqual(verify_receipt_artifacts(root, receipt), [])
            artifact.write_text('{"value":2}\n', encoding="utf-8")
            self.assertEqual(
                verify_receipt_artifacts(root, receipt),
                ["hash_mismatch:artifact.json"],
            )

    def test_source_configs_use_production_adapters_and_official_coverage_group(self) -> None:
        adapters = {
            row["adapter"]
            for row in self.tender_config["sources"] + self.ma_config["sources"]
        }
        self.assertNotIn("health_probe_only", adapters)
        self.assertNotIn("registry_uncovered", adapters)
        self.assertIn("ccgp_shaanxi_notice_api_v2", adapters)
        self.assertIn("sntba_notice_api_v2", adapters)
        self.assertIn("xbcq_project_api_v2", adapters)
        self.assertIn("sx_sasac_html_list_v2", adapters)
        self.assertIn("issuer_registry_html_v2", adapters)
        group = self.tender_config["coverageGroups"][0]
        self.assertEqual(group["rule"], "any_complete")
        self.assertEqual(
            set(group["members"]),
            {"tender-sx-bidding-service", "tender-national-bulletin"},
        )
        ccgp = next(
            row for row in self.tender_config["sources"]
            if row["adapter"] == "ccgp_shaanxi_notice_api_v2"
        )
        self.assertFalse(ccgp["required"])
        self.assertTrue(ccgp["degradedOnFailure"])

    def test_ccgp_fixture_full_list_and_embedded_body(self) -> None:
        source = next(
            row for row in self.tender_config["sources"]
            if row["adapter"] == "ccgp_shaanxi_notice_api_v2"
        )
        fixture = (
            ROOT / "v2/tests/fixtures/ccgp-notice-page.json"
        ).read_bytes()

        def fake_fetch(url: str, **kwargs):
            return 200, url, fixture, {}

        with patch.object(self.tender_scanner, "fetch", side_effect=fake_fetch):
            run, rows = self.tender_scanner.scan_ccgp(
                source, self.tender_config, "2026-07-27", 1
            )
        self.assertTrue(run["searchCompleted"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["buyer"], "陕西某集团")
        self.assertIn("主承销商", rows[0]["title"])
        self.assertRegex(rows[0]["embeddedBodySha256"], r"^[0-9a-f]{64}$")

    def test_sasac_and_xbcq_response_fixtures(self) -> None:
        sasac_html = (
            ROOT / "v2/tests/fixtures/sasac-list.html"
        ).read_text(encoding="utf-8")
        parsed = self.ma_scanner.parse_sasac_rows(
            "https://sxgz.shaanxi.gov.cn/sy/gqzc/qydt/", sasac_html
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["publishedAt"], "2026-07-27")
        self.assertIn("股权收购", parsed[0]["title"])

        source = {
            **next(
                row for row in self.ma_config["sources"]
                if row["adapter"] == "xbcq_project_api_v2"
            ),
            "categories": [{"name": "股权转让", "cateid": "fixture"}],
            "resultLists": [],
        }
        list_fixture = (
            ROOT / "v2/tests/fixtures/xbcq-list-page.json"
        ).read_bytes()
        detail_fixture = (
            ROOT / "v2/tests/fixtures/xbcq-detail.json"
        ).read_bytes()

        def fake_fetch(url: str, timeout: int):
            raw = detail_fixture if "/detail/" in url else list_fixture
            return 200, url, raw, {}

        with patch.object(self.ma_scanner, "fetch", side_effect=fake_fetch):
            run, rows, _ = self.ma_scanner.scan_xbcq(
                source, "2026-07-27", 1
            )
        self.assertTrue(run["searchCompleted"])
        self.assertEqual(run["detailVerifiedCount"], 1)
        self.assertEqual(rows[0]["publishedAt"], "2026-07-27")

    def test_tender_default_runs_full_adapter_query_sets(self) -> None:
        sx_source = next(
            row for row in self.tender_config["sources"]
            if row["adapter"] == "sxggzy_fulltext_v2"
        )
        ceb_source = next(
            row for row in self.tender_config["sources"]
            if row["adapter"] == "ceb_html_search_v2"
        )
        empty_sx = json.dumps(
            {"content": json.dumps({"result": {"records": [], "totalcount": 0}})}
        ).encode()

        def fake_fetch(url: str, **kwargs):
            return (200, url, empty_sx if "getFullTextDataNew" in url else b"<html></html>", {})

        with patch.object(self.tender_scanner, "fetch", side_effect=fake_fetch):
            sx_run, _ = self.tender_scanner.scan_sxggzy(
                sx_source, self.tender_config, "2026-07-27", 1
            )
            ceb_run, _ = self.tender_scanner.scan_ceb(
                ceb_source, self.tender_config, "2026-07-27", 1
            )
            limited_run, _ = self.tender_scanner.scan_sxggzy(
                sx_source, self.tender_config, "2026-07-27", 1, max_queries=1
            )
        term_count = len(
            set(
                self.tender_config["keywordGroups"]["products"]
                + self.tender_config["keywordGroups"]["services"]
            )
        )
        self.assertEqual(sx_run["queryCount"], term_count)
        self.assertTrue(sx_run["searchCompleted"])
        self.assertEqual(ceb_run["queryCount"], term_count * 4)
        self.assertTrue(ceb_run["searchCompleted"])
        self.assertEqual(limited_run["queryCount"], 1)
        self.assertFalse(limited_run["searchCompleted"])
        self.assertEqual(limited_run["status"], "degraded")

    def test_existing_event_stores_are_preserved(self) -> None:
        ma = json.loads(
            (ROOT / "v2/data/source/ma/events-2026.json").read_text(encoding="utf-8")
        )
        tender = json.loads(
            (ROOT / "v2/data/source/tender/events-2026.json").read_text(encoding="utf-8")
        )
        ma_ids = [row["maProjectId"] for row in ma["projects"]]
        tender_ids = [row["id"] for row in tender["opportunities"]]
        self.assertGreaterEqual(len(ma_ids), 25)
        self.assertEqual(len(ma_ids), len(set(ma_ids)))
        self.assertRegex(
            sha256_file(ROOT / "v2/data/source/ma/events-2026.json"),
            r"^[0-9a-f]{64}$",
        )
        self.assertGreaterEqual(len(tender_ids), 5)
        self.assertEqual(len(tender_ids), len(set(tender_ids)))

    def test_controlled_real_scan_receipts_distinguish_complete_and_external_block(self) -> None:
        for channel, minimum_count, expected_status, event_on_date in (
            ("ma", 25, "completed", False),
            ("tender", 5, "blocked", False),
        ):
            receipt_path = FIXTURES / f"{channel}-scan-2026-07-27-closing.json"
            self.assertTrue(receipt_path.is_file())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], expected_status)
            self.assertEqual(
                receipt["coverageComplete"], expected_status == "completed"
            )
            self.assertTrue(receipt["networkVerified"])
            self.assertEqual(receipt["eventOnScanDate"], event_on_date)
            if channel == "ma":
                self.assertIn("candidateOnScanDate", receipt)
                self.assertEqual(
                    receipt["eventOnScanDate"],
                    bool(receipt["counts"]["importedOrUpdated"]),
                )
            self.assertGreaterEqual(receipt["counts"]["projectsAfter"], minimum_count)
            self.assertRegex(receipt["inputSha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(receipt["configSha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(receipt["scannerSha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(receipt["artifactHashes"])
            self.assertTrue(
                all(
                    re.fullmatch(r"[0-9a-f]{64}", value)
                    for value in receipt["artifactHashes"].values()
                )
            )
            self.assertLess(receipt["latestEventDate"], receipt["scanAsOf"])

    def test_readiness_uses_dedicated_receipts_over_manual_channel_status(self) -> None:
        readiness = json.loads(
            (FIXTURES / "readiness-2026-07-27-closing.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(readiness["channels"]["ma"]["status"], "no_new")
        self.assertEqual(readiness["channels"]["tender"]["status"], "no_new")
        self.assertEqual(readiness["status"], "blocked")
        self.assertTrue(readiness["ma"]["coverageComplete"])
        self.assertNotIn("ma_dedicated_scan_incomplete", readiness["failures"])
        self.assertIn("tender_dedicated_scan_incomplete", readiness["failures"])

    def test_runtime_scripts_are_v2_owned(self) -> None:
        for name in ("refresh_ma_events.py", "refresh_tender_events.py"):
            text = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertNotIn('ROOT / "v1', text)
            self.assertNotIn('ROOT / "v3', text)
            self.assertNotIn("record_channel_scan.py", text)
        runner = (SCRIPTS / "run_daily_v2.sh").read_text(encoding="utf-8")
        pipeline = (SCRIPTS / "run_v2_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("run_v2_pipeline.py", runner)
        self.assertIn("refresh_ma_events.py", pipeline)
        self.assertIn("refresh_tender_events.py", pipeline)
        self.assertNotIn("--max-queries", runner)
        self.assertLess(pipeline.index("refresh_ma_events.py"), pipeline.index("write_v2_readiness.py"))
        self.assertLess(pipeline.index("refresh_tender_events.py"), pipeline.index("write_v2_readiness.py"))

    def test_repository_automation_prompt_contract(self) -> None:
        prompt = (
            ROOT / "v2/docs/AUTOMATION_PROMPT_V2.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("每个栏目都必须调用 `record_channel_scan.py`", prompt)
        self.assertNotIn("专用扫描器补齐前", prompt)
        self.assertIn("不得在入口外\n   人工声明任一栏目", prompt)
        self.assertIn("MA/tender 当前没有可靠的“上次游标后”增量窗口", prompt)
        self.assertIn("正式运行禁止传 `--max-queries`", prompt)
        self.assertIn("不调用或读取旧版本的当日流程", prompt)
        self.assertIn("从 V2 冻结快照生成一次四张日图", prompt)
        self.assertNotIn("partial_ready", prompt)

    def test_installed_v2_automation_prompts_match_scanner_contract(self) -> None:
        automation_root = Path.home() / ".codex/automations"
        if not automation_root.is_dir():
            self.skipTest("Codex客户端自动化目录不存在")
        expected = {
            "v2-2": ("BYHOUR=5;BYMINUTE=30", "slot morning"),
            "v2-12-00": ("BYHOUR=12;BYMINUTE=0", "slot midday"),
            "v2-17-00": ("BYHOUR=17;BYMINUTE=0", "slot closing"),
        }
        for automation_id, (schedule, slot_marker) in expected.items():
            path = automation_root / automation_id / "automation.toml"
            self.assertTrue(path.is_file(), automation_id)
            row = automation_toml_fields(path)
            self.assertEqual(row["id"], automation_id)
            self.assertEqual(row["status"], "ACTIVE")
            self.assertEqual(row["model"], "gpt-5.6-sol")
            self.assertEqual(row["reasoning_effort"], "high")
            self.assertEqual(row["notification_policy"], "failed_runs_only")
            self.assertIn(schedule, row["rrule"])
            self.assertIn("run_daily_v2.sh", row["prompt"])
            self.assertIn("不得运行 V1 或 V3", row["prompt"])
            self.assertIn(slot_marker, row["prompt"])
            self.assertNotIn("专用扫描器补齐前", row["prompt"])
            self.assertNotIn("五栏目分别用 v2/scripts/record_channel_scan.py", row["prompt"])
            self.assertNotIn("五个栏目分别运行v2/scripts/record_channel_scan.py", row["prompt"])
            self.assertIn("blocked", row["prompt"])
            self.assertIn("只调用一次", row["prompt"])
            self.assertIn("V2 不得读取任何同日 V1", row["prompt"])
            self.assertIn("V2 快照", row["prompt"])
            self.assertNotIn("partial_ready", row["prompt"])
            self.assertNotIn("V1 已冻结", row["prompt"])

        v1 = automation_toml_fields(automation_root / "v1" / "automation.toml")
        self.assertEqual(v1["status"], "PAUSED")
        self.assertIn("历史档案", v1["prompt"])


if __name__ == "__main__":
    unittest.main()
