"""Unit tests for STIX ipv4 indicator parsing."""

from __future__ import annotations

import unittest

from app.services.threat_intel import parse_stix_ipv4_indicators


class TestTaxiiParse(unittest.TestCase):
    def test_extracts_ipv4(self) -> None:
        objects = [
            {
                "type": "indicator",
                "pattern": "[ipv4-addr:value = '198.51.100.1']",
            },
            {"type": "malware", "name": "x"},
        ]
        out = parse_stix_ipv4_indicators(objects)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["ip_address"], "198.51.100.1")


if __name__ == "__main__":
    unittest.main()
