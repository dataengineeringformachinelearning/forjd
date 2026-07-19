"""Security and contract tests for the headless SIEM/SOAR foundation."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import threat_intel as threat_api
from app.api.v1.domain import SecurityAlertRequest
from app.core.auth import AuthUser, PrincipalKind
from app.core.config import settings
from app.models.domain import CorrelateRequest, PlaybookActionIn, TaxiiIngestRequest
from app.models.siem import CreateSecuritySignalRequest
from app.services import assets, audit, playbooks, security_ingest, siem, soc, threat_intel
from app.services.service_accounts import ALLOWED_SCOPES, DEFAULT_SCOPES

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_TENANT_ID = UUID("22222222-2222-2222-2222-222222222222")
ACTOR_ID = "33333333-3333-3333-3333-333333333333"


def _service(*scopes: str) -> AuthUser:
    return AuthUser(
        user_id=ACTOR_ID,
        email=None,
        role="service",
        raw_claims={},
        kind=PrincipalKind.SERVICE,
        tenant_id=str(TENANT_ID),
        scopes=frozenset(scopes),
    )


def _human(*, platform_admin: bool = False) -> AuthUser:
    forjd = {"platform_admin": True} if platform_admin else {}
    return AuthUser(
        user_id=ACTOR_ID,
        email="operator@example.invalid",
        role="authenticated",
        raw_claims={"app_metadata": {"forjd": forjd}},
    )


def _signal(**overrides: object) -> CreateSecuritySignalRequest:
    values: dict[str, object] = {
        "tenant_id": TENANT_ID,
        "client_signal_id": "guardduty:evt-001",
        "observed_at": datetime(2026, 7, 19, 12, 0, tzinfo=UTC),
        "source": "guardduty",
        "category": "threat_intelligence",
        "signal_type": "network.malicious_ip",
        "severity": "high",
        "title": "Known malicious endpoint contacted",
        "summary": "Normalized edge finding",
        "confidence": 90,
        "observables": [{"type": "ipv4", "value": "198.51.100.10", "role": "destination"}],
        "metadata": {"threat_match": True, "abuse_confidence_score": 90},
        "correlate": False,
        "run_playbooks": False,
    }
    values.update(overrides)
    return CreateSecuritySignalRequest.model_validate(values)


class TestScopePolicy(unittest.TestCase):
    def test_defaults_cover_headless_siem_but_not_admin_or_ml_training(self) -> None:
        required = {
            "siem:read",
            "siem:write",
            "cases:read",
            "cases:write",
            "playbooks:read",
            "playbooks:write",
            "playbooks:execute",
            "threat-intel:read",
        }
        self.assertTrue(required.issubset(DEFAULT_SCOPES))
        self.assertNotIn("threat-intel:write", DEFAULT_SCOPES)
        self.assertNotIn("ml:write", DEFAULT_SCOPES)
        self.assertIn("threat-intel:write", ALLOWED_SCOPES)
        self.assertIn("ml:read", DEFAULT_SCOPES)
        self.assertIn("ml:read", ALLOWED_SCOPES)
        self.assertIn("ml:write", ALLOWED_SCOPES)


class TestLegacyAlertBridge(unittest.IsolatedAsyncioTestCase):
    def test_client_key_and_observed_time_are_required(self) -> None:
        with self.assertRaises(ValidationError):
            SecurityAlertRequest.model_validate(
                {
                    "tenant_id": TENANT_ID,
                    "source": "deml",
                    "severity": "high",
                    "title": "Normalized alert",
                }
            )

    async def test_bridge_routes_through_idempotent_signal_core(self) -> None:
        observed_at = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
        result = {
            "signal": {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
            "duplicate": True,
            "matches": [{"rule_id": "known-malicious"}],
            "case": {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"},
            "playbook_runs": [],
        }
        pool = AsyncMock()
        with (
            patch.object(
                security_ingest.tenant_svc,
                "require_tenant_access",
                new=AsyncMock(),
            ),
            patch.object(
                security_ingest.siem_svc,
                "create_signal",
                new=AsyncMock(return_value=result),
            ) as create_signal,
        ):
            response = await security_ingest.ingest_security_alert(
                pool,
                user=_service(
                    "integrations:write",
                    "siem:write",
                    "cases:write",
                    "playbooks:execute",
                ),
                tenant_id=TENANT_ID,
                client_alert_id="detector:evt-1",
                observed_at=observed_at,
                source="deml",
                severity="high",
                title="Normalized alert",
                ip_address="198.51.100.10",
                raw={"threat_match": True},
            )
        signal = create_signal.await_args.kwargs["signal"]
        self.assertEqual(signal.client_signal_id, "security-alert:detector:evt-1")
        self.assertEqual(signal.observed_at, observed_at)
        self.assertTrue(signal.correlate)
        self.assertTrue(signal.run_playbooks)
        self.assertTrue(response["duplicate"])
        self.assertTrue(response["deprecated_contract"])


class TestCorrelationReceipts(unittest.IsolatedAsyncioTestCase):
    async def test_exact_receipt_replay_resolves_existing_id(self) -> None:
        receipt_id = UUID("77777777-7777-7777-7777-777777777777")
        digest = "a" * 64
        pool = AsyncMock()
        pool.fetchrow.side_effect = [
            None,
            {"id": str(receipt_id), "request_sha256": digest},
        ]
        with patch.object(threat_intel, "ensure_threat_schema", new=AsyncMock()):
            resolved, created = await threat_intel.claim_correlation_receipt(
                pool,
                tenant_id=TENANT_ID,
                idempotency_key="correlate:evt-1",
                request_sha256=digest,
                actor_id=ACTOR_ID,
            )
        self.assertEqual(resolved, receipt_id)
        self.assertFalse(created)
        self.assertIn("tenant_id = $1::uuid", pool.fetchrow.await_args.args[0])

    async def test_receipt_key_reuse_with_changed_payload_conflicts(self) -> None:
        pool = AsyncMock()
        pool.fetchrow.side_effect = [
            None,
            {
                "id": "77777777-7777-7777-7777-777777777777",
                "request_sha256": "b" * 64,
            },
        ]
        with (
            patch.object(threat_intel, "ensure_threat_schema", new=AsyncMock()),
            self.assertRaises(HTTPException) as error,
        ):
            await threat_intel.claim_correlation_receipt(
                pool,
                tenant_id=TENANT_ID,
                idempotency_key="correlate:evt-1",
                request_sha256="a" * 64,
                actor_id=ACTOR_ID,
            )
        self.assertEqual(error.exception.status_code, 409)

    async def test_completed_correlation_replays_prior_result_without_current_rules(self) -> None:
        receipt_id = UUID("77777777-7777-7777-7777-777777777777")
        prior = {
            "matches": [{"rule_id": "prior-rule"}],
            "case": {"id": "case-prior"},
            "playbooks": [{"id": "run-prior"}],
        }
        pool = AsyncMock()
        body = CorrelateRequest(
            tenant_id=TENANT_ID,
            context={"event_type": "security_signal"},
            run_playbooks=True,
            idempotency_key="correlate:evt-1",
        )
        with (
            patch.object(threat_api, "pool_from_request", return_value=pool),
            patch.object(threat_api.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(threat_api.audit, "record_required", new=AsyncMock()),
            patch.object(
                threat_api.threat_svc,
                "claim_correlation_receipt",
                new=AsyncMock(return_value=(receipt_id, False)),
            ),
            patch.object(
                threat_api.threat_svc,
                "get_correlation_receipt_state",
                new=AsyncMock(return_value={"status": "completed", "result_snapshot": prior}),
            ),
            patch.object(threat_api, "evaluate_correlation_rules") as evaluate,
            patch.object(threat_api.soc_svc, "open_case_from_context", new=AsyncMock()) as case,
            patch.object(
                threat_api.playbook_svc,
                "run_matching_playbooks",
                new=AsyncMock(),
            ) as run,
        ):
            result = await threat_api.correlate(
                SimpleNamespace(),
                body,
                _service("siem:write", "cases:write", "playbooks:execute"),
            )
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["matches"], prior["matches"])
        self.assertEqual(result["case"], prior["case"])
        self.assertEqual(result["playbooks"], prior["playbooks"])
        evaluate.assert_not_called()
        case.assert_not_awaited()
        run.assert_not_awaited()


class TestRequiredAudit(unittest.IsolatedAsyncioTestCase):
    async def test_required_audit_propagates_storage_failure(self) -> None:
        pool = AsyncMock()
        pool.execute.side_effect = RuntimeError("audit unavailable")
        with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
            await audit.record_required(
                pool,
                action="playbook.action_retry",
                actor_user_id=ACTOR_ID,
                tenant_id=TENANT_ID,
                resource_type="playbook_action_result",
                resource_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                details={"status": "retry_scheduled"},
            )


class TestSignalContract(unittest.TestCase):
    def test_rejects_raw_secret_and_direct_identifier_fields(self) -> None:
        with self.assertRaises(ValidationError):
            _signal(metadata={"raw_payload": "anything"})
        with self.assertRaises(ValidationError):
            _signal(metadata={"api_token": "anything"})
        with self.assertRaises(ValidationError):
            _signal(metadata={"provider": {"password": "anything"}})
        with self.assertRaises(ValidationError):
            _signal(title="Login for person@example.com")

    def test_bounded_behavioral_context_remains_supported(self) -> None:
        signal = _signal(metadata={"behavioral": {"scroll_depth_pct": 2, "session_duration_s": 3}})
        self.assertEqual(signal.metadata["behavioral"]["scroll_depth_pct"], 2)

    def test_rejects_unknown_fields_and_unbounded_observables(self) -> None:
        values = _signal().model_dump(mode="json")
        values["ciphertext"] = "never"
        with self.assertRaises(ValidationError):
            CreateSecuritySignalRequest.model_validate(values)
        with self.assertRaises(ValidationError):
            _signal(observables=[{"type": "file_sha256", "value": "not-a-hash"}])

    def test_processing_flags_do_not_change_content_idempotency_hash(self) -> None:
        first = _signal(correlate=False, run_playbooks=False)
        second = _signal(correlate=True, run_playbooks=True)
        self.assertEqual(siem._content_sha256(first), siem._content_sha256(second))


class TestPlatformAndOutboundSecurity(unittest.IsolatedAsyncioTestCase):
    async def test_taxii_scope_must_be_explicit_and_well_formed(self) -> None:
        with self.assertRaises(ValidationError):
            TaxiiIngestRequest.model_validate(
                {"collection_url": "https://taxii.example.test", "source": "vendor"}
            )
        with self.assertRaises(ValidationError):
            TaxiiIngestRequest.model_validate(
                {
                    "collection_url": "https://taxii.example.test",
                    "source": "vendor",
                    "tenant_id": TENANT_ID,
                    "is_platform": True,
                }
            )

    async def test_platform_mutation_requires_human_admin_claim(self) -> None:
        with self.assertRaises(HTTPException):
            threat_intel.require_platform_admin(_service("*"))
        with self.assertRaises(HTTPException):
            threat_intel.require_platform_admin(_human())
        self.assertIsNotNone(threat_intel.require_platform_admin(_human(platform_admin=True)))

    async def test_ssrf_rejects_loopback_and_private_dns(self) -> None:
        with self.assertRaises(ValueError):
            await threat_intel.validate_outbound_url(
                "http://127.0.0.1/internal",
                purpose="test",
            )
        loop = asyncio.get_running_loop()
        with (
            patch.object(
                loop,
                "getaddrinfo",
                new=AsyncMock(return_value=[(2, 1, 6, "", ("10.0.0.5", 443))]),
            ),
            self.assertRaises(ValueError),
        ):
            await threat_intel.validate_outbound_url(
                "https://collector.example.test/taxii",
                purpose="test",
            )

    async def test_production_requires_https(self) -> None:
        with (
            patch.object(settings, "ENVIRONMENT", "production"),
            self.assertRaises(ValueError),
        ):
            await threat_intel.validate_outbound_url(
                "http://8.8.8.8/hook",
                purpose="webhook",
            )

    async def test_production_allowlist_fails_closed_and_honors_suffix_boundaries(self) -> None:
        self.assertTrue(
            threat_intel.host_matches_outbound_allowlist(
                "tenant.hooks.example.com",
                "taxii.vendor.com,*.hooks.example.com",
            )
        )
        self.assertFalse(
            threat_intel.host_matches_outbound_allowlist(
                "hooks.example.com",
                "*.hooks.example.com",
            )
        )
        self.assertFalse(
            threat_intel.host_matches_outbound_allowlist(
                "evilhooks.example.com",
                "*.hooks.example.com",
            )
        )
        with (
            patch.object(settings, "ENVIRONMENT", "production"),
            patch.object(settings, "OUTBOUND_HOST_ALLOWLIST", ""),
            self.assertRaises(ValueError),
        ):
            await threat_intel.validate_outbound_url(
                "https://8.8.8.8/hook",
                purpose="webhook",
            )

    async def test_ssrf_rejects_ipv4_mapped_loopback(self) -> None:
        with self.assertRaises(ValueError):
            await threat_intel.validate_outbound_url(
                "http://[::ffff:127.0.0.1]/internal",
                purpose="test",
            )

    async def test_taxii_redirect_and_oversized_response_are_rejected(self) -> None:
        redirect = httpx.Response(302, headers={"location": "https://elsewhere.example"})
        with self.assertRaises(ValueError):
            await threat_intel._read_taxii_response(redirect)
        oversized = httpx.Response(
            200,
            content=b"x" * (threat_intel._MAX_TAXII_RESPONSE_BYTES + 1),
            request=httpx.Request("GET", "https://taxii.example.test/collection"),
        )
        with self.assertRaises(ValueError):
            await threat_intel._read_taxii_response(oversized)

    async def test_service_lookup_cannot_cross_tenant(self) -> None:
        with self.assertRaises(HTTPException) as error:
            await threat_intel.lookup_ip(
                AsyncMock(),
                user=_service("threat-intel:read"),
                ip_address="198.51.100.10",
                tenant_id=OTHER_TENANT_ID,
            )
        self.assertEqual(error.exception.status_code, 403)


class TestTenantOwnedUpdates(unittest.IsolatedAsyncioTestCase):
    async def test_case_patch_filters_by_case_and_tenant(self) -> None:
        case_id = UUID("44444444-4444-4444-4444-444444444444")
        row = {
            "id": str(case_id),
            "tenant_id": str(TENANT_ID),
            "title": "Updated",
            "description": "",
            "status": "investigating",
            "severity": "high",
            "assigned_actor_id": None,
            "source_signal_id": None,
            "source_correlation_id": None,
            "correlation_rule_ids": [],
            "metadata": {},
            "created_by_actor_id": ACTOR_ID,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        pool = AsyncMock()
        pool.fetchrow.return_value = row
        with (
            patch.object(soc.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(soc, "ensure_soc_schema", new=AsyncMock()),
            patch.object(soc.audit, "record_required", new=AsyncMock()),
        ):
            result = await soc.update_case(
                pool,
                user=_service("cases:write"),
                tenant_id=TENANT_ID,
                case_id=case_id,
                updates={"title": "Updated", "status": "investigating"},
            )
        query = pool.fetchrow.call_args.args[0]
        self.assertIn("id = $1::uuid AND tenant_id = $2::uuid", query)
        self.assertEqual(pool.fetchrow.call_args.args[1:3], (str(case_id), str(TENANT_ID)))
        self.assertEqual(result["title"], "Updated")

    async def test_vulnerability_patch_rejects_cross_tenant_asset(self) -> None:
        pool = AsyncMock()
        pool.fetchval.return_value = False
        with (
            patch.object(assets.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(assets, "ensure_asset_schema", new=AsyncMock()),
            self.assertRaises(HTTPException) as error,
        ):
            await assets.update_vulnerability(
                pool,
                user=_service("vulnerabilities:write"),
                tenant_id=TENANT_ID,
                vulnerability_id=UUID("55555555-5555-5555-5555-555555555555"),
                updates={"asset_id": UUID("66666666-6666-6666-6666-666666666666")},
            )
        self.assertEqual(error.exception.status_code, 404)

    async def test_case_patch_rejects_actor_outside_tenant(self) -> None:
        pool = AsyncMock()
        pool.fetchval.return_value = False
        with (
            patch.object(soc.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(soc, "ensure_soc_schema", new=AsyncMock()),
            self.assertRaises(HTTPException) as error,
        ):
            await soc.update_case(
                pool,
                user=_service("cases:write"),
                tenant_id=TENANT_ID,
                case_id=UUID("44444444-4444-4444-4444-444444444444"),
                updates={"assigned_actor_id": UUID("66666666-6666-6666-6666-666666666666")},
            )
        self.assertEqual(error.exception.status_code, 404)


class TestSiemReadiness(unittest.IsolatedAsyncioTestCase):
    async def test_sql_025_replay_receipt_and_indexes_are_required(self) -> None:
        pool = AsyncMock()
        pool.fetch.side_effect = [
            [{"relname": "security_signals"}, {"relname": "correlation_receipts"}],
            [
                {"table_name": table, "column_name": column}
                for table, column in siem._REQUIRED_REPLAY_COLUMNS
                if (table, column) != ("correlation_receipts", "result_snapshot")
            ],
            [{"indexname": name} for name in siem._REQUIRED_REPLAY_INDEXES],
            [{"conname": name} for name in siem._REQUIRED_REPLAY_CONSTRAINTS],
        ]
        with (
            patch.object(siem.tenant_svc, "ensure_secure_schema", new=AsyncMock()),
            patch.object(siem.settings, "SOFT_MIGRATE_SCHEMA", False),
            self.assertRaisesRegex(
                RuntimeError,
                "column:correlation_receipts.result_snapshot",
            ),
        ):
            await siem.ensure_siem_schema(pool)


class TestSignalAndRunIdempotency(unittest.IsolatedAsyncioTestCase):
    async def test_completed_duplicate_signal_replays_snapshot_without_new_automation(self) -> None:
        signal = _signal()
        row = {
            "id": "77777777-7777-7777-7777-777777777777",
            "tenant_id": str(TENANT_ID),
            "client_signal_id": signal.client_signal_id,
            "content_sha256": siem._content_sha256(signal),
            "observed_at": signal.observed_at,
            "source": signal.source,
            "category": signal.category,
            "signal_type": signal.signal_type,
            "severity": signal.severity,
            "title": signal.title,
            "summary": signal.summary,
            "confidence": signal.confidence,
            "observables": [item.model_dump(mode="json") for item in signal.observables],
            "metadata": signal.metadata,
            "processing_status": "completed",
            "processing_result": {
                "matches": [{"rule_id": "prior-rule"}],
                "case": {"id": "case-prior"},
                "playbook_runs": [{"id": "run-prior"}],
            },
            "processing_completed_at": datetime.now(UTC),
            "created_by_actor_id": ACTOR_ID,
            "created_at": datetime.now(UTC),
        }
        pool = AsyncMock()
        pool.fetchrow.side_effect = [None, row]
        with (
            patch.object(siem.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(siem, "ensure_siem_schema", new=AsyncMock()),
            patch.object(siem.soc_svc, "open_case_from_context", new=AsyncMock()) as open_case,
            patch.object(siem.playbook_svc, "run_matching_playbooks", new=AsyncMock()) as run,
            patch.object(siem, "evaluate_correlation_rules") as evaluate,
        ):
            result = await siem.create_signal(pool, user=_service("siem:write"), signal=signal)
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["matches"], [{"rule_id": "prior-rule"}])
        self.assertEqual(result["case"], {"id": "case-prior"})
        self.assertEqual(result["playbook_runs"], [{"id": "run-prior"}])
        evaluate.assert_not_called()
        open_case.assert_not_awaited()
        run.assert_not_awaited()

    async def test_duplicate_signal_can_heal_idempotent_case_and_run_processing(self) -> None:
        signal = _signal(correlate=True, run_playbooks=True)
        signal_id = "77777777-7777-7777-7777-777777777777"
        row = {
            "id": signal_id,
            "tenant_id": str(TENANT_ID),
            "client_signal_id": signal.client_signal_id,
            "content_sha256": siem._content_sha256(signal),
            "observed_at": signal.observed_at,
            "source": signal.source,
            "category": signal.category,
            "signal_type": signal.signal_type,
            "severity": signal.severity,
            "title": signal.title,
            "summary": signal.summary,
            "confidence": signal.confidence,
            "observables": [item.model_dump(mode="json") for item in signal.observables],
            "metadata": signal.metadata,
            "processing_status": "processing",
            "processing_result": {},
            "processing_completed_at": None,
            "created_by_actor_id": ACTOR_ID,
            "created_at": datetime.now(UTC),
        }
        pool = AsyncMock()
        pool.fetchrow.side_effect = [None, row, {"id": signal_id}]
        with (
            patch.object(siem.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(siem, "ensure_siem_schema", new=AsyncMock()),
            patch.object(
                siem.soc_svc,
                "open_case_from_context",
                new=AsyncMock(return_value={"id": "case-1"}),
            ) as open_case,
            patch.object(
                siem.playbook_svc,
                "run_matching_playbooks",
                new=AsyncMock(return_value=[{"id": "run-1", "duplicate": True}]),
            ) as run,
            patch.object(siem.audit, "record_required", new=AsyncMock()),
        ):
            result = await siem.create_signal(pool, user=_service("*"), signal=signal)
        self.assertTrue(result["duplicate"])
        open_case.assert_awaited_once()
        run.assert_awaited_once()

    async def test_signal_idempotency_key_rejects_different_content(self) -> None:
        signal = _signal()
        row = {
            "id": "77777777-7777-7777-7777-777777777777",
            "tenant_id": str(TENANT_ID),
            "client_signal_id": signal.client_signal_id,
            "content_sha256": "0" * 64,
            "observed_at": signal.observed_at,
            "source": signal.source,
            "category": signal.category,
            "signal_type": signal.signal_type,
            "severity": signal.severity,
            "title": signal.title,
            "summary": signal.summary,
            "confidence": signal.confidence,
            "observables": [],
            "metadata": {},
            "created_by_actor_id": ACTOR_ID,
            "created_at": datetime.now(UTC),
        }
        pool = AsyncMock()
        pool.fetchrow.side_effect = [None, row]
        with (
            patch.object(siem.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(siem, "ensure_siem_schema", new=AsyncMock()),
            self.assertRaises(HTTPException) as error,
        ):
            await siem.create_signal(pool, user=_service("siem:write"), signal=signal)
        self.assertEqual(error.exception.status_code, 409)

    async def test_playbook_run_idempotency_resumes_through_durable_action_guard(self) -> None:
        playbook_id = UUID("88888888-8888-8888-8888-888888888888")
        run_id = UUID("99999999-9999-9999-9999-999999999999")
        context = {"event_type": "security_signal"}
        pool = AsyncMock()
        pool.fetchrow.return_value = {
            "id": str(run_id),
            "playbook_id": str(playbook_id),
            "trigger_context": context,
            "trigger_source": "manual",
            "source_signal_id": None,
        }
        existing = {"id": str(run_id), "status": "awaiting_ack", "actions": []}
        with (
            patch.object(playbooks, "_authorize", new=AsyncMock()),
            patch.object(playbooks, "ensure_playbook_schema", new=AsyncMock()),
            patch.object(playbooks.audit, "record_required", new=AsyncMock()),
            patch.object(playbooks, "_fetch_run", new=AsyncMock(return_value=existing)),
            patch.object(playbooks, "_execute_run_actions", new=AsyncMock()) as execute,
        ):
            result = await playbooks.execute_playbook(
                pool,
                user=_service("playbooks:execute"),
                tenant_id=TENANT_ID,
                playbook_id=playbook_id,
                idempotency_key="manual:contain:001",
                context=context,
            )
        self.assertTrue(result["duplicate"])
        execute.assert_awaited_once()
        self.assertEqual(pool.fetchrow.await_count, 1)
        self.assertIn("FROM playbook_runs", pool.fetchrow.await_args.args[0])

    async def test_playbook_idempotency_key_rejects_different_request(self) -> None:
        playbook_id = UUID("88888888-8888-8888-8888-888888888888")
        pool = AsyncMock()
        pool.fetchrow.return_value = {
            "id": "99999999-9999-9999-9999-999999999999",
            "playbook_id": str(playbook_id),
            "trigger_context": {"event_type": "different"},
            "trigger_source": "manual",
            "source_signal_id": None,
        }
        with (
            patch.object(playbooks, "_authorize", new=AsyncMock()),
            patch.object(playbooks, "ensure_playbook_schema", new=AsyncMock()),
            patch.object(playbooks.audit, "record_required", new=AsyncMock()),
            self.assertRaises(HTTPException) as error,
        ):
            await playbooks.execute_playbook(
                pool,
                user=_service("playbooks:execute"),
                tenant_id=TENANT_ID,
                playbook_id=playbook_id,
                idempotency_key="manual:contain:001",
                context={"event_type": "security_signal"},
            )
        self.assertEqual(error.exception.status_code, 409)

    async def test_control_plane_action_persists_awaiting_ack(self) -> None:
        run_id = UUID("99999999-9999-9999-9999-999999999999")
        action_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        result_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        pool = AsyncMock()
        pool.fetchrow.side_effect = [
            {
                "action_plan_snapshot": [
                    {
                        "key": action_id,
                        "playbook_action_id": action_id,
                        "action_type": "block_ip",
                        "configuration": {},
                        "sort_order": 0,
                    }
                ],
                "trigger_context": {"event_type": "security_signal"},
            },
            {"id": result_id},
        ]
        with (
            patch.object(playbooks, "_refresh_run_status", new=AsyncMock()),
            patch.object(playbooks.audit, "record_required", new=AsyncMock()),
        ):
            await playbooks._execute_run_actions(
                pool,
                user=_service("playbooks:execute"),
                tenant_id=TENANT_ID,
                run_id=run_id,
                playbook_id=UUID("88888888-8888-8888-8888-888888888888"),
            )
        insert_call = pool.fetchrow.call_args
        self.assertIn("INSERT INTO playbook_action_results", insert_call.args[0])
        self.assertEqual(insert_call.args[6], "awaiting_ack")
        self.assertEqual(insert_call.args[7], 1)
        self.assertIsNone(insert_call.args[10])
        snapshot_query = pool.fetchrow.await_args_list[0].args[0]
        self.assertIn("FROM playbook_runs", snapshot_query)
        self.assertIn("action_plan_snapshot", snapshot_query)

    def test_control_plane_result_exposes_only_safe_immutable_configuration(self) -> None:
        row = {
            "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            "action_plan_key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "playbook_action_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "action_type": "block_ip",
            "status": "awaiting_ack",
            "attempt": 1,
            "max_attempts": 1,
            "status_code": None,
            "error_code": None,
            "external_reference": None,
            "configuration_snapshot": {
                "provider_ref": "edge-waf",
                "duration_seconds": 3600,
                "unexpected": "drop-me",
            },
            "result_metadata": {},
            "next_attempt_at": None,
            "last_attempt_at": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
            "completed_at": None,
        }
        result = playbooks._action_result_dict(row)  # type: ignore[arg-type]
        self.assertEqual(
            result["configuration"],
            {"provider_ref": "edge-waf", "duration_seconds": 3600},
        )

    async def test_existing_action_result_prevents_webhook_reexecution(self) -> None:
        pool = AsyncMock()
        action = {
            "key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "playbook_action_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "action_type": "webhook",
            "configuration": {"url": "https://hooks.example.test/forjd"},
            "sort_order": 0,
        }
        pool.fetchrow.side_effect = [
            {
                "action_plan_snapshot": [action],
                "trigger_context": {"event_type": "security_signal"},
            },
            None,
        ]
        pool.fetchval.return_value = "awaiting_ack"
        with (
            patch.object(playbooks, "_refresh_run_status", new=AsyncMock()),
            patch.object(playbooks, "_run_webhook", new=AsyncMock()) as webhook,
        ):
            await playbooks._execute_run_actions(
                pool,
                user=_service("playbooks:execute"),
                tenant_id=TENANT_ID,
                run_id=UUID("99999999-9999-9999-9999-999999999999"),
                playbook_id=UUID("88888888-8888-8888-8888-888888888888"),
            )
        webhook.assert_not_awaited()

    async def test_retryable_initial_webhook_failure_is_durably_scheduled(self) -> None:
        run_id = UUID("99999999-9999-9999-9999-999999999999")
        result_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
        pool = AsyncMock()
        action = {
            "key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "playbook_action_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "action_type": "webhook",
            "configuration": {"url": "https://hooks.example.test/forjd"},
            "sort_order": 0,
        }
        pool.fetchrow.side_effect = [
            {
                "action_plan_snapshot": [action],
                "trigger_context": {"event_type": "security_signal"},
            },
            {"id": result_id},
            {"status": "retry_scheduled"},
        ]
        failure = {
            "status": "failed",
            "status_code": 503,
            "error_code": "upstream_error",
            "metadata": {},
            "retryable": True,
            "retry_after_seconds": None,
        }
        with (
            patch.object(playbooks, "_run_webhook", new=AsyncMock(return_value=failure)),
            patch.object(playbooks, "_refresh_run_status", new=AsyncMock()),
            patch.object(playbooks.audit, "record_required", new=AsyncMock()),
        ):
            await playbooks._execute_run_actions(
                pool,
                user=_service("playbooks:execute"),
                tenant_id=TENANT_ID,
                run_id=run_id,
                playbook_id=UUID("88888888-8888-8888-8888-888888888888"),
            )
        update_call = pool.fetchrow.await_args_list[2]
        self.assertEqual(update_call.args[4], "retry_scheduled")
        self.assertEqual(update_call.args[8], 5)
        self.assertIn("INSERT INTO audit_events", update_call.args[0])
        insert_call = pool.fetchrow.await_args_list[1]
        self.assertEqual(insert_call.args[7], 5)
        self.assertIn("configuration_snapshot", insert_call.args[0])

    async def test_retry_worker_claim_is_skip_locked_and_webhook_only(self) -> None:
        pool = AsyncMock()
        pool.fetch.return_value = []
        rows = await playbooks._claim_due_webhook_retries(
            pool,
            batch_size=25,
            worker_id="soar:test",
        )
        self.assertEqual(rows, [])
        query = pool.fetch.call_args.args[0]
        self.assertIn("FOR UPDATE OF result SKIP LOCKED", query)
        self.assertIn("result.action_type = 'webhook'", query)
        self.assertIn("attempt = result.attempt + 1", query)
        self.assertIn("lease_expires_at", query)

    async def test_retry_worker_processes_claim_and_resumes_ordered_run(self) -> None:
        run_id = UUID("99999999-9999-9999-9999-999999999999")
        action_result_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        playbook_id = UUID("88888888-8888-8888-8888-888888888888")
        claimed = {
            "id": str(action_result_id),
            "run_id": str(run_id),
            "tenant_id": str(TENANT_ID),
            "playbook_id": str(playbook_id),
            "attempt": 2,
            "max_attempts": 5,
            "configuration_snapshot": {"url": "https://hooks.example.test/forjd"},
            "trigger_context": {"event_type": "security_signal"},
            "created_by_actor_id": ACTOR_ID,
        }
        success = {
            "status": "succeeded",
            "status_code": 204,
            "error_code": None,
            "metadata": {},
            "retryable": False,
            "retry_after_seconds": None,
        }
        pool = AsyncMock()
        with (
            patch.object(playbooks, "ensure_playbook_schema", new=AsyncMock()),
            patch.object(
                playbooks,
                "_finalize_expired_retry_leases",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                playbooks,
                "_claim_due_webhook_retries",
                new=AsyncMock(side_effect=[[claimed], []]),
            ) as claim,
            patch.object(playbooks, "_run_webhook", new=AsyncMock(return_value=success)) as send,
            patch.object(
                playbooks,
                "_persist_webhook_outcome",
                new=AsyncMock(return_value={"persisted": True, "status": "succeeded"}),
            ),
            patch.object(playbooks, "_execute_run_actions", new=AsyncMock()) as resume,
            patch.object(playbooks.audit, "record_required", new=AsyncMock()),
        ):
            result = await playbooks.tick_playbook_retries(pool, worker_id="soar:test")
        self.assertEqual(result["claimed"], 1)
        self.assertEqual(result["succeeded"], 1)
        send.assert_awaited_once_with(
            claimed["configuration_snapshot"],
            claimed["trigger_context"],
            run_id=run_id,
            action_result_id=action_result_id,
        )
        resume.assert_awaited_once()
        self.assertIsNone(resume.await_args.kwargs["user"])
        self.assertEqual(claim.await_args_list[0].kwargs["batch_size"], 1)

    async def test_continuation_reconciler_resumes_runs_without_active_actions(self) -> None:
        run_id = UUID("99999999-9999-9999-9999-999999999999")
        playbook_id = UUID("88888888-8888-8888-8888-888888888888")
        pool = AsyncMock()
        pool.fetch.return_value = [
            {
                "id": str(run_id),
                "tenant_id": str(TENANT_ID),
                "playbook_id": str(playbook_id),
            }
        ]
        with (
            patch.object(playbooks, "ensure_playbook_schema", new=AsyncMock()),
            patch.object(playbooks, "_execute_run_actions", new=AsyncMock()) as resume,
        ):
            result = await playbooks.tick_playbook_continuations(pool, batch_size=5)
        self.assertEqual(result["eligible"], 1)
        self.assertEqual(result["resumed"], 1)
        query = pool.fetch.await_args.args[0]
        self.assertIn("NOT EXISTS", query)
        self.assertIn("result.status IN", query)
        resume.assert_awaited_once_with(
            pool,
            user=None,
            tenant_id=TENANT_ID,
            run_id=run_id,
            playbook_id=playbook_id,
        )

    async def test_operator_retry_is_tenant_scoped_and_attempt_bounded(self) -> None:
        run_id = UUID("99999999-9999-9999-9999-999999999999")
        action_result_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        pool = AsyncMock()
        pool.fetchrow.return_value = {
            "id": str(action_result_id),
            "attempt": 2,
            "max_attempts": 5,
        }
        expected = {"id": str(run_id), "status": "retrying"}
        with (
            patch.object(playbooks, "_authorize", new=AsyncMock()),
            patch.object(playbooks, "ensure_playbook_schema", new=AsyncMock()),
            patch.object(playbooks, "_refresh_run_status", new=AsyncMock()),
            patch.object(playbooks.audit, "record_required", new=AsyncMock()),
            patch.object(playbooks, "_fetch_run", new=AsyncMock(return_value=expected)),
        ):
            result = await playbooks.retry_action(
                pool,
                user=_service("playbooks:execute"),
                tenant_id=TENANT_ID,
                run_id=run_id,
                action_result_id=action_result_id,
            )
        self.assertEqual(result, expected)
        query = pool.fetchrow.call_args.args[0]
        self.assertIn("run.tenant_id = $3::uuid", query)
        self.assertIn("result.action_type = 'webhook'", query)
        self.assertIn("result.attempt < result.max_attempts", query)

    async def test_operator_retry_rejects_control_plane_actions(self) -> None:
        pool = AsyncMock()
        pool.fetchrow.side_effect = [
            None,
            {
                "action_type": "block_ip",
                "status": "awaiting_ack",
                "attempt": 1,
                "max_attempts": 1,
            },
        ]
        with (
            patch.object(playbooks, "_authorize", new=AsyncMock()),
            patch.object(playbooks, "ensure_playbook_schema", new=AsyncMock()),
            self.assertRaises(HTTPException) as error,
        ):
            await playbooks.retry_action(
                pool,
                user=_service("playbooks:execute"),
                tenant_id=TENANT_ID,
                run_id=UUID("99999999-9999-9999-9999-999999999999"),
                action_result_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            )
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn("acknowledgement", str(error.exception.detail))

    async def test_successful_control_plane_ack_resumes_ordered_run(self) -> None:
        run_id = UUID("99999999-9999-9999-9999-999999999999")
        playbook_id = UUID("88888888-8888-8888-8888-888888888888")
        action_result_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        pool = AsyncMock()
        pool.fetchrow.return_value = {
            "id": str(action_result_id),
            "status": "awaiting_ack",
            "playbook_id": str(playbook_id),
            "trigger_context": {"event_type": "security_signal"},
        }
        with (
            patch.object(playbooks, "_authorize", new=AsyncMock()),
            patch.object(playbooks, "ensure_playbook_schema", new=AsyncMock()),
            patch.object(playbooks.audit, "record_required", new=AsyncMock()),
            patch.object(playbooks, "_execute_run_actions", new=AsyncMock()) as resume,
            patch.object(
                playbooks,
                "_fetch_run",
                new=AsyncMock(return_value={"id": str(run_id), "status": "succeeded"}),
            ),
        ):
            await playbooks.acknowledge_action(
                pool,
                user=_service("playbooks:execute"),
                tenant_id=TENANT_ID,
                run_id=run_id,
                action_result_id=action_result_id,
                succeeded=True,
                external_reference="deml:action:123",
                metadata={"provider": "deml"},
            )
        resume.assert_awaited_once()
        self.assertEqual(resume.await_args.kwargs["playbook_id"], playbook_id)
        ack_query = pool.fetchrow.await_args.args[0]
        self.assertIn("result.status = 'awaiting_ack'", ack_query)
        self.assertIn("INSERT INTO audit_events", ack_query)
        self.assertIn("RETURNING", ack_query)

    async def test_webhook_is_not_sent_when_required_attempt_audit_fails(self) -> None:
        action_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        pool = AsyncMock()
        pool.fetchrow.side_effect = [
            {
                "action_plan_snapshot": [
                    {
                        "key": action_id,
                        "playbook_action_id": action_id,
                        "action_type": "webhook",
                        "configuration": {"url": "https://hooks.example.test/forjd"},
                        "sort_order": 0,
                    }
                ],
                "trigger_context": {},
            },
            {"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"},
        ]
        with (
            patch.object(
                playbooks.audit,
                "record_required",
                new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
            ),
            patch.object(playbooks, "_run_webhook", new=AsyncMock()) as webhook,
            self.assertRaisesRegex(RuntimeError, "audit unavailable"),
        ):
            await playbooks._execute_run_actions(
                pool,
                user=_service("playbooks:execute"),
                tenant_id=TENANT_ID,
                run_id=UUID("99999999-9999-9999-9999-999999999999"),
                playbook_id=UUID("88888888-8888-8888-8888-888888888888"),
            )
        webhook.assert_not_awaited()

    async def test_exact_ack_replay_is_idempotent_and_not_reaudited(self) -> None:
        run_id = UUID("99999999-9999-9999-9999-999999999999")
        playbook_id = UUID("88888888-8888-8888-8888-888888888888")
        action_result_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        pool = AsyncMock()
        pool.fetchrow.side_effect = [
            None,
            {
                "action_type": "block_ip",
                "status": "succeeded",
                "external_reference": "firewall:receipt:1",
                "result_metadata": {"provider": "edge"},
                "playbook_id": str(playbook_id),
            },
        ]
        audit_record = AsyncMock()
        expected = {"id": str(run_id), "status": "succeeded"}
        with (
            patch.object(playbooks, "_authorize", new=AsyncMock()),
            patch.object(playbooks, "ensure_playbook_schema", new=AsyncMock()),
            patch.object(playbooks.audit, "record_required", new=audit_record),
            patch.object(playbooks, "_execute_run_actions", new=AsyncMock()) as resume,
            patch.object(playbooks, "_fetch_run", new=AsyncMock(return_value=expected)),
        ):
            result = await playbooks.acknowledge_action(
                pool,
                user=_service("playbooks:execute"),
                tenant_id=TENANT_ID,
                run_id=run_id,
                action_result_id=action_result_id,
                succeeded=True,
                external_reference="firewall:receipt:1",
                metadata={"provider": "edge"},
            )
        self.assertTrue(result["ack_duplicate"])
        audit_record.assert_not_awaited()
        resume.assert_awaited_once()

    async def test_conflicting_ack_replay_cannot_flip_durable_decision(self) -> None:
        pool = AsyncMock()
        pool.fetchrow.side_effect = [
            None,
            {
                "action_type": "block_ip",
                "status": "succeeded",
                "external_reference": "firewall:receipt:1",
                "result_metadata": {"provider": "edge"},
                "playbook_id": "88888888-8888-8888-8888-888888888888",
            },
        ]
        with (
            patch.object(playbooks, "_authorize", new=AsyncMock()),
            patch.object(playbooks, "ensure_playbook_schema", new=AsyncMock()),
            patch.object(playbooks.audit, "record_required", new=AsyncMock()) as audit_record,
            self.assertRaises(HTTPException) as error,
        ):
            await playbooks.acknowledge_action(
                pool,
                user=_service("playbooks:execute"),
                tenant_id=TENANT_ID,
                run_id=UUID("99999999-9999-9999-9999-999999999999"),
                action_result_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                succeeded=False,
                external_reference="firewall:receipt:2",
                metadata={"provider": "edge"},
            )
        self.assertEqual(error.exception.status_code, 409)
        audit_record.assert_not_awaited()

    def test_run_status_summary_is_truthful(self) -> None:
        self.assertEqual(playbooks.summarize_action_statuses([]), "succeeded")
        self.assertEqual(
            playbooks.summarize_action_statuses(["succeeded", "awaiting_ack"]),
            "awaiting_ack",
        )
        self.assertEqual(
            playbooks.summarize_action_statuses(["succeeded", "failed"]),
            "partial",
        )
        self.assertEqual(playbooks.summarize_action_statuses(["unsupported"]), "unsupported")
        self.assertEqual(
            playbooks.summarize_action_statuses(["succeeded", "retry_scheduled"]),
            "retrying",
        )


class TestPlaybookActionContract(unittest.TestCase):
    def test_inline_credentials_are_not_accepted(self) -> None:
        with self.assertRaises(ValidationError):
            PlaybookActionIn.model_validate(
                {
                    "action_type": "webhook",
                    "configuration": {
                        "url": "https://hooks.example.test/forjd",
                        "authorization": "Bearer secret",
                    },
                }
            )

    def test_control_plane_reference_is_allowed(self) -> None:
        action = PlaybookActionIn.model_validate(
            {
                "action_type": "block_ip",
                "configuration": {"provider_ref": "deml:firewall", "duration_seconds": 3600},
            }
        )
        self.assertEqual(action.action_type, "block_ip")

    def test_retry_backoff_and_retry_after_are_bounded(self) -> None:
        self.assertEqual(playbooks._retry_backoff_seconds(1), 5)
        self.assertEqual(playbooks._retry_backoff_seconds(2), 10)
        self.assertEqual(
            playbooks._retry_backoff_seconds(2, retry_after_seconds=120),
            120,
        )
        self.assertEqual(
            playbooks._retry_backoff_seconds(100, retry_after_seconds=10_000),
            300,
        )
        self.assertEqual(playbooks._parse_retry_after("10000"), 300)
        self.assertIsNone(playbooks._parse_retry_after("not-a-date"))
        for code in (408, 425, 429, 500, 503, 599):
            self.assertTrue(playbooks._is_retryable_webhook_status(code))
        for code in (301, 400, 401, 403, 404, 409, 422):
            self.assertFalse(playbooks._is_retryable_webhook_status(code))

    def test_run_request_fingerprint_binds_immutable_action_plan(self) -> None:
        playbook_id = UUID("88888888-8888-8888-8888-888888888888")
        common = {
            "playbook_id": playbook_id,
            "playbook_version": 1,
            "context": {},
            "trigger_source": "manual",
            "source_signal_id": None,
        }
        first = playbooks._run_request_sha256(
            **common,
            action_plan=[{"key": "a", "action_type": "webhook"}],
        )
        second = playbooks._run_request_sha256(
            **common,
            action_plan=[{"key": "b", "action_type": "webhook"}],
        )
        self.assertNotEqual(first, second)

    def test_only_retryable_failures_are_auto_scheduled(self) -> None:
        retryable = {
            "status": "failed",
            "status_code": 503,
            "error_code": "upstream_error",
            "metadata": {},
            "retryable": True,
            "retry_after_seconds": 90,
        }
        scheduled = playbooks._durable_webhook_outcome(retryable, attempt=1, max_attempts=5)
        self.assertEqual(scheduled["status"], "retry_scheduled")
        self.assertEqual(scheduled["retry_after_seconds"], 90)

        exhausted = playbooks._durable_webhook_outcome(retryable, attempt=5, max_attempts=5)
        self.assertEqual(exhausted["status"], "failed")
        self.assertTrue(exhausted["metadata"]["retry_exhausted"])

        permanent = playbooks._durable_webhook_outcome(
            {
                "status": "failed",
                "status_code": 400,
                "error_code": "http_error",
                "metadata": {},
                "retryable": False,
                "retry_after_seconds": None,
            },
            attempt=1,
            max_attempts=5,
        )
        self.assertEqual(permanent["status"], "failed")
        self.assertIsNone(permanent["retry_after_seconds"])

    def test_migration_contains_durable_soar_retry_contract(self) -> None:
        sql = (Path(__file__).parents[1] / "sql/020_headless_siem_soar.sql").read_text()
        for marker in (
            "retry_scheduled",
            "max_attempts",
            "next_attempt_at",
            "lease_owner",
            "lease_expires_at",
            "configuration_snapshot",
            "action_plan_snapshot",
            "action_plan_key",
            "playbook_runs_immutable_plan",
            "playbook_action_results_retry_ready_idx",
            "correlation_receipts",
            "incident_cases_source_correlation_uidx",
            "audit_events_append_only",
            "REVOKE ALL ON public.audit_events",
        ):
            self.assertIn(marker, sql)

        replay_sql = (
            Path(__file__).parents[1] / "sql/025_siem_soar_replay_continuation.sql"
        ).read_text()
        for marker in (
            "processing_status",
            "processing_result",
            "result_snapshot",
            "security_signals_processing_contract",
            "playbook_runs_continuation_ready_idx",
        ):
            self.assertIn(marker, replay_sql)


class TestWebhookEgress(unittest.IsolatedAsyncioTestCase):
    def test_playbook_write_rejects_unconfigured_signing_reference(self) -> None:
        with (
            patch.object(settings, "WEBHOOK_SIGNING_SECRETS_JSON", "{}"),
            self.assertRaises(HTTPException) as error,
        ):
            playbooks._validate_action_configuration(
                "webhook",
                {
                    "url": "https://hooks.example.test/forjd",
                    "secret_ref": "missing-hook",
                },
            )
        self.assertEqual(error.exception.status_code, 422)
        self.assertEqual(error.exception.detail, "webhook secret_ref is not configured")

    async def test_configured_secret_ref_signs_the_exact_canonical_body(self) -> None:
        sent: dict[str, object] = {}

        class _Stream:
            async def __aenter__(self) -> SimpleNamespace:
                return SimpleNamespace(status_code=204, headers={})

            async def __aexit__(self, *_args: object) -> None:
                return None

        class _Client:
            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *_args: object) -> None:
                return None

            def stream(self, *_args: object, **kwargs: object) -> _Stream:
                sent.update(kwargs)
                return _Stream()

        secret = "0123456789abcdef0123456789abcdef"
        context = {"severity": "high", "event_type": "security_signal"}
        with (
            patch.object(
                settings,
                "WEBHOOK_SIGNING_SECRETS_JSON",
                json.dumps({"primary-hook": secret}),
            ),
            patch.object(
                playbooks,
                "validate_outbound_url",
                new=AsyncMock(return_value="https://hooks.example.test/forjd"),
            ),
            patch.object(playbooks.httpx, "AsyncClient", return_value=_Client()),
        ):
            result = await playbooks._run_webhook(
                {
                    "url": "https://hooks.example.test/forjd",
                    "secret_ref": "primary-hook",
                },
                context,
                run_id=UUID("99999999-9999-9999-9999-999999999999"),
                action_result_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            )
        self.assertEqual(result["status"], "succeeded")
        expected_body = json.dumps(
            {"context": context, "source": "forjd-playbook"},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        self.assertEqual(sent["content"], expected_body)
        headers = sent["headers"]
        assert isinstance(headers, dict)
        timestamp = headers["X-FORJD-Timestamp"]
        expected_signature = hmac.new(
            secret.encode(),
            timestamp.encode() + b"." + expected_body,
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(headers["X-FORJD-Key-ID"], "primary-hook")
        self.assertEqual(headers["X-FORJD-Signature"], f"v1={expected_signature}")

    async def test_missing_secret_ref_fails_without_network_delivery(self) -> None:
        with (
            patch.object(settings, "WEBHOOK_SIGNING_SECRETS_JSON", "{}"),
            patch.object(playbooks, "validate_outbound_url", new=AsyncMock()) as validate,
            patch.object(playbooks.httpx, "AsyncClient") as client,
        ):
            result = await playbooks._run_webhook(
                {
                    "url": "https://hooks.example.test/forjd",
                    "secret_ref": "missing-hook",
                },
                {},
                run_id=UUID("99999999-9999-9999-9999-999999999999"),
                action_result_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            )
        self.assertEqual(result["error_code"], "signing_secret_unavailable")
        self.assertFalse(result["retryable"])
        validate.assert_not_awaited()
        client.assert_not_called()

    async def test_redirect_is_not_followed_or_reported_as_success(self) -> None:
        class _Stream:
            async def __aenter__(self) -> SimpleNamespace:
                return SimpleNamespace(status_code=302)

            async def __aexit__(self, *_args: object) -> None:
                return None

        class _Client:
            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *_args: object) -> None:
                return None

            def stream(self, *_args: object, **_kwargs: object) -> _Stream:
                return _Stream()

        with (
            patch.object(
                playbooks,
                "validate_outbound_url",
                new=AsyncMock(return_value="https://hooks.example.test/forjd"),
            ),
            patch.object(playbooks.httpx, "AsyncClient", return_value=_Client()),
        ):
            result = await playbooks._run_webhook(
                {"url": "https://hooks.example.test/forjd"},
                {"event_type": "security_signal"},
                run_id=UUID("99999999-9999-9999-9999-999999999999"),
                action_result_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "redirect_rejected")
        self.assertFalse(result["retryable"])

    async def test_retry_after_is_capped_and_delivery_key_stays_stable(self) -> None:
        sent_headers: list[dict[str, str]] = []

        class _Stream:
            async def __aenter__(self) -> SimpleNamespace:
                return SimpleNamespace(
                    status_code=429,
                    headers={"Retry-After": "10000"},
                )

            async def __aexit__(self, *_args: object) -> None:
                return None

        class _Client:
            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *_args: object) -> None:
                return None

            def stream(self, *_args: object, **kwargs: object) -> _Stream:
                sent_headers.append(dict(kwargs["headers"]))
                return _Stream()

        run_id = UUID("99999999-9999-9999-9999-999999999999")
        action_result_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        with (
            patch.object(
                playbooks,
                "validate_outbound_url",
                new=AsyncMock(return_value="https://hooks.example.test/forjd"),
            ),
            patch.object(playbooks.httpx, "AsyncClient", return_value=_Client()),
        ):
            first = await playbooks._run_webhook(
                {"url": "https://hooks.example.test/forjd"},
                {"event_type": "security_signal"},
                run_id=run_id,
                action_result_id=action_result_id,
            )
            second = await playbooks._run_webhook(
                {"url": "https://hooks.example.test/forjd"},
                {"event_type": "security_signal"},
                run_id=run_id,
                action_result_id=action_result_id,
            )
        self.assertTrue(first["retryable"])
        self.assertEqual(first["error_code"], "rate_limited")
        self.assertEqual(first["retry_after_seconds"], 300)
        self.assertTrue(second["retryable"])
        self.assertEqual(len(sent_headers), 2)
        self.assertEqual(
            sent_headers[0]["Idempotency-Key"],
            sent_headers[1]["Idempotency-Key"],
        )
        self.assertEqual(
            sent_headers[0]["Idempotency-Key"],
            f"{run_id}:{action_result_id}",
        )

    async def test_network_errors_are_retryable_but_permanent_4xx_is_not(self) -> None:
        with patch.object(
            playbooks,
            "validate_outbound_url",
            new=AsyncMock(side_effect=httpx.ConnectError("network unavailable")),
        ):
            network = await playbooks._run_webhook(
                {"url": "https://hooks.example.test/forjd"},
                {},
                run_id=UUID("99999999-9999-9999-9999-999999999999"),
                action_result_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            )
        self.assertTrue(network["retryable"])
        self.assertEqual(network["error_code"], "network_error")

        class _Stream:
            async def __aenter__(self) -> SimpleNamespace:
                return SimpleNamespace(status_code=422, headers={})

            async def __aexit__(self, *_args: object) -> None:
                return None

        class _Client:
            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *_args: object) -> None:
                return None

            def stream(self, *_args: object, **_kwargs: object) -> _Stream:
                return _Stream()

        with (
            patch.object(
                playbooks,
                "validate_outbound_url",
                new=AsyncMock(return_value="https://hooks.example.test/forjd"),
            ),
            patch.object(playbooks.httpx, "AsyncClient", return_value=_Client()),
        ):
            permanent = await playbooks._run_webhook(
                {"url": "https://hooks.example.test/forjd"},
                {},
                run_id=UUID("99999999-9999-9999-9999-999999999999"),
                action_result_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            )
        self.assertFalse(permanent["retryable"])
        self.assertEqual(permanent["status_code"], 422)


if __name__ == "__main__":
    unittest.main()
