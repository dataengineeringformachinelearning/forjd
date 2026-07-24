"""Scheduled ML training + HF publishing worker — unit tests (mocked pool)."""

from __future__ import annotations

import unittest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import training_worker

TENANT_ID = uuid.uuid4()


def _pool(rows: list[dict[str, str]] | None = None) -> MagicMock:
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows or [])
    return pool


class TestTenantsDueTraining(unittest.IsolatedAsyncioTestCase):
    async def test_returns_uuid_list(self) -> None:
        pool = _pool([{"tenant_id": str(TENANT_ID)}])
        due = await training_worker._tenants_due_training(pool)
        self.assertEqual(due, [TENANT_ID])
        query = pool.fetch.await_args.args[0]
        self.assertIn("FROM ml_scores score", query)
        self.assertIn("run.status = 'insufficient_data'", query)

    async def test_empty_when_all_models_fresh(self) -> None:
        pool = _pool([])
        self.assertEqual(await training_worker._tenants_due_training(pool), [])


class TestScoreSeries(unittest.IsolatedAsyncioTestCase):
    async def test_short_series_remains_real_and_is_not_padded(self) -> None:
        pool = _pool([{"score": 0.5}] * 5)
        self.assertEqual(await training_worker._score_series(pool, TENANT_ID), [0.5] * 5)
        self.assertIn("score IS NOT NULL", pool.fetch.await_args.args[0])

    async def test_long_series_reversed_to_ascending(self) -> None:
        rows = [{"score": float(i)} for i in range(training_worker.MIN_SERIES_LEN)]
        pool = _pool(rows)
        series = await training_worker._score_series(pool, TENANT_ID)
        self.assertEqual(series[0], float(training_worker.MIN_SERIES_LEN - 1))
        self.assertEqual(series[-1], 0.0)

    async def test_nonfinite_database_scores_are_excluded(self) -> None:
        pool = _pool([{"score": float("nan")}, {"score": 0.5}])
        self.assertEqual(await training_worker._score_series(pool, TENANT_ID), [0.5])


class TestTrainTenant(unittest.IsolatedAsyncioTestCase):
    async def test_persists_tenant_norse_fit_and_score(self) -> None:
        pool = _pool()
        series = [float(i) / 100.0 for i in range(training_worker.MIN_SERIES_LEN)]
        fit_result = {
            "ok": True,
            "family": "norse_ssn",
            "path": "/models/tenant/spiking_temporal.pt",
            "sample_count": len(series),
            "backend": "norse_lif",
            "uses_norse": True,
        }
        score_result = {
            "ok": True,
            "family": "norse_ssn",
            "score": 0.42,
            "sample_count": len(series),
            "backend": "norse_lif",
            "uses_norse": True,
        }
        with (
            patch(
                "app.services.ml.sla_model.train_tenant_sla",
                new=AsyncMock(return_value={"ok": True}),
            ),
            patch(
                "app.services.ml.threat_model.train_threat_model",
                new=AsyncMock(return_value={"ok": True}),
            ),
            patch.object(
                training_worker,
                "_score_series",
                new=AsyncMock(return_value=series),
            ),
            patch("app.services.ml.norse_ssn.fit", return_value=fit_result) as fit,
            patch("app.services.ml.norse_ssn.score", return_value=score_result) as score,
            patch(
                "app.services.ml.supabase_bridge.persist_fit",
                new=AsyncMock(return_value=fit_result),
            ) as persist_fit,
            patch(
                "app.services.ml.supabase_bridge.persist_score",
                new=AsyncMock(return_value=score_result),
            ) as persist_score,
        ):
            result = await training_worker._train_tenant(pool, TENANT_ID)

        self.assertTrue(result["temporal"])
        self.assertTrue(result["norse_ssn"])
        self.assertEqual(fit.call_args.kwargs["tenant_id"], str(TENANT_ID))
        self.assertEqual(fit.call_args.kwargs["series"], series)
        self.assertEqual(score.call_args.kwargs["tenant_id"], str(TENANT_ID))
        persist_fit.assert_awaited_once()
        persist_score.assert_awaited_once()

    async def test_short_series_records_insufficient_data_without_fitting(self) -> None:
        pool = _pool()
        series = [0.1] * (training_worker.MIN_SERIES_LEN - 1)
        with (
            patch(
                "app.services.ml.sla_model.train_tenant_sla",
                new=AsyncMock(return_value={"ok": True}),
            ),
            patch(
                "app.services.ml.threat_model.train_threat_model",
                new=AsyncMock(return_value={"ok": True}),
            ),
            patch.object(
                training_worker,
                "_score_series",
                new=AsyncMock(return_value=series),
            ),
            patch("app.services.ml.norse_ssn.fit") as fit,
            patch(
                "app.services.ml.store.record_training_run",
                new=AsyncMock(return_value="run-id"),
            ) as record,
        ):
            result = await training_worker._train_tenant(pool, TENANT_ID)

        self.assertFalse(result["temporal"])
        self.assertFalse(result["norse_ssn"])
        fit.assert_not_called()
        self.assertEqual(record.await_args.kwargs["status"], "insufficient_data")
        self.assertEqual(
            record.await_args.kwargs["metrics"],
            {
                "sample_count": len(series),
                "min_required": training_worker.MIN_SERIES_LEN,
            },
        )

    async def test_auxiliary_model_failures_do_not_block_temporal_score(self) -> None:
        pool = _pool()
        series = [float(i) / 100.0 for i in range(training_worker.MIN_SERIES_LEN)]
        fit_result = {"ok": True, "family": "norse_ssn"}
        score_result = {
            "ok": True,
            "family": "norse_ssn",
            "score": 0.2,
            "backend": "norse_lif",
            "uses_norse": True,
            "sample_count": len(series),
        }
        with (
            patch(
                "app.services.ml.sla_model.train_tenant_sla",
                new=AsyncMock(side_effect=RuntimeError("sla unavailable")),
            ),
            patch(
                "app.services.ml.threat_model.train_threat_model",
                new=AsyncMock(side_effect=RuntimeError("threat unavailable")),
            ),
            patch.object(
                training_worker,
                "_score_series",
                new=AsyncMock(return_value=series),
            ),
            patch("app.services.ml.norse_ssn.fit", return_value=fit_result),
            patch("app.services.ml.norse_ssn.score", return_value=score_result),
            patch(
                "app.services.ml.supabase_bridge.persist_fit",
                new=AsyncMock(return_value=fit_result),
            ),
            patch(
                "app.services.ml.supabase_bridge.persist_score",
                new=AsyncMock(return_value=score_result),
            ) as persist_score,
        ):
            result = await training_worker._train_tenant(pool, TENANT_ID)

        self.assertFalse(result["sla"])
        self.assertFalse(result["threat"])
        self.assertTrue(result["temporal"])
        persist_score.assert_awaited_once()


