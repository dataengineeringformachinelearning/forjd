"""Durable canonical ingest processing ledger and recovery regressions."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.core.auth import AuthUser, PrincipalKind
from app.services import ingest_processing as processing_svc
from app.workflows.registry import resolve_workflow

ROOT = Path(__file__).resolve().parents[1]


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *_args: object) -> None:
        return None


def _event(*, event_id: UUID, tenant_id: UUID) -> dict[str, object]:
    return {
        "event_id": str(event_id),
        "tenant_id": str(tenant_id),
        "key_id": "session-1",
        "cipher_len": 42,
        "content_type": "application/forjd-event+v1",
        "event_type": "",
        "workflow_id": "default_sealed",
        "created_at": datetime.now(UTC),
        # The ledger sanitizer must drop unknown fields rather than retaining a
        # caller-controlled or future sensitive field.
        "ciphertext": "must-not-persist",
    }


def _claimed_row(*, event_ids: list[UUID] | None = None) -> dict[str, object]:
    ids = event_ids or [uuid4()]
    tenant_id = uuid4()
    workflow = resolve_workflow(
        content_type="application/forjd-event+v1",
        workflow_id="default_sealed",
    )
    snapshot = processing_svc.workflow_snapshot(workflow)
    events = [_event(event_id=event_id, tenant_id=tenant_id) for event_id in ids]
    safe_events = processing_svc._safe_events(events)
    return {
        "id": uuid4(),
        "acceptance_id": uuid4(),
        "group_ordinal": 0,
        "requested_by": "svc:worker-test",
        "workflow_id": workflow.id,
        "workflow_version": workflow.version,
        "workflow_hash": processing_svc.workflow_snapshot_hash(snapshot),
        "workflow_snapshot": snapshot,
        "projection_name": workflow.pipeline.projection_name,
        "projection_version": workflow.pipeline.projection.version,
        "content_type": "application/forjd-event+v1",
        "event_type": None,
        "events": safe_events,
        "event_ids": ids,
        "tenant_ids": [tenant_id],
        "status": "running",
        "attempts": 1,
        "max_attempts": 10,
    }


class ProcessingReceiptTests(unittest.IsolatedAsyncioTestCase):
    def test_workflow_hash_is_canonical_and_binds_configuration(self) -> None:
        workflow = resolve_workflow(
            content_type="application/forjd-event+v1",
            workflow_id="default_sealed",
        )
        snapshot = processing_svc.workflow_snapshot(workflow)
        first = processing_svc.workflow_snapshot_hash(snapshot)
        self.assertEqual(first, processing_svc.workflow_snapshot_hash(dict(snapshot)))
        changed = {**snapshot, "version": int(snapshot["version"]) + 1}
        self.assertNotEqual(first, processing_svc.workflow_snapshot_hash(changed))

    async def test_receipt_stores_ordered_metadata_only_inside_caller_connection(self) -> None:
        workflow = resolve_workflow(
            content_type="application/forjd-event+v1",
            workflow_id="default_sealed",
        )
        tenant_id = uuid4()
        event_ids = [uuid4(), uuid4()]
        conn = MagicMock()
        conn.fetchrow = AsyncMock(
            return_value={
                "id": str(uuid4()),
                "acceptance_id": str(uuid4()),
                "group_ordinal": 0,
                "status": "queued",
                "attempts": 0,
                "max_attempts": 10,
            }
        )

        await processing_svc.register_processing_batch(
            conn,
            acceptance_id=uuid4(),
            group_ordinal=0,
            requested_by="svc:test",
            workflow=workflow,
            content_type="application/forjd-event+v1",
            event_type=None,
            events=[_event(event_id=value, tenant_id=tenant_id) for value in event_ids],
        )

        query = conn.fetchrow.await_args.args[0]
        args = conn.fetchrow.await_args.args
        self.assertIn("INSERT INTO ingest_processing_batches", query)
        self.assertEqual(args[14], [str(value) for value in event_ids])
        self.assertNotIn("must-not-persist", str(args))
        self.assertIn("workflow_snapshot", query)

    async def test_receipt_rejects_mixed_tenants(self) -> None:
        workflow = resolve_workflow(
            content_type="application/forjd-event+v1",
            workflow_id="default_sealed",
        )
        conn = MagicMock()
        conn.fetchrow = AsyncMock()
        with self.assertRaisesRegex(ValueError, "exactly one tenant"):
            await processing_svc.register_processing_batch(
                conn,
                acceptance_id=uuid4(),
                group_ordinal=0,
                requested_by="svc:test",
                workflow=workflow,
                content_type="application/forjd-event+v1",
                event_type=None,
                events=[
                    _event(event_id=uuid4(), tenant_id=uuid4()),
                    _event(event_id=uuid4(), tenant_id=uuid4()),
                ],
            )
        conn.fetchrow.assert_not_awaited()

    async def test_claim_uses_skip_locked_and_recovers_expired_leases(self) -> None:
        pool = MagicMock()
        pool.execute = AsyncMock(return_value="UPDATE 0")
        pool.fetch = AsyncMock(return_value=[])
        await processing_svc._recover_expired_processing_leases(pool)
        await processing_svc._claim_processing_batches(
            pool,
            worker_id=uuid4(),
            batch_size=10,
            batch_ids=None,
        )
        reclaim_query = pool.execute.await_args.args[0]
        claim_query = pool.fetch.await_args.args[0]
        self.assertIn("lease_expires_at <= NOW()", reclaim_query)
        self.assertIn("FOR UPDATE SKIP LOCKED", claim_query)
        self.assertIn("attempts < max_attempts", claim_query)

    def test_claim_validation_rejects_a_stored_multi_tenant_receipt(self) -> None:
        row = _claimed_row(event_ids=[uuid4(), uuid4()])
        second_tenant = uuid4()
        row["events"][1]["tenant_id"] = str(second_tenant)
        row["tenant_ids"] = [row["tenant_ids"][0], second_tenant]

        with self.assertRaisesRegex(RuntimeError, "exactly one tenant"):
            processing_svc._validated_claim(row)

    async def test_production_schema_requires_tenant_integrity_trigger(self) -> None:
        pool = MagicMock()
        pool.fetch = AsyncMock(
            side_effect=[
                [{"column_name": name} for name in processing_svc._REQUIRED_COLUMNS],
                [{"indexname": name} for name in processing_svc._REQUIRED_INDEXES],
                [
                    {"tgname": "ingest_processing_identity_immutable"},
                ],
                [{"conname": name} for name in processing_svc._REQUIRED_CONSTRAINTS],
            ]
        )
        with (
            patch.object(processing_svc.tenant_svc, "ensure_secure_schema", AsyncMock()),
            patch.object(processing_svc.settings, "SOFT_MIGRATE_SCHEMA", False),
            self.assertRaisesRegex(RuntimeError, "ingest_processing_tenant_integrity"),
        ):
            await processing_svc.ensure_ingest_processing_schema(pool)


class ProcessingExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_active_processing_lease_is_heartbeated_with_attempt_fence(self) -> None:
        row = _claimed_row()
        pool = MagicMock()
        pool.execute = AsyncMock(return_value="UPDATE 1")
        stop = __import__("asyncio").Event()
        lease_lost = __import__("asyncio").Event()
        wait_calls = 0

        async def fake_wait_for(awaitable: object, *, timeout: float) -> None:
            nonlocal wait_calls
            del timeout
            wait_calls += 1
            close = getattr(awaitable, "close", None)
            if callable(close):
                close()
            if wait_calls == 1:
                raise TimeoutError
            stop.set()

        worker_id = uuid4()
        with patch.object(processing_svc.asyncio, "wait_for", fake_wait_for):
            await processing_svc._heartbeat_processing_lease(
                pool,
                row=row,
                worker_id=worker_id,
                stop_event=stop,
                lease_lost=lease_lost,
            )

        self.assertFalse(lease_lost.is_set())
        pool.execute.assert_awaited_once()
        query = pool.execute.await_args.args[0]
        self.assertIn("lease_expires_at", query)
        self.assertIn("lease_owner = $2::uuid", query)
        self.assertIn("attempts = $3", query)

    async def test_lost_heartbeat_fence_prevents_projection_commit(self) -> None:
        row = _claimed_row()
        pool = MagicMock()

        async def lose_lease(*_args: object, **kwargs: object) -> None:
            kwargs["lease_lost"].set()

        persist = AsyncMock(
            return_value={
                "id": str(row["id"]),
                "ok": False,
                "status": "retry_scheduled",
                "written": 0,
                "dlq_enqueued": 0,
                "error": "lease lost",
            }
        )
        upsert = AsyncMock()
        with (
            patch.object(processing_svc, "_heartbeat_processing_lease", lose_lease),
            patch.object(
                processing_svc,
                "run_ingest_flow",
                return_value={"pathway": {"ok": True}, "stream_results": []},
            ),
            patch.object(processing_svc, "_persist_processing_failure", persist),
            patch.object(processing_svc.proj_svc, "upsert_stream_results", upsert),
        ):
            result = await processing_svc._process_claimed_batch(
                pool,
                row=row,
                worker_id=uuid4(),
            )

        self.assertFalse(result["ok"])
        upsert.assert_not_awaited()
        persist.assert_awaited_once()

    async def test_success_uses_stored_snapshot_and_completes_with_results_atomically(self) -> None:
        row = _claimed_row()
        conn = MagicMock()
        conn.execute = AsyncMock(return_value="UPDATE 1")
        conn.transaction = MagicMock(return_value=_AsyncContext(None))
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=_AsyncContext(conn))
        run = MagicMock(
            return_value={
                "pathway": {
                    "ok": True,
                    "count": 1,
                    "anomaly_count": 0,
                    "workflow_id": "default_sealed",
                },
                "stream_results": [],
            }
        )
        upsert = AsyncMock(return_value=0)
        resolve = AsyncMock(return_value=0)
        advance = AsyncMock()
        worker_id = uuid4()
        with (
            patch.object(processing_svc, "run_ingest_flow", run),
            patch.object(processing_svc.proj_svc, "upsert_stream_results", upsert),
            patch.object(
                processing_svc.proj_svc,
                "resolve_projection_dlq_for_events",
                resolve,
            ),
            patch.object(
                processing_svc.proj_svc,
                "advance_checkpoint_from_meta",
                advance,
            ),
        ):
            result = await processing_svc._process_claimed_batch(
                pool,
                row=row,
                worker_id=worker_id,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            processing_svc.workflow_snapshot_hash(run.call_args.kwargs["workflow_snapshot"]),
            row["workflow_hash"],
        )
        upsert.assert_awaited_once()
        advance.assert_awaited_once_with(
            conn,
            meta_rows=row["events"],
            workflow_id=row["workflow_id"],
            projection_name=row["projection_name"],
        )
        completion_query = conn.execute.await_args.args[0]
        self.assertIn("status = 'completed'", completion_query)
        self.assertIn("lease_owner", completion_query)

    async def test_failure_enqueues_dlq_and_schedules_retry_in_one_transaction(self) -> None:
        row = _claimed_row()
        conn = MagicMock()
        conn.execute = AsyncMock(return_value="UPDATE 1")
        conn.transaction = MagicMock(return_value=_AsyncContext(None))
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=_AsyncContext(conn))
        enqueue = AsyncMock(return_value=str(uuid4()))
        with (
            patch.object(
                processing_svc,
                "run_ingest_flow",
                MagicMock(side_effect=RuntimeError("processor unavailable")),
            ),
            patch.object(processing_svc.proj_svc, "enqueue_projection_dlq", enqueue),
        ):
            result = await processing_svc._process_claimed_batch(
                pool,
                row=row,
                worker_id=uuid4(),
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "retry_scheduled")
        self.assertEqual(enqueue.await_count, len(row["event_ids"]))
        retry_query = conn.execute.await_args.args[0]
        self.assertIn("retry_scheduled", retry_query)
        self.assertIn("lease_owner = NULL", retry_query)

    async def test_one_persistence_failure_does_not_block_later_claimed_batch(self) -> None:
        first = _claimed_row()
        second = _claimed_row()
        pool = MagicMock()
        pool.execute = AsyncMock(return_value="UPDATE 0")
        claim = AsyncMock(side_effect=[[first], [second], []])
        process = AsyncMock(
            side_effect=[
                RuntimeError("db write failed"),
                {
                    "id": str(second["id"]),
                    "ok": True,
                    "status": "completed",
                    "written": 1,
                    "dlq_enqueued": 0,
                },
            ]
        )
        with (
            patch.object(processing_svc.tenant_svc, "ensure_secure_schema", AsyncMock()),
            patch.object(processing_svc, "_claim_processing_batches", claim),
            patch.object(processing_svc, "_process_claimed_batch", process),
        ):
            outcomes = await processing_svc.tick_ingest_processing(pool)
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(outcomes[0]["status"], "running")
        self.assertTrue(outcomes[1]["ok"])
        self.assertEqual(process.await_count, 2)
        self.assertTrue(all(item.kwargs["batch_size"] == 1 for item in claim.await_args_list))


class ProcessingStatusAndWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_status_authorizes_every_tenant_in_a_multi_tenant_batch(self) -> None:
        tenant_ids = [uuid4(), uuid4()]
        batch_id = uuid4()
        now = datetime.now(UTC)
        pool = MagicMock()
        pool.fetchrow = AsyncMock(
            return_value={
                "id": str(batch_id),
                "acceptance_id": str(uuid4()),
                "group_ordinal": 0,
                "workflow_id": "default_sealed",
                "workflow_version": 1,
                "workflow_hash": "a" * 64,
                "projection_name": "sealed.default",
                "projection_version": 1,
                "tenant_ids": tenant_ids,
                "event_count": 2,
                "status": "running",
                "attempts": 1,
                "max_attempts": 10,
                "next_attempt_at": now,
                "last_attempt_at": now,
                "error_class": None,
                "result_summary": {},
                "created_at": now,
                "updated_at": now,
                "completed_at": None,
            }
        )
        user = AuthUser(
            user_id=str(uuid4()),
            email=None,
            role="authenticated",
            raw_claims={},
            kind=PrincipalKind.USER,
        )
        authorize = AsyncMock(return_value="member")
        with patch.object(processing_svc.tenant_svc, "require_tenant_access", authorize):
            result = await processing_svc.get_processing_batch_status(
                pool,
                user=user,
                batch_id=batch_id,
            )
        self.assertEqual(result["status"], "running")
        self.assertEqual(authorize.await_count, 2)
        self.assertNotIn("error", result)

    async def test_worker_waits_for_lazy_pool_then_processes_it(self) -> None:
        pool = MagicMock()
        pool.execute = AsyncMock(return_value="CREATE TRIGGER")
        stop = __import__("asyncio").Event()
        provider = MagicMock(side_effect=[None, pool])
        ensure = AsyncMock()
        tick = AsyncMock(return_value=[])
        waits = 0

        async def fake_wait_for(awaitable: object, *, timeout: float) -> None:
            nonlocal waits
            del timeout
            waits += 1
            close = getattr(awaitable, "close", None)
            if callable(close):
                close()
            if waits == 1:
                raise TimeoutError
            stop.set()

        with (
            patch.object(processing_svc.tenant_svc, "ensure_secure_schema", ensure),
            patch.object(processing_svc, "tick_ingest_processing", tick),
            patch.object(processing_svc.asyncio, "wait_for", fake_wait_for),
        ):
            await processing_svc.run_ingest_processing_worker(
                provider,
                stop,
                interval_seconds=0.25,
            )
        ensure.assert_awaited_once_with(pool)
        tick.assert_awaited_once()


class ProcessingMigrationTests(unittest.TestCase):
    def test_migration_has_atomic_receipt_and_worker_contract(self) -> None:
        sql = (ROOT / "sql/024_durable_ingest_processing.sql").read_text()
        for marker in (
            "ingest_processing_batches",
            "workflow_snapshot",
            "workflow_hash",
            "event_ids UUID[]",
            "ingest_processing_worker_idx",
            "ingest_processing_event_ids_gin_idx",
            "ingest_processing_identity_immutable",
            "ingest_processing_tenant_integrity",
            "enforce_ingest_processing_tenant_integrity",
            "cardinality(tenant_ids) = 1",
            "event_value->>'tenant_id' IS DISTINCT FROM NEW.tenant_ids[1]::text",
            "workflow_snapshot IS DISTINCT FROM OLD.workflow_snapshot",
            "ENABLE ROW LEVEL SECURITY",
        ):
            self.assertIn(marker, sql)
