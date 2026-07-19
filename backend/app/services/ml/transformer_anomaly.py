"""Transformer encoder for sequence anomaly (reconstruction MSE)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.ml import common as mlc
from app.services.ml.lstm_autoencoder import (
    synthetic_normal_windows,
    windows_from_series,
)

FAMILY = "transformer_anomaly"


def _require() -> Any:
    mlc.require_torch()
    import torch
    from torch import nn

    return torch, nn


def _build(torch: Any, nn: Any, *, d_model: int, nhead: int, seq_len: int) -> Any:
    class SeqTransformerAE(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.proj = nn.Linear(1, d_model)
            layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=d_model * 2,
                batch_first=True,
                dropout=0.0,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=2)
            self.out = nn.Linear(d_model, 1)
            self.seq_len = seq_len

        def forward(self, x: Any) -> Any:
            # x: (B, T, 1)
            h = self.proj(x)
            z = self.encoder(h)
            return self.out(z)

    return SeqTransformerAE()


def _ckpt(tenant_id: str | None) -> Path:
    return mlc.model_dir(FAMILY, tenant_id=tenant_id) / "transformer_ae.pt"


def fit(
    *,
    series: list[float] | None = None,
    seq_len: int = 16,
    epochs: int = 12,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    torch, nn = _require()
    if series:
        windows = windows_from_series(series, seq_len)
    else:
        windows = synthetic_normal_windows(n_windows=96, seq_len=seq_len)
    if windows.shape[0] == 0:
        raise ValueError("no training windows")

    model = _build(torch, nn, d_model=32, nhead=4, seq_len=seq_len)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()
    x = torch.from_numpy(windows).unsqueeze(-1)
    last = 0.0
    model.train()
    for _ in range(max(1, epochs)):
        opt.zero_grad()
        recon = model(x)
        loss = loss_fn(recon, x)
        loss.backward()
        opt.step()
        last = float(loss.item())
    model.eval()

    path = _ckpt(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "meta": {"seq_len": seq_len, "d_model": 32, "nhead": 4, "final_loss": last},
        },
        path,
    )
    return {
        "ok": True,
        "family": FAMILY,
        "final_loss": last,
        "n_windows": int(windows.shape[0]),
        "seq_len": seq_len,
        "path": str(path),
    }


def score(
    *,
    series: list[float],
    tenant_id: str | None = None,
    threshold: float = 0.15,
) -> dict[str, Any]:
    torch, nn = _require()
    path = _ckpt(tenant_id)
    if not path.exists():
        raise RuntimeError("transformer anomaly model not fitted; POST .../fit first")
    blob = torch.load(path, map_location="cpu", weights_only=True)
    meta = dict(blob.get("meta") or {})
    seq_len = int(meta.get("seq_len") or 16)
    model = _build(torch, nn, d_model=32, nhead=4, seq_len=seq_len)
    model.load_state_dict(blob["state_dict"])
    model.eval()

    window = windows_from_series(series, seq_len)[-1:]
    with torch.no_grad():
        x = torch.from_numpy(window).unsqueeze(-1)
        recon = model(x)
        err = float(torch.mean((recon - x) ** 2).item())
    return {
        "ok": True,
        "family": FAMILY,
        "reconstruction_error": err,
        "is_anomaly": err >= threshold,
        "threshold": threshold,
        "seq_len": seq_len,
    }
