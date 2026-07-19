"""Regression tests for ingest, projection, replay, and schema reliability."""

from __future__ import annotations

import base64
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.core.auth import AuthUser, PrincipalKind
from app.core.crypto import b64decode, seal
from app.models.ingest import (
    EmbeddingIngestRequest,
    EncryptedEnvelope,
    IngestBatchRequest,
    IngestEventRequest,
)
from app.services import ingest as ingest_svc
from app.services import projection_worker as projection_worker_svc
from app.services import projections as proj_svc
from app.services import replay as replay_svc
from app.services import tenants as tenant_svc
from app.workflows.registry import resolve_workflow
from scripts import apply_sql_migrations

ROOT = Path(__file__).resolve().parents[1]


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *_args: object) -> None:
        return None


def _event(tenant_id: UUID, client_event_id: str) -> IngestEventRequest:
    sealed = seal(
        b"sealed reliability payload",
        key=b"k" * 32,
        key_id="session-1",
        tenant_id=str(tenant_id),
        client_event_id=client_event_id,
    )
    envelope = EncryptedEnvelope(
        algo=sealed.algo,
        key_id=sealed.key_id,
        nonce=sealed.nonce,
        ciphertext=sealed.ciphertext,
        ratchet_header=sealed.ratchet_header,
        ciphertext_sha256=sealed.ciphertext_sha256,
    )
    return IngestEventRequest(
        tenant_id=tenant_id,
        client_event_id=client_event_id,
        envelope=envelope,
        metadata={"source": "sdk"},
    )


def _existing_row(event: IngestEventRequest, *, event_id: UUID, created_at: datetime) -> dict:
    workflow = resolve_workflow(content_type=event.content_type)
    sealed = event.envelope.to_sealed()
    ciphertext_bytes = len(b64decode(sealed.ciphertext))
    fingerprint = ingest_svc._event_fingerprint(
        event,
        workflow_id=workflow.id,
        event_type=event.event_type,
        ciphertext_bytes=ciphertext_bytes,
    )
    return {
        "id": event_id,
        "tenant_id": event.tenant_id,
        "client_event_id": event.client_event_id,
        "created_at": created_at,
        "occurred_at": event.occurred_at,
        "algo": sealed.algo,
        "key_id": sealed.key_id,
        "ratchet_header": sealed.ratchet_header,
        "nonce": sealed.nonce,
        "ciphertext_sha256": sealed.ciphertext_sha256,
        "ciphertext_bytes": ciphertext_bytes,
        "ingest_fingerprint": fingerprint,
        "content_type": event.content_type,
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "workflow_id": workflow.id,
        "metadata": event.metadata,
    }


def _principal(tenant_id: UUID) -> AuthUser:
    return AuthUser(
        user_id=str(uuid4()),
        email=None,
        role="service",
        raw_claims={},
        kind=PrincipalKind.SERVICE,
        tenant_id=str(tenant_id),
        scopes=frozenset({"ingest:write"}),
    )


class SchemaCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        tenant_svc.reset_secure_schema_cache()

    def tearDown(self) -> None:
        tenant_svc.reset_secure_schema_cache()

    async def test_successful_assertion_is_cached_and_resettable(self) -> None:
        pool = MagicMock()
        verify = AsyncMock()
        with patch.object(tenant_svc, "_assert_secure_schema_uncached", verify):
            await tenant_svc.assert_secure_schema(pool)
            await tenant_svc.assert_secure_schema(pool)
            verify.assert_awaited_once_with(pool)

            tenant_svc.reset_secure_schema_cache(pool)
            await tenant_svc.assert_secure_schema(pool)
            self.assertEqual(verify.await_count, 2)

    async def test_failed_assertion_is_not_cached(self) -> None:
        pool = MagicMock()
        verify = AsyncMock(side_effect=[RuntimeError("not ready"), None])
        with patch.object(tenant_svc, "_assert_secure_schema_uncached", verify):
            with self.assertRaises(RuntimeError):
                await tenant_svc.assert_secure_schema(pool)
            await tenant_svc.assert_secure_schema(pool)
        self.assertEqual(verify.await_count, 2)


class IngestReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_is_not_reprocessed(self) -> None:
        tenant_id = uuid4()
        duplicate = _event(tenant_id, "evt-duplicate")
        fresh = _event(tenant_id, "evt-fresh")
        now = datetime.now(UTC)
        duplicate_id = uuid4()
        fresh_id = uuid4()

        conn = MagicMock()
        conn.fetchrow = AsyncMock(
            side_effect=[
                None,
                _existing_row(duplicate, event_id=duplicate_id, created_at=now),
                {
                    "id": fresh_id,
                    "tenant_id": tenant_id,
                    "client_event_id": fresh.client_event_id,
                    "created_at": now,
                },
            ]
        )
        conn.execute = AsyncMock()
        conn.fetchval = AsyncMock(return_value=True)
        conn.transaction = MagicMock(return_value=_AsyncContext(None))
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=_AsyncContext(conn))

        pathway = {
            "ok": True,
            "count": 1,
            "anomaly_count": 0,
            "by_tenant": {str(tenant_id): {"count": 1, "bytes": 42, "max_cipher_len": 42}},
        }
        batch_id = uuid4()
        register = AsyncMock(
            return_value={
                "id": str(batch_id),
                "acceptance_id": str(uuid4()),
                "group_ordinal": 0,
                "status": "queued",
                "attempts": 0,
                "max_attempts": 10,
            }
        )
        tick = AsyncMock(
            return_value=[
                {
                    "id": str(batch_id),
                    "ok": True,
                    "status": "completed",
                    "written": 0,
                    "dlq_enqueued": 0,
                    "pathway": pathway,
                    "prefect": {"ok": True},
                }
            ]
        )
        required_audit = AsyncMock()
        with (
            patch.object(ingest_svc.tenant_svc, "ensure_secure_schema", AsyncMock()),
            patch.object(ingest_svc.tenant_svc, "require_tenant_access", AsyncMock()),
            patch.object(ingest_svc.session_svc, "require_active_sessions", AsyncMock()),
            patch.object(
                ingest_svc.processing_svc,
                "register_processing_batch",
                register,
            ),
            patch.object(ingest_svc.processing_svc, "tick_ingest_processing", tick),
            patch.object(
                ingest_svc.processing_svc,
                "fetch_processing_batch_states",
                AsyncMock(
                    return_value=[
                        {
                            "id": str(batch_id),
                            "status": "completed",
                            "attempts": 1,
                            "max_attempts": 10,
                        }
                    ]
                ),
            ),
            patch.object(ingest_svc.audit, "record_required", required_audit),
        ):
            result = await ingest_svc.ingest_events(
                pool=pool,
                user=_principal(tenant_id),
                batch=IngestBatchRequest(events=[duplicate, fresh]),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["accepted"], 2)
        self.assertEqual(result["new_events"], 1)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["processing_state"], "completed")
        registered_events = register.await_args.kwargs["events"]
        self.assertEqual(len(registered_events), 1)
        self.assertEqual(registered_events[0]["event_id"], str(fresh_id))
        tick.assert_awaited_once()
        lock_query, lock_name = conn.fetchval.await_args.args
        self.assertIn("pg_advisory_xact_lock", lock_query)
        self.assertEqual(
            lock_name,
            proj_svc.projection_acceptance_fence_name(
                tenant_id=tenant_id,
                projection_name="sealed.default",
                workflow_id="default_sealed",
            ),
        )
        self.assertTrue(lock_name.endswith(":acceptance"))
        insert_queries = [call.args[0] for call in conn.fetchrow.await_args_list]
        self.assertTrue(any("clock_timestamp()" in query for query in insert_queries))
        self.assertTrue(
            any(
                "MAX(existing.created_at) + INTERVAL '1 microsecond'" in query
                for query in insert_queries
            )
        )
        required_audit.assert_awaited_once()
        self.assertIs(required_audit.await_args.args[0], conn)
        self.assertEqual(required_audit.await_args.kwargs["resource_type"], "ingest_acceptance")
        audit_details = required_audit.await_args.kwargs["details"]
        self.assertEqual(audit_details["accepted"], 2)
        self.assertEqual(audit_details["new_events"], 1)
        self.assertEqual(audit_details["duplicates"], 1)
        self.assertEqual(audit_details["processing_batch_ids"], [str(batch_id)])
        self.assertNotIn("ciphertext", audit_details)

    async def test_required_audit_failure_aborts_before_processing(self) -> None:
        tenant_id = uuid4()
        event = _event(tenant_id, "evt-audit-required")
        event_id = uuid4()
        now = datetime.now(UTC)
        conn = MagicMock()
        conn.fetchrow = AsyncMock(
            return_value={
                "id": event_id,
                "tenant_id": tenant_id,
                "client_event_id": event.client_event_id,
                "created_at": now,
            }
        )
        conn.fetchval = AsyncMock(return_value=True)
        conn.transaction = MagicMock(return_value=_AsyncContext(None))
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=_AsyncContext(conn))
        batch_id = uuid4()
        register = AsyncMock(
            return_value={
                "id": str(batch_id),
                "acceptance_id": str(uuid4()),
                "group_ordinal": 0,
                "status": "queued",
                "attempts": 0,
                "max_attempts": 10,
            }
        )
        tick = AsyncMock()
        with (
            patch.object(ingest_svc.tenant_svc, "ensure_secure_schema", AsyncMock()),
            patch.object(ingest_svc.tenant_svc, "require_tenant_access", AsyncMock()),
            patch.object(ingest_svc.session_svc, "require_active_sessions", AsyncMock()),
            patch.object(ingest_svc.processing_svc, "register_processing_batch", register),
            patch.object(ingest_svc.processing_svc, "tick_ingest_processing", tick),
            patch.object(
                ingest_svc.audit,
                "record_required",
                AsyncMock(side_effect=RuntimeError("audit unavailable")),
            ) as required_audit,
            self.assertRaisesRegex(RuntimeError, "audit unavailable"),
        ):
            await ingest_svc.ingest_events(
                pool=pool,
                user=_principal(tenant_id),
                batch=IngestBatchRequest(events=[event]),
            )

        register.assert_awaited_once()
        required_audit.assert_awaited_once()
        self.assertIs(required_audit.await_args.args[0], conn)
        tick.assert_not_awaited()

    async def test_exact_duplicate_retry_revives_original_failed_processing_group(self) -> None:
        tenant_id = uuid4()
        event = _event(tenant_id, "evt-recover")
        event_id = uuid4()
        batch_id = uuid4()
        now = datetime.now(UTC)
        conn = MagicMock()
        conn.fetchrow = AsyncMock(
            side_effect=[
                None,
                _existing_row(event, event_id=event_id, created_at=now),
            ]
        )
        conn.fetchval = AsyncMock(return_value=True)
        conn.transaction = MagicMock(return_value=_AsyncContext(None))
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=_AsyncContext(conn))
        find = AsyncMock(
            return_value=[
                {
                    "id": str(batch_id),
                    "status": "failed",
                    "attempts": 10,
                    "max_attempts": 10,
                }
            ]
        )
        wake = AsyncMock()
        tick = AsyncMock(
            return_value=[
                {
                    "id": str(batch_id),
                    "ok": True,
                    "status": "completed",
                    "written": 0,
                    "dlq_enqueued": 0,
                    "pathway": {"ok": True, "workflow_id": "default_sealed"},
                }
            ]
        )
        with (
            patch.object(ingest_svc.tenant_svc, "ensure_secure_schema", AsyncMock()),
            patch.object(ingest_svc.tenant_svc, "require_tenant_access", AsyncMock()),
            patch.object(ingest_svc.session_svc, "require_active_sessions", AsyncMock()),
            patch.object(
                ingest_svc.processing_svc,
                "register_processing_batch",
                AsyncMock(),
            ) as register,
            patch.object(
                ingest_svc.processing_svc,
                "find_processing_batches_covered_by_retry",
                find,
            ),
            patch.object(ingest_svc.processing_svc, "wake_processing_batches", wake),
            patch.object(ingest_svc.processing_svc, "tick_ingest_processing", tick),
            patch.object(
                ingest_svc.processing_svc,
                "fetch_processing_batch_states",
                AsyncMock(
                    return_value=[
                        {
                            "id": str(batch_id),
                            "status": "completed",
                            "attempts": 1,
                            "max_attempts": 10,
                        }
                    ]
                ),
            ),
            patch.object(ingest_svc.audit, "record_required", AsyncMock()),
        ):
            result = await ingest_svc.ingest_events(
                pool=pool,
                user=_principal(tenant_id),
                batch=IngestBatchRequest(events=[event]),
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["duplicates"], 1)
        register.assert_not_awaited()
        find.assert_awaited_once_with(
            pool,
            workflow_id="default_sealed",
            event_ids=[str(event_id)],
        )
        wake.assert_awaited_once_with(
            pool,
            batch_ids=[str(batch_id)],
            revive_failed=True,
        )
        self.assertEqual(tick.await_args.kwargs["batch_ids"], [str(batch_id)])

    async def test_processing_failure_is_false_and_dlq_persists_each_event(self) -> None:
        tenant_id = uuid4()
        event = _event(tenant_id, "evt-fails")
        now = datetime.now(UTC)
        conn = MagicMock()
        conn.fetchrow = AsyncMock(
            return_value={
                "id": uuid4(),
                "tenant_id": tenant_id,
                "client_event_id": event.client_event_id,
                "created_at": now,
            }
        )
        conn.fetchval = AsyncMock(return_value=True)
        conn.transaction = MagicMock(return_value=_AsyncContext(None))
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=_AsyncContext(conn))
        batch_id = uuid4()
        with (
            patch.object(ingest_svc.tenant_svc, "ensure_secure_schema", AsyncMock()),
            patch.object(ingest_svc.tenant_svc, "require_tenant_access", AsyncMock()),
            patch.object(ingest_svc.session_svc, "require_active_sessions", AsyncMock()),
            patch.object(
                ingest_svc.processing_svc,
                "register_processing_batch",
                AsyncMock(
                    return_value={
                        "id": str(batch_id),
                        "acceptance_id": str(uuid4()),
                        "group_ordinal": 0,
                        "status": "queued",
                        "attempts": 0,
                        "max_attempts": 10,
                    }
                ),
            ),
            patch.object(
                ingest_svc.processing_svc,
                "tick_ingest_processing",
                AsyncMock(
                    return_value=[
                        {
                            "id": str(batch_id),
                            "ok": False,
                            "status": "retry_scheduled",
                            "written": 0,
                            "dlq_enqueued": 1,
                            "error": "boom",
                        }
                    ]
                ),
            ),
            patch.object(
                ingest_svc.processing_svc,
                "fetch_processing_batch_states",
                AsyncMock(
                    return_value=[
                        {
                            "id": str(batch_id),
                            "status": "retry_scheduled",
                            "attempts": 1,
                            "max_attempts": 10,
                        }
                    ]
                ),
            ),
            patch.object(ingest_svc.audit, "record_required", AsyncMock()),
        ):
            result = await ingest_svc.ingest_events(
                pool=pool,
                user=_principal(tenant_id),
                batch=IngestBatchRequest(events=[event]),
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["processing_state"], "failed")
        self.assertEqual(result["processing_recovery_state"], "retry_scheduled")
        self.assertEqual(result["dlq_enqueued"], 1)

    def test_fingerprint_binds_routing_metadata(self) -> None:
        tenant_id = uuid4()
        first = _event(tenant_id, "evt-1")
        changed = first.model_copy(update={"metadata": {"source": "other"}})
        workflow = resolve_workflow(content_type=first.content_type)
        size = len(b64decode(first.envelope.ciphertext))
        original = ingest_svc._event_fingerprint(
            first,
            workflow_id=workflow.id,
            event_type=None,
            ciphertext_bytes=size,
        )
        altered = ingest_svc._event_fingerprint(
            changed,
            workflow_id=workflow.id,
            event_type=None,
            ciphertext_bytes=size,
        )
        self.assertNotEqual(original, altered)


class ProjectionReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_projector_snapshots_under_the_acceptance_fence(self) -> None:
        tenant_id = uuid4()
        conn = MagicMock()
        conn.fetchval = AsyncMock(side_effect=[True, None, True])
        conn.transaction = MagicMock(return_value=_AsyncContext(None))
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=_AsyncContext(conn))
        with (
            patch.object(proj_svc.tenant_svc, "ensure_secure_schema", AsyncMock()),
            patch.object(proj_svc, "get_checkpoint", AsyncMock(return_value=None)),
            patch.object(
                proj_svc,
                "fetch_meta_after_checkpoint",
                AsyncMock(return_value=[]),
            ),
        ):
            result = await proj_svc.run_projection_core(
                pool,
                tenant_id=tenant_id,
                workflow_id="default_sealed",
            )

        self.assertTrue(result["ok"])
        calls = conn.fetchval.await_args_list
        self.assertIn("pg_try_advisory_lock", calls[0].args[0])
        self.assertIn("pg_advisory_xact_lock", calls[1].args[0])
        self.assertEqual(
            calls[1].args[1],
            proj_svc.projection_acceptance_fence_name(
                tenant_id=tenant_id,
                projection_name="sealed.default",
                workflow_id="default_sealed",
            ),
        )

    async def test_failed_page_handoffs_to_versioned_dlq_and_advances_cursor(self) -> None:
        tenant_id = uuid4()
        now = datetime.now(UTC)
        meta = [
            {
                "event_id": str(uuid4()),
                "tenant_id": str(tenant_id),
                "key_id": "session-1",
                "cipher_len": 42,
                "content_type": "application/forjd-event+v1",
                "event_type": "",
                "workflow_id": "default_sealed",
                "created_at": now,
            }
            for _ in range(2)
        ]
        conn = MagicMock()
        conn.fetchval = AsyncMock(side_effect=[True, None, True])
        conn.transaction = MagicMock(return_value=_AsyncContext(None))
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=_AsyncContext(conn))
        enqueue = AsyncMock(return_value=str(uuid4()))
        advance = AsyncMock()
        upsert = AsyncMock(return_value=0)
        with (
            patch.object(proj_svc.tenant_svc, "ensure_secure_schema", AsyncMock()),
            patch.object(proj_svc, "get_checkpoint", AsyncMock(return_value=None)),
            patch.object(
                proj_svc,
                "fetch_meta_after_checkpoint",
                AsyncMock(return_value=meta),
            ),
            patch.object(
                proj_svc,
                "run_project_flow",
                MagicMock(return_value={"pathway": {"ok": False, "error": "poison"}}),
            ),
            patch.object(proj_svc, "enqueue_projection_dlq", enqueue),
            patch.object(proj_svc, "advance_checkpoint", advance),
            patch.object(proj_svc, "upsert_stream_results", upsert),
        ):
            result = await proj_svc.run_projection_core(
                pool,
                tenant_id=tenant_id,
                workflow_id="default_sealed",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["dlq_enqueued"], 2)
        self.assertEqual(enqueue.await_count, 2)
        self.assertTrue(
            all(call.kwargs["projection_version"] == 1 for call in enqueue.await_args_list)
        )
        advance.assert_awaited_once()
        upsert.assert_not_awaited()

    async def test_success_closes_only_matching_versioned_dlq_before_checkpoint(self) -> None:
        tenant_id = uuid4()
        event_id = str(uuid4())
        meta = [
            {
                "event_id": event_id,
                "tenant_id": str(tenant_id),
                "key_id": "session-1",
                "cipher_len": 42,
                "content_type": "application/forjd-event+v1",
                "event_type": "",
                "workflow_id": "default_sealed",
                "created_at": datetime.now(UTC),
            }
        ]
        conn = MagicMock()
        conn.fetchval = AsyncMock(side_effect=[True, None, True])
        conn.transaction = MagicMock(return_value=_AsyncContext(None))
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=_AsyncContext(conn))
        resolve = AsyncMock(return_value=1)
        advance = AsyncMock()
        with (
            patch.object(proj_svc.tenant_svc, "ensure_secure_schema", AsyncMock()),
            patch.object(proj_svc, "get_checkpoint", AsyncMock(return_value=None)),
            patch.object(
                proj_svc,
                "fetch_meta_after_checkpoint",
                AsyncMock(return_value=meta),
            ),
            patch.object(
                proj_svc,
                "run_project_flow",
                MagicMock(return_value={"pathway": {"ok": True}, "stream_results": []}),
            ),
            patch.object(
                proj_svc,
                "upsert_stream_results",
                AsyncMock(return_value=0),
            ),
            patch.object(proj_svc, "resolve_projection_dlq_for_events", resolve),
            patch.object(proj_svc, "advance_checkpoint", advance),
        ):
            result = await proj_svc.run_projection_core(
                pool,
                tenant_id=tenant_id,
                workflow_id="default_sealed",
            )

        self.assertTrue(result["ok"])
        resolve.assert_awaited_once_with(
            conn,
            tenant_id=str(tenant_id),
            source_event_ids=[event_id],
            workflow_id="default_sealed",
            projection_name="sealed.default",
            projection_version=1,
        )
        advance.assert_awaited_once()

    def test_dlq_identity_is_projection_version_specific(self) -> None:
        args = {
            "source_event_id": str(uuid4()),
            "workflow_id": "default_sealed",
            "projection_name": "sealed.default",
        }
        self.assertNotEqual(
            proj_svc._dlq_dedupe_key(**args, projection_version=1),
            proj_svc._dlq_dedupe_key(**args, projection_version=2),
        )

    async def test_live_recovery_does_not_steal_an_active_retry_lease(self) -> None:
        conn = MagicMock()
        conn.execute = AsyncMock(return_value="UPDATE 0")
        await proj_svc.resolve_projection_dlq_for_events(
            conn,
            tenant_id=str(uuid4()),
            source_event_ids=[str(uuid4())],
            workflow_id="default_sealed",
            projection_name="sealed.default",
            projection_version=1,
        )
        query = conn.execute.await_args.args[0]
        self.assertIn("locked_by IS NULL OR lease_expires_at <= NOW()", query)

    def test_detector_and_aggregate_result_keys_are_deterministic(self) -> None:
        source = str(uuid4())
        base = {
            "source_event_id": source,
            "kind": "transform",
            "workflow_id": "default_sealed",
        }
        size = proj_svc._projection_result_key(
            {**base, "features": {"detector": "size_anomaly"}},
            projection_name="sealed.default",
            projection_version=2,
        )
        rate = proj_svc._projection_result_key(
            {**base, "features": {"detector": "rate_anomaly"}},
            projection_name="sealed.default",
            projection_version=2,
        )
        self.assertNotEqual(size, rate)

        ids = [str(uuid4()), str(uuid4())]
        first = proj_svc._projection_result_key(
            {"kind": "rollup", "workflow_id": "default_sealed"},
            projection_name="sealed.default",
            projection_version=2,
            aggregate_event_ids=ids,
        )
        second = proj_svc._projection_result_key(
            {"kind": "rollup", "workflow_id": "default_sealed"},
            projection_name="sealed.default",
            projection_version=2,
            aggregate_event_ids=list(reversed(ids)),
        )
        self.assertEqual(first, second)

    async def test_upsert_preserves_multiple_detectors_without_delete(self) -> None:
        tenant_id = str(uuid4())
        event_id = str(uuid4())
        conn = MagicMock()
        conn.execute = AsyncMock(return_value="INSERT 0 1")
        rows = [
            {
                "tenant_id": tenant_id,
                "source_event_id": event_id,
                "kind": "transform",
                "projection_name": "sealed.default",
                "workflow_id": "default_sealed",
                "features": {"detector": detector},
            }
            for detector in ("size_anomaly", "rate_anomaly")
        ]
        written = await proj_svc.upsert_stream_results(
            conn,
            rows,
            projection_version=3,
            expected_tenant_ids={tenant_id},
            expected_event_ids={event_id},
        )
        self.assertEqual(written, 2)
        queries = [call.args[0] for call in conn.execute.await_args_list]
        self.assertTrue(all("DELETE" not in query for query in queries))
        self.assertTrue(all("ON CONFLICT" in query for query in queries))
        keys = [call.args[-1] for call in conn.execute.await_args_list]
        self.assertEqual(len(set(keys)), 2)

    async def test_checkpoint_query_uses_tuple_and_canonical_bytes(self) -> None:
        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])
        await proj_svc.fetch_meta_after_checkpoint(
            pool,
            tenant_id=uuid4(),
            after_created_at=datetime.now(UTC),
            after_event_id=uuid4(),
            workflow_id=None,
            limit=20,
        )
        query = pool.fetch.await_args.args[0]
        self.assertIn("(created_at, id) >", query)
        self.assertIn("ciphertext_bytes AS cipher_len", query)

    async def test_checkpoint_update_is_monotonic(self) -> None:
        pool = MagicMock()
        pool.execute = AsyncMock(return_value="UPDATE 1")
        await proj_svc.advance_checkpoint(
            pool,
            tenant_id=uuid4(),
            projection_name="sealed.default",
            workflow_id="default_sealed",
            last_event_id=str(uuid4()),
            last_created_at=datetime.now(UTC),
        )
        query = pool.execute.await_args.args[0]
        self.assertIn("EXCLUDED.last_created_at, EXCLUDED.last_event_id", query)
        self.assertIn("> (projection_checkpoints.last_created_at", query)

    async def test_projection_worker_pages_all_tenants(self) -> None:
        first_page = [{"tenant_id": UUID(int=value)} for value in range(1, 51)]
        second_page = [{"tenant_id": UUID(int=value)} for value in range(51, 53)]
        pool = MagicMock()
        pool.fetch = AsyncMock(side_effect=[first_page, second_page])
        with patch.object(projection_worker_svc, "all_workflows", return_value=[]):
            result = await projection_worker_svc.tick_projections(pool)
        self.assertTrue(result["ok"])
        self.assertEqual(result["tenants"], 52)
        self.assertEqual(pool.fetch.await_count, 2)


class ReplayAndMigrationReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_retry_lookup_is_tenant_bound(self) -> None:
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=None)
        await replay_svc.fetch_meta_event(pool, tenant_id=uuid4(), event_id=uuid4())
        query = pool.fetchrow.await_args.args[0]
        self.assertIn("tenant_id = $1::uuid AND id = $2::uuid", query)
        self.assertIn("ciphertext_bytes AS cipher_len", query)

    def test_backoff_is_bounded(self) -> None:
        self.assertEqual(replay_svc._retry_backoff_seconds(1), 30)
        self.assertEqual(replay_svc._retry_backoff_seconds(2), 60)
        self.assertEqual(replay_svc._retry_backoff_seconds(100), 3600)

    async def test_dlq_retry_claims_lease_and_processes_exact_event(self) -> None:
        tenant_id = uuid4()
        source_id = uuid4()
        dlq_id = uuid4()
        user = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(tenant_id),
            scopes=frozenset({"replay:write"}),
        )
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            return_value={
                "id": dlq_id,
                "source_event_id": str(source_id),
                "workflow_id": "default_sealed",
                "projection_name": "sealed.default",
                "projection_version": 1,
                "payload_meta": {},
                "attempts": 1,
                "max_attempts": 10,
            }
        )
        pool.execute = AsyncMock(return_value="UPDATE 1")
        meta = {
            "event_id": str(source_id),
            "tenant_id": str(tenant_id),
            "key_id": "session-1",
            "cipher_len": 42,
            "content_type": "application/forjd-event+v1",
            "event_type": "",
            "workflow_id": "default_sealed",
            "created_at": datetime.now(UTC),
        }
        exact = AsyncMock(return_value=meta)
        with (
            patch.object(replay_svc.tenant_svc, "require_tenant_access", AsyncMock()),
            patch.object(replay_svc, "fetch_meta_event", exact),
            patch.object(
                replay_svc,
                "run_project_flow",
                MagicMock(
                    return_value={
                        "pathway": {"ok": True},
                        "stream_results": [],
                    }
                ),
            ),
            patch.object(
                replay_svc.proj_svc,
                "upsert_stream_results",
                AsyncMock(return_value=0),
            ),
        ):
            result = await replay_svc.retry_dlq_item(
                pool,
                user=user,
                tenant_id=tenant_id,
                dlq_id=dlq_id,
            )
        self.assertTrue(result["ok"])
        claim_query = pool.fetchrow.await_args.args[0]
        self.assertIn("attempts = attempts + 1", claim_query)
        self.assertIn("lease_expires_at", claim_query)
        self.assertIn("projection_version", claim_query)
        exact.assert_awaited_once_with(pool, tenant_id=tenant_id, event_id=source_id)

    async def test_dlq_retry_fails_closed_on_projection_version_drift(self) -> None:
        tenant_id = uuid4()
        source_id = uuid4()
        dlq_id = uuid4()
        user = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="service",
            raw_claims={},
            kind=PrincipalKind.SERVICE,
            tenant_id=str(tenant_id),
            scopes=frozenset({"replay:write"}),
        )
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            return_value={
                "id": dlq_id,
                "source_event_id": str(source_id),
                "workflow_id": "default_sealed",
                "projection_name": "sealed.default",
                "projection_version": 2,
                "payload_meta": {},
                "attempts": 1,
                "max_attempts": 10,
            }
        )
        pool.execute = AsyncMock(return_value="UPDATE 1")
        meta = {
            "event_id": str(source_id),
            "tenant_id": str(tenant_id),
            "key_id": "session-1",
            "cipher_len": 42,
            "content_type": "application/forjd-event+v1",
            "event_type": "",
            "workflow_id": "default_sealed",
            "created_at": datetime.now(UTC),
        }
        run = MagicMock()
        with (
            patch.object(replay_svc.tenant_svc, "require_tenant_access", AsyncMock()),
            patch.object(replay_svc, "fetch_meta_event", AsyncMock(return_value=meta)),
            patch.object(replay_svc, "run_project_flow", run),
            patch.object(
                replay_svc.proj_svc,
                "upsert_stream_results",
                AsyncMock(),
            ) as upsert,
        ):
            result = await replay_svc.retry_dlq_item(
                pool,
                user=user,
                tenant_id=tenant_id,
                dlq_id=dlq_id,
            )

        self.assertFalse(result["ok"])
        self.assertIn("version", result["error"])
        run.assert_not_called()
        upsert.assert_not_awaited()
        backoff_query = pool.execute.await_args.args[0]
        self.assertIn("next_attempt_at", backoff_query)

    def test_migrations_are_contiguous_through_024(self) -> None:
        migrations = apply_sql_migrations._migration_files()
        versions = [version for version, _path in migrations]
        self.assertGreaterEqual(versions[-1], 21)
        self.assertEqual(versions, list(range(3, versions[-1] + 1)))
        migration_names = {version: path.name for version, path in migrations}
        self.assertEqual(migration_names[21], "021_ingest_projection_reliability.sql")
        self.assertEqual(migration_names[24], "024_durable_ingest_processing.sql")

    def test_migration_contains_reliability_contract(self) -> None:
        sql = (ROOT / "sql/021_ingest_projection_reliability.sql").read_text()
        for marker in (
            "ciphertext_bytes",
            "ingest_fingerprint",
            "projection_result_key",
            "projection_dlq_open_dedupe_uidx",
            "tenant_erase_receipts",
            "erased_credential_hash",
            "tenant_erase_receipts_credential_hash_uidx",
            "projection_dlq_projection_version_positive",
        ):
            self.assertIn(marker, sql)


class EmbeddingContractTests(unittest.TestCase):
    def test_embedding_dimension_and_finite_values_match_vector_16(self) -> None:
        with self.assertRaises(ValidationError):
            EmbeddingIngestRequest(
                tenant_id=uuid4(),
                model_version="v1",
                embedding=[0.0] * 15,
            )
        with self.assertRaises(ValidationError):
            EmbeddingIngestRequest(
                tenant_id=uuid4(),
                model_version="v1",
                embedding=[float("nan")] + [0.0] * 15,
            )

    def test_sealed_context_is_all_or_none(self) -> None:
        with self.assertRaises(ValidationError):
            EmbeddingIngestRequest(
                tenant_id=uuid4(),
                model_version="v1",
                context_key_id="key-1",
            )
        request = EmbeddingIngestRequest(
            tenant_id=uuid4(),
            model_version="v1",
            context_key_id="key-1",
            context_nonce=base64.b64encode(b"n" * 12).decode(),
            context_ciphertext=base64.b64encode(b"c" * 16).decode(),
        )
        self.assertEqual(request.context_key_id, "key-1")


if __name__ == "__main__":
    unittest.main()
