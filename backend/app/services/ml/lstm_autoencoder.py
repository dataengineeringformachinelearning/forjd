"""Compact LSTM Autoencoder for unsupervised time-series anomaly detection.

Reconstruction MSE is the anomaly score; the bottleneck latent vector is what we
store in Supabase pgvector for nearest-neighbor retrieval.

Forecasting (TFT-lite, NeuralSeasonal, GRU/LSTM P99) lives in
``app.services.ml.forecasting`` — separate supervised suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    _TORCH_OK = True
except ImportError:  # pragma: no cover - optional ml group
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    DataLoader = None  # type: ignore[assignment]
    TensorDataset = None  # type: ignore[assignment]
    _TORCH_OK = False


def torch_available() -> bool:
    return _TORCH_OK


def _require_torch() -> None:
    if not _TORCH_OK:
        raise RuntimeError("PyTorch is not installed. From backend/: uv sync --group ml")


if _TORCH_OK:

    class LSTMAutoencoder(nn.Module):
        """Seq2seq LSTM autoencoder with a fixed-size latent bottleneck."""

        def __init__(
            self,
            *,
            input_dim: int = 1,
            hidden_dim: int = 32,
            latent_dim: int = 16,
            num_layers: int = 1,
        ) -> None:
            super().__init__()
            self.input_dim = input_dim
            self.hidden_dim = hidden_dim
            self.latent_dim = latent_dim
            self.num_layers = num_layers

            self.encoder = nn.LSTM(
                input_dim,
                hidden_dim,
                num_layers=num_layers,
                batch_first=True,
            )
            self.to_latent = nn.Linear(hidden_dim, latent_dim)
            self.from_latent = nn.Linear(latent_dim, hidden_dim)
            self.decoder = nn.LSTM(
                hidden_dim,
                hidden_dim,
                num_layers=num_layers,
                batch_first=True,
            )
            self.out = nn.Linear(hidden_dim, input_dim)

        def encode(self, x: torch.Tensor) -> torch.Tensor:
            # x: (B, T, F)
            _, (h_n, _) = self.encoder(x)
            return self.to_latent(h_n[-1])

        def decode(self, z: torch.Tensor, seq_len: int) -> torch.Tensor:
            h0 = self.from_latent(z).unsqueeze(0).repeat(self.num_layers, 1, 1)
            c0 = torch.zeros_like(h0)
            dec_in = h0[-1].unsqueeze(1).repeat(1, seq_len, 1)
            decoded, _ = self.decoder(dec_in, (h0, c0))
            return self.out(decoded)

        def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
            z = self.encode(x)
            recon = self.decode(z, x.size(1))
            return recon, z

else:  # pragma: no cover

    class LSTMAutoencoder:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            _require_torch()


@dataclass(frozen=True)
class FitResult:
    epochs: int
    final_loss: float
    n_windows: int
    model_version: str
    checkpoint_path: str


@dataclass(frozen=True)
class ScoreResult:
    reconstruction_error: float
    embedding: list[float]
    reconstructed: list[float]


def windows_from_series(values: list[float], seq_len: int) -> np.ndarray:
    """Sliding windows; pad short series to one window."""
    arr = np.asarray(values, dtype=np.float32)
    if arr.size == 0:
        return np.zeros((0, seq_len), dtype=np.float32)
    if arr.size < seq_len:
        pad = np.zeros(seq_len, dtype=np.float32)
        pad[: arr.size] = arr
        return pad.reshape(1, seq_len)
    n = arr.size - seq_len + 1
    return np.stack([arr[i : i + seq_len] for i in range(n)], axis=0)


def pad_or_truncate(values: list[float], seq_len: int) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32)
    out = np.zeros(seq_len, dtype=np.float32)
    n = min(arr.size, seq_len)
    out[:n] = arr[:n]
    return out


def synthetic_normal_windows(
    *,
    n_windows: int = 128,
    seq_len: int = 16,
    seed: int = 42,
) -> np.ndarray:
    """Smooth sine + low noise — the unsupervised 'normal' class for baseline training."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, 2.0 * np.pi, seq_len, dtype=np.float32)
    phases = rng.uniform(0, 2 * np.pi, size=n_windows).astype(np.float32)
    amps = rng.uniform(0.6, 1.4, size=n_windows).astype(np.float32)
    noise = rng.normal(0.0, 0.05, size=(n_windows, seq_len)).astype(np.float32)
    return (amps[:, None] * np.sin(t[None, :] + phases[:, None]) + noise).astype(np.float32)


def build_model(*, hidden_dim: int, latent_dim: int) -> LSTMAutoencoder:
    _require_torch()
    return LSTMAutoencoder(
        input_dim=1,
        hidden_dim=hidden_dim,
        latent_dim=latent_dim,
        num_layers=1,
    )


def fit_model(
    model: LSTMAutoencoder,
    windows: np.ndarray,
    *,
    epochs: int,
    lr: float = 1e-3,
    batch_size: int = 32,
) -> float:
    """Train in-process; returns final MSE loss."""
    _require_torch()
    assert torch is not None and nn is not None

    if windows.ndim != 2 or windows.shape[0] == 0:
        raise ValueError("need at least one training window")

    device = torch.device("cpu")
    model = model.to(device)
    model.train()

    x = torch.from_numpy(windows).unsqueeze(-1)  # (N, T, 1)
    loader = DataLoader(
        TensorDataset(x),
        batch_size=min(batch_size, len(windows)),
        shuffle=True,
    )
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()
    last = 0.0

    for _ in range(epochs):
        epoch_loss = 0.0
        n_batches = 0
        for (batch,) in loader:
            batch = batch.to(device)
            opt.zero_grad()
            recon, _ = model(batch)
            loss = loss_fn(recon, batch)
            loss.backward()
            opt.step()
            epoch_loss += float(loss.item())
            n_batches += 1
        last = epoch_loss / max(n_batches, 1)

    model.eval()
    return last


def score_window(model: LSTMAutoencoder, window: np.ndarray) -> ScoreResult:
    _require_torch()
    assert torch is not None

    model.eval()
    with torch.no_grad():
        x = torch.from_numpy(window.astype(np.float32)).view(1, -1, 1)
        recon, z = model(x)
        err = float(torch.mean((recon - x) ** 2).item())
        embedding = z.squeeze(0).cpu().numpy().astype(np.float32).tolist()
        reconstructed = recon.squeeze(0).squeeze(-1).cpu().numpy().astype(np.float32).tolist()
    return ScoreResult(
        reconstruction_error=err,
        embedding=embedding,
        reconstructed=reconstructed,
    )


def save_checkpoint(
    model: LSTMAutoencoder,
    path: Path,
    *,
    meta: dict[str, Any],
) -> None:
    _require_torch()
    assert torch is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "meta": meta}, path)


def load_checkpoint(
    path: Path,
    *,
    hidden_dim: int,
    latent_dim: int,
) -> tuple[LSTMAutoencoder, dict[str, Any]]:
    _require_torch()
    assert torch is not None
    blob = torch.load(path, map_location="cpu", weights_only=True)
    model = build_model(hidden_dim=hidden_dim, latent_dim=latent_dim)
    model.load_state_dict(blob["state_dict"])
    model.eval()
    return model, dict(blob.get("meta") or {})
