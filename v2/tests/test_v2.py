#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path
from urllib.parse import urlparse

OUT = Path(__file__).resolve().parents[1]
ROOT = OUT.parents[0]
AS_OF = json.loads(
    (OUT / "data" / "production-data.json").read_text(encoding="utf-8")
)["asOf"]


def paginate(rows: list, size: int = 10) -> list[list]:
    return [rows[index:index + size] for index in range(0, len(rows), size)]


def listed_rows(data: dict) -> list[dict]:
    daily = data["listed"]["daily"]
    return [
        row
        for key in ("opportunities", "risk_rows", "tiles", "capital_rows", "follow_items")
        for row in daily[key]
    ] + [row for group in daily["fixed_columns"] for row in group["items"]]


class ProductionV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data_path = OUT / "data" / "production-data.json"
        cls.data = json.loads(cls.data_path.read_text(encoding="utf-8"))
        cls.app = (OUT / "assets" / "app.js").read_text(encoding="utf-8")
        cls.styles = (OUT / "assets" / "styles.css").read_text(encoding="utf-8")
        spec = importlib.util.spec_from_file_location("build_daily_v2", OUT / "scripts" / "build_daily_v2.py")
        cls.build_module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(cls.build_module)

    def test_pagination_boundaries_have_no_loss_or_duplication(self) -> None:
        for count, expected in ((0, 0), (1, 1), (10, 1), (11, 2), (20, 2), (21, 3)):
            pages = paginate(list(range(count)))
            self.assertEqual(len(pages), expected)
            self.assertEqual([item for page in pages for item in page], list(range(count)))
            self.assertTrue(all(1 <= len(page) <= 10 for page in pages))

    def test_exact_listed_date_is_fail_closed(self) -> None:
        result = subprocess.run(
            ["python3", str(OUT / "scripts" / "build_daily_v2.py"), "--date", "2026-07-26"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("失败关闭", result.stderr + result.stdout)

    def test_build_is_repeatable_and_versioned_consistently(self) -> None:
        before = self.data_path.read_bytes()
        contract = json.loads((OUT / "config" / "source-contract.json").read_text())
        receipts = [
            ROOT / contract[f"{channel}ScanDirectory"]
            / f"scan-{AS_OF}-{self.data['scanSlot']}.json"
            for channel in ("ma", "tender")
        ]
        def release_ready(path: Path) -> bool:
            if not path.is_file():
                return False
            receipt = json.loads(path.read_text())
            if receipt.get("status") == "completed":
                return True
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

        scanners_ready = all(release_ready(path) for path in receipts) and (
            self.data.get("readiness", {}).get("status") == "ready"
        )
        inputs_ready = all(
            (ROOT / row["path"]).is_file()
            and hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
            == row["sha256"]
            for row in self.data.get("build", {}).get("inputs", [])
        )
        result = subprocess.run(
            [
                "python3",
                str(OUT / "scripts" / "build_daily_v2.py"),
                "--date",
                AS_OF,
                "--slot",
                self.data["scanSlot"],
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        after = self.data_path.read_bytes()
        self.assertEqual(before, after)
        if scanners_ready and inputs_ready:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        else:
            self.assertNotEqual(result.returncode, 0)
        data = json.loads(after)
        version = data["build"]["version"]
        self.assertRegex(version, r"^[0-9a-f]{12}$")
        self.assertEqual(json.loads((OUT / "data" / "build-version.json").read_text())["buildVersion"], version)
        for name in ("index.html", "listed.html", "private.html", "ma.html", "tender.html", "soe.html"):
            text = (OUT / name).read_text(encoding="utf-8")
            self.assertIn(f"assets/styles.css?v={version}", text)
            self.assertIn(f"assets/app.js?v={version}", text)
            self.assertIn(f'data-build-version="{version}"', text)
        self.assertIn("data/build-version.json?probe=${Date.now()}", self.app)
        self.assertIn("production-data.json?v=${encodeURIComponent(activeBuildVersion)}", self.app)
        self.assertIn('cache:"no-store"', self.app)

    def test_generated_pages_and_internal_links(self) -> None:
        pages = [OUT / name for name in (
            "index.html", "listed.html", "private.html", "ma.html",
            "tender.html", "soe.html",
        )]
        for page in pages:
            text = page.read_text(encoding="utf-8")
            self.assertIn("V2", text)
            self.assertNotIn("PREVIEW", text)
            for href in re.findall(r'href=["\']([^"\']+)', text):
                parsed = urlparse(href)
                if parsed.scheme or href.startswith(("#", "mailto:")):
                    continue
                target = (page.parent / parsed.path).resolve()
                self.assertTrue(target.exists(), f"{page}: {href}")
        for page in pages:
            nav = re.search(r"<nav>(.*?)</nav>", page.read_text(encoding="utf-8"), re.S)
            self.assertIsNotNone(nav)
            self.assertNotIn(">观察池</a>", nav.group(1))
            self.assertNotIn(">分享图库</a>", nav.group(1))

    def test_customer_pages_exclude_internal_production_language(self) -> None:
        customer_code = self.app + "\n" + "\n".join(
            (OUT / name).read_text(encoding="utf-8")
            for name in ("index.html", "listed.html", "private.html", "ma.html", "tender.html", "soe.html")
        )
        for forbidden in (
            "PREVIEW", "候选版", "未发布", "本地路径", "内部 JSON", "抓取上限",
            "接口抽取", "PDF抽取", "生成状态", "overlay", "review-candidate",
            "三个月分享窗口", "查看分享图", "三个月可分享项目",
        ):
            self.assertNotIn(forbidden, customer_code)
        self.assertNotRegex(customer_code, r"2026-\d{2}-\d{2}T\d{2}:")

    def test_page_and_source_dates_are_visible(self) -> None:
        self.assertIn("<b>页面日期</b>", self.app)
        self.assertIn("<b>数据截至</b>", self.app)
        for marker in (
            "data.scanAsOf", "scanLabel(data,\"listed\")", "scanLabel(data,\"private\")",
            "scanLabel(data,\"ma\")", "scanLabel(data,\"tender\")", "scanLabel(data,\"soe\")",
            "最近事件",
        ):
            self.assertIn(marker, self.app)

    def test_home_four_cards_are_current_unique_sorted_and_linked(self) -> None:
        cards = self.data["homeHighlights"]
        self.assertEqual([row["category"] for row in cards], ["上市公司", "上市公司", "证券私募", "收并购"])
        self.assertEqual(len(cards), 4)
        self.assertEqual(len({row["company"] for row in cards[:2]}), 2)
        self.assertTrue(all(row["date"] and row["href"] for row in cards))
        self.assertTrue(cards[0]["href"].startswith("listed.html#"))
        self.assertTrue(cards[2]["href"].startswith("private.html#fund-"))
        self.assertTrue(cards[3]["href"].startswith("ma.html#"))

    def test_listed_pool_sources_and_focus_contract(self) -> None:
        listed = self.data["listed"]
        self.assertEqual(listed["counts"], {"total": 110, "L1": 85, "L2": 14, "L3": 11})
        self.assertEqual(len(listed["entities"]), 110)
        self.assertEqual(listed["sourceAsOf"], AS_OF)
        self.assertFalse(listed["isAsOfFallback"])
        self.assertGreater(listed["sourceCoverage"]["total"], 0)
        self.assertEqual(
            listed["sourceCoverage"]["linked"],
            listed["sourceCoverage"]["total"],
        )
        self.assertEqual(listed["sourceCoverage"]["unmatched"], [])
        self.assertTrue(all(row.get("sources") for row in listed_rows(self.data)))
        self.assertTrue(
            all(
                row["sourceUrl"].startswith(
                    ("https://static.cninfo.com.cn/", "https://www1.hkexnews.hk/")
                )
                for row in listed_rows(self.data)
            )
        )
        focus = listed["focusCompanies"]
        self.assertGreaterEqual(len(focus), 1)
        self.assertLessEqual(len(focus), 4)
        self.assertEqual(len({row["company"] for row in focus}), len(focus))
        self.assertEqual(len({row["anchorId"] for row in focus}), len(focus))
        self.assertTrue(all(row["anchorId"].startswith("listed-detail-") for row in focus))
        focus_tags = listed["businessTaxonomy"]["focusTags"]
        self.assertEqual(len(focus_tags), 21)
        self.assertIn('class="focus-tag hit"', self.app)
        self.assertIn('class="focus-tag"', self.app)
        self.assertIn("const focusTagRows=", self.app)
        self.assertIn('href="#${esc(anchor)}"', self.app)
        self.assertIn('row.business?.priority==="focus"', self.app)
        self.assertIn("row.focusAnchorId=", self.app)
        self.assertIn('row.canonicalDetailId||row.focusAnchorId', self.app)
        self.assertIn("固定展示21个二级标签", self.app)
        self.assertIn(".focus-tag.hit{", self.styles)
        self.assertIn(".pool-scroll{height:330px;overflow:auto}", self.styles)

    def test_listed_buyback_multisource_and_bad_token_correction(self) -> None:
        daily = self.data["listed"]["daily"]
        aike_rows = [
            row for group in daily["fixed_columns"] for row in group["items"]
            if row["title"].startswith("爱科赛博｜")
        ]
        if aike_rows:
            self.assertEqual(aike_rows[0]["business"]["subcategory"], "股份回购")
            self.assertIn("回购股份", aike_rows[0]["announcementTitle"])
        self.assertNotIn("AAsti", json.dumps(self.data, ensure_ascii=False))

    def test_layered_listed_references_resolve_to_one_canonical_matter(self) -> None:
        daily = self.data["listed"]["daily"]
        canonical = {
            row["matter_id"]: row["canonicalDetailId"]
            for row in listed_rows(self.data)
            if not row.get("isReference") and row.get("canonicalDetailId")
        }
        references = [
            row
            for group in ("opportunities", "follow_items")
            for row in daily[group]
            if row.get("isReference")
        ]
        self.assertTrue(references)
        for row in references:
            matter_id = row.get("referenceMatterId") or row.get("matter_id")
            self.assertIn(matter_id, canonical)
            self.assertEqual(row.get("referenceAnchor"), canonical[matter_id])
        multi = [row for row in listed_rows(self.data) if len(row.get("sources", [])) > 1]
        if multi:
            self.assertIn('rows.length>1?`公告${index+1}`:"公告"', self.app)

    def test_private_counts_months_and_custodian_ranking(self) -> None:
        private = self.data["private"]
        # Daily AMAC ingestion is intentionally live; the invariant is that
        # every page-level aggregate is derived from the exact current product
        # set rather than a stale hard-coded total.
        product_count = len(private["products"])
        self.assertGreater(product_count, 0)
        self.assertEqual(private["managerCounts"], {
            "total": 92, "PF1": 87, "PF2": 5,
            "PF2Substantive": 3, "PF2Association": 2,
        })
        month_counts = private["annualMonthCounts"]
        self.assertEqual(sum(month_counts.values()), product_count)
        self.assertTrue(all(re.fullmatch(r"2026-(0[1-9]|1[0-2])", key) for key in month_counts))
        self.assertEqual(sum(row["count"] for row in private["custodianStats"]), product_count)
        counts = [row["count"] for row in private["custodianStats"]]
        self.assertEqual(counts, sorted(counts, reverse=True))
        for marker in ("aria-expanded", "data-month-group", "data-custodian-toggle", "data-private-pool"):
            self.assertIn(marker, self.app)
        cicc = next(row for row in private["products"] if row["custodian"] == "中国国际金融股份有限公司")
        self.assertEqual(cicc["custodianLabel"], "中金公司")
        self.assertIn("row.custodianLabel||row.custodian", self.app)

    def test_private_relationships_do_not_regress(self) -> None:
        managers = {row["name"]: row for row in self.data["private"]["managers"]}
        self.assertEqual(
            managers["深圳抱朴容易私募证券基金管理有限公司"]["relationLabel"],
            "广东注册 / 西安办公分部 / PF2强关联",
        )
        zhuozhu = managers["上海卓铸私募基金管理有限公司"]
        self.assertEqual(zhuozhu["registerNo"], "P1027840")
        self.assertEqual(
            zhuozhu["relationLabel"],
            "上海注册 / 上海AMAC办公 / 西安持续办公+存续分公司 / PF2强关联",
        )
        self.assertTrue(any(item.get("url") == "https://www.zhuozhuinvest.com/website/w/h" for item in zhuozhu["evidence"]))
        tianyou = managers["添佑私募基金管理（上海）有限公司"]
        self.assertEqual(tianyou["registerNo"], "P1018901")
        self.assertEqual(tianyou["relationType"], "current_shaanxi_shareholders_and_historical_shaanxi_platform")
        association = [row for row in managers.values() if row.get("relationGroup") == "association_member"]
        self.assertEqual({row["name"] for row in association}, {
            "龙泉云锋私募基金管理有限公司", "苏州水润山禾私募基金管理有限公司",
        })
        self.assertTrue(all("非陕西注册/办公" in row["relationLabel"] for row in association))

    def test_ma_source_gate_and_planned_date_contract(self) -> None:
        ma = self.data["ma"]
        self.assertGreaterEqual(ma["sourceCoverage"]["total"], 25)
        self.assertEqual(
            ma["sourceCoverage"]["linked"]
            + ma["sourceCoverage"]["historicalExactDocumentBacklog"],
            ma["sourceCoverage"]["total"],
        )
        self.assertEqual(
            len(ma["verifiedProjects"]) + len(ma["pendingProjects"]),
            ma["sourceCoverage"]["total"],
        )
        self.assertTrue(all(row["sourceVerified"] and row["sourceUrl"] for row in ma["verifiedProjects"]))
        self.assertTrue(all(not row["sourceVerified"] and not row["sourceUrl"] for row in ma["pendingProjects"]))
        self.assertTrue(all(
            row["sourceVerified"] and row["sourceUrl"]
            for row in ma["projects"] if row["entityType"] == "listed"
        ))
        self.assertEqual(
            {row["dimension"] for row in ma["projects"]},
            {"已上市公司", "新三板挂牌公司"},
        )
        rainbow = next(row for row in ma["projects"] if row["id"] == "ma-rainbow-hongyang-minority-2026")
        self.assertEqual((rainbow["eventDate"], rainbow["updatedAt"], rainbow["plannedNextDate"]), (
            "2026-07-07", "2026-07-07", "2026-07-20",
        ))
        self.assertNotEqual(rainbow["eventDate"], rainbow["plannedNextDate"])

    def test_tender_five_plus_one_and_dynamic_copy(self) -> None:
        tender = self.data["tender"]
        self.assertEqual((len(tender["projects"]), len(tender["pending"])), (5, 1))
        self.assertEqual(len({row["id"] for row in tender["projects"]}), 5)
        self.assertTrue(all(row["formalTitle"] and row["latestProgressDate"] for row in tender["projects"]))
        self.assertNotIn("<b>5 + 1</b>", self.app)
        self.assertIn("${channel.projects.length} + ${channel.pending.length}", self.app)
        self.assertNotIn("<details", self.app)

    def test_soe_uses_v2_owned_verified_refresh_and_truthful_dates(self) -> None:
        soe = self.data["soe"]
        self.assertEqual(soe["scanAsOf"], AS_OF)
        self.assertTrue(soe["networkVerified"])
        self.assertEqual(soe["isAsOfFallback"], soe["sourceAsOf"] != AS_OF)
        self.assertEqual(len(soe["focusRecords"]), 5)
        self.assertEqual(set(soe["categoryOrder"]), {
            "资本金融", "项目资产", "风险治理", "产业经营", "综合动态",
        })
        self.assertTrue(all(len(rows) <= 5 for rows in soe["categoryRecords"].values()))
        self.assertIn("今日未识别新增有效事项", self.app)
        self.assertNotIn("channel.archiveHref", self.app)
        self.assertNotIn("channel.dailyHref", self.app)

    def test_private_and_ma_three_month_share_pipeline_is_retired_but_daily_delivery_is_v2_owned(self) -> None:
        self.assertNotIn("window", self.data["private"])
        self.assertNotIn("window", self.data["ma"])
        self.assertNotIn("imageWindow", self.data["rules"])
        self.assertFalse((OUT / "images").exists())
        self.assertFalse((OUT / "share").exists())
        self.assertFalse((OUT / "data" / "share-images.json").exists())
        self.assertFalse((OUT / "scripts" / "export_share_images.cjs").exists())
        self.assertFalse((OUT / "scripts" / "upload_daily_ima.sh").exists())
        self.assertFalse((OUT / "scripts" / "upload_ima_image.cjs").exists())
        self.assertTrue((OUT / "scripts" / "upload_v2_daily_images.py").exists())
        self.assertTrue((OUT / "scripts" / "upload_ima_v2_image.cjs").exists())
        self.assertEqual(json.loads((OUT / "config" / "ima.json").read_text())["status"], "active")
        self.assertIn("三个月分享图已永久停用", (OUT / "config" / "ima.json").read_text())

    def test_daily_image_archive_is_compact_and_history_is_opt_in(self) -> None:
        self.assertIn('class="daily-image-summary"', self.app)
        self.assertIn('data-daily-image-toggle', self.app)
        self.assertIn('data-daily-image-history', self.app)
        self.assertIn('V2日图期次', self.app)
        self.assertNotIn('迁移期V1日图', self.app)
        self.assertNotIn('V1历史期次', self.app)
        self.assertNotIn('daily-image-card', self.app)
        self.assertNotIn('class="daily-image-archive"', self.app)
        self.assertNotIn('历史早报正文', self.app)
        self.assertNotIn('id="listed-archive"', self.app)
        self.assertIn('"section-06","06","今日重点跟踪公司"', self.app)
        self.assertIn('["section-06","06 下一步"]', self.app)
        self.assertIn('dailyImageArchive(data.dailyImageArchive,"listed")', self.app)
        self.assertIn('history.hidden=!reveal', self.app)
        self.assertIn('.daily-image-summary{', self.styles)
        self.assertNotIn('.daily-image-card{', self.styles)

    def test_daily_images_use_v2_frozen_snapshot_and_v2_ima_delivery(self) -> None:
        artifacts = (OUT / "scripts" / "daily_artifacts.py").read_text(encoding="utf-8")
        uploader = (OUT / "scripts" / "upload_v2_daily_images.py").read_text(encoding="utf-8")
        runner = (OUT / "scripts" / "run_daily_v2.sh").read_text(encoding="utf-8")
        self.assertIn('morning-production-data.json.gz', artifacts)
        self.assertIn('def compact_snapshots()', artifacts)
        self.assertIn('def read_snapshot(', artifacts)
        self.assertIn('return prepare_v2_legacy(', artifacts)
        self.assertNotIn('def prepare_v1_daily(', artifacts)
        self.assertNotIn('def restore_v1_daily(', artifacts)
        self.assertNotIn('ROOT / "v1"', artifacts)
        self.assertIn('def purge_day_staging(', uploader)
        self.assertIn('finally:', uploader)
        self.assertIn('"v2"', uploader)
        self.assertIn('legacy-version hand-off', runner)
        self.assertNotIn('cleanup_v1_daily_image_sources.py --execute', runner)

    def test_publish_cannot_bypass_the_formal_v2_pipeline(self) -> None:
        publisher = (OUT / "scripts" / "publish_v2_to_github_pages.sh").read_text(encoding="utf-8")
        pipeline = (OUT / "scripts" / "run_v2_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('V2_PUBLISH_AUTHORIZED', publisher)
        self.assertIn('拒绝直接发布', publisher)
        self.assertIn('extra_env={"V2_PUBLISH_AUTHORIZED": "1"}', pipeline)

    def test_late_scheduled_runs_fail_closed_instead_of_masquerading_as_on_time(self) -> None:
        runner = (OUT / "scripts" / "run_daily_v2.sh").read_text(encoding="utf-8")
        pipeline = (OUT / "scripts" / "run_v2_pipeline.py").read_text(encoding="utf-8")
        self.assertIn('SLOT_STARTS = {"morning": "05:30", "midday": "12:00", "closing": "17:00"}', pipeline)
        self.assertIn('--max-start-lag-minutes', pipeline)
        self.assertIn('正式运行启动滞后', pipeline)
        self.assertIn('--expected-start', runner)
        self.assertIn('--max-start-lag-minutes', runner)

    def test_build_records_canonical_source_paths_and_hashes(self) -> None:
        build = self.data["build"]
        self.assertEqual(build["script"], "v2/scripts/build_daily_v2.py")
        self.assertEqual(build["schema"], "v2-production-2")
        self.assertGreaterEqual(len(build["inputs"]), 10)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) for row in build["inputs"]))
        paths = {row["path"] for row in build["inputs"]}
        self.assertIn("v2/config/source-contract.json", paths)
        self.assertIn(f"v2/data/daily/listed/listed-official-{AS_OF}.json", paths)
        self.assertIn("v2/data/source/events/unified-2026.json", paths)
        self.assertIn("v2/data/source/observation-pool.json", paths)
        self.assertIn(f"v2/data/source/soe/scans/scan-{AS_OF}-{self.data['scanSlot']}.json", paths)
        self.assertIn(f"v2/data/source/soe/evidence/verified-{AS_OF}-{self.data['scanSlot']}.json", paths)
        self.assertTrue(all(path.startswith("v2/") for path in paths))

    def test_only_v2_runtime_is_present_in_the_source_tree(self) -> None:
        build_text = (OUT / "scripts" / "build_daily_v2.py").read_text(encoding="utf-8")
        self.assertIn('OUT = ROOT / "v2"', build_text)
        self.assertNotIn('OUT = ROOT / "v1"', build_text)
        self.assertNotIn("run_morning_v1", build_text)
        self.assertNotIn("v1/data/readiness", build_text)
        self.assertNotIn("v3/data", build_text)
        self.assertNotIn("soe-radar", build_text)
        self.assertFalse((ROOT / "v1").exists())
        self.assertFalse((ROOT / "v3").exists())
        self.assertFalse((OUT / "陕西省上市公司日报v2").exists())
        for retired in (
            "bootstrap_v2_sources.py",
            "import_v1_daily_image_history.sh",
            "record_parallel_validation.py",
            "stage_listed_quality_repair.py",
        ):
            self.assertFalse((OUT / "scripts" / retired).exists())

    def test_unified_store_and_truthful_readiness_contract(self) -> None:
        event_store = json.loads((ROOT / self.data["sources"]["eventStore"]).read_text(encoding="utf-8"))
        pool = json.loads((ROOT / self.data["sources"]["observationPool"]).read_text(encoding="utf-8"))
        self.assertEqual(event_store["scanAsOf"], AS_OF)
        self.assertEqual(set(event_store["channelCounts"]), {"listed", "private", "ma", "tender", "soe"})
        self.assertEqual(pool["scanAsOf"], AS_OF)
        pool_counts = {key: len(value) for key, value in pool["channels"].items()}
        self.assertEqual(
            {key: pool_counts[key] for key in ("listed", "private", "ma", "tender")},
            {
                "listed": 110,
                "private": 92,
                "ma": pool_counts["ma"],
                "tender": 5,
            },
        )
        self.assertGreaterEqual(pool_counts["ma"], 50)
        self.assertGreater(pool_counts["soe"], 22)
        ids = [row["eventId"] for row in event_store["events"]]
        self.assertEqual(len(ids), len(set(ids)))
        required = {
            "eventId", "channel", "relatedEntities", "shaanxiRelation", "stage",
            "keyFacts", "primarySources", "timeline", "scanAsOf",
            "latestEventDate", "sourceStatus",
        }
        self.assertTrue(all(required <= set(row) for row in event_store["events"]))
        readiness = self.data["readiness"]
        self.assertEqual(
            (readiness["status"], readiness["date"], readiness["slot"]),
            (readiness["status"], AS_OF, self.data["scanSlot"]),
        )
        self.assertIn(readiness["status"], {"ready", "partial_ready"})
        self.assertTrue(all(row["ready"] for row in readiness["channels"].values()))
        self.assertIn(readiness["channels"]["tender"]["status"], {"no_new", "degraded", "completed"})
        self.assertIn(readiness["channels"]["soe"]["status"], {"no_new", "completed"})
        self.assertIn("已完成扫描，今日无新增", self.app)
        receipt = json.loads((ROOT / self.data["sources"]["soeScanEvidence"]).read_text())
        self.assertTrue(receipt["networkVerified"])
        self.assertLessEqual(receipt["latestVerifiedEventDate"], AS_OF)

    def test_run_script_is_v2_owned_and_fail_closed(self) -> None:
        runner = (OUT / "scripts" / "run_daily_v2.sh").read_text(encoding="utf-8")
        pipeline = (OUT / "scripts" / "run_v2_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("run_v2_pipeline.py", runner)
        self.assertIn("build_unified_store.py", pipeline)
        self.assertIn("write_v2_readiness.py", pipeline)
        self.assertIn("refresh_soe_events.py", pipeline)
        self.assertIn("refresh_ma_events.py", pipeline)
        self.assertIn("refresh_tender_events.py", pipeline)
        self.assertIn("--verify-network", pipeline)
        self.assertIn("--slot", runner)
        self.assertNotIn("--wait-for-v1", runner)
        self.assertNotIn("v1/data/readiness", runner)
        self.assertIn("upload_v2_daily_images.py", pipeline)
        self.assertNotIn("--upload-ima", runner)
        self.assertNotIn("upload_daily_ima.sh", runner)

    def test_publisher_uses_a_v2_only_runtime_allowlist(self) -> None:
        publisher = (OUT / "scripts" / "publish_v2_to_github_pages.sh").read_text(encoding="utf-8")
        self.assertIn("for file in index.html listed.html private.html ma.html tender.html soe.html", publisher)
        self.assertIn("for dir in assets", publisher)
        self.assertIn("for file in production-data.json build-version.json", publisher)
        self.assertIn("v2/images v2/share v2/data/share-images.json", publisher)
        self.assertNotIn('rsync -a --delete "$ROOT_DIR/v2/"', publisher)
        self.assertNotIn("陕西省上市公司日报v2/", publisher)
        self.assertNotIn("v1/scripts/publish", publisher)
        self.assertNotIn("V1_BEFORE_HASH", publisher)
        self.assertNotIn("V1_AFTER_HASH", publisher)
        self.assertNotIn('\"$LIVE_ROOT/v1/\"', publisher)
        self.assertIn('data.get("asOf") != expected_date', publisher)
        self.assertIn('data.get("build", {}).get("version") != expected_version', publisher)
        self.assertIn("--force-with-lease", publisher)
        self.assertIn("daily-image-archive.json", publisher)
        self.assertIn("--archive-stage", publisher)


if __name__ == "__main__":
    unittest.main()
