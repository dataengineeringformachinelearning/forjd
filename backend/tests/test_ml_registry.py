"""Unit tests for the unified ML model catalog."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.ml import common as mlc
from app.services.ml import lstm_autoencoder as lae
from app.services.ml.lstm_autoencoder import torch_available
from app.services.ml.registry import fit_model, list_models, score_model


class TestArtifactPathIsolation(unittest.TestCase):
    def test_rejects_path_components_and_non_uuid_tenants(self) -> None:
        with self.assertRaisesRegex(ValueError, "family"):
            mlc.model_dir("../forecasting")
        with self.assertRaisesRegex(ValueError, "UUID"):
            mlc.model_dir("forecasting", tenant_id="../../other-tenant")


@unittest.skipUnless(mlc.sklearn_available(), "sklearn ml group not installed")
class TestClassicalAndEnsemble(unittest.TestCase):
    def test_classical_anomaly_roundtrip(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(mlc, "ml_root", return_value=Path(tmp)),
        ):
            fit = fit_model("classical_anomaly")
            self.assertTrue(fit["ok"])
            score = score_model(
                "classical_anomaly",
                features=[[0.0] * 6, [4.0] * 6],
            )
            self.assertEqual(score["count"], 2)
            self.assertIn("is_anomaly", score["results"][0])

    def test_threat_ensemble_roundtrip(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(mlc, "ml_root", return_value=Path(tmp)),
        ):
            fit = fit_model("threat_ensemble")
            self.assertTrue(fit["ok"])
            score = score_model("threat_ensemble", features=[[0.1] * 6])
            self.assertIn("score", score["results"][0])


@unittest.skipUnless(torch_available(), "torch ml group not installed")
class TestTorchFamilies(unittest.TestCase):
    def test_catalog_lists_all(self) -> None:
        ids = {m["id"] for m in list_models()}
        self.assertTrue(
            {
                "lstm_autoencoder",
                "classical_anomaly",
                "threat_ensemble",
                "transformer_anomaly",
                "forecasting",
                "embeddings",
                "norse_ssn",
            }.issubset(ids)
        )

    def test_transformer_and_norse(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch("app.core.config.settings.ML_MODEL_DIR", tmp),
            patch.object(mlc, "ml_root", return_value=Path(tmp)),
        ):
            tfit = fit_model("transformer_anomaly", epochs=2, seq_len=8)
            self.assertTrue(tfit["ok"])
            tscore = score_model(
                "transformer_anomaly",
                series=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            )
            self.assertIn("reconstruction_error", tscore)

            tenant_id = "11111111-1111-1111-1111-111111111111"
            series = [1.0, 1.1, 1.2, 1.0, 1.1, 1.2, 1.0, 1.1, 8.0, 1.0, 1.1, 1.2]
            nfit = fit_model(
                "norse_ssn",
                epochs=2,
                seq_len=8,
                series=series,
                tenant_id=tenant_id,
            )
            self.assertTrue(nfit["ok"])
            self.assertIn("uses_norse", nfit)
            self.assertEqual(nfit["sample_count"], len(series))
            self.assertIn(tenant_id, nfit["path"])
            nscore = score_model(
                "norse_ssn",
                series=series,
                tenant_id=tenant_id,
            )
            self.assertIn("score", nscore)
            self.assertEqual(nscore["sample_count"], len(series))
            with self.assertRaisesRegex(ValueError, "threshold"):
                score_model(
                    "norse_ssn",
                    series=series,
                    tenant_id=tenant_id,
                    threshold=2.0,
                )
            with self.assertRaisesRegex(ValueError, "at least 8"):
                fit_model(
                    "transformer_anomaly",
                    series=[1.0, 2.0],
                    seq_len=8,
                    epochs=1,
                    tenant_id=tenant_id,
                )

    def test_lstm_artifacts_are_tenant_scoped_and_require_real_series(self) -> None:
        tenant_a = "11111111-1111-1111-1111-111111111111"
        tenant_b = "22222222-2222-2222-2222-222222222222"
        series = [float(i) for i in range(8)]
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(mlc, "ml_root", return_value=Path(tmp)),
        ):
            with self.assertRaisesRegex(ValueError, "tenant_id"):
                fit_model(
                    "lstm_autoencoder",
                    series=series,
                    seq_len=4,
                    epochs=1,
                )
            with self.assertRaisesRegex(ValueError, "real series"):
                fit_model(
                    "lstm_autoencoder",
                    tenant_id=tenant_a,
                    seq_len=4,
                    epochs=1,
                )
            with self.assertRaisesRegex(ValueError, "at least 4"):
                fit_model(
                    "lstm_autoencoder",
                    tenant_id=tenant_a,
                    series=[1.0, 2.0, 3.0],
                    seq_len=4,
                    epochs=1,
                )

            fitted = fit_model(
                "lstm_autoencoder",
                tenant_id=tenant_a,
                series=series,
                seq_len=4,
                epochs=1,
            )
            self.assertIn(f"lstm_autoencoder/{tenant_a}", fitted["path"])
            self.assertTrue(Path(fitted["path"]).is_file())
            self.assertTrue(
                score_model(
                    "lstm_autoencoder",
                    tenant_id=tenant_a,
                    series=series,
                )["ok"]
            )
            with patch(
                "app.services.ml.lstm_autoencoder.score_window",
                wraps=lae.score_window,
            ) as score_window:
                score_model(
                    "lstm_autoencoder",
                    tenant_id=tenant_a,
                    series=series,
                )
            self.assertEqual(score_window.call_args.args[1].tolist(), series[-4:])
            with self.assertRaisesRegex(RuntimeError, "not fitted"):
                score_model(
                    "lstm_autoencoder",
                    tenant_id=tenant_b,
                    series=series,
                )
            with self.assertRaisesRegex(ValueError, "at least 4"):
                score_model(
                    "lstm_autoencoder",
                    tenant_id=tenant_a,
                    series=[1.0, 2.0, 3.0],
                )

    def test_tenant_norse_fit_rejects_synthetic_fallback(self) -> None:
        with self.assertRaisesRegex(ValueError, "real series"):
            fit_model(
                "norse_ssn",
                tenant_id="11111111-1111-1111-1111-111111111111",
            )

    def test_forecasting_and_embeddings(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(mlc, "ml_root", return_value=Path(tmp)),
        ):
            ffit = fit_model("forecasting", epochs=2, seq_len=8, horizon=2)
            self.assertTrue(ffit["ok"])
            series = list(range(24))
            for model in ("tft_lite", "neural_seasonal", "p99_gru", "p99_lstm"):
                out = score_model("forecasting", series=series, model=model)
                self.assertTrue(out["ok"], model)
                self.assertIn("forecast", out)

            efit = fit_model("embeddings", epochs=2)
            self.assertTrue(efit["ok"])
            enc = score_model("embeddings", texts=["sealed event ingest"])
            self.assertEqual(len(enc["embeddings"][0]), 32)


if __name__ == "__main__":
    unittest.main()
