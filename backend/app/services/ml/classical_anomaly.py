"""Classical unsupervised anomaly detectors — Isolation Forest + One-Class SVM."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.services.ml import common as mlc

FAMILY = "classical_anomaly"


def _paths(tenant_id: str | None) -> dict[str, Path]:
    root = mlc.model_dir(FAMILY, tenant_id=tenant_id)
    return {
        "isolation_forest": root / "isolation_forest.joblib",
        "one_class_svm": root / "one_class_svm.joblib",
    }


def fit(
    *,
    features: list[list[float]] | None = None,
    tenant_id: str | None = None,
    contamination: float = 0.1,
) -> dict[str, Any]:
    """Fit Isolation Forest + One-Class SVM on tabular features (or synthetic)."""
    mlc.require_sklearn()
    from sklearn.ensemble import IsolationForest
    from sklearn.svm import OneClassSVM

    if features:
        x = np.asarray(features, dtype=np.float32)
        if x.ndim != 2 or x.shape[0] < 8:
            raise ValueError("features must be a 2-d matrix with >= 8 rows")
    else:
        x, _ = mlc.synthetic_feature_matrix()

    if_model = IsolationForest(
        n_estimators=100,
        contamination=contamination,
        random_state=42,
    )
    if_model.fit(x)

    # OCSVM expects mostly-normal data; train on inliers from IF.
    labels = if_model.predict(x)
    normals = x[labels == 1]
    if normals.shape[0] < 4:
        normals = x
    oc_model = OneClassSVM(kernel="rbf", gamma="scale", nu=min(0.2, contamination + 0.05))
    oc_model.fit(normals)

    paths = _paths(tenant_id)
    mlc.save_joblib(
        if_model,
        paths["isolation_forest"],
        meta={"n_samples": int(x.shape[0]), "n_features": int(x.shape[1])},
    )
    mlc.save_joblib(
        oc_model,
        paths["one_class_svm"],
        meta={"n_samples": int(normals.shape[0]), "n_features": int(x.shape[1])},
    )
    return {
        "ok": True,
        "family": FAMILY,
        "models": ["isolation_forest", "one_class_svm"],
        "n_samples": int(x.shape[0]),
        "n_features": int(x.shape[1]),
        "paths": {k: str(v) for k, v in paths.items()},
    }


def score(
    *,
    features: list[list[float]],
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Score rows with both detectors. anomaly: True when either flags outlier."""
    mlc.require_sklearn()
    x = np.asarray(features, dtype=np.float32)
    if x.ndim == 1:
        x = x.reshape(1, -1)
    paths = _paths(tenant_id)
    if not paths["isolation_forest"].exists() or not paths["one_class_svm"].exists():
        raise RuntimeError("classical anomaly models not fitted; POST .../fit first")

    if_model, _ = mlc.load_joblib(paths["isolation_forest"])
    oc_model, _ = mlc.load_joblib(paths["one_class_svm"])

    if_pred = if_model.predict(x)  # -1 anomaly
    if_score = -if_model.score_samples(x)  # higher = more anomalous
    oc_pred = oc_model.predict(x)
    oc_score = -oc_model.decision_function(x)

    rows: list[dict[str, Any]] = []
    for i in range(x.shape[0]):
        if_anom = bool(if_pred[i] == -1)
        oc_anom = bool(oc_pred[i] == -1)
        rows.append(
            {
                "isolation_forest": {
                    "is_anomaly": if_anom,
                    "score": float(if_score[i]),
                },
                "one_class_svm": {
                    "is_anomaly": oc_anom,
                    "score": float(oc_score[i]),
                },
                "is_anomaly": if_anom or oc_anom,
                "score": float(max(if_score[i], oc_score[i])),
            }
        )
    return {"ok": True, "family": FAMILY, "count": len(rows), "results": rows}
