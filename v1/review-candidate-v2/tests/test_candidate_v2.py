#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import math
import re
import subprocess
import unittest
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image


OUT = Path(__file__).resolve().parents[1]
ROOT = OUT.parents[1]


def paginate(rows: list, size: int = 10) -> list[list]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def listed_rows(data: dict) -> list[dict]:
    daily = data["listed"]["daily"]
    return [
        row
        for key in ("opportunities", "risk_rows", "tiles", "capital_rows", "follow_items")
        for row in daily[key]
    ] + [
        row
        for group in daily["fixed_columns"]
        for row in group["items"]
    ]


class CandidateV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads((OUT / "data" / "candidate-data.json").read_text(encoding="utf-8"))
        cls.app = (OUT / "assets" / "app.js").read_text(encoding="utf-8")
        cls.styles = (OUT / "assets" / "styles.css").read_text(encoding="utf-8")
        spec = importlib.util.spec_from_file_location("candidate_v2_build", OUT / "scripts" / "build_candidate_v2.py")
        cls.build_module = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(cls.build_module)

    def test_pagination_boundaries(self) -> None:
        for count, expected in ((0, 0), (1, 1), (10, 1), (11, 2), (20, 2), (21, 3)):
            pages = paginate(list(range(count)))
            self.assertEqual(len(pages), expected)
            self.assertEqual([item for page in pages for item in page], list(range(count)))
            self.assertTrue(all(1 <= len(page) <= 10 for page in pages))

    def test_build_is_repeatable_and_versioned_consistently(self) -> None:
        before = (OUT / "data" / "candidate-data.json").read_bytes()
        subprocess.run(
            ["python3", str(OUT / "scripts" / "build_candidate_v2.py")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        after = (OUT / "data" / "candidate-data.json").read_bytes()
        self.assertEqual(before, after)
        data = json.loads(after)
        version = data["build"]["version"]
        self.assertRegex(version, r"^[0-9a-f]{12}$")
        for name in ("index.html", "listed.html", "private.html", "ma.html", "tender.html", "soe.html"):
            text = (OUT / name).read_text(encoding="utf-8")
            self.assertIn(f"assets/styles.css?v={version}", text)
            self.assertIn(f"assets/app.js?v={version}", text)
            self.assertIn(f'data-build-version="{version}"', text)
        self.assertIn("candidate-data.json?v=${encodeURIComponent(buildVersion)}", self.app)
        self.assertIn('cache:"no-store"', self.app)

    def test_generated_pages_links_and_navigation(self) -> None:
        pages = [OUT / name for name in ("index.html", "listed.html", "private.html", "ma.html", "tender.html", "soe.html", "watchlist.html", "images/index.html")]
        for page in pages:
            text = page.read_text(encoding="utf-8")
            self.assertIn("PREVIEW", text)
            for href in re.findall(r'href=["\']([^"\']+)', text):
                parsed = urlparse(href)
                if parsed.scheme or href.startswith(("#", "mailto:")):
                    continue
                target = (page.parent / parsed.path).resolve()
                self.assertTrue(target.exists(), f"{page.name}: {href}")
        for page in pages[:-1]:
            nav = re.search(r"<nav>(.*?)</nav>", page.read_text(encoding="utf-8"), flags=re.S)
            self.assertIsNotNone(nav)
            self.assertNotIn(">观察池</a>", nav.group(1))
            self.assertNotIn(">分享图库</a>", nav.group(1))

    def test_customer_code_has_no_hardcoded_date_or_internal_terms(self) -> None:
        customer_code = self.app + "\n" + "\n".join(
            (OUT / name).read_text(encoding="utf-8")
            for name in ("index.html", "listed.html", "private.html", "ma.html", "tender.html", "soe.html", "watchlist.html")
        )
        for forbidden in (
            "2026.07.23",
            "2026年7月23日",
            "RM",
            "配置固定",
            "日报原分类",
            "结构化",
            "候选证据",
            "overlay",
            "PUBLICATION_",
            "ANNOUNCEMENT_",
            "needs_source_backfill",
        ):
            self.assertNotIn(forbidden, customer_code)
        self.assertIn("const zhDate=", self.app)
        self.assertNotRegex(customer_code, r"2026-\d{2}-\d{2}T\d{2}:")

    def test_external_sources_open_new_tabs_and_empty_sources_are_not_links(self) -> None:
        self.assertIn('target="_blank" rel="noopener noreferrer"', self.app)
        self.assertIn('if(!rows.length)return `<span class="row-source pending-source">待核验</span>`', self.app)
        self.assertIn('row.sourceUrl?external(row.sourceUrl,row.sourceName)', self.app)

    def test_listed_page_renders_all_sources_and_falls_back_to_single_source(self) -> None:
        self.assertIn("const rows=(row.sources||[]).filter", self.app)
        self.assertIn("if(!rows.length&&row.sourceUrl)rows.push", self.app)
        self.assertIn('rows.length>1?`公告${index+1}`:"公告"', self.app)
        self.assertIn("${newsSources(row)}</article>", self.app)
        listed_page = (OUT / "listed.html").read_text(encoding="utf-8")
        self.assertIn(f"assets/app.js?v={self.data['build']['version']}", listed_page)

    def test_home_four_cards_are_latest_dated_unique_and_linked(self) -> None:
        cards = self.data["homeHighlights"]
        self.assertEqual([row["category"] for row in cards], ["上市公司", "上市公司", "证券私募", "收并购"])
        self.assertEqual(len(cards), 4)
        self.assertTrue(all(row["date"] and row["href"] for row in cards))
        self.assertEqual([row["date"] for row in cards[:2]], sorted((row["date"] for row in cards[:2]), reverse=True))
        self.assertEqual(len({row["company"] for row in cards[:2]}), 2)
        self.assertEqual([row["title"] for row in cards[:2]], ["必看｜中国西电", "重点｜爱科赛博"])
        self.assertTrue(all(row["sortBasis"] == "公告日期倒序，同日按重要度排序" for row in cards[:2]))
        self.assertIn("#listed-detail-", cards[0]["href"])
        self.assertIn("#fund-", cards[2]["href"])
        self.assertIn("#ma-", cards[3]["href"])

    def test_home_has_five_channels_and_no_watchlist_section(self) -> None:
        home_code = self.app[self.app.index("function home"):self.app.index("function listed")]
        self.assertEqual(home_code.count(',"listed.html"]'), 1)
        for href in ("private.html", "ma.html", "tender.html", "soe.html"):
            self.assertIn(href, home_code)
        self.assertNotIn("观察池概览", home_code)
        self.assertNotIn("watchlist.html", home_code)
        self.assertIn(".channel-grid", self.styles)

    def test_hero_height_contract(self) -> None:
        self.assertIn(".cover{position:relative;min-height:380px", self.styles)
        self.assertIn("[data-page=soe]", self.styles)
        self.assertIn(".cover{min-height:290px}", self.styles)

    def test_listed_source_coverage_is_verified_not_company_fallback(self) -> None:
        coverage = self.data["listed"]["sourceCoverage"]
        self.assertEqual(coverage, {"total": 29, "linked": 29, "unmatched": []})
        for row in listed_rows(self.data):
            self.assertIn(row["sourceConfidence"], {"verified-company-and-topic", "verified-exact-announcement"})
            self.assertTrue(row["sourceKeyword"])
            self.assertTrue(row["sourceUrl"].startswith("https://static.cninfo.com.cn/finalpage/"))
            self.assertTrue(row["announcementTitle"])
            self.assertTrue(row["sources"])

    def test_listed_exact_multi_announcement_mappings(self) -> None:
        daily = self.data["listed"]["daily"]
        kelong = next(row for row in daily["capital_rows"] if row["company"] == "科隆新材")
        self.assertTrue(kelong["sourceUrl"].endswith("/1225436726.PDF"))
        self.assertEqual(
            [Path(urlparse(row["sourceUrl"]).path).stem for row in kelong["sources"]],
            ["1225436726", "1225436773"],
        )
        xian_risk = next(row for row in daily["risk_rows"] if row["company"] == "西安旅游")
        self.assertEqual(
            [Path(urlparse(row["sourceUrl"]).path).stem for row in xian_risk["sources"]],
            ["1225435983", "1225435982"],
        )
        xian_meeting = next(
            row
            for group in daily["fixed_columns"]
            for row in group["items"]
            if row["title"].startswith("西安旅游｜")
        )
        self.assertTrue(xian_meeting["sourceUrl"].endswith("/1225435981.PDF"))
        self.assertIn("临时股东会", xian_meeting["announcementTitle"])

    def test_listed_aike_buyback_and_malformed_rating_removed(self) -> None:
        daily = self.data["listed"]["daily"]
        aike = [
            row
            for key in ("opportunities", "capital_rows")
            for row in daily[key]
            if "爱科赛博" in (row.get("company", "") + row.get("title", ""))
        ]
        self.assertTrue(aike)
        self.assertTrue(all(row["business"]["subcategory"] == "股份回购" for row in aike))
        self.assertNotIn("AAsti", json.dumps(self.data, ensure_ascii=False))
        laite = next(row for row in daily["capital_rows"] if row["company"] == "莱特光电")
        self.assertIn("本次可转债信用等级<b>AA</b>", laite["numbersHtml"])

    def test_listed_duplicate_events_reference_one_canonical_record(self) -> None:
        daily = self.data["listed"]["daily"]
        for company in ("中国西电", "康惠股份", "爱科赛博", "源杰科技", "泰金新能", "广电网络"):
            rows = [row for row in listed_rows(self.data) if row.get("company") == company or str(row.get("title", "")).startswith(company + "｜")]
            canonical = [row for row in rows if row.get("canonicalDetailId")]
            references = [row for row in rows if row.get("isReference")]
            self.assertEqual(len(canonical), 1, company)
            self.assertTrue(references, company)
            self.assertTrue(all(row["referenceAnchor"] == canonical[0]["canonicalDetailId"] for row in references))
        self.assertIn("newsReference", self.app)
        self.assertIn("查看主事项", self.app)

    def test_listed_focus_and_observation_pool_contract(self) -> None:
        self.assertEqual(self.data["listed"]["counts"], {"total": 110, "L1": 85, "L2": 14, "L3": 11})
        self.assertEqual(len(self.data["listed"]["entities"]), 110)
        focus = self.data["listed"]["focusCompanies"]
        self.assertEqual([row["company"] for row in focus], ["莱特光电", "科隆新材", "爱科赛博", "三角防务"])
        self.assertEqual(len({row["anchorId"] for row in focus}), 4)
        self.assertIn(".pool-scroll{height:330px;overflow:auto}", self.styles)

    def test_private_product_and_manager_counts_are_separate(self) -> None:
        private = self.data["private"]
        self.assertEqual(len(private["products"]), 33)
        self.assertEqual(len({row["managerName"] for row in private["products"]}), 23)
        self.assertEqual(len(private["managers"]), 93)
        self.assertEqual(private["managerCounts"], {
            "total": 93,
            "PF1": 88,
            "PF2": 5,
            "PF2Substantive": 3,
            "PF2Association": 2,
        })
        self.assertEqual(private["annualMonthCounts"], {
            "2026-01": 0,
            "2026-02": 0,
            "2026-03": 1,
            "2026-04": 8,
            "2026-05": 3,
            "2026-06": 12,
            "2026-07": 9,
        })

    def test_private_relation_labels_are_specific(self) -> None:
        managers = self.data["private"]["managers"]
        self.assertFalse(any("注册地或办公地在陕西" in row["relationLabel"] for row in managers))
        association = [row for row in managers if row.get("relationGroup") == "association_member"]
        self.assertEqual(len(association), 2)
        self.assertTrue(all(row["relationLabel"] == "协会会员观察（非陕西注册/办公）" for row in association))
        self.assertTrue(all("陕西办公" not in row["relation"] for row in association))
        substantive = [row for row in managers if row.get("relationGroup") == "substantive_operation_or_equity"]
        self.assertEqual(len(substantive), 3)
        self.assertTrue(all(any(label in row["relationLabel"] for label in ("实质经营", "股权关系")) for row in substantive))

    def test_private_filters_dates_and_custodian_expand(self) -> None:
        for marker in ("data-tier", "data-reset", "成立日期", "data-custodian-toggle", "custodian-extra"):
            self.assertIn(marker, self.app)
        self.assertIn('channel.custodianStats.map((row,index)', self.app)
        self.assertIn('index>=8', self.app)
        self.assertEqual(sum(row["count"] for row in self.data["private"]["custodianStats"]), 33)
        self.assertEqual(len(self.data["private"]["custodianStats"]), 14)
        self.assertEqual([(row["label"], row["count"]) for row in self.data["private"]["custodianStats"][:3]], [
            ("招商证券", 6),
            ("华泰证券", 5),
            ("中信证券", 4),
        ])

    def test_ma_source_gate_and_verified_window(self) -> None:
        ma = self.data["ma"]
        self.assertEqual(ma["sourceCoverage"], {"beforeLinked": 2, "linked": 8, "total": 25})
        self.assertEqual(len(ma["verifiedProjects"]), 8)
        self.assertEqual(len(ma["pendingProjects"]), 17)
        self.assertEqual(len(ma["window"]), 8)
        self.assertTrue(all(row["sourceVerified"] and row["sourceUrl"] for row in ma["verifiedProjects"]))
        self.assertTrue(all(not row["sourceVerified"] and not row["sourceUrl"] for row in ma["pendingProjects"]))
        self.assertEqual({row["id"] for row in ma["window"]}, {row["id"] for row in ma["verifiedProjects"]})
        self.assertEqual([row["eventDate"] for row in ma["window"]], sorted((row["eventDate"] for row in ma["window"]), reverse=True))

    def test_ma_rainbow_plan_date_is_not_event_date(self) -> None:
        row = next(item for item in self.data["ma"]["projects"] if item["id"] == "ma-rainbow-hongyang-minority-2026")
        self.assertEqual(row["eventDate"], "2026-07-07")
        self.assertEqual(row["updatedAt"], "2026-07-07")
        self.assertEqual(row["plannedNextDate"], "2026-07-20")
        self.assertIn("交割观察节点", row["plannedNextLabel"])
        self.assertNotIn("下一节点", row["importance"])
        self.assertNotEqual(row["eventDate"], row["plannedNextDate"])

    def test_ma_stage_and_customer_structure_contract(self) -> None:
        allowed = {"筹划", "审议", "协议签署", "生效条件达成", "交割中", "已完成交割", "终止"}
        self.assertTrue(all(row["stageText"] in allowed for row in self.data["ma"]["projects"]))
        supply = next(row for row in self.data["ma"]["projects"] if "供销大集收购国投农产品" in row["title"])
        self.assertEqual(supply["stageText"], "生效条件达成")
        self.assertNotEqual(supply["stageText"], "已完成交割")
        for marker in ("事实：", "为什么重要：", "关注要点：", "计划节点（待后续公告确认）"):
            self.assertIn(marker, self.app)
        self.assertIn("待补原始来源", self.app)
        self.assertNotIn("近期重点项目", self.app)

    def test_tender_five_plus_one_and_result_fields(self) -> None:
        tender = self.data["tender"]
        self.assertEqual(len(tender["projects"]), 5)
        self.assertEqual(len({row["id"] for row in tender["projects"]}), 5)
        self.assertEqual(len(tender["pending"]), 1)
        self.assertEqual(tender["pending"][0]["statusGroup"], "待回源线索")
        self.assertFalse(tender["pending"][0]["sourceUrl"])
        self.assertTrue(all(row["formalTitle"] and row["projectScale"] and row["latestProgressDate"] for row in tender["projects"]))
        self.assertEqual([row["latestProgressDate"] for row in tender["projects"]], sorted((row["latestProgressDate"] for row in tender["projects"]), reverse=True))
        rich = [row for row in tender["projects"] if row["winningOrCandidateUnits"]]
        self.assertEqual(len(rich), 4)
        self.assertTrue(any(any(unit.get("quote") for unit in row["winningOrCandidateUnits"]) for row in rich))
        for marker in ("formal-title", "tender-results", "今日可参与机会", "正在推进", "已出结果", "待回源观察"):
            self.assertIn(marker, self.app)
        self.assertNotIn("<details", self.app)

    def test_soe_uses_latest_real_period_fallback(self) -> None:
        soe = self.data["soe"]
        self.assertEqual(soe["latestRecordDate"], "2026-07-10")
        self.assertTrue(soe["isAsOfFallback"])
        self.assertEqual(len(soe["latestRecords"]), 6)
        self.assertTrue(all(row["publishedAt"] == "2026-07-10" for row in soe["latestRecords"]))
        self.assertTrue(all(row["category"] in {"资本金融", "项目资产", "产业经营", "风险治理", "综合动态"} for row in soe["latestRecords"]))
        self.assertIn("本期未识别新增，展示最近一期", self.app)

    def test_share_windows_and_page_shapes(self) -> None:
        private = self.data["private"]["window"]
        ma = self.data["ma"]["window"]
        self.assertEqual([len(page) for page in paginate(private)], [10, 10, 8])
        self.assertEqual([len(page) for page in paginate(ma)], [8])
        self.assertTrue(all("2026-04-23" <= row["filingDate"] <= "2026-07-23" for row in private))
        self.assertTrue(all(row["sourceVerified"] for row in ma))
        private_pages = sorted((OUT / "share").glob("private-detail-*.html"))
        ma_pages = sorted((OUT / "share").glob("ma-detail-*.html"))
        self.assertEqual([page.read_text(encoding="utf-8").count("<article>") for page in private_pages], [10, 10, 8])
        self.assertEqual([page.read_text(encoding="utf-8").count("<article>") for page in ma_pages], [8])
        self.assertFalse((OUT / "share" / "ma-detail-2.html").exists())

    def test_share_layout_contract_is_embedded(self) -> None:
        pages = list((OUT / "share").glob("*.html"))
        self.assertEqual(len(pages), 6)
        for page in pages:
            text = page.read_text(encoding="utf-8")
            self.assertIn("window.__shareLayout", text)
            self.assertIn("dataset.layoutOk", text)
            self.assertNotRegex(text, r"2026-\d{2}-\d{2}T\d{2}:")

    def test_ma_detail_height_adapts_to_record_count(self) -> None:
        ma_page = (OUT / "share" / "ma-detail-1.html").read_text(encoding="utf-8")
        expected_height = min(2100, max(1240, 450 + len(self.data["ma"]["window"]) * 173))
        self.assertEqual(expected_height, 1834)
        self.assertIn(f"height:{expected_height}px", ma_page)
        self.assertIn(f"const canvasHeight={expected_height}", ma_page)
        self.assertIn("450 + len(cards) * 173", (OUT / "scripts" / "build_candidate_v2.py").read_text(encoding="utf-8"))
        ten_cards = [
            {"date": "2026年7月23日", "tag": "进行中", "title": f"测试项目{i}", "fields": []}
            for i in range(10)
        ]
        ten_card_page = self.build_module.share_html("收并购", "测试", "测试", ten_cards, 2, 2, "2026-07-23", adaptive_detail_height=True)
        self.assertIn("height:2100px", ten_card_page)
        self.assertIn("const canvasHeight=2100", ten_card_page)
        with Image.open(OUT / "images" / "ma-detail-1.png") as image:
            self.assertEqual(image.size, (1242, expected_height))

    def test_isolated_from_official_v1_and_automation(self) -> None:
        build_text = (OUT / "scripts" / "build_candidate_v2.py").read_text(encoding="utf-8")
        writes = re.findall(r"\(([^\\n]+)\)\.write_text", build_text)
        self.assertTrue(writes)
        self.assertFalse(any("v1/index.html" in line for line in writes))
        self.assertFalse(any("run_morning_v1" in line for line in writes))
        self.assertEqual(self.data["build"]["script"], "v1/review-candidate-v2/scripts/build_candidate_v2.py")


if __name__ == "__main__":
    unittest.main()
