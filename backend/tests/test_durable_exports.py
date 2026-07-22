"""Durable export contract, idempotency, serialization, and signed download tests."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.core.auth import AuthUser, PrincipalKind
from app.core.worker_health import WorkerHealthRegistry
from app.models.domain import CreateExportRequest
from app.services import exports

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
JOB_ID = UUID("22222222-2222-2222-2222-222222222222")
ROOT = Path(__file__).resolve().parents[1]


def _user() -> AuthUser:
    return AuthUser(
        user_id="33333333-3333-3333-3333-333333333333",
        email=None,
        role="service",
        raw_claims={},
        kind=PrincipalKind.SERVICE,
        tenant_id=str(TENANT_ID),
        scopes=frozenset({"exports:read", "exports:write"}),
    )


def _row(*, fingerprint: str, status: str = "queued") -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": str(JOB_ID),
        "tenant_id": str(TENANT_ID),
        "format": "csv",
        "status": status,
        "source_kind": "analytics",
        "idempotency_key": "export:test:0001",
        "request_fingerprint": fingerprint,
        "filters": {"days": 7, "site_url": ""},
        "object_key": "tenants/t/exports/j/export.csv" if status == "completed" else None,
        "checksum_sha256": "a" * 64 if status == "completed" else None,
        "byte_size": 42 if status == "completed" else 0,
        "content_type": "text/csv; charset=utf-8",
        "error": None,
        "attempts": 1,
        "max_attempts": 5,
        "next_attempt_at": now,
        "created_by_actor_id": _user().user_id,
        "created_at": now,
        "completed_at": now if status == "completed" else None,
        "expires_at": now + timedelta(days=7) if status == "completed" else None,
    }


class TestExportContract(unittest.TestCase):
    def test_migration_drops_legacy_checks_before_state_transition(self) -> None:
        sql = (ROOT / "sql/023_durable_exports.sql").read_text()
        drop_position = sql.index("DROP CONSTRAINT IF EXISTS export_jobs_status_check")
        transition_position = sql.index("UPDATE public.export_jobs")
        self.assertLess(drop_position, transition_position)
        self.assertIn(
            "status = 'running' AND (lease_owner IS NULL OR lease_expires_at IS NULL)",
            sql,
        )
        self.assertIn("export_jobs_lease_shape", sql)

    def test_requires_stable_idempotency_and_supports_product_formats(self) -> None:
        request = CreateExportRequest.model_validate(
            {
                "tenant_id": TENANT_ID,
                "idempotency_key": "export:test:0001",
                "source_kind": "lighthouse",
                "format": "pdf",
                "days": 30,
            }
        )
        self.assertEqual(request.format, "pdf")
        self.assertEqual(request.limit, 1_000)
        with self.assertRaises(ValidationError):
            CreateExportRequest.model_validate(
                {
                    "tenant_id": TENANT_ID,
                    "idempotency_key": "export:test:0002",
                    "format": "pdf",
                    "limit": 1_001,
                }
            )
        with self.assertRaises(ValidationError):
            CreateExportRequest.model_validate({"tenant_id": TENANT_ID})

    def test_renders_csv_json_parquet_and_pdf(self) -> None:
        rows = [{"id": "one", "score": 0.75}]
        self.assertIn(b"score", exports._render_export(rows, "csv"))
        self.assertIn(b"0.75", exports._render_export(rows, "json"))
        self.assertTrue(exports._render_export(rows, "parquet").startswith(b"PAR1"))
        self.assertTrue(exports._render_export(rows, "pdf").startswith(b"%PDF"))
        with self.assertRaisesRegex(ValueError, "at most 1000"):
            exports._render_export([{"id": index} for index in range(1_001)], "pdf")


class TestExportIdempotency(unittest.IsolatedAsyncioTestCase):
    async def test_worker_reports_successful_ticks_not_just_task_liveness(self) -> None:
        stop = exports.asyncio.Event()
        health = WorkerHealthRegistry()
        health.started("exports", stale_after_seconds=60)

        async def one_tick(*args: object, **kwargs: object) -> int:
            stop.set()
            return 0

        with patch.object(exports, "tick_export_jobs", side_effect=one_tick):
            await exports.run_export_worker(AsyncMock(), stop, health=health)

        healthy, detail = health.status("exports")
        self.assertTrue(healthy)
        self.assertEqual(detail["state"], "healthy")

    async def test_production_schema_requires_complete_worker_contract(self) -> None:
        pool = AsyncMock()
        pool.fetch.side_effect = [
            [{"column_name": name} for name in exports._REQUIRED_COLUMNS],
            [
                {"indexname": name}
                for name in exports._REQUIRED_INDEXES
                if name != "export_jobs_worker_idx"
            ],
            [{"conname": name} for name in exports._REQUIRED_CONSTRAINTS],
        ]
        with (
            patch.object(exports.tenant_svc, "ensure_secure_schema", new=AsyncMock()),
            patch.object(exports.settings, "SOFT_MIGRATE_SCHEMA", False),
            self.assertRaisesRegex(RuntimeError, "index:export_jobs_worker_idx"),
        ):
            await exports.ensure_export_schema(pool)

    async def test_soft_upgrade_drops_legacy_checks_before_requeue(self) -> None:
        pool = AsyncMock()
        with (
            patch.object(exports.tenant_svc, "ensure_secure_schema", new=AsyncMock()),
            patch.object(exports.settings, "SOFT_MIGRATE_SCHEMA", True),
        ):
            await exports.ensure_export_schema(pool)

        queries = [str(item.args[0]) for item in pool.execute.await_args_list]
        drop_position = next(
            index
            for index, query in enumerate(queries)
            if "DROP CONSTRAINT IF EXISTS export_jobs_status_check" in query
        )
        transition_position = next(
            index for index, query in enumerate(queries) if "SET idempotency_key" in query
        )
        self.assertLess(drop_position, transition_position)
        self.assertIn("lease_owner IS NULL", queries[transition_position])
        joined_queries = "\n".join(queries)
        for index_name in exports._REQUIRED_INDEXES:
            self.assertIn(index_name, joined_queries)

    async def test_worker_claims_each_serial_export_just_in_time(self) -> None:
        claimed_row = {
            "id": str(JOB_ID),
            "tenant_id": str(TENANT_ID),
            "format": "csv",
            "source_kind": "analytics",
            "filters": {},
            "attempts": 1,
            "max_attempts": 5,
        }
        pool = AsyncMock()
        pool.fetch.side_effect = [[claimed_row], [claimed_row], []]
        process = AsyncMock()
        with (
            patch.object(exports, "ensure_export_schema", new=AsyncMock()),
            patch.object(exports, "_process_claimed_job", new=process),
            patch.object(exports, "_expire_artifacts", new=AsyncMock()),
        ):
            processed = await exports.tick_export_jobs(
                pool,
                batch_size=25,
                worker_id=uuid4(),
            )

        self.assertEqual(processed, 2)
        self.assertEqual(process.await_count, 2)
        self.assertEqual(pool.fetch.await_count, 3)
        self.assertTrue(all("LIMIT 1" in item.args[0] for item in pool.fetch.await_args_list))

    async def test_exact_retry_returns_original_job(self) -> None:
        fingerprint = exports._request_fingerprint(
            format="csv", source_kind="analytics", limit=10000, days=7, site_url=None
        )
        pool = AsyncMock()
        pool.fetchrow.side_effect = [None, _row(fingerprint=fingerprint)]
        with (
            patch.object(exports.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(exports, "ensure_export_schema", new=AsyncMock()),
        ):
            result = await exports.create_export_job(
                pool,
                user=_user(),
                tenant_id=TENANT_ID,
                idempotency_key="export:test:0001",
                source_kind="analytics",
            )
        self.assertTrue(result["duplicate"])
        self.assertEqual(result["job"]["id"], str(JOB_ID))

    async def test_changed_retry_conflicts(self) -> None:
        pool = AsyncMock()
        pool.fetchrow.side_effect = [None, _row(fingerprint="0" * 64)]
        with (
            patch.object(exports.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(exports, "ensure_export_schema", new=AsyncMock()),
            self.assertRaises(HTTPException) as error,
        ):
            await exports.create_export_job(
                pool,
                user=_user(),
                tenant_id=TENANT_ID,
                idempotency_key="export:test:0001",
                source_kind="analytics",
            )
        self.assertEqual(error.exception.status_code, 409)

    async def test_service_rejects_oversize_pdf_without_silent_truncation(self) -> None:
        with (
            patch.object(exports.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(exports, "ensure_export_schema", new=AsyncMock()),
            self.assertRaises(HTTPException) as error,
        ):
            await exports.create_export_job(
                AsyncMock(),
                user=_user(),
                tenant_id=TENANT_ID,
                idempotency_key="export:test:pdf-too-large",
                format="pdf",
                limit=1_001,
            )
        self.assertEqual(error.exception.status_code, 422)

    async def test_source_pages_are_snapshot_bounded_before_rendering(self) -> None:
        pool = MagicMock()
        connection = MagicMock()
        acquire_context = AsyncMock()
        acquire_context.__aenter__.return_value = connection
        pool.acquire.return_value = acquire_context
        transaction_context = AsyncMock()
        connection.transaction.return_value = transaction_context
        page = [{"id": "one", "description": "x" * 256}]
        with (
            patch.object(exports, "_load_source_rows", new=AsyncMock(return_value=page)),
            patch.object(exports.settings, "EXPORT_MAX_SOURCE_BYTES", 128),
            self.assertRaises(exports.ExportSourceTooLargeError),
        ):
            await exports._load_source_rows_bounded(
                pool,
                tenant_id=TENANT_ID,
                source_kind="vulnerabilities",
                filters={},
                limit=1,
            )

        connection.transaction.assert_called_once_with(isolation="repeatable_read", readonly=True)

    async def test_delete_job_removes_artifact_and_row(self) -> None:
        fingerprint = exports._request_fingerprint(
            format="csv", source_kind="analytics", limit=10000, days=7, site_url=None
        )
        completed = _row(fingerprint=fingerprint, status="completed")
        pool = AsyncMock()
        pool.execute.return_value = "DELETE 1"
        with (
            patch.object(exports.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(exports, "ensure_export_schema", new=AsyncMock()),
            patch.object(exports, "_fetch_job_row", new=AsyncMock(return_value=completed)),
            patch.object(exports, "_delete_artifact", new=AsyncMock()) as delete_artifact,
        ):
            result = await exports.delete_job(
                pool, user=_user(), tenant_id=TENANT_ID, job_id=JOB_ID
            )
        self.assertEqual(result, {"ok": True, "id": str(JOB_ID)})
        delete_artifact.assert_awaited_once_with(completed["object_key"])
        self.assertIn("DELETE FROM export_jobs", pool.execute.await_args.args[0])

    async def test_delete_job_without_artifact_only_removes_row(self) -> None:
        fingerprint = exports._request_fingerprint(
            format="csv", source_kind="analytics", limit=10000, days=7, site_url=None
        )
        failed = _row(fingerprint=fingerprint, status="failed")
        pool = AsyncMock()
        pool.execute.return_value = "DELETE 1"
        with (
            patch.object(exports.tenant_svc, "require_tenant_access", new=AsyncMock()),
            patch.object(exports, "ensure_export_schema", new=AsyncMock()),
            patch.object(exports, "_fetch_job_row", new=AsyncMock(return_value=failed)),
            patch.object(exports, "_delete_artifact", new=AsyncMock()) as delete_artifact,
        ):
            result = await exports.delete_job(
                pool, user=_user(), tenant_id=TENANT_ID, job_id=JOB_ID
            )
        self.assertEqual(result, {"ok": True, "id": str(JOB_ID)})
        delete_artifact.assert_not_awaited()
        self.assertIn("DELETE FROM export_jobs", pool.execute.await_args.args[0])

    async def test_completed_job_returns_short_lived_signed_download(self) -> None:
        fingerprint = exports._request_fingerprint(
            format="csv", source_kind="analytics", limit=10000, days=7, site_url=None
        )
        pool = AsyncMock()
        with (
            patch.object(
                exports,
                "get_job",
                new=AsyncMock(
                    return_value=exports._job_dict(
                        _row(fingerprint=fingerprint, status="completed")
                    )
                ),
            ),
            patch.object(exports.object_storage, "is_configured", return_value=True),
            patch.object(
                exports.object_storage,
                "generate_presigned_get",
                return_value="https://objects.example/signed",
            ) as presign,
        ):
            result = await exports.create_download(
                pool, user=_user(), tenant_id=TENANT_ID, job_id=JOB_ID
            )
        self.assertEqual(result["url"], "https://objects.example/signed")
        self.assertLessEqual(result["expires_in"], 900)
        self.assertEqual(
            presign.call_args.kwargs["key"],
            _row(fingerprint=fingerprint, status="completed")["object_key"],
        )

    async def test_signed_download_never_outlives_artifact(self) -> None:
        fingerprint = exports._request_fingerprint(
            format="csv", source_kind="analytics", limit=10000, days=7, site_url=None
        )
        job = exports._job_dict(_row(fingerprint=fingerprint, status="completed"))
        job["expires_at"] = datetime.now(UTC) + timedelta(seconds=12)
        with (
            patch.object(exports, "get_job", new=AsyncMock(return_value=job)),
            patch.object(exports.object_storage, "is_configured", return_value=True),
            patch.object(
                exports.object_storage,
                "generate_presigned_get",
                return_value="https://objects.example/signed",
            ) as presign,
        ):
            result = await exports.create_download(
                AsyncMock(), user=_user(), tenant_id=TENANT_ID, job_id=JOB_ID
            )
        self.assertGreater(result["expires_in"], 0)
        self.assertLessEqual(result["expires_in"], 12)
        self.assertEqual(presign.call_args.kwargs["expires_in"], result["expires_in"])

    async def test_worker_persists_planned_key_before_upload(self) -> None:
        owner = uuid4()
        row = {
            "id": str(JOB_ID),
            "tenant_id": str(TENANT_ID),
            "format": "csv",
            "source_kind": "analytics",
            "filters": {"limit": 10},
            "attempts": 1,
            "max_attempts": 5,
            "object_key": None,
        }
        pool = AsyncMock()
        pool.execute.side_effect = ["UPDATE 1", "UPDATE 1", "UPDATE 1"]

        async def assert_planned_before_upload(*args: object, **kwargs: object) -> str:
            self.assertEqual(pool.execute.await_count, 2)
            self.assertIn("SET object_key = $3", pool.execute.await_args_list[0].args[0])
            self.assertEqual(kwargs["object_key"], pool.execute.await_args_list[0].args[3])
            self.assertIn("SET lease_expires_at", pool.execute.await_args_list[1].args[0])
            return str(kwargs["object_key"])

        with (
            patch.object(exports, "_load_source_rows_bounded", new=AsyncMock(return_value=[])),
            patch.object(exports, "_store_artifact", side_effect=assert_planned_before_upload),
            patch.object(
                exports,
                "_artifact_key",
                return_value="tenants/t/exports/j/planned.csv",
            ),
        ):
            await exports._process_claimed_job(pool, owner=owner, row=row)

        completed = pool.execute.await_args_list[2]
        self.assertIn("status = 'completed'", completed.args[0])
        # $6 (expires_at TTL) is cast ::text — asyncpg rejects int for text params.
        self.assertIsInstance(completed.args[6], str)

    async def test_failed_cleanup_retains_durable_artifact_pointer(self) -> None:
        owner = uuid4()
        row = {
            "id": str(JOB_ID),
            "tenant_id": str(TENANT_ID),
            "format": "csv",
            "source_kind": "analytics",
            "filters": {"limit": 10},
            "attempts": 1,
            "max_attempts": 5,
            "object_key": None,
        }
        pool = AsyncMock()
        pool.execute.side_effect = ["UPDATE 1", "UPDATE 1", "UPDATE 1"]
        planned_key = "tenants/t/exports/j/planned.csv"
        with (
            patch.object(exports, "_load_source_rows_bounded", new=AsyncMock(return_value=[])),
            patch.object(exports, "_artifact_key", return_value=planned_key),
            patch.object(exports, "_store_artifact", new=AsyncMock(side_effect=OSError("put"))),
            patch.object(exports, "_delete_artifact", new=AsyncMock(side_effect=OSError("delete"))),
        ):
            await exports._process_claimed_job(pool, owner=owner, row=row)

        failure = pool.execute.await_args_list[2]
        self.assertIn("object_key = CASE", failure.args[0])
        self.assertFalse(failure.args[4])
        self.assertEqual(failure.args[5], planned_key)

    async def test_export_lease_heartbeat_detects_fencing(self) -> None:
        stop = exports.asyncio.Event()
        lost = exports.asyncio.Event()
        renew = AsyncMock(side_effect=[True, False])
        with (
            patch.object(exports, "_EXPORT_HEARTBEAT_SECONDS", 0.001),
            patch.object(exports, "_renew_export_lease", new=renew),
        ):
            await exports._heartbeat_export_lease(
                AsyncMock(),
                job_id=str(JOB_ID),
                owner=uuid4(),
                stop_event=stop,
                lease_lost=lost,
            )

        self.assertTrue(lost.is_set())
        self.assertEqual(renew.await_count, 2)

    async def test_terminal_failed_artifact_cleanup_is_retried(self) -> None:
        key = "tenants/t/exports/j/failed.csv"
        pool = AsyncMock()
        pool.fetch.return_value = [{"id": str(JOB_ID), "object_key": key, "status": "failed"}]
        pool.execute.return_value = "UPDATE 1"
        with patch.object(exports, "_delete_artifact", new=AsyncMock()) as delete:
            cleaned = await exports._expire_artifacts(pool)

        self.assertEqual(cleaned, 1)
        delete.assert_awaited_once_with(key)
        self.assertIn("status = 'failed'", pool.execute.await_args.args[0])

    async def test_artifact_cleanup_failure_gets_a_backoff(self) -> None:
        key = "tenants/t/exports/j/failed.csv"
        pool = AsyncMock()
        pool.fetch.return_value = [{"id": str(JOB_ID), "object_key": key, "status": "failed"}]
        pool.execute.return_value = "UPDATE 1"
        with patch.object(
            exports,
            "_delete_artifact",
            new=AsyncMock(side_effect=OSError("storage unavailable")),
        ):
            cleaned = await exports._expire_artifacts(pool)

        self.assertEqual(cleaned, 0)
        self.assertIn("INTERVAL '5 minutes'", pool.execute.await_args.args[0])

    async def test_each_worker_attempt_uses_a_distinct_artifact_key(self) -> None:
        with (
            patch.object(exports.object_storage, "is_configured", return_value=True),
            patch.object(exports.object_storage, "put_bytes"),
            patch.object(
                exports.object_storage,
                "export_object_key",
                side_effect=lambda **kwargs: kwargs["filename"],
            ),
        ):
            first = await exports._store_artifact(
                b"one",
                tenant_id=TENANT_ID,
                job_id=str(JOB_ID),
                format="csv",
                checksum="a" * 64,
                artifact_version="1-worker-a",
            )
            second = await exports._store_artifact(
                b"two",
                tenant_id=TENANT_ID,
                job_id=str(JOB_ID),
                format="csv",
                checksum="b" * 64,
                artifact_version="2-worker-b",
            )
        self.assertNotEqual(first, second)


# --- Source query parameter typing (regression: asyncpg rejects int for ::text) ---
class TestLoadSourceRowParams(unittest.IsolatedAsyncioTestCase):
    async def test_days_binds_as_text_for_every_source_kind(self) -> None:
        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])
        for source_kind in (
            "stream_results",
            "analytics",
            "threat",
            "lighthouse",
            "vulnerabilities",
        ):
            await exports._load_source_rows(
                pool,
                tenant_id=TENANT_ID,
                source_kind=source_kind,
                filters={"days": 7, "site_url": ""},
                limit=10,
            )
            args = pool.fetch.await_args.args
            self.assertIsInstance(args[2], str, f"{source_kind}: $2 (days) must bind as text")


if __name__ == "__main__":
    unittest.main()
