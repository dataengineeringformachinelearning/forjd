"""Unit tests for ML Supabase bridge helpers (no live DB required)."""

from __future__ import annotations

import unittest
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

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


if __name__ == "__main__":
    unittest.main()
