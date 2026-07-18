"""Optional ML suite — anomaly, threat, forecasting, embeddings, NorseSSN.

Install: ``uv sync --group ml``
Optional Norse LIF: ``uv sync --group ml-spiking``
Optional Sentence-Transformers: ``uv sync --group ml-nlp``
"""

from app.services.ml.lstm_autoencoder import LSTMAutoencoder, torch_available
from app.services.ml.norse_ssn import norse_available
from app.services.ml.registry import CATALOG, fit_model, list_models, score_model
from app.services.ml.threat_model import CESModel, ThreatModel

__all__ = [
    "CATALOG",
    "CESModel",
    "LSTMAutoencoder",
    "ThreatModel",
    "fit_model",
    "list_models",
    "norse_available",
    "score_model",
    "torch_available",
]
