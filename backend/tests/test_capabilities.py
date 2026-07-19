"""Headless contract and ML scope regression tests."""

from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.api.v1.capabilities import CONTRACT_VERSION, build_capability_document
from app.api.v1.ml import _require_catalog_scope
from app.core.auth import AuthUser, PrincipalKind
from app.main import app


class TestCapabilityContract(unittest.TestCase):
    def test_contract_only_advertises_mounted_surfaces(self) -> None:
        document = build_capability_document(app.openapi())
        self.assertEqual(document["contract_version"], CONTRACT_VERSION)
        self.assertEqual(document["service"], "forjd")
        self.assertTrue(document["authentication"]["tenant_bound"])
        self.assertIn("report_documents", document["capabilities"])
        for capability in document["capabilities"].values():
            self.assertTrue(capability["available"], capability.get("missing"))

    def test_missing_route_fails_closed(self) -> None:
        document = build_capability_document({"paths": {}})
        self.assertFalse(document["capabilities"]["siem"]["available"])
        self.assertIn("missing", document["capabilities"]["siem"])


class TestMlCatalogScope(unittest.TestCase):
    def _service(self, *scopes: str) -> AuthUser:
        return AuthUser(
            user_id="11111111-1111-1111-1111-111111111111",
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id="22222222-2222-2222-2222-222222222222",
            scopes=frozenset(scopes),
        )

    def test_service_catalog_requires_ml_read(self) -> None:
        with self.assertRaises(HTTPException) as error:
            _require_catalog_scope(self._service("ingest:write"))
        self.assertEqual(error.exception.status_code, 403)
        _require_catalog_scope(self._service("ml:read"))


if __name__ == "__main__":
    unittest.main()
