"""Event embedding encoders for pgvector similarity search.

Default: compact custom torch EventEncoder (no HuggingFace download).
Optional: SentenceTransformer when ``sentence-transformers`` is installed
(``uv sync --group ml-nlp``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.services.ml import common as mlc

FAMILY = "embeddings"
DEFAULT_DIM = 32

try:
    from sentence_transformers import SentenceTransformer

    _ST_OK = True
except ImportError:  # pragma: no cover
    SentenceTransformer = None  # type: ignore[misc, assignment]
    _ST_OK = False


def sentence_transformers_available() -> bool:
    return _ST_OK


def _require() -> Any:
    mlc.require_torch()
    import torch
    from torch import nn

    return torch, nn


def _build_encoder(torch: Any, nn: Any, *, vocab: int = 512, dim: int = DEFAULT_DIM) -> Any:
    class EventEncoder(nn.Module):
        """Hash-bag → MLP encoder for short event text / content_type tags."""

        def __init__(self) -> None:
            super().__init__()
            self.embed = nn.EmbeddingBag(vocab, dim, mode="mean", padding_idx=0)
            self.proj = nn.Sequential(
                nn.Linear(dim, dim),
                nn.ReLU(),
                nn.Linear(dim, dim),
            )
            self.dim = dim
            self.vocab = vocab

        def tokenize(self, texts: list[str]) -> Any:
            rows = []
            for text in texts:
                tokens = [((hash(tok) % (self.vocab - 1)) + 1) for tok in text.lower().split()]
                if not tokens:
                    tokens = [1]
                rows.append(tokens[:64])
            max_len = max(len(r) for r in rows)
            mat = torch.zeros((len(rows), max_len), dtype=torch.long)
            for i, r in enumerate(rows):
                mat[i, : len(r)] = torch.tensor(r, dtype=torch.long)
            return mat

        def forward(self, token_ids: Any) -> Any:
            h = self.embed(token_ids)
            z = self.proj(h)
            return torch.nn.functional.normalize(z, dim=-1)

    return EventEncoder()


def _ckpt(tenant_id: str | None) -> Path:
    return mlc.model_dir(FAMILY, tenant_id=tenant_id) / "event_encoder.pt"


def fit(
    *,
    texts: list[str] | None = None,
    epochs: int = 8,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    torch, nn = _require()
    corpus = texts or [
        "application/forjd-event+v1 sealed ingest",
        "threat.alert elevated abuse score",
        "latency spike p99 forecast",
        "session revoke crypto key_id",
        "rollup anomaly size_anomaly detector",
        "status page incident investigating",
    ]
    model = _build_encoder(torch, nn)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    # Self-supervised: pull shuffled batch toward itself (identity) + mild noise.
    last = 0.0
    model.train()
    for _ in range(max(1, epochs)):
        ids = model.tokenize(corpus)
        opt.zero_grad()
        z = model(ids)
        # Contrastive-lite: maximize diagonal cosine of z @ z.T
        sim = z @ z.T
        target = torch.eye(sim.size(0))
        loss = nn.MSELoss()(sim, target)
        loss.backward()
        opt.step()
        last = float(loss.item())
    model.eval()
    path = _ckpt(tenant_id)
    torch.save(
        {"state_dict": model.state_dict(), "meta": {"dim": DEFAULT_DIM, "final_loss": last}},
        path,
    )
    return {
        "ok": True,
        "family": FAMILY,
        "encoder": "event_encoder",
        "dim": DEFAULT_DIM,
        "n_texts": len(corpus),
        "final_loss": last,
        "path": str(path),
        "sentence_transformers": sentence_transformers_available(),
    }


def encode(
    *,
    texts: list[str],
    tenant_id: str | None = None,
    backend: str = "event_encoder",
) -> dict[str, Any]:
    """Encode texts → unit vectors for pgvector / similarity."""
    if not texts:
        raise ValueError("texts required")

    if backend == "sentence_transformers":
        if not _ST_OK:
            raise RuntimeError(
                "sentence-transformers not installed. From backend/: uv sync --group ml-nlp"
            )
        assert SentenceTransformer is not None
        st = SentenceTransformer("all-MiniLM-L6-v2")
        vecs = st.encode(texts, normalize_embeddings=True)
        return {
            "ok": True,
            "family": FAMILY,
            "backend": backend,
            "dim": int(vecs.shape[1]),
            "embeddings": np.asarray(vecs, dtype=np.float32).tolist(),
        }

    torch, nn = _require()
    path = _ckpt(tenant_id)
    model = _build_encoder(torch, nn)
    if path.exists():
        blob = torch.load(path, map_location="cpu", weights_only=False)
        model.load_state_dict(blob["state_dict"])
    model.eval()
    with torch.no_grad():
        ids = model.tokenize(texts)
        z = model(ids).cpu().numpy().astype(np.float32)
    return {
        "ok": True,
        "family": FAMILY,
        "backend": "event_encoder",
        "dim": int(z.shape[1]),
        "embeddings": z.tolist(),
        "fitted": path.exists(),
    }
