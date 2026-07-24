"""Unit tests for ML Supabase bridge helpers (no live DB required)."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import ml as ml_api
from app.api.v1.ml import _require_tenant_inputs
from app.models.ml import MlFitRequest, MlScoreRequest
from app.services.ml import store as ml_store
from app.services.ml import supabase_bridge as bridge


class TestSupabaseBridge(unittest.IsolatedAsyncioTestCase):
    async def test_hydrate_noop_without_pool(self) -> None:
        kwargs = {"tenant_id": "t1"}
        out = await bridge.hydrate_fit_kwargs(None, "classical_anomaly", kwargs)
        self.assertEqual(out, kwargs)

    async def test_persist_fit_skips_without_tenant(self) -> None:
        result = {"ok": True, "family": "classical_anomaly"}
        out = await bridge.persist_fit(
            MagicMock(), model_id="classical_anomaly", tenant_id=None, result=result
        )
        self.assertFalse(out["supabase"]["persisted"])

    async def test_persist_score_writes_rows(self) -> None:
        pool = AsyncMock()
        with (
            mock.patch(
                "app.services.ml.supabase_bridge.ml_store.ensure_ml_store_schema",
                new_callable=AsyncMock,
            ),
            mock.patch(
                "app.services.ml.supabase_bridge.ml_store.persist_scores",
                new_callable=AsyncMock,
                return_value=2,
            ) as persist,
        ):
            out = await bridge.persist_score(
                pool,
                model_id="threat_ensemble",
                tenant_id="11111111-1111-1111-1111-111111111111",
                result={
                    "ok": True,
                    "results": [
                        {"score": 0.9, "is_threat": True},
                        {"score": 0.1, "is_threat": False},
                    ],
                },
            )
        self.assertTrue(out["supabase"]["persisted"])
        self.assertEqual(out["supabase"]["ml_scores_written"], 2)
        persist.assert_awaited_once()

    async def test_persist_temporal_score_keeps_runtime_metadata(self) -> None:
        pool = AsyncMock()
        with (
            mock.patch.object(
                ml_store,
                "ensure_ml_store_schema",
                new_callable=AsyncMock,
            ),
            mock.patch.object(
                ml_store,
                "persist_scores",
                new_callable=AsyncMock,
                return_value=1,
            ) as persist,
        ):
            await bridge.persist_score(
                pool,
                model_id="norse_ssn",
                tenant_id="11111111-1111-1111-1111-111111111111",
                result={
                    "ok": True,
                    "score": 0.42,
                    "uses_norse": True,
                    "backend": "norse_lif",
                    "sample_count": 64,
                    "seq_len": 16,
                },
            )
        features = persist.await_args.kwargs["rows"][0]["features"]
        self.assertEqual(features["backend"], "norse_lif")
        self.assertEqual(features["sample_count"], 64)
        self.assertTrue(features["uses_norse"])


class TestTenantInputContract(unittest.TestCase):
    def test_tenant_fit_requires_real_series(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _require_tenant_inputs(
                "norse_ssn",
                {"tenant_id": "tenant-a"},
                fit=True,
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("series", raised.exception.detail)

    def test_unscoped_local_fit_may_use_fixture_data(self) -> None:
        _require_tenant_inputs("norse_ssn", {"tenant_id": None}, fit=True)

    def test_tenant_threat_fit_requires_features_and_labels(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            _require_tenant_inputs(
                "threat_ensemble",
                {"tenant_id": "tenant-a", "features": [[0.1] * 6]},
                fit=True,
            )
        self.assertIn("labels", raised.exception.detail)


class TestTenantGate(unittest.IsolatedAsyncioTestCase):
    async def test_human_fit_cannot_create_global_artifact(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await ml_api._require_tenant(
                MagicMock(),
                MagicMock(is_service=False),
                None,
                write=True,
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("tenant_id", raised.exception.detail)


class TestMlRequestBounds(unittest.TestCase):
    def test_rejects_nonfinite_oversized_and_unknown_inputs(self) -> None:
        tenant_id = uuid4()
        invalid = (
            {"tenant_id": tenant_id, "series": [float("nan")]},
            {"tenant_id": tenant_id, "series": [0.0] * 4097},
            {"tenant_id": tenant_id, "features": [[0.0] * 65]},
            {"tenant_id": tenant_id, "texts": ["x"] * 129},
            {"tenant_id": tenant_id, "unknown": True},
        )
        for payload in invalid:
            with self.subTest(payload=payload.keys()), self.assertRaises(ValidationError):
                MlFitRequest.model_validate(payload)

    def test_tenant_id_is_required_by_the_request_schema(self) -> None:
        with self.assertRaises(ValidationError):
            MlFitRequest.model_validate({"series": [0.0] * 8})
        with self.assertRaises(ValidationError):
            MlScoreRequest.model_validate({"series": [0.0] * 8})

    def test_score_threshold_must_be_nonnegative_and_finite(self) -> None:
        tenant_id = uuid4()
        for threshold in (-0.1, float("inf")):
            with self.subTest(threshold=threshold), self.assertRaises(ValidationError):
                MlScoreRequest(tenant_id=tenant_id, threshold=threshold)


class TestScoreHydration(unittest.IsolatedAsyncioTestCase):
    async def test_classical_score_uses_newest_feature_row(self) -> None:
        tenant_id = uuid4()
        newest = [0.9] * 6
        older = [0.1] * 6
        result = {"ok": True, "results": [{"score": 0.5, "is_anomaly": False}]}
        with (
            mock.patch.object(ml_api, "_require_tenant", new=AsyncMock()),
            mock.patch.object(ml_api, "pool_from_request", return_value=MagicMock()),
            mock.patch.object(
                ml_api.ml_store,
                "features_from_stream_results",
                new=AsyncMock(return_value=[newest, older]),
            ),
            mock.patch.object(ml_api.ml_registry, "score_model", return_value=result) as score,
            mock.patch.object(
                ml_api.ml_sb,
                "persist_score",
                new=AsyncMock(return_value=result),
            ),
        ):
            await ml_api.score_ml_model(
                "classical_anomaly",
                MagicMock(),
                MlScoreRequest(tenant_id=tenant_id),
                MagicMock(),
            )

        self.assertEqual(score.call_args.kwargs["features"], [newest])


class TestTemporalSignal(unittest.TestCase):
    def test_missing_score_is_explicitly_insufficient(self) -> None:
        signal = ml_store.temporal_signal_from_score(None)
        self.assertIsNone(signal["spiking_temporal_forecast"])
        self.assertEqual(signal["temporal_status"], "insufficient_data")
        self.assertFalse(signal["uses_norse"])

    def test_persisted_norse_score_drives_public_signal(self) -> None:
        now = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
        signal = ml_store.temporal_signal_from_score(
            {
                "score": 0.4234,
                "features": {
                    "uses_norse": True,
                    "backend": "norse_lif",
                    "sample_count": 64,
                },
                "metadata": {},
                "created_at": now.isoformat(),
            },
            now=now,
        )
        self.assertEqual(signal["spiking_temporal_forecast"], 42.34)
        self.assertEqual(signal["temporal_status"], "ready")
        self.assertEqual(signal["temporal_backend"], "norse_lif")
        self.assertEqual(signal["temporal_sample_count"], 64)
        self.assertTrue(signal["uses_norse"])

    def test_old_score_is_stale(self) -> None:
        now = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
        signal = ml_store.temporal_signal_from_score(
            {
                "score": 0.1,
                "features": {"backend": "gru_mlp_fallback", "sample_count": 24},
                "metadata": {},
                "created_at": (now - timedelta(days=3)).isoformat(),
            },
            now=now,
        )
        self.assertEqual(signal["temporal_status"], "stale")
        self.assertFalse(signal["uses_norse"])

    def test_invalid_or_unproven_score_is_not_published(self) -> None:
        now = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)
        invalid_rows = (
            {
                "score": float("nan"),
                "features": {
                    "backend": "norse_lif",
                    "sample_count": 24,
                },
                "created_at": now.isoformat(),
            },
            {
                "score": 0.4,
                "features": {"sample_count": 24},
                "created_at": now.isoformat(),
            },
            {
                "score": 0.4,
                "features": {"backend": "norse_lif"},
                "created_at": now.isoformat(),
            },
        )
        for row in invalid_rows:
            with self.subTest(row=row):
                signal = ml_store.temporal_signal_from_score(row, now=now)
                self.assertEqual(signal["temporal_status"], "error")
                self.assertIsNone(signal["spiking_temporal_forecast"])


class TestFeatureExtraction(unittest.IsolatedAsyncioTestCase):
    async def test_kind_feature_uses_stable_sha256_value(self) -> None:
        pool = MagicMock()
        pool.fetch = AsyncMock(
            return_value=[
                {
                    "score": 0.5,
                    "is_anomaly": False,
                    "features": {},
                    "kind": "sealed.rollup",
                }
            ]
        )
        features = await ml_store.features_from_stream_results(
            pool,
            tenant_id=str(uuid4()),
        )
        import hashlib

        digest = hashlib.sha256(b"sealed.rollup").digest()
        expected = int.from_bytes(digest[:4], "big") / float(2**32)
        self.assertEqual(features[0][-1], expected)

    async def test_public_score_reads_do_not_run_schema_ddl(self) -> None:
        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])
        pool.execute = AsyncMock()
        self.assertEqual(
            await ml_store.list_recent_scores(
                pool,
                tenant_id=uuid4(),
                family="norse_ssn",
                limit=1,
            ),
            [],
        )
        pool.execute.assert_not_awaited()

    async def test_insufficient_temporal_run_exposes_real_sample_count(self) -> None:
        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[])
        pool.fetchrow = AsyncMock(
            return_value={
                "status": "insufficient_data",
                "metrics": {"sample_count": 7, "min_required": 24},
            }
        )

        signal = await ml_store.latest_temporal_signal(pool, tenant_id=uuid4())

        self.assertIsNone(signal["spiking_temporal_forecast"])
        self.assertEqual(signal["temporal_status"], "insufficient_data")
        self.assertEqual(signal["temporal_sample_count"], 7)
        self.assertIn("tenant_id = $1::uuid", pool.fetchrow.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
