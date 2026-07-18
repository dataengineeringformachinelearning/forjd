"""Threat scoring ensembles — Random Forest + HistGradientBoosting (XGBoost-class).

Uses scikit-learn only (no xgboost/lightgbm binary deps) so the ``ml`` group stays lean.
HistGradientBoosting is the sklearn stand-in for LightGBM-style GBDT.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.services.ml import common as mlc

FAMILY = "threat_ensemble"


def _paths(tenant_id: str | None) -> dict[str, Path]:
    root = mlc.model_dir(FAMILY, tenant_id=tenant_id)
    return {
        "random_forest": root / "random_forest.joblib",
        "hist_gradient_boosting": root / "hist_gradient_boosting.joblib",
    }


def fit(
    *,
    features: list[list[float]] | None = None,
    labels: list[int] | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    mlc.require_sklearn()
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier

    if features is not None and labels is not None:
        x = np.asarray(features, dtype=np.float32)
        y = np.asarray(labels, dtype=np.int32)
        if x.shape[0] != y.shape[0] or x.shape[0] < 8:
            raise ValueError("need matching features/labels with >= 8 rows")
    else:
        x, y = mlc.synthetic_feature_matrix()

    rf = RandomForestClassifier(
        n_estimators=64,
        max_depth=8,
        random_state=42,
        n_jobs=1,
        class_weight="balanced",
    )
    rf.fit(x, y)

    hgb = HistGradientBoostingClassifier(
        max_depth=6,
        learning_rate=0.08,
        max_iter=80,
        random_state=42,
    )
    hgb.fit(x, y)

    paths = _paths(tenant_id)
    meta = {
        "n_samples": int(x.shape[0]),
        "n_features": int(x.shape[1]),
        "positive_rate": float(y.mean()),
    }
    mlc.save_joblib(rf, paths["random_forest"], meta=meta)
    mlc.save_joblib(hgb, paths["hist_gradient_boosting"], meta=meta)
    return {
        "ok": True,
        "family": FAMILY,
        "models": ["random_forest", "hist_gradient_boosting"],
        "n_samples": meta["n_samples"],
        "n_features": meta["n_features"],
        "paths": {k: str(v) for k, v in paths.items()},
        "note": "hist_gradient_boosting is the LightGBM/XGBoost-class GBDT in sklearn",
    }


def score(
    *,
    features: list[list[float]],
    tenant_id: str | None = None,
) -> dict[str, Any]:
    mlc.require_sklearn()
    x = np.asarray(features, dtype=np.float32)
    if x.ndim == 1:
        x = x.reshape(1, -1)
    paths = _paths(tenant_id)
    for key, path in paths.items():
        if not path.exists():
            raise RuntimeError(f"{key} not fitted; POST .../fit first")

    rf, _ = mlc.load_joblib(paths["random_forest"])
    hgb, _ = mlc.load_joblib(paths["hist_gradient_boosting"])

    rf_proba = rf.predict_proba(x)[:, 1]
    hgb_proba = hgb.predict_proba(x)[:, 1]
    rows = []
    for i in range(x.shape[0]):
        ensemble = float(0.5 * (rf_proba[i] + hgb_proba[i]))
        rows.append(
            {
                "random_forest": float(rf_proba[i]),
                "hist_gradient_boosting": float(hgb_proba[i]),
                "score": ensemble,
                "is_threat": ensemble >= 0.5,
            }
        )
    return {"ok": True, "family": FAMILY, "count": len(rows), "results": rows}
