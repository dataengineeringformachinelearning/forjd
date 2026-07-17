"""Unit tests for audit detail sanitization (no ciphertext / secrets)."""

from __future__ import annotations

import unittest

from app.services.audit import _sanitize_details


class TestAuditSanitize(unittest.TestCase):
    def test_strips_forbidden_keys(self) -> None:
        raw = {
            "accepted": 3,
            "ciphertext": "deadbeef",
            "nonce": "abc",
            "workflow_id": "default_sealed",
            "nested": {"secret": "x", "ok": 1},
        }
        clean = _sanitize_details(raw)
        self.assertEqual(clean["accepted"], 3)
        self.assertEqual(clean["workflow_id"], "default_sealed")
        self.assertNotIn("ciphertext", clean)
        self.assertNotIn("nonce", clean)
        self.assertEqual(clean["nested"], {"ok": 1})


if __name__ == "__main__":
    unittest.main()
