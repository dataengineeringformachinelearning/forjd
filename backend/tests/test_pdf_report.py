"""Suite Role C PDF report tokens and styled-report structure."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.services import exports, pdf_report

TOKEN_FILE = Path(__file__).resolve().parents[1] / "static" / "fjord-report-tokens.json"


class TestPdfReportSuiteTokens(unittest.TestCase):
    def setUp(self) -> None:
        pdf_report.load_pdf_report_theme.cache_clear()

    def tearDown(self) -> None:
        pdf_report.load_pdf_report_theme.cache_clear()

    def test_role_c_tokens_align_with_suite_chrome(self) -> None:
        tokens = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        self.assertEqual(tokens["meta"]["role"], "C")
        self.assertEqual(tokens["color"]["electric"]["500"], "#2176ff")
        self.assertEqual(tokens["color"]["gold"]["500"], "#d4af37")
        self.assertEqual(tokens["color"]["brand"]["blue"], "#0078ff")
        self.assertEqual(tokens["color"]["brand"]["navy"], "#070c20")
        self.assertNotIn("--fj-space-20", tokens["chart"]["plotHeight"])
        self.assertNotIn("--fj-space-24", tokens["chart"]["plotHeight"])

    def test_theme_resolves_suite_primary_and_institutional_gold(self) -> None:
        theme = pdf_report.load_pdf_report_theme()
        self.assertEqual(theme.primary, (0x21 / 255, 0x76 / 255, 0xFF / 255))
        self.assertEqual(theme.gold, (0xD4 / 255, 0xAF / 255, 0x37 / 255))
        self.assertEqual(theme.brand_blue, (0x00 / 255, 0x78 / 255, 0xFF / 255))
        self.assertEqual(theme.brand_navy, (0x07 / 255, 0x0C / 255, 0x20 / 255))

    def test_render_is_styled_report_not_csv_wrapper(self) -> None:
        rows = [
            {"site": "https://example.com", "score": 0.91, "status": "ok"},
            {"site": "https://demo.example", "score": 0.42, "status": "warn"},
        ]
        artifact = pdf_report.render_pdf_report(
            rows,
            title="Analytics Report",
            metadata={
                "Reporting window": "Last 30 days",
                "Scope": "https://example.com",
            },
        )
        self.assertTrue(artifact.startswith(b"%PDF"))
        self.assertIn(b"/Marked true", artifact)
        self.assertIn(b"/StructTreeRoot", artifact)
        self.assertIn(b"Analytics Report", artifact)
        self.assertIn(b"FORJD", artifact)
        self.assertIn(b"DATA ENGINEERING FOR MACHINE LEARNING", artifact)
        self.assertIn(b"REPORT DATA", artifact)
        self.assertIn(b"RECORDS", artifact)
        self.assertIn(b"REPORTING WINDOW", artifact)
        self.assertIn(b"Last 30 days", artifact)
        self.assertIn(b"CONFIDENTIAL OPERATIONAL REPORT", artifact)
        # Raw CSV dump would be plain text/comma rows — styled report is PDF operators.
        self.assertNotIn(b"site,score,status\n", artifact)


class TestPdfExportMetadata(unittest.TestCase):
    def test_pdf_title_and_metadata_follow_source_kind(self) -> None:
        self.assertEqual(exports._pdf_report_title("analytics"), "Analytics Report")
        self.assertEqual(exports._pdf_report_title("vulnerabilities"), "Vulnerability Report")
        metadata = exports._pdf_report_metadata(
            "analytics",
            {"days": 90, "site_url": "https://tenant.example"},
        )
        self.assertEqual(metadata["Reporting window"], "Last 90 days")
        self.assertEqual(metadata["Scope"], "https://tenant.example")
        self.assertEqual(metadata["Source"], "Analytics")

    def test_render_export_pdf_uses_styled_title(self) -> None:
        artifact = exports._render_export(
            [{"id": "one", "score": 1}],
            "pdf",
            source_kind="threat",
            filters={"days": 7},
        )
        self.assertTrue(artifact.startswith(b"%PDF"))
        self.assertIn(b"Threat Intelligence Report", artifact)
        self.assertIn(b"Last 7 days", artifact)


if __name__ == "__main__":
    unittest.main()
