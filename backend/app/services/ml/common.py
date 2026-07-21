"""Shared ML helpers — availability guards, synthetic series, checkpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
from app.services.ml.lstm_autoencoder import torch_available

try:
    import joblib

    _JOBLIB_OK = True
except ImportError:  # pragma: no cover
    joblib = None  # type: ignore[assignment]
    _JOBLIB_OK = False

try:
    from sklearn.ensemble import (  # noqa: F401
        HistGradientBoostingClassifier,
        IsolationForest,
        RandomForestClassifier,
    )
    from sklearn.svm import OneClassSVM  # noqa: F401

    _SKLEARN_OK = True
except ImportError:  # pragma: no cover
    _SKLEARN_OK = False


def sklearn_available() -> bool:
    return _SKLEARN_OK and _JOBLIB_OK


def require_sklearn() -> None:
    if not sklearn_available():
        raise RuntimeError("scikit-learn is not installed. From backend/: uv sync --group ml")


def require_torch() -> None:
    if not torch_available():
        raise RuntimeError("PyTorch is not installed. From backend/: uv sync --group ml")


def ml_root() -> Path:
    root = Path(settings.ML_MODEL_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def model_dir(family: str, *, tenant_id: str | None = None) -> Path:
    base = ml_root() / family
    if tenant_id:
        base = base / tenant_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def synthetic_feature_matrix(
    *,
    n: int = 128,
    n_features: int = 6,
    seed: int = 7,
    anomaly_frac: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    """Labeled tabular features for classical / ensemble model training."""
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 1.0, size=(n, n_features)).astype(np.float32)
    n_anom = max(1, int(n * anomaly_frac))
    x[-n_anom:] += rng.normal(3.0, 0.5, size=(n_anom, n_features)).astype(np.float32)
    y = np.zeros(n, dtype=np.int32)
    y[-n_anom:] = 1
    return x, y


def synthetic_series(
    *,
    length: int = 64,
    seed: int = 11,
) -> np.ndarray:
    """Latency-like series with mild seasonality for forecasting model training."""
    rng = np.random.default_rng(seed)
    t = np.arange(length, dtype=np.float32)
    base = 40.0 + 8.0 * np.sin(t / 6.0) + 3.0 * np.cos(t / 13.0)
    noise = rng.normal(0.0, 1.5, size=length).astype(np.float32)
    spikes = np.zeros(length, dtype=np.float32)
    for i in rng.choice(length, size=max(1, length // 16), replace=False):
        spikes[i] = float(rng.uniform(15.0, 40.0))
    return (base + noise + spikes).astype(np.float32)


def save_joblib(obj: Any, path: Path, *, meta: dict[str, Any] | None = None) -> None:
    require_sklearn()
    assert joblib is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": obj, "meta": meta or {}}, path)


def load_joblib(path: Path) -> tuple[Any, dict[str, Any]]:
    require_sklearn()
    assert joblib is not None
    blob = joblib.load(path)
    if isinstance(blob, dict) and "model" in blob:
        return blob["model"], dict(blob.get("meta") or {})
    return blob, {}


def dump_meta(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
