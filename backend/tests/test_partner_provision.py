"""Unit tests for partner provision helpers."""

from __future__ import annotations

import unittest

from app.services.partner_provision import _slug_for_external_ref


class TestPartnerProvisionHelpers(unittest.TestCase):
    def test_slug_from_external_ref_is_stable(self) -> None:
        a = _slug_for_external_ref("deml:efeff1e1-14c6-4d13-b3fa-be4316c3f783", explicit=None)
        b = _slug_for_external_ref("deml:efeff1e1-14c6-4d13-b3fa-be4316c3f783", explicit=None)
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("deml-"))
        self.assertLessEqual(len(a), 63)

    def test_explicit_slug(self) -> None:
        self.assertEqual(
            _slug_for_external_ref("deml:abc", explicit="Acme-Tenant"),
            "acme-tenant",
        )


if __name__ == "__main__":
    unittest.main()