class TestTick(unittest.IsolatedAsyncioTestCase):
    async def test_skips_when_torch_unavailable(self) -> None:
        pool = _pool()
        with patch.object(training_worker, "torch_available", return_value=False):
            self.assertEqual(await training_worker.tick_training(pool), 0)
        pool.fetch.assert_not_awaited()

    async def test_one_tenant_failure_does_not_block_others(self) -> None:
        other = uuid.uuid4()
        pool = _pool()
        with (
            patch.object(training_worker, "torch_available", return_value=True),
            patch.object(
                training_worker,
                "_tenants_due_training",
                new=AsyncMock(return_value=[TENANT_ID, other]),
            ),
            patch.object(
                training_worker,
                "_train_tenant",
                new=AsyncMock(side_effect=[RuntimeError("boom"), {"sla": True}]),
            ) as train,
            patch.object(training_worker, "_hf_configured", return_value=False),
        ):
            count = await training_worker.tick_training(pool)
        self.assertEqual(count, 2)
        self.assertEqual(train.await_count, 2)

    async def test_hf_publish_called_only_when_configured(self) -> None:
        pool = _pool()
        with (
            patch.object(training_worker, "torch_available", return_value=True),
            patch.object(
                training_worker,
                "_tenants_due_training",
                new=AsyncMock(return_value=[TENANT_ID]),
            ),
            patch.object(training_worker, "_train_tenant", new=AsyncMock(return_value={})),
            patch.object(training_worker, "_hf_configured", return_value=True),
            patch.object(training_worker, "_publish_tenant_artifacts", return_value=3) as pub,
        ):
            await training_worker.tick_training(pool)
        pub.assert_called_once_with(TENANT_ID)

    async def test_hf_publish_failure_does_not_fail_tick(self) -> None:
        pool = _pool()
        with (
            patch.object(training_worker, "torch_available", return_value=True),
            patch.object(
                training_worker,
                "_tenants_due_training",
                new=AsyncMock(return_value=[TENANT_ID]),
            ),
            patch.object(training_worker, "_train_tenant", new=AsyncMock(return_value={})),
            patch.object(training_worker, "_hf_configured", return_value=True),
            patch.object(
                training_worker,
                "_publish_tenant_artifacts",
                side_effect=RuntimeError("hub down"),
            ),
        ):
            self.assertEqual(await training_worker.tick_training(pool), 1)


class TestTenantHash(unittest.TestCase):
    def test_hash_is_stable_and_opaque(self) -> None:
        hashed = training_worker._tenant_hash(TENANT_ID)
        self.assertEqual(len(hashed), 16)
        self.assertNotIn(str(TENANT_ID)[:8], hashed)
        self.assertEqual(hashed, training_worker._tenant_hash(TENANT_ID))


if __name__ == "__main__":
    unittest.main()
