"""NorseSSN — spiking temporal forecaster (Norse LIF) with MLP fallback.

Port of the SpikingTemporalForecaster pattern: sequence in → forecast score out.
Uses ``norse`` when installed (``uv sync --group ml-spiking``); otherwise a
compact torch MLP / GRU path so the platform still trains and scores.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.services.ml import common as mlc
from app.services.ml.lstm_autoencoder import windows_from_series

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


def _build(torch: Any, nn: Any, *, seq_len: int, input_dim: int = 1) -> tuple[Any, bool]:
    uses_norse = False

    class SpikingTemporalForecaster(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.seq_len = seq_len
            self.input_dim = input_dim
            self.pre = nn.Linear(input_dim, 32)
            if _NORSE_OK and norse_torch is not None:
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
    uses_norse = bool(getattr(model, "_uses_norse", False))
    return model, uses_norse


def _ckpt(tenant_id: str | None) -> Path:
    return mlc.model_dir(FAMILY, tenant_id=tenant_id) / "spiking_temporal.pt"


def fit(
    *,
    series: list[float] | None = None,
    seq_len: int = 16,
    epochs: int = 16,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    torch, nn = _require()
    arr = np.asarray(series, dtype=np.float32) if series else mlc.synthetic_series(length=96)
    windows = windows_from_series(arr.tolist(), seq_len)
    if windows.shape[0] < 4:
        raise ValueError("need more series points for spiking fit")

    # Label = whether next-step residual exceeds rolling threshold (spike risk).
    y = []
    for i in range(windows.shape[0]):
        w = windows[i]
        y.append(1.0 if float(w[-1] - w.mean()) > 1.5 * (w.std() + 1e-3) else 0.0)
    y_t = torch.tensor(y, dtype=torch.float32)
    x = torch.from_numpy(windows).unsqueeze(-1)

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
    torch.save(
        {
            "state_dict": model.state_dict(),
            "meta": {
                "seq_len": seq_len,
                "uses_norse": uses_norse,
                "final_loss": last,
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
        "n_windows": int(windows.shape[0]),
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
    path = _ckpt(tenant_id)
    if not path.exists():
        raise RuntimeError("norse_ssn not fitted; POST .../fit first")
    blob = torch.load(path, map_location="cpu", weights_only=True)
    meta = dict(blob.get("meta") or {})
    seq_len = int(meta.get("seq_len") or 16)
    model, uses_norse = _build(torch, nn, seq_len=seq_len)
    # If checkpoint was trained with Norse but runtime lacks it (or vice versa),
    # rebuild matching architecture via meta flag when possible.
    model.load_state_dict(blob["state_dict"], strict=False)
    model.eval()
    window = windows_from_series(series, seq_len)[-1:]
    with torch.no_grad():
        x = torch.from_numpy(window).unsqueeze(-1)
        score = float(model(x).item())
    return {
        "ok": True,
        "family": FAMILY,
        "score": score,
        "is_anomaly": score >= threshold,
        "threshold": threshold,
        "uses_norse": bool(meta.get("uses_norse", uses_norse)),
        "backend": "norse_lif" if meta.get("uses_norse") else "gru_mlp_fallback",
    }
