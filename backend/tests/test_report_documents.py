"""Contract and security tests for tenant-scoped report documents."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.auth import AuthUser, PrincipalKind, get_current_user
from app.main import app
from app.models.reports import CreateReportDocumentRequest
from app.services import report_documents
from app.services.service_accounts import ALLOWED_SCOPES, DEFAULT_SCOPES
from app.services.tenant_erase import _ERASE_TABLES

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_TENANT_ID = UUID("22222222-2222-2222-2222-222222222222")
ACTOR_ID = "33333333-3333-3333-3333-333333333333"
CLIENT_REPORT_ID = UUID("44444444-4444-4444-4444-444444444444")


def _service(*scopes: str, tenant_id: UUID = TENANT_ID) -> AuthUser:
    return AuthUser(
        user_id=ACTOR_ID,
        email=None,
        role="service",
        raw_claims={},
        kind=PrincipalKind.SERVICE,
        tenant_id=str(tenant_id),
        scopes=frozenset(scopes),
    )


def _document(**overrides: object) -> CreateReportDocumentRequest:
    values: dict[str, object] = {
        "tenant_id": TENANT_ID,
        "client_report_id": CLIENT_REPORT_ID,
        "kind": "issue_report",
        "title": "Learner-reported issue",
        "body": "The lesson instructions are unclear on step three.",
        "context": {"route": "/account", "user_agent": "Mozilla/5.0"},
        "submitted_by_pseudonym": "acct:7f3a",
    }
    values.update(overrides)
    return CreateReportDocumentRequest.model_validate(values)


class TestDocumentContract(unittest.TestCase):
    def test_accepts_bounded_partner_issue_report(self) -> None:
        document = _document()
        self.assertEqual(document.kind, "issue_report")
        self.assertEqual(document.context["route"], "/account")

    def test_rejects_direct_identifiers_and_credentials(self) -> None:
        with self.assertRaises(ValidationError):
            _document(body="Contact me at person@example.com")
        with self.assertRaises(ValidationError):
            _document(body="Header was Bearer abc123def456")
        with self.assertRaises(ValidationError):
            _document(submitted_by_pseudonym="person@example.com")
        with self.assertRaises(ValidationError):
            _document(context={"password": "hunter2"})
        with self.assertRaises(ValidationError):
            _document(context={"raw_payload": "anything"})

    def test_rejects_unknown_fields_and_bad_kind(self) -> None:
        values = _document().model_dump(mode="json")
        values["ciphertext"] = "never"
        with self.assertRaises(ValidationError):
            CreateReportDocumentRequest.model_validate(values)
        with self.assertRaises(ValidationError):
            _document(kind="Not A Kind!")

    def test_body_is_bounded(self) -> None:
        with self.assertRaises(ValidationError):
            _document(body="x" * 8001)


class TestScopesAndErase(unittest.TestCase):
    def test_default_scopes_cover_report_documents(self) -> None:
        self.assertIn("reports:read", DEFAULT_SCOPES)
        self.assertIn("reports:write", DEFAULT_SCOPES)
        self.assertIn("reports:write", ALLOWED_SCOPES)

    def test_tenant_erase_covers_report_documents(self) -> None:
        self.assertIn("report_documents", _ERASE_TABLES)
        self.assertIn("correlation_receipts", _ERASE_TABLES)
        self.assertIn("threat_reports", _ERASE_TABLES)


class TestTenantIsolation(unittest.IsolatedAsyncioTestCase):
    async def test_cross_tenant_service_write_is_rejected_before_db(self) -> None:
        # Tenant binding fails closed before any pool interaction (pool=None).
        with self.assertRaises(HTTPException) as ctx:
            await report_documents.create_document(
                None,  # type: ignore[arg-type]
                user=_service("reports:write", tenant_id=OTHER_TENANT_ID),
                document=_document(),
            )
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_missing_scope_is_rejected_before_db(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await report_documents.create_document(
                None,  # type: ignore[arg-type]
                user=_service("status:read"),
                document=_document(),
            )
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_list_requires_read_scope(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await report_documents.list_documents(
                None,  # type: ignore[arg-type]
                user=_service("ingest:write"),
                tenant_id=TENANT_ID,
            )
        self.assertEqual(ctx.exception.status_code, 403)


class TestHttpEndToEnd(unittest.IsolatedAsyncioTestCase):
    """Full HTTP path: routing → auth dependency → validation → service → SQL."""

    async def _request(self, pool: AsyncMock, json_body: dict[str, object]) -> httpx.Response:
        app.dependency_overrides[get_current_user] = lambda: _service(
            "reports:write", "reports:read"
        )
        app.state.db_pool = pool
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                return await client.post("/api/v1/reports/documents", json=json_body)
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.state.db_pool = None

    async def test_create_document_over_http_persists_tenant_bound_row(self) -> None:
        pool = AsyncMock()
        pool.fetchrow.return_value = {
            "id": "55555555-5555-5555-5555-555555555555",
            "tenant_id": str(TENANT_ID),
            "client_report_id": str(CLIENT_REPORT_ID),
            "content_sha256": report_documents._content_fingerprint(_document()),
            "kind": "issue_report",
            "title": "Learner-reported issue",
            "body": "The lesson instructions are unclear on step three.",
            "context": {"route": "/account"},
            "submitted_by_pseudonym": "acct:7f3a",
            "created_at": datetime.now(UTC),
        }
        with (
            patch.object(report_documents, "ensure_report_documents_schema", new=AsyncMock()),
            patch.object(report_documents.audit, "record", new=AsyncMock()),
        ):
            response = await self._request(pool, _document().model_dump(mode="json"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["duplicate"])
        self.assertEqual(payload["document"]["tenant_id"], str(TENANT_ID))
        insert_sql = pool.fetchrow.call_args.args[0]
        self.assertIn("INSERT INTO report_documents", insert_sql)
        self.assertEqual(pool.fetchrow.call_args.args[1], str(TENANT_ID))

    async def test_http_rejects_pii_payload_before_any_db_write(self) -> None:
        pool = AsyncMock()
        body = _document().model_dump(mode="json")
        body["body"] = "Contact person@example.com"
        response = await self._request(pool, body)
        self.assertEqual(response.status_code, 422)
        pool.fetchrow.assert_not_called()

    async def test_exact_client_report_replay_is_idempotent(self) -> None:
        existing = {
            "id": "55555555-5555-5555-5555-555555555555",
            "tenant_id": str(TENANT_ID),
            "client_report_id": str(CLIENT_REPORT_ID),
            "content_sha256": report_documents._content_fingerprint(_document()),
            "kind": "issue_report",
            "title": "Learner-reported issue",
            "body": "The lesson instructions are unclear on step three.",
            "context": {"route": "/account", "user_agent": "Mozilla/5.0"},
            "submitted_by_pseudonym": "acct:7f3a",
            "created_at": datetime.now(UTC),
        }
        pool = AsyncMock()
        pool.fetchrow.side_effect = [None, existing]
        with (
            patch.object(report_documents, "ensure_report_documents_schema", new=AsyncMock()),
            patch.object(report_documents.audit, "record", new=AsyncMock()) as audit_record,
        ):
            response = await self._request(pool, _document().model_dump(mode="json"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["duplicate"])
        audit_record.assert_not_awaited()

    async def test_client_report_key_reuse_with_changed_content_conflicts(self) -> None:
        existing = {
            "id": "55555555-5555-5555-5555-555555555555",
            "tenant_id": str(TENANT_ID),
            "client_report_id": str(CLIENT_REPORT_ID),
            "content_sha256": "0" * 64,
            "kind": "issue_report",
            "title": "Earlier report",
            "body": "Earlier body",
            "context": {},
            "submitted_by_pseudonym": "acct:7f3a",
            "created_at": datetime.now(UTC),
        }
        pool = AsyncMock()
        pool.fetchrow.side_effect = [None, existing]
        with (
            patch.object(report_documents, "ensure_report_documents_schema", new=AsyncMock()),
            patch.object(report_documents.audit, "record", new=AsyncMock()),
        ):
            response = await self._request(pool, _document().model_dump(mode="json"))
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
