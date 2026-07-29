from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "v2" / "scripts"
LEGACY_LAYOUT_FIXTURE = (
    ROOT / "v2" / "tests" / "fixtures" / "legacy-layout"
    / "listed-official-2026-07-28.json"
)
sys.path.insert(0, str(SCRIPTS))

from listed_editorial import (  # noqa: E402
    build_editorial_report,
    build_matters,
    customer_copy_is_clean,
    normalize_pdf_text,
    text_quality_report,
)


artifacts_spec = importlib.util.spec_from_file_location("daily_artifacts", SCRIPTS / "daily_artifacts.py")
daily_artifacts = importlib.util.module_from_spec(artifacts_spec)
assert artifacts_spec.loader
artifacts_spec.loader.exec_module(daily_artifacts)

prepare_spec = importlib.util.spec_from_file_location(
    "prepare_listed_daily_quality", SCRIPTS / "prepare_listed_daily.py"
)
prepare_listed = importlib.util.module_from_spec(prepare_spec)
assert prepare_spec.loader
prepare_spec.loader.exec_module(prepare_listed)


def evidence(
    source_id: str,
    company: str,
    title: str,
    text: str,
    *,
    day: str = "2026-07-29",
) -> dict:
    return {
        "matter_id": source_id,
        "company": company,
        "title": title,
        "publishedAt": day,
        "sourceUrl": f"https://static.cninfo.com.cn/finalpage/2026-07-29/{source_id}.PDF",
        "pdfSha256": "a" * 64,
        "textSha256": "b" * 64,
        "textQuality": text_quality_report(text),
        "fullText": text,
    }


