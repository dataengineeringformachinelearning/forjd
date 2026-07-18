"""Forecasting models — TFT-lite, NeuralSeasonal (Prophet-class), GRU/LSTM P99.

Compact torch implementations for the ``ml`` group (no pytorch-forecasting /
prophet packages — those are heavy and brittle for a lean platform).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import numpy as np

from app.services.ml import common as mlc

FAMILY = "forecasting"
CellKind = Literal["gru", "lstm"]


def _require() -> Any:
    mlc.require_torch()
    import torch
    from torch import nn

    return torch, nn


def _paths(tenant_id: str | None) -> dict[str, Path]:
    root = mlc.model_dir(FAMILY, tenant_id=tenant_id)
    return {
        "tft_lite": root / "tft_lite.pt",
        "neural_seasonal": root / "neural_seasonal.pt",
        "p99_gru": root / "p99_gru.pt",
        "p99_lstm": root / "p99_lstm.pt",
    }


# --- TFT-lite (variable selection → temporal attention → horizon) ---
def _tft(torch: Any, nn: Any, *, seq_len: int, horizon: int) -> Any:
    class TFTLite(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.seq_len = seq_len
            self.horizon = horizon
            self.sel = nn.Sequential(nn.Linear(1, 16), nn.ReLU(), nn.Linear(16, 1))
            enc = nn.TransformerEncoderLayer(
                d_model=16, nhead=4, dim_feedforward=32, batch_first=True, dropout=0.0
            )
            self.temporal = nn.TransformerEncoder(enc, num_layers=1)
            self.proj_in = nn.Linear(1, 16)
            self.head = nn.Linear(16, horizon)

        def forward(self, x: Any) -> Any:
            # x: (B, T, 1)
            gates = torch.sigmoid(self.sel(x))
            h = self.proj_in(x * gates)
            z = self.temporal(h)
            return self.head(z[:, -1, :])

    return TFTLite()


# --- Neural seasonal (Prophet-class additive: trend + Fourier seasonality) ---
def _neural_seasonal(torch: Any, nn: Any, *, n_harmonics: int = 4) -> Any:
    class NeuralSeasonal(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.trend = nn.Linear(1, 1)
            self.season = nn.Linear(n_harmonics * 2, 1)
            self.n_harmonics = n_harmonics

        def _fourier(self, t: Any) -> Any:
            cols = []
            for k in range(1, self.n_harmonics + 1):
                cols.append(torch.sin(2 * np.pi * k * t / 24.0))
                cols.append(torch.cos(2 * np.pi * k * t / 24.0))
            return torch.cat(cols, dim=-1)

        def forward(self, t: Any) -> Any:
            # t: (B, 1) integer timesteps
            return self.trend(t) + self.season(self._fourier(t))

    return NeuralSeasonal()


# --- GRU / LSTM multi-step P99 latency forecaster ---
def _seq_forecaster(
    torch: Any, nn: Any, *, kind: CellKind, seq_len: int, horizon: int
) -> Any:
    cell = nn.GRU if kind == "gru" else nn.LSTM

    class P99Forecaster(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.seq_len = seq_len
            self.horizon = horizon
            self.rnn = cell(1, 32, batch_first=True)
            self.head = nn.Linear(32, horizon)

        def forward(self, x: Any) -> Any:
            out, _ = self.rnn(x)
            return self.head(out[:, -1, :])

    return P99Forecaster()


def _make_xy(series: np.ndarray, *, seq_len: int, horizon: int) -> tuple[Any, Any]:
    xs, ys = [], []
    for i in range(0, len(series) - seq_len - horizon + 1):
        xs.append(series[i : i + seq_len])
        ys.append(series[i + seq_len : i + seq_len + horizon])
    if not xs:
        raise ValueError("series too short for seq_len+horizon windows")
    return (
        np.stack(xs).astype(np.float32)[..., None],
        np.stack(ys).astype(np.float32),
    )


def fit(
    *,
    series: list[float] | None = None,
    seq_len: int = 16,
    horizon: int = 4,
    epochs: int = 20,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    torch, nn = _require()
    arr = (
        np.asarray(series, dtype=np.float32)
        if series
        else mlc.synthetic_series(length=max(80, seq_len + horizon + 32))
    )
    x_np, y_np = _make_xy(arr, seq_len=seq_len, horizon=horizon)
    x = torch.from_numpy(x_np)
    y = torch.from_numpy(y_np)
    t_idx = torch.arange(len(arr), dtype=torch.float32).view(-1, 1)
    y_full = torch.from_numpy(arr).view(-1, 1)

    paths = _paths(tenant_id)
    losses: dict[str, float] = {}

    # TFT-lite
    tft = _tft(torch, nn, seq_len=seq_len, horizon=horizon)
    opt = torch.optim.Adam(tft.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()
    last = 0.0
    for _ in range(epochs):
        opt.zero_grad()
        pred = tft(x)
        loss = loss_fn(pred, y)
        loss.backward()
        opt.step()
        last = float(loss.item())
    losses["tft_lite"] = last
    torch.save(
        {"state_dict": tft.state_dict(), "meta": {"seq_len": seq_len, "horizon": horizon}},
        paths["tft_lite"],
    )

    # Neural seasonal (Prophet-class)
    ns = _neural_seasonal(torch, nn)
    opt = torch.optim.Adam(ns.parameters(), lr=1e-2)
    last = 0.0
    for _ in range(epochs * 2):
        opt.zero_grad()
        pred = ns(t_idx)
        loss = loss_fn(pred, y_full)
        loss.backward()
        opt.step()
        last = float(loss.item())
    losses["neural_seasonal"] = last
    torch.save({"state_dict": ns.state_dict(), "meta": {"length": int(len(arr))}}, paths["neural_seasonal"])

    # GRU + LSTM P99
    for kind, key in (("gru", "p99_gru"), ("lstm", "p99_lstm")):
        model = _seq_forecaster(torch, nn, kind=kind, seq_len=seq_len, horizon=horizon)  # type: ignore[arg-type]
        opt = torch.optim.Adam(model.parameters(), lr=1e-3)
        last = 0.0
        for _ in range(epochs):
            opt.zero_grad()
            pred = model(x)
            # Supervise toward rolling p99 of the horizon window.
            target = torch.quantile(y, 0.99, dim=1, keepdim=True).expand_as(pred)
            loss = loss_fn(pred, target)
            loss.backward()
            opt.step()
            last = float(loss.item())
        losses[key] = last
        torch.save(
            {
                "state_dict": model.state_dict(),
                "meta": {"seq_len": seq_len, "horizon": horizon, "cell": kind},
            },
            paths[key],
        )

    return {
        "ok": True,
        "family": FAMILY,
        "models": list(paths.keys()),
        "losses": losses,
        "seq_len": seq_len,
        "horizon": horizon,
        "n_points": int(len(arr)),
        "paths": {k: str(v) for k, v in paths.items()},
    }


def score(
    *,
    series: list[float],
    tenant_id: str | None = None,
    model: str = "tft_lite",
) -> dict[str, Any]:
    torch, nn = _require()
    paths = _paths(tenant_id)
    if model not in paths:
        raise ValueError(f"unknown forecasting model {model!r}; known: {sorted(paths)}")
    path = paths[model]
    if not path.exists():
        raise RuntimeError(f"{model} not fitted; POST .../fit first")

    blob = torch.load(path, map_location="cpu", weights_only=False)
    meta = dict(blob.get("meta") or {})
    arr = np.asarray(series, dtype=np.float32)

    if model == "neural_seasonal":
        m = _neural_seasonal(torch, nn)
        m.load_state_dict(blob["state_dict"])
        m.eval()
        future_t = torch.arange(len(arr), len(arr) + 8, dtype=torch.float32).view(-1, 1)
        with torch.no_grad():
            forecast = m(future_t).squeeze(-1).cpu().numpy().astype(np.float32).tolist()
        return {
            "ok": True,
            "family": FAMILY,
            "model": model,
            "forecast": forecast,
            "kind": "prophet_neural",
        }

    seq_len = int(meta.get("seq_len") or 16)
    horizon = int(meta.get("horizon") or 4)
    if len(arr) < seq_len:
        pad = np.zeros(seq_len, dtype=np.float32)
        pad[-len(arr) :] = arr
        window = pad
    else:
        window = arr[-seq_len:]

    if model == "tft_lite":
        m = _tft(torch, nn, seq_len=seq_len, horizon=horizon)
    else:
        kind: CellKind = "gru" if model == "p99_gru" else "lstm"
        m = _seq_forecaster(torch, nn, kind=kind, seq_len=seq_len, horizon=horizon)

    m.load_state_dict(blob["state_dict"])
    m.eval()
    with torch.no_grad():
        x = torch.from_numpy(window).view(1, seq_len, 1)
        pred = m(x).squeeze(0).cpu().numpy().astype(np.float32)
    out: dict[str, Any] = {
        "ok": True,
        "family": FAMILY,
        "model": model,
        "forecast": pred.tolist(),
        "horizon": horizon,
        "seq_len": seq_len,
    }
    if model.startswith("p99_"):
        out["p99_forecast"] = float(np.max(pred))
        out["kind"] = "latency_p99"
    else:
        out["kind"] = "tft_lite"
    return out
