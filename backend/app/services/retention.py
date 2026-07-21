"""Data retention sweep — bounded deletes for aged sealed telemetry and receipts.

Enforces the FORJD-side retention policy that BOOK.md/Appendix D assigns to the
data plane: sealed ``telemetry_events`` and ``stream_results`` beyond the
retention window, expired/revoked ``crypto_sessions``, and completed
``ingest_processing_batches`` receipts are deleted in small batches so sweeps
never take long locks. Export artifacts are expired by the exports worker.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Final

import asyncpg

from app.core.config import settings
from app.core.worker_health import WorkerHealthRegistry

logger = logging.getLogger("forjd.retention")

WORKER_NAME = "retention"
# Bounded per-table delete batch; the hourly cadence absorbs backlogs.
BATCH_LIMIT: Final[int] = 5000


# --- Bounded batch delete helper ---
async def _delete_batch(pool: asyncpg.Pool, query: str, *args: object) -> int:
    result = await pool.execute(query, *args)
    # asyncpg returns e.g. "DELETE 42".
    try:
        return int(result.split()[-1])
    except (ValueError, IndexError, AttributeError):
        return 0


# --- One sweep across all retention-managed tables ---
async def tick_retention(pool: asyncpg.Pool) -> dict[str, int]:
    deleted: dict[str, int] = {}

    deleted["telemetry_events"] = await _delete_batch(
        pool,
        """
        DELETE FROM telemetry_events
        WHERE ctid IN (
            SELECT ctid FROM telemetry_events
            WHERE created_at < NOW() - make_interval(days => $1)
            LIMIT $2
        )
        """,
        settings.RETENTION_TELEMETRY_DAYS,
        BATCH_LIMIT,
    )

    deleted["stream_results"] = await _delete_batch(
        pool,
        """
        DELETE FROM stream_results
        WHERE ctid IN (
            SELECT ctid FROM stream_results
            WHERE created_at < NOW() - make_interval(days => $1)
            LIMIT $2
        )
        """,
        settings.RETENTION_RESULTS_DAYS,
        BATCH_LIMIT,
    )

    # E2EE boundary: expired or revoked session public keys have no value and
    # keeping them only widens the audit surface.
    deleted["crypto_sessions"] = await _delete_batch(
        pool,
        """
        DELETE FROM crypto_sessions
        WHERE ctid IN (
            SELECT ctid FROM crypto_sessions
            WHERE (expires_at IS NOT NULL AND expires_at < NOW() - INTERVAL '7 days')
               OR (revoked_at IS NOT NULL AND revoked_at < NOW() - INTERVAL '7 days')
            LIMIT $1
        )
        """,
        BATCH_LIMIT,
    )

    deleted["ingest_receipts"] = await _delete_batch(
        pool,
        """
        DELETE FROM ingest_processing_batches
        WHERE ctid IN (
            SELECT ctid FROM ingest_processing_batches
            WHERE status = 'completed'
              AND completed_at < NOW() - make_interval(days => $1)
            LIMIT $2
        )
        """,
        settings.RETENTION_RECEIPTS_DAYS,
        BATCH_LIMIT,
    )

    total = sum(deleted.values())
    if total:
        logger.info("retention sweep deleted=%s", deleted)
    return deleted


# --- Supervised loop ---
async def run_retention_worker(
    pool: asyncpg.Pool,
    stop_event: asyncio.Event,
    *,
    interval_seconds: float | None = None,
    health: WorkerHealthRegistry | None = None,
) -> None:
    interval = interval_seconds or settings.RETENTION_SWEEP_INTERVAL_SECONDS
    logger.info(
        "retention worker started interval=%ss telemetry_days=%s results_days=%s",
        interval,
        settings.RETENTION_TELEMETRY_DAYS,
        settings.RETENTION_RESULTS_DAYS,
    )
    while not stop_event.is_set():
        try:
            await tick_retention(pool)
            if health is not None:
                health.succeeded(WORKER_NAME)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - supervised retry loop
            logger.exception("retention sweep failed")
            if health is not None:
                health.failed(WORKER_NAME, exc)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
