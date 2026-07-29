#!/usr/bin/env python3
"""Fast regression checks for V2's self-contained production contract."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "v2"
SCRIPTS = V2 / "scripts"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ProductionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location(
            "run_v2_pipeline_contract", SCRIPTS / "run_v2_pipeline.py"
        )
        cls.pipeline = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(cls.pipeline)

    def test_quality_contract_locks_the_v1_standard_without_v1_runtime_input(self) -> None:
        contract = load(V2 / "config/production-quality-contract.json")
        self.assertEqual(contract["owner"], "V2")
        self.assertEqual(contract["standard"], "v1-source-and-editorial-quality")
        self.assertTrue(contract["release"]["blockOnAnyChannelFailure"])
        self.assertTrue(contract["release"]["blockOnSourceOrSnapshotDrift"])
        self.assertEqual(contract["channels"]["listed"]["requiredUniverse"], {"total": 110, "hkexL2": 14})
        self.assertEqual(contract["channels"]["private"]["requiredObservationManagers"], 92)

    def test_hkex_registry_matches_exactly_the_l2_observation_pool(self) -> None:
        registry = load(V2 / "config/hkex-issuers.json")
        universe = load(V2 / "data/source/listed/universe.json")
        l2 = {
            str(row["securityCode"]).split(".")[0].zfill(5)
            for row in universe["entities"]
            if row["universeTier"] == "L2"
        }
        registered = {str(row["securityCode"]).zfill(5) for row in registry["issuers"]}
        self.assertEqual(len(l2), 14)
        self.assertEqual(registered, l2)
        self.assertTrue(all(int(row["stockId"]) > 0 for row in registry["issuers"]))

    def test_pipeline_acquires_all_formerly_external_inputs_before_scanning(self) -> None:
        self.assertEqual(self.pipeline.ACCEPTED, {"completed", "no_new"})
        commands = {
            channel: self.pipeline.input_command(channel, "2026-07-28", "morning")[0]
            for channel in ("listed", "private", "soe")
        }
        self.assertIn("prepare_listed_daily.py", " ".join(commands["listed"]))
        self.assertIn("fetch_private_funds.py", " ".join(commands["private"]))
        self.assertIn("collect_soe_evidence.py", " ".join(commands["soe"]))
        text = (SCRIPTS / "run_v2_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("skip_input_preparation and args.run_kind == \"production\"", text)
        self.assertIn("V2质量门禁未达到 ready", text)
        self.assertNotIn("prepares only the two editorial inputs", text)

    def test_same_day_increment_reuses_verified_editorial_brief(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            v2 = Path(directory)
            brief = v2 / "data/daily/listed/editorial-brief-2026-07-29.json"
            brief.parent.mkdir(parents=True)
            brief.write_text("{}", encoding="utf-8")
            with mock.patch.object(self.pipeline, "V2", v2):
                command = self.pipeline.input_command(
                    "listed", "2026-07-29", "midday"
                )[0]
        self.assertIn("--editorial-brief", command)
        brief_arg = command[command.index("--editorial-brief") + 1]
        self.assertTrue(brief_arg.endswith("editorial-brief-2026-07-29.json"))

    def test_blocked_run_rollback_restores_inputs_and_removes_new_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            v2 = root / "v2"
            existing = v2 / "data/daily/listed/listed-official-2026-07-29.json"
            created = v2 / "data/daily/listed/new-2026-07-29.json"
            existing.parent.mkdir(parents=True)
            existing.write_text("trusted", encoding="utf-8")
            with (
                mock.patch.object(self.pipeline, "ROOT", root),
                mock.patch.object(self.pipeline, "V2", v2),
            ):
                rollback = self.pipeline.FailedRunRollback("2026-07-29", "midday")
                existing.write_text("untrusted", encoding="utf-8")
                created.write_text("new", encoding="utf-8")
                result = rollback.restore()
                rollback.close()
            self.assertEqual(existing.read_text(encoding="utf-8"), "trusted")
            self.assertFalse(created.exists())
            self.assertEqual(result["status"], "restored")

    def test_current_daily_images_are_created_from_v2_snapshot(self) -> None:
        text = (SCRIPTS / "daily_artifacts.py").read_text(encoding="utf-8")
        prepare_body = text[text.index("def prepare("):text.index("def mark_web_published(")]
        self.assertIn("prepare_v2_legacy", prepare_body)
        self.assertNotIn("prepare_v1_daily(", prepare_body)
        self.assertIn('"origin": "v2"', text)

    def test_tender_constraint_is_the_only_degraded_release_exception(self) -> None:
        eligible = {
            "status": "degraded",
            "coverageComplete": True,
            "networkVerified": True,
            "releaseEligibility": {
                "eligible": True,
                "mode": "official_equivalent_coverage_with_supplemental_source_constraint",
                "constrainedSourceIds": ["tender-sx-government-procurement"],
            },
        }
        self.assertTrue(self.pipeline.tender_constraint_release_eligible(eligible))
        self.assertTrue(
            self.pipeline.release_acceptable(
                "tender", {"status": "degraded", "releaseEligible": True}
            )
        )
        self.assertFalse(
            self.pipeline.release_acceptable(
                "ma", {"status": "degraded", "releaseEligible": True}
            )
        )
        self.assertFalse(
            self.pipeline.tender_constraint_release_eligible(
                {**eligible, "coverageComplete": False}
            )
        )

    def test_soe_source_registry_has_only_official_reviewed_sources(self) -> None:
        registry = load(V2 / "config/soe-sources.json")
        sources = registry["sources"]
        self.assertEqual(len(sources), 6)
        self.assertEqual(len({row["url"] for row in sources}), len(sources))
        self.assertTrue(all(row["url"].startswith("https://") for row in sources))
        self.assertTrue(all(row["entity"] and row["category"] for row in sources))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
