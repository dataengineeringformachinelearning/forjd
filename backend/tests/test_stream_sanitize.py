"""Sealed stream sanitize + processor registry tests."""

from __future__ import annotations

import unittest

from app.services.stream import _sanitize
from app.workflows.processors import REGISTRY


class TestStreamSanitize(unittest.TestCase):
    def test_sanitize_strips_to_metadata(self) -> None:
        rows = _sanitize(
            [
                {
                    "event_id": "e1",
                    "tenant_id": "t1",
                    "key_id": "k",
                    "cipher_len": 42,
                    "ciphertext": "SHOULD_NOT_APPEAR_IN_LOGIC",
                }
            ]
        )
        self.assertEqual(rows[0]["cipher_len"], 42)
        self.assertNotIn("ciphertext", rows[0])

    def test_rust_processor_registered(self) -> None:
        self.assertIn("sealed_metadata", REGISTRY)
        self.assertIn("rust_sealed_metadata", REGISTRY)


if __name__ == "__main__":
    unittest.main()
