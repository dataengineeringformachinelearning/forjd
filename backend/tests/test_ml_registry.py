"""Unit tests for the unified ML model catalog."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.ml import common as mlc
from app.services.ml.lstm_autoencoder import torch_available
from app.services.ml.registry import fit_model, list_models, score_model


@unittest.skipUnless(mlc.sklearn_available(), "sklearn ml group not installed")
class TestClassicalAndEnsemble(unittest.TestCase):
    def test_classical_anomaly_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mlc, "ml_root", return_value=Path(tmp)):
                fit = fit_model("classical_anomaly")
                self.assertTrue(fit["ok"])
                score = score_model(
                    "classical_anomaly",
                    features=[[0.0] * 6, [4.0] * 6],
                )
                self.assertEqual(score["count"], 2)
                self.assertIn("is_anomaly", score["results"][0])

    def test_threat_ensemble_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mlc, "ml_root", return_value=Path(tmp)):
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
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.core.config.settings.ML_MODEL_DIR", tmp):
                with patch.object(mlc, "ml_root", return_value=Path(tmp)):
                    tfit = fit_model("transformer_anomaly", epochs=2, seq_len=8)
                    self.assertTrue(tfit["ok"])
                    tscore = score_model(
                        "transformer_anomaly",
                        series=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
                    )
                    self.assertIn("reconstruction_error", tscore)

                    nfit = fit_model("norse_ssn", epochs=2, seq_len=8)
                    self.assertTrue(nfit["ok"])
                    self.assertIn("uses_norse", nfit)
                    nscore = score_model(
                        "norse_ssn",
                        series=[1.0, 2.0, 1.5, 1.2, 8.0, 1.1, 1.0, 1.0],
                    )
                    self.assertIn("score", nscore)

    def test_forecasting_and_embeddings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(mlc, "ml_root", return_value=Path(tmp)):
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
