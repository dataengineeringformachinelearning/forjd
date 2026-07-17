"""Unit tests for projection event contract helpers."""

from __future__ import annotations

import unittest

from app.workflows.event_contract import (
    projection_payload_hash,
    validate_idempotency_key,
)


class TestEventContract(unittest.TestCase):
    def test_valid_key(self) -> None:
        key = validate_idempotency_key("abcdef0123456789")
        self.assertEqual(key, "abcdef0123456789")

    def test_rejects_short_key(self) -> None:
        with self.assertRaises(ValueError):
            validate_idempotency_key("short")

    def test_payload_hash_stable(self) -> None:
        a = projection_payload_hash("upsert", {"b": 2, "a": 1})
        b = projection_payload_hash("upsert", {"a": 1, "b": 2})
        self.assertEqual(a, b)

    def test_payload_hash_changes_with_action(self) -> None:
        a = projection_payload_hash("upsert", {"x": 1})
        b = projection_payload_hash("delete", {"x": 1})
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
