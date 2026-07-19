"""FORJD ML model catalog — fit/score dispatch by family id."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.ml import (
    classical_anomaly,
    embeddings,
    forecasting,
    norse_ssn,
    threat_ensemble,
    transformer_anomaly,
)
from app.services.ml.common import sklearn_available
from app.services.ml.lstm_autoencoder import torch_available

# --- Catalog entry ---
CatalogEntry = dict[str, Any]
FitFn = Callable[..., dict[str, Any]]
ScoreFn = Callable[..., dict[str, Any]]


def _lstm_fit(**kwargs: Any) -> dict[str, Any]:
    """Thin wrapper so LSTM-AE participates in the unified registry."""
    from app.core.config import settings
    from app.services.ml import lstm_autoencoder as lae

    seq_len = int(kwargs.get("seq_len") or settings.ML_SEQ_LEN)
    epochs = int(kwargs.get("epochs") or 8)
    series = kwargs.get("series")
    if series:
        windows = lae.windows_from_series(list(series), seq_len)
    else:
        windows = lae.synthetic_normal_windows(seq_len=seq_len)
    model = lae.build_model(
        hidden_dim=settings.ML_HIDDEN_DIM,
        latent_dim=settings.ML_LATENT_DIM,
    )
    loss = lae.fit_model(model, windows, epochs=epochs)
    path = __import__("pathlib").Path(settings.ML_MODEL_DIR) / f"{settings.ML_MODEL_VERSION}.pt"
    lae.save_checkpoint(
        model,
        path,
        meta={
            "seq_len": seq_len,
            "latent_dim": settings.ML_LATENT_DIM,
            "hidden_dim": settings.ML_HIDDEN_DIM,
        },
    )
    return {
        "ok": True,
        "family": "lstm_autoencoder",
        "final_loss": loss,
        "n_windows": int(windows.shape[0]),
        "path": str(path),
    }


def _lstm_score(**kwargs: Any) -> dict[str, Any]:
    from app.core.config import settings
    from app.services.ml import lstm_autoencoder as lae

    series = kwargs.get("series") or []
    if not series:
        raise ValueError("series required for lstm_autoencoder score")
    path = __import__("pathlib").Path(settings.ML_MODEL_DIR) / f"{settings.ML_MODEL_VERSION}.pt"
    if not path.exists():
        raise RuntimeError("lstm_autoencoder not fitted")
    model, meta = lae.load_checkpoint(
        path,
        hidden_dim=settings.ML_HIDDEN_DIM,
        latent_dim=settings.ML_LATENT_DIM,
    )
    seq_len = int(meta.get("seq_len") or settings.ML_SEQ_LEN)
    window = lae.pad_or_truncate(list(series), seq_len)
    result = lae.score_window(model, window)
    return {
        "ok": True,
        "family": "lstm_autoencoder",
        "reconstruction_error": result.reconstruction_error,
        "embedding": result.embedding,
        "is_anomaly": result.reconstruction_error >= settings.ML_ANOMALY_THRESHOLD,
        "threshold": settings.ML_ANOMALY_THRESHOLD,
    }


# --- Registry ---
CATALOG: dict[str, CatalogEntry] = {
    "lstm_autoencoder": {
        "category": "anomaly",
        "title": "LSTM Autoencoder",
        "description": "Unsupervised time-series reconstruction anomaly (pgvector latents).",
        "requires": ["torch"],
        "fit": _lstm_fit,
        "score": _lstm_score,
    },
    "classical_anomaly": {
        "category": "anomaly",
        "title": "Isolation Forest + One-Class SVM",
        "description": "Classical tabular anomaly detectors (sklearn).",
        "requires": ["sklearn"],
        "fit": classical_anomaly.fit,
        "score": classical_anomaly.score,
    },
    "threat_ensemble": {
        "category": "threat",
        "title": "Random Forest + HistGradientBoosting",
        "description": "Threat scoring ensembles (LightGBM/XGBoost-class via sklearn HGB).",
        "requires": ["sklearn"],
        "fit": threat_ensemble.fit,
        "score": threat_ensemble.score,
    },
    "transformer_anomaly": {
        "category": "threat",
        "title": "Transformer sequence anomaly",
        "description": "TransformerEncoder reconstruction MSE on telemetry windows.",
        "requires": ["torch"],
        "fit": transformer_anomaly.fit,
        "score": transformer_anomaly.score,
    },
    "forecasting": {
        "category": "forecasting",
        "title": "TFT-lite + NeuralSeasonal + GRU/LSTM P99",
        "description": "Multi-horizon forecasting suite (Prophet-class neural seasonal included).",
        "requires": ["torch"],
        "fit": forecasting.fit,
        "score": forecasting.score,
    },
    "embeddings": {
        "category": "embeddings",
        "title": "EventEncoder (+ optional Sentence-Transformers)",
        "description": "Custom event embeddings for similarity; ST via ml-nlp group.",
        "requires": ["torch"],
        "fit": embeddings.fit,
        "score": embeddings.encode,
    },
    "norse_ssn": {
        "category": "forecasting",
        "title": "NorseSSN spiking temporal forecaster",
        "description": "Norse LIF spiking model with GRU/MLP fallback when norse absent.",
        "requires": ["torch"],
        "optional": ["norse"],
        "fit": norse_ssn.fit,
        "score": norse_ssn.score,
    },
}


def list_models() -> list[dict[str, Any]]:
    out = []
    for mid, entry in CATALOG.items():
        reqs = list(entry.get("requires") or [])
        available = True
        if "torch" in reqs and not torch_available():
            available = False
        if "sklearn" in reqs and not sklearn_available():
            available = False
        out.append(
            {
                "id": mid,
                "category": entry["category"],
                "title": entry["title"],
                "description": entry["description"],
                "requires": reqs,
                "optional": list(entry.get("optional") or []),
                "available": available,
                "norse": norse_ssn.norse_available() if mid == "norse_ssn" else None,
                "sentence_transformers": (
                    embeddings.sentence_transformers_available() if mid == "embeddings" else None
                ),
            }
        )
    return out


def fit_model(model_id: str, **kwargs: Any) -> dict[str, Any]:
    entry = CATALOG.get(model_id)
    if entry is None:
        known = ", ".join(sorted(CATALOG))
        raise ValueError(f"unknown model {model_id!r}; known: {known}")
    fn: FitFn = entry["fit"]
    return fn(**kwargs)


def score_model(model_id: str, **kwargs: Any) -> dict[str, Any]:
    entry = CATALOG.get(model_id)
    if entry is None:
        known = ", ".join(sorted(CATALOG))
        raise ValueError(f"unknown model {model_id!r}; known: {known}")
    fn: ScoreFn = entry["score"]
    return fn(**kwargs)


# Re-export for tests / docs
__all__ = ["CATALOG", "fit_model", "list_models", "score_model"]
