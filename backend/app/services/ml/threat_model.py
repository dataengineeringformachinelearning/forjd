"""ThreatModel / CESModel — tenant-scoped training without end-user FK.

Feature extraction reads FORJD threat_intelligence + incident_cases + stream_results.
Install: uv sync --group ml
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

logger = logging.getLogger("forjd.ml.threat")

try:
    import torch
    from torch import nn

    _TORCH_OK = True
except ImportError:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_OK = False


# --- Model definitions  ---
if _TORCH_OK:

    class ThreatModel(nn.Module):
        FEATURE_DIM = 6

        def __init__(self, in_features: int = FEATURE_DIM) -> None:
            super().__init__()
            self.fc1 = nn.Linear(in_features, 12)
            self.fc2 = nn.Linear(12, 1)
            self.sigmoid = nn.Sigmoid()

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            x = torch.relu(self.fc1(x))
            return self.sigmoid(self.fc2(x))

    class CESModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.fc1 = nn.Linear(3, 8)
            self.fc2 = nn.Linear(8, 1)
            self.sigmoid = nn.Sigmoid()

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            x = torch.relu(self.fc1(x))
            return self.sigmoid(self.fc2(x)) * 100.0

else:  # pragma: no cover

    class ThreatModel:  # type: ignore[no-redef]
        FEATURE_DIM = 6

        def __init__(self, *_a: Any, **_k: Any) -> None:
            raise RuntimeError("PyTorch is not installed. From backend/: uv sync --group ml")

    class CESModel:  # type: ignore[no-redef]
        def __init__(self, *_a: Any, **_k: Any) -> None:
            raise RuntimeError("PyTorch is not installed. From backend/: uv sync --group ml")


def _require_torch() -> None:
    if not _TORCH_OK or not torch_available():
        raise RuntimeError("PyTorch is not installed. From backend/: uv sync --group ml")


# --- Soft schema for training_runs / threat_reports ---
async def ensure_ml_domain_schema(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS training_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'completed',
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            artifact_path TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS threat_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            score DOUBLE PRECISION NOT NULL DEFAULT 0,
            features JSONB NOT NULL DEFAULT '[]'::jsonb,
            summary TEXT NOT NULL DEFAULT '',
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


# --- Feature extraction (asyncpg, tenant_id) ---
async def extract_threat_features(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
) -> list[float]:
    """Six-feature vector: location weight, suspicious ratio, failure, velocity, behavior, cases."""
    threat_count = await pool.fetchval(
        """
        SELECT COUNT(*)::int FROM threat_intelligence
        WHERE (tenant_id = $1::uuid OR is_platform = TRUE)
          AND created_at >= NOW() - INTERVAL '24 hours'
        """,
        str(tenant_id),
    )
    malicious_count = await pool.fetchval(
        """
        SELECT COUNT(*)::int FROM threat_intelligence
        WHERE (tenant_id = $1::uuid OR is_platform = TRUE)
          AND is_malicious = TRUE
          AND created_at >= NOW() - INTERVAL '24 hours'
        """,
        str(tenant_id),
    )
    case_total = await pool.fetchval(
        """
        SELECT COUNT(*)::int FROM incident_cases
        WHERE tenant_id = $1::uuid AND created_at >= NOW() - INTERVAL '90 days'
        """,
        str(tenant_id),
    )
    case_resolved = await pool.fetchval(
        """
        SELECT COUNT(*)::int FROM incident_cases
        WHERE tenant_id = $1::uuid
          AND status IN ('resolved', 'mitigated')
          AND created_at >= NOW() - INTERVAL '90 days'
        """,
        str(tenant_id),
    )
    # Metadata anomaly density from stream_results (ciphertext-blind)
    result_total = await pool.fetchval(
        """
        SELECT COUNT(*)::int FROM stream_results
        WHERE tenant_id = $1::uuid AND created_at >= NOW() - INTERVAL '7 days'
        """,
        str(tenant_id),
    )
    anomaly_total = await pool.fetchval(
        """
        SELECT COUNT(*)::int FROM stream_results
        WHERE tenant_id = $1::uuid
          AND created_at >= NOW() - INTERVAL '7 days'
          AND (is_anomaly = TRUE OR COALESCE(score, 0) >= 0.7)
        """,
        str(tenant_id),
    )

    location_weight = min(1.0, 0.35 + float(malicious_count or 0) * 0.1)
    suspicious_ratio = float(anomaly_total or 0) / float(result_total) if result_total else 0.05
    failure_rate = min(1.0, suspicious_ratio * 0.5)
    threat_velocity = min(1.0, float(threat_count or 0) / 100.0)
    behavioral_score = min(1.0, suspicious_ratio)
    incident_confidence = float(case_resolved or 0) / float(max(1, case_total or 0))

    return [
        max(0.0, min(1.0, location_weight)),
        max(0.0, min(1.0, suspicious_ratio)),
        max(0.0, min(1.0, failure_rate)),
        max(0.0, min(1.0, threat_velocity)),
        max(0.0, min(1.0, behavioral_score)),
        max(0.0, min(1.0, incident_confidence)),
    ]


def _model_path(tenant_id: UUID) -> Path:
    path = Path(settings.ML_MODEL_DIR) / "threat" / str(tenant_id)
    path.mkdir(parents=True, exist_ok=True)
    return path / "threat_model.pt"


# --- Train + score ---
async def train_threat_model(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    epochs: int = 40,
) -> dict[str, Any]:
    _require_torch()
    from app.services import soc as soc_svc
    from app.services import threat_intel as threat_svc

    await threat_svc.ensure_threat_schema(pool)
    await soc_svc.ensure_soc_schema(pool)
    await ensure_ml_domain_schema(pool)
    features = await extract_threat_features(pool, tenant_id=tenant_id)
    x = torch.tensor([features], dtype=torch.float32)
    # Weak self-supervised target: elevated velocity/malicious pressure
    target = torch.tensor(
        [[min(1.0, (features[3] + features[1]) / 2.0)]],
        dtype=torch.float32,
    )
    model = ThreatModel()
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    loss_fn = nn.MSELoss()
    last_loss = 0.0
    model.train()
    for _ in range(max(1, epochs)):
        opt.zero_grad()
        pred = model(x)
        loss = loss_fn(pred, target)
        loss.backward()
        opt.step()
        last_loss = float(loss.item())

    artifact = _model_path(tenant_id)
    torch.save({"state_dict": model.state_dict(), "features": features}, artifact)

    model.eval()
    with torch.no_grad():
        score = float(model(x).item())

    run = await pool.fetchrow(
        """
        INSERT INTO training_runs (
            tenant_id, model_name, model_version, status, metrics, artifact_path
        )
        VALUES ($1::uuid, 'threat', $2, 'completed', $3::jsonb, $4)
        RETURNING id::text, model_name, model_version, status, metrics, artifact_path, created_at
        """,
        str(tenant_id),
        settings.ML_MODEL_VERSION,
        json.dumps({"loss": last_loss, "score": score, "features": features}),
        str(artifact),
    )
    report = await pool.fetchrow(
        """
        INSERT INTO threat_reports (tenant_id, score, features, summary, metadata)
        VALUES ($1::uuid, $2, $3::jsonb, $4, $5::jsonb)
        RETURNING id::text, score, features, summary, created_at
        """,
        str(tenant_id),
        score,
        json.dumps(features),
        f"Threat model score={score:.4f}",
        json.dumps({"training_run_id": run["id"]}),
    )
    return {
        "ok": True,
        "score": score,
        "features": features,
        "training_run": dict(run),
        "threat_report": dict(report),
        "artifact_path": str(artifact),
    }


async def score_threat_model(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
) -> dict[str, Any]:
    _require_torch()
    from app.services import soc as soc_svc
    from app.services import threat_intel as threat_svc

    await threat_svc.ensure_threat_schema(pool)
    await soc_svc.ensure_soc_schema(pool)
    features = await extract_threat_features(pool, tenant_id=tenant_id)
    artifact = _model_path(tenant_id)
    model = ThreatModel()
    if artifact.is_file():
        payload = torch.load(artifact, map_location="cpu", weights_only=True)
        model.load_state_dict(payload["state_dict"])
    model.eval()
    with torch.no_grad():
        x = torch.tensor([features], dtype=torch.float32)
        score = float(model(x).item())
    return {"ok": True, "score": score, "features": features, "loaded": artifact.is_file()}
