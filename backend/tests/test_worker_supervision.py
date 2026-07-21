"""Application lifespan worker supervision regression tests."""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app import main
from app.core.worker_health import WorkerHealthRegistry
from app.services import (
    analytics_worker,
    exports,
    ingest_processing,
    playbooks,
    retention,
    siem,
    training_worker,
)


class TestWorkerSupervision(unittest.IsolatedAsyncioTestCase):
    async def test_readiness_verifies_each_durable_worker_contract(self) -> None:
        pool = object()
        app = SimpleNamespace(
            state=SimpleNamespace(
                worker_lock=asyncio.Lock(),
                verified_worker_contract_pools={},
            )
        )
        ingest_check = AsyncMock()
        siem_check = AsyncMock()
        soar_check = AsyncMock()
        export_check = AsyncMock()

        with (
            patch.object(ingest_processing, "ensure_ingest_processing_schema", ingest_check),
            patch.object(siem, "ensure_siem_schema", siem_check),
            patch.object(playbooks, "ensure_playbook_schema", soar_check),
            patch.object(exports, "ensure_export_schema", export_check),
        ):
            await main._verify_worker_contracts(app, pool)
            await main._verify_worker_contracts(app, pool)

        ingest_check.assert_awaited_once_with(pool)
        siem_check.assert_awaited_once_with(pool)
        soar_check.assert_awaited_once_with(pool)
        export_check.assert_awaited_once_with(pool)
        self.assertIs(app.state.verified_worker_contract_pools[id(pool)], pool)

    async def test_all_durable_workers_are_started_once(self) -> None:
        state = SimpleNamespace(
            worker_stop=asyncio.Event(),
            worker_tasks={},
            worker_health=WorkerHealthRegistry(),
        )
        app = SimpleNamespace(state=state)
        started: list[str] = []

        async def ingest_worker(*_args, **kwargs) -> None:
            started.append("ingest-processing")
            kwargs["health"].succeeded("ingest-processing")
            await state.worker_stop.wait()

        async def soar_worker(*_args, **kwargs) -> None:
            started.append("soar-retries")
            kwargs["health"].succeeded("soar-retries")
            await state.worker_stop.wait()

        async def export_worker(*_args, **kwargs) -> None:
            started.append("exports")
            kwargs["health"].succeeded("exports")
            await state.worker_stop.wait()

        async def rollup_worker(*_args, **kwargs) -> None:
            started.append("analytics-rollup")
            kwargs["health"].succeeded("analytics-rollup")
            await state.worker_stop.wait()

        async def training_task(*_args, **kwargs) -> None:
            started.append("ml-training")
            kwargs["health"].succeeded("ml-training")
            await state.worker_stop.wait()

        async def retention_task(*_args, **kwargs) -> None:
            started.append("retention")
            kwargs["health"].succeeded("retention")
            await state.worker_stop.wait()

        with (
            patch.object(ingest_processing, "run_ingest_processing_worker", ingest_worker),
            patch.object(playbooks, "run_playbook_retry_worker", soar_worker),
            patch.object(exports, "run_export_worker", export_worker),
            patch.object(analytics_worker, "run_analytics_worker", rollup_worker),
            patch.object(training_worker, "run_training_worker", training_task),
            patch.object(retention, "run_retention_worker", retention_task),
            patch.object(main.settings, "PROJECTION_TICK_SECONDS", 0),
        ):
            await main._ensure_background_workers(app, object())
            original = dict(state.worker_tasks)
            await asyncio.sleep(0)
            await main._ensure_background_workers(app, object())

            self.assertEqual(
                set(state.worker_tasks),
                {
                    "ingest-processing",
                    "soar-retries",
                    "exports",
                    "analytics-rollup",
                    "ml-training",
                    "retention",
                },
            )
            self.assertEqual(original, state.worker_tasks)
            self.assertEqual(
                sorted(started),
                [
                    "analytics-rollup",
                    "exports",
                    "ingest-processing",
                    "ml-training",
                    "retention",
                    "soar-retries",
                ],
            )
            self.assertTrue(main._worker_health(app)[0])

        state.worker_stop.set()
        await asyncio.gather(*state.worker_tasks.values())

    async def test_repeated_tick_failures_gate_readiness_while_task_is_alive(self) -> None:
        stop = asyncio.Event()
        registry = WorkerHealthRegistry()
        tasks = {
            name: asyncio.create_task(stop.wait())
            for name in ("ingest-processing", "soar-retries", "exports")
        }
        for name in tasks:
            registry.started(name, stale_after_seconds=60)
            registry.succeeded(name)
        for _ in range(3):
            registry.failed("ingest-processing", RuntimeError("database unavailable"))
        app = SimpleNamespace(state=SimpleNamespace(worker_tasks=tasks, worker_health=registry))

        with (
            patch.object(main.settings, "PROJECTION_TICK_SECONDS", 0),
            patch.object(main.settings, "ANALYTICS_ROLLUP_INTERVAL_SECONDS", 0),
        ):
            healthy, detail = main._worker_health(app)

        self.assertFalse(healthy)
        self.assertEqual(detail["ingest-processing"]["state"], "failed")
        self.assertEqual(detail["ingest-processing"]["consecutive_failures"], 3)
        stop.set()
        await asyncio.gather(*tasks.values())

    def test_successful_but_stale_worker_is_unhealthy(self) -> None:
        registry = WorkerHealthRegistry()
        registry.started("worker", stale_after_seconds=5)
        registry.succeeded("worker")

        healthy, detail = registry.status(
            "worker",
            now=datetime.now(UTC) + timedelta(seconds=10),
        )

        self.assertFalse(healthy)
        self.assertEqual(detail["state"], "stale")


if __name__ == "__main__":
    unittest.main()
