"""NorseSSN — spiking temporal forecaster (Norse LIF) with MLP fallback.

Port of the SpikingTemporalForecaster pattern: sequence in → forecast score out.
Uses ``norse`` when installed (``uv sync --group ml-spiking``); otherwise a
compact torch MLP / GRU path so the platform still trains and scores.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np

from app.services.ml import common as mlc

FAMILY = "norse_ssn"

try:
    import norse.torch as norse_torch

    _NORSE_OK = True
except ImportError:  # pragma: no cover
    norse_torch = None  # type: ignore[assignment]
    _NORSE_OK = False


def norse_available() -> bool:
    return _NORSE_OK


def _require() -> Any:
    mlc.require_torch()
    import torch
    from torch import nn

    return torch, nn


def _build(
    torch: Any,
    nn: Any,
    *,
    seq_len: int,
    input_dim: int = 1,
    use_norse: bool | None = None,
) -> tuple[Any, bool]:
    selected_norse = _NORSE_OK if use_norse is None else use_norse
    if selected_norse and (not _NORSE_OK or norse_torch is None):
        raise RuntimeError("checkpoint requires Norse; install with: uv sync --group ml-spiking")

    class SpikingTemporalForecaster(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.seq_len = seq_len
            self.input_dim = input_dim
            self.pre = nn.Linear(input_dim, 32)
            if selected_norse and norse_torch is not None:
                # LIF recurrent cell over the projected sequence.
                self.lif = norse_torch.LIFCell()
                self._uses_norse = True
            else:
                self.lif = None
                self.fallback = nn.GRU(32, 32, batch_first=True)
                self._uses_norse = False
            self.head = nn.Sequential(nn.Linear(32, 16), nn.ReLU(), nn.Linear(16, 1), nn.Sigmoid())

        def forward(self, x: Any) -> Any:
            # x: (B, T, F)
            h = torch.relu(self.pre(x))
            if self.lif is not None:
                state = None
                spikes = []
                for t in range(h.size(1)):
                    z, state = self.lif(h[:, t, :], state)
                    spikes.append(z)
                seq = torch.stack(spikes, dim=1)
                pooled = seq.mean(dim=1)
            else:
                out, _ = self.fallback(h)
                pooled = out[:, -1, :]
            return self.head(pooled).squeeze(-1)

    model = SpikingTemporalForecaster()
    return model, bool(getattr(model, "_uses_norse", False))


def _ckpt(tenant_id: str | None) -> Path:
    return mlc.model_dir(FAMILY, tenant_id=tenant_id) / "spiking_temporal.pt"


def _save_checkpoint(torch: Any, payload: dict[str, Any], path: Path) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        torch.save(payload, temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def fit(
    *,
    series: list[float] | None = None,
    seq_len: int = 16,
    epochs: int = 16,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    torch, nn = _require()
    if tenant_id and not series:
        raise ValueError("real series is required for tenant-scoped norse_ssn fit")
    arr = np.asarray(series, dtype=np.float32) if series else mlc.synthetic_series(length=96)
    if arr.ndim != 1 or not np.isfinite(arr).all():
        raise ValueError("series must be a finite one-dimensional sequence")
    if len(arr) < seq_len + 4:
        raise ValueError(f"series must contain at least {seq_len + 4} points")

    # Forecast the next observation's spike risk from the preceding window.
    windows: list[np.ndarray[Any, Any]] = []
    y: list[float] = []
    for i in range(len(arr) - seq_len):
        window = arr[i : i + seq_len]
        next_value = float(arr[i + seq_len])
        windows.append(window)
        y.append(
            1.0 if next_value > float(window.mean()) + 1.5 * (float(window.std()) + 1e-3) else 0.0
        )
    window_matrix = np.stack(windows).astype(np.float32)
    y_t = torch.tensor(y, dtype=torch.float32)
    x = torch.from_numpy(window_matrix).unsqueeze(-1)

    model, uses_norse = _build(torch, nn, seq_len=seq_len)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.BCELoss()
    last = 0.0
    model.train()
    for _ in range(max(1, epochs)):
        opt.zero_grad()
        pred = model(x)
        loss = loss_fn(pred, y_t)
        loss.backward()
        opt.step()
        last = float(loss.item())
    model.eval()

    path = _ckpt(tenant_id)
    _save_checkpoint(
        torch,
        {
            "state_dict": model.state_dict(),
            "meta": {
                "seq_len": seq_len,
                "uses_norse": uses_norse,
                "final_loss": last,
                "sample_count": int(len(arr)),
            },
        },
        path,
    )
    return {
        "ok": True,
        "family": FAMILY,
        "model": "spiking_temporal_forecaster",
        "uses_norse": uses_norse,
        "backend": "norse_lif" if uses_norse else "gru_mlp_fallback",
        "final_loss": last,
        "n_windows": int(window_matrix.shape[0]),
        "sample_count": int(len(arr)),
        "seq_len": seq_len,
        "path": str(path),
        "hint": None
        if uses_norse
        else "Install Norse for LIF dynamics: uv sync --group ml-spiking",
    }


def score(
    *,
    series: list[float],
    tenant_id: str | None = None,
    threshold: float = 0.55,
) -> dict[str, Any]:
    torch, nn = _require()
    if not series:
        raise ValueError("series required for norse_ssn score")
    if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    path = _ckpt(tenant_id)
    if not path.exists():
        raise RuntimeError("norse_ssn not fitted; POST .../fit first")
    blob = torch.load(path, map_location="cpu", weights_only=True)
    meta = dict(blob.get("meta") or {})
    seq_len = int(meta.get("seq_len") or 16)
    arr = np.asarray(series, dtype=np.float32)
    if arr.ndim != 1 or not np.isfinite(arr).all():
        raise ValueError("series must be a finite one-dimensional sequence")
    if len(arr) < seq_len:
        raise ValueError(f"series must contain at least {seq_len} points")
    trained_with_norse = bool(meta.get("uses_norse"))
    model, _ = _build(torch, nn, seq_len=seq_len, use_norse=trained_with_norse)
    model.load_state_dict(blob["state_dict"])
    model.eval()
    window = arr[-seq_len:].reshape(1, seq_len)
    with torch.no_grad():
        x = torch.from_numpy(window).unsqueeze(-1)
        score = float(model(x).item())
    return {
        "ok": True,
        "family": FAMILY,
        "score": score,
        "is_anomaly": score >= threshold,
        "threshold": threshold,
        "uses_norse": trained_with_norse,
        "backend": "norse_lif" if trained_with_norse else "gru_mlp_fallback",
        "sample_count": int(len(arr)),
        "seq_len": seq_len,
    }
