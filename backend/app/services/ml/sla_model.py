"""Tenant SLA regressor (tenant_id I/O).

Optional deps: torch (ml group). GridSearchCV needs scikit-learn when available;
falls back to a single estimator fit without sklearn.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.services.ml.lstm_autoencoder import torch_available
from app.services.ml.threat_model import ensure_ml_domain_schema

logger = logging.getLogger("forjd.ml.sla")

try:
    import numpy as np
    import torch
    from torch import nn

    _TORCH_OK = True
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_OK = False


def _require_torch() -> None:
    if not _TORCH_OK or not torch_available():
        raise RuntimeError("PyTorch is not installed. From backend/: uv sync --group ml")


def _heuristic_sla(status_code: float, response_time_s: float, active: float) -> float:
    if active < 0.5 or status_code >= 5.0:
        return 0.0
    # Mild latency penalty
    return max(0.0, min(1.0, 1.0 - min(response_time_s, 5.0) / 10.0))


async def train_tenant_sla(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
) -> dict[str, Any]:
    """Train SLA model from discovered_endpoints + stream health signals."""
    _require_torch()
    await ensure_ml_domain_schema(pool)

    # Prefer discovered endpoints; synthesize minimal features from stream_results if empty.
    endpoints = await pool.fetch(
        """
        SELECT url, is_active FROM discovered_endpoints
        WHERE tenant_id = $1::uuid
        LIMIT 500
        """,
        str(tenant_id),
    )
    x_data: list[list[float]] = []
    y_data: list[list[float]] = []
    if endpoints:
        for ep in endpoints:
            status = 2.0  # unknown → treat as 200-ish
            resp = 0.2
            active = 1.0 if ep["is_active"] else 0.0
            x_data.append([status, resp, active])
            y_data.append([_heuristic_sla(status, resp, active)])
    else:
        rows = await pool.fetch(
            """
            SELECT COALESCE(score, 0)::float AS score, is_anomaly
            FROM stream_results
            WHERE tenant_id = $1::uuid
            ORDER BY created_at DESC
            LIMIT 100
            """,
            str(tenant_id),
        )
        for r in rows:
            score = float(r["score"] or 0)
            active = 0.0 if r["is_anomaly"] else 1.0
            status = 5.0 if r["is_anomaly"] else 2.0
            resp = max(0.05, score)
            x_data.append([status, resp, active])
            y_data.append([_heuristic_sla(status, resp, active)])

    if len(x_data) < 1:
        return {"ok": False, "error": "insufficient_samples"}

    X_np = np.array(x_data, dtype=np.float32)
    Y_np = np.array(y_data, dtype=np.float32)

    class SLAModel(nn.Module):
        def __init__(self, hidden_size: int = 16) -> None:
            super().__init__()
            self.fc1 = nn.Linear(3, hidden_size)
            self.fc2 = nn.Linear(hidden_size, 1)
            self.relu = nn.ReLU()

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.fc2(self.relu(self.fc1(x)))

    best_lr = 0.01
    best_hidden = 16
    final_loss = 0.0
    try:
        from sklearn.base import BaseEstimator, RegressorMixin
        from sklearn.model_selection import GridSearchCV

        class PyTorchSLAEstimator(BaseEstimator, RegressorMixin):
            def __init__(self, lr: float = 0.01, hidden_size: int = 16) -> None:
                self.lr = lr
                self.hidden_size = hidden_size
                self.model = None

            def fit(self, X: Any, y: Any) -> Any:
                self.model = SLAModel(self.hidden_size)
                criterion = nn.MSELoss()
                optimizer = torch.optim.Adam(self.model.parameters(), lr=self.lr)
                xt = torch.tensor(X, dtype=torch.float32)
                yt = torch.tensor(y, dtype=torch.float32)
                for _ in range(50):
                    optimizer.zero_grad()
                    loss = criterion(self.model(xt), yt)
                    loss.backward()
                    optimizer.step()
                return self

            def predict(self, X: Any) -> Any:
                assert self.model is not None
                self.model.eval()
                with torch.no_grad():
                    return self.model(torch.tensor(X, dtype=torch.float32)).numpy()

            def score(self, X: Any, y: Any) -> float:
                preds = self.predict(X)
                return float(-np.mean((preds - y) ** 2))

        if len(x_data) >= 2:
            grid = GridSearchCV(
                PyTorchSLAEstimator(),
                {"lr": [0.01, 0.001], "hidden_size": [8, 16]},
                cv=min(2, len(x_data)),
                scoring="neg_mean_squared_error",
            )
            grid.fit(X_np, Y_np)
            model = grid.best_estimator_.model
            final_loss = float(-grid.best_score_)
            best_lr = float(grid.best_params_["lr"])
            best_hidden = int(grid.best_params_["hidden_size"])
            preds = grid.best_estimator_.predict(X_np)
        else:
            est = PyTorchSLAEstimator().fit(X_np, Y_np)
            model = est.model
            preds = est.predict(X_np)
    except ImportError:
        model = SLAModel(best_hidden)
        opt = torch.optim.Adam(model.parameters(), lr=best_lr)
        loss_fn = nn.MSELoss()
        xt = torch.tensor(X_np, dtype=torch.float32)
        yt = torch.tensor(Y_np, dtype=torch.float32)
        for _ in range(50):
            opt.zero_grad()
            loss = loss_fn(model(xt), yt)
            loss.backward()
            opt.step()
            final_loss = float(loss.item())
        model.eval()
        with torch.no_grad():
            preds = model(xt).numpy()

    avg_predicted_sla = max(0.0, min(100.0, float(np.mean(preds)) * 100.0))
    artifact = Path(settings.ML_MODEL_DIR) / "sla" / str(tenant_id)
    artifact.mkdir(parents=True, exist_ok=True)
    path = artifact / "sla_model.pt"
    torch.save({"state_dict": model.state_dict(), "hidden": best_hidden, "lr": best_lr}, path)

    run = await pool.fetchrow(
        """
        INSERT INTO training_runs (
            tenant_id, model_name, model_version, status, metrics, artifact_path
        )
        VALUES ($1::uuid, 'sla', $2, 'completed', $3::jsonb, $4)
        RETURNING id::text, model_name, status, metrics, artifact_path, created_at
        """,
        str(tenant_id),
        settings.ML_MODEL_VERSION,
        json.dumps(
            {
                "loss": final_loss,
                "average_sla": avg_predicted_sla,
                "samples": len(x_data),
                "lr": best_lr,
                "hidden_size": best_hidden,
            }
        ),
        str(path),
    )
    return {
        "ok": True,
        "average_sla": avg_predicted_sla,
        "training_run": dict(run),
        "artifact_path": str(path),
    }
