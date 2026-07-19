"""Unit tests for status page helpers."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from typing import Any

from app.services.status import _overall_status, _page_dict, _public_page_dict


def _page_row() -> dict[str, Any]:
    now = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "22222222-2222-2222-2222-222222222222",
        "slug": "acme-status",
        "title": "Acme",
        "description": "Public status",
        "is_published": True,
        "created_at": now,
        "updated_at": now,
    }


class TestOverallStatus(unittest.TestCase):
    def test_empty_operational(self) -> None:
        self.assertEqual(_overall_status([]), "operational")

    def test_worst_wins(self) -> None:
        self.assertEqual(
            _overall_status(["operational", "degraded", "major_outage"]),
            "major_outage",
        )


class TestPublicPageDict(unittest.TestCase):
    def test_authenticated_page_dict_includes_tenant_id(self) -> None:
        page = _page_dict(_page_row())
        self.assertEqual(page["tenant_id"], "22222222-2222-2222-2222-222222222222")
        self.assertEqual(page["slug"], "acme-status")

    def test_public_page_dict_omits_tenant_id(self) -> None:
        page = _public_page_dict(_page_row())
        self.assertNotIn("tenant_id", page)
        self.assertEqual(page["slug"], "acme-status")
        self.assertEqual(page["title"], "Acme")
        self.assertTrue(page["is_published"])


if __name__ == "__main__":
    unittest.main()