class ListedEditorialQualityTests(unittest.TestCase):
    def test_official_source_fetch_retries_a_transient_tls_reset(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def geturl(self):
                return "https://official.example/final"

            def read(self, _limit):
                return b"verified"

        with (
            mock.patch.object(
                prepare_listed,
                "urlopen",
                side_effect=[OSError("tls reset"), Response()],
            ) as fetch,
            mock.patch.object(prepare_listed.time, "sleep"),
        ):
            final_url, raw = prepare_listed.fetch_bytes("https://official.example/source")
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(final_url, "https://official.example/final")
        self.assertEqual(raw, b"verified")

    def test_mojibake_is_fail_closed_before_customer_copy(self) -> None:
        broken = (
            "– 1 – ʫ ͪ d ฿ ٙߧ ዄ΂Оப΂ f ʮ̡ IRICO GROUP NEW ENERGY COMPANY LIMITED "
            "лཫᙆ ʮ̡   ͉ʮ̡ 571 ███ 4.40 ԫ໨ԫ"
        )
        report = text_quality_report(broken)
        self.assertFalse(report["eligible"])
        self.assertIn("replacement_or_mojibake_markers", report["reasons"])

    def test_pdf_headers_and_legal_templates_are_not_customer_copy(self) -> None:
        leaked = (
            "陕西省西安市太白南路139号云图中心十五层 邮编：710065 "
            "传真/Fax:029-88360129 北京市康达（西安）律师事务所 法律意见书。"
        )
        self.assertFalse(customer_copy_is_clean(leaked))
        self.assertFalse(customer_copy_is_clean("证券代码：002267 本公司及董事会全体成员保证信息披露真实。"))

    def test_broken_entity_spacing_is_normalized_without_company_hardcode(self) -> None:
        raw = "北 京航 天时 代光 电科 技有 限公 司持 有北 京航 天兴 华科 技有 限公 司股权。"
        normalized = normalize_pdf_text(raw)
        self.assertIn("北京航天时代光电科技有限公司", normalized)
        self.assertNotIn("北 京", normalized)

    def test_same_matter_sources_are_merged(self) -> None:
        rows = [
            evidence(
                "1225445448",
                "航天电子",
                "关于资产置换暨关联交易的进展公告",
                "公司拟实施资产置换，相关标的评估结果已完成国有资产备案，本次交易构成关联交易，无需提交股东会审议。后续将签署协议并推进交割。",
            ),
            evidence(
                "1225445459",
                "航天电子",
                "西安太乙电子有限公司股东全部权益价值资产评估报告",
                "本次资产置换涉及西安太乙电子有限公司股东全部权益，评估结果已经备案，交易价格以备案结果为基础确定。",
            ),
        ]
        matters = build_matters(rows)
        self.assertEqual(len(matters), 1)
        self.assertEqual(matters[0]["matterType"], "资产置换")
        self.assertEqual(len(matters[0]["sources"]), 2)

    def test_incentive_reviews_are_combined_but_sources_remain_traceable(self) -> None:
        rows = [
            evidence(
                "1225442884",
                "炬光科技",
                "2026年限制性股票激励计划首次授予激励对象名单核查意见及公示情况说明",
                "2026年限制性股票激励计划首次授予对象已完成内部公示，公示期内未收到异议，后续将推进首次授予安排。",
            ),
            evidence(
                "1225442890",
                "炬光科技",
                "2025年限制性股票激励计划剩余预留授予激励对象名单核查意见及公示情况说明",
                "2025年限制性股票激励计划剩余预留授予对象已完成内部公示，公示期内未收到异议，后续将推进预留授予安排。",
            ),
        ]
        matters = build_matters(rows)
        self.assertEqual(len(matters), 1)
        self.assertEqual(set(matters[0]["sourceAnnouncementIds"]), {"1225442884", "1225442890"})

    def test_editorial_report_has_structured_customer_fields_and_bounded_home_copy(self) -> None:
        rows = [
            evidence(
                "1",
                "甲公司",
                "关于首次回购公司股份的公告",
                "公司首次回购股份1,200,000股，占总股本0.35%，成交金额2,360万元，后续将根据市场情况继续实施回购计划。",
            ),
            evidence(
                "2",
                "乙公司",
                "关于为全资子公司提供担保的公告",
                "公司为全资子公司新增5,000万元授信提供连带责任担保，担保期限不超过24个月，董事会已审议通过。",
            ),
        ]
        report = build_editorial_report(
            day="2026-07-29",
            evidence=rows,
            rejected=[],
            raw_summary={"companyUniverseCount": 110, "announcementCount": 2},
            hkex_company_count=14,
        )
        self.assertEqual(report["template"], "v2-listed-v1-editorial")
        self.assertGreaterEqual(len(report["opportunities"]), 2)
        for row in report["opportunities"]:
            self.assertTrue(35 <= len(row["body"]) <= 95)
            for key in ("company", "matterType", "businessSubcategory", "importance", "conclusion", "whyImportant", "sources"):
                self.assertTrue(row[key])

    def test_listed_image_uses_six_v1_sections_without_engineering_metadata(self) -> None:
        daily = json.loads(LEGACY_LAYOUT_FIXTURE.read_text(encoding="utf-8"))
        html = daily_artifacts.listed_image_html({
            "asOf": "2026-07-28",
            "listed": {"daily": daily, "counts": {"total": 110, "L1": 85, "L2": 14, "L3": 11}},
        })
        for heading in (
            "01</span>今日业务机会",
            "02</span>重大事项与风险公告",
            "03</span>上市公司动态",
            "04</span>股东变动与资本运作",
            "05</span>股东会、治理与固定披露清单",
            "06</span>今日重点跟踪公司",
        ):
            self.assertIn(heading, html)
        self.assertNotIn("构建版本", html)
        self.assertNotIn("数据与来源以 V2 当日已核验快照为准", html)

    def test_web_page_and_daily_image_keep_the_six_section_structure(self) -> None:
        app = (ROOT / "v2" / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn('"section-06","06","今日重点跟踪公司"', app)
        self.assertIn('["section-06","06 下一步"]', app)
        self.assertNotIn("历史早报正文", app)
        daily = json.loads(LEGACY_LAYOUT_FIXTURE.read_text(encoding="utf-8"))
        html = daily_artifacts.listed_image_html({
            "asOf": "2026-07-28",
            "listed": {"daily": daily, "counts": {"total": 110, "L1": 85, "L2": 14, "L3": 11}},
        })
        self.assertIn("06</span>今日重点跟踪公司", html)

    def test_css_colors_only_key_numbers_not_whole_paragraph(self) -> None:
        styles = (ROOT / "v2" / "assets" / "styles.css").read_text(encoding="utf-8")
        self.assertIn(".news-numbers{color:#304154;font-weight:400}", styles)
        self.assertIn(".news-numbers b{color:var(--red)", styles)

    def test_home_cards_have_browser_runtime_height_and_overflow_assertions(self) -> None:
        app = (ROOT / "v2" / "assets" / "app.js").read_text(encoding="utf-8")
        styles = (ROOT / "v2" / "assets" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("function assertHomeHighlightLayout()", app)
        self.assertIn("Math.max(...heights)-Math.min(...heights)>1", app)
        self.assertIn("paragraph.scrollHeight>paragraph.clientHeight+1", app)
        self.assertIn('dataset.homeLayoutVerified="true"', app)
        self.assertNotIn("-webkit-line-clamp", styles)


if __name__ == "__main__":
    unittest.main()
