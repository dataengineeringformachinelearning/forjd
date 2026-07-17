from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "forjd"
    PROJECT_VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:4200",
            "http://127.0.0.1:4200",
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
    )

    POSTGRES_DSN: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/forjd"
    # Dragonfly (Redis protocol). Local Compose or Fly: redis://:pass@forjd-dragonfly.internal:6379/0
    REDIS_URL: str = "redis://localhost:6379/0"
    PREFECT_API_URL: str = "http://127.0.0.1:4200/api"

    # Optional shared secret for mutating API routes (empty = disabled, local PoC).
    # Prefer X-API-Key. Bearer JWTs are not treated as the API key (see security.py).
    API_KEY: str = ""

    # Supabase Auth — set SUPABASE_URL (JWKS) and/or SUPABASE_JWT_SECRET (HS256).
    SUPABASE_URL: str = ""
    SUPABASE_JWT_SECRET: str = ""
    # Usually "authenticated" for user access tokens; empty skips aud check.
    SUPABASE_JWT_AUDIENCE: str = "authenticated"
    # When true, missing auth config fails closed on protected routes.
    SUPABASE_AUTH_REQUIRED: bool = False

    # Out-of-process Rust engine (Fly / Compose). Empty = in-process PyO3.
    ENGINE_URL: str = ""
    ENGINE_API_TOKEN: str = ""
    ENGINE_TIMEOUT_SECONDS: float = 10.0

    # Rollbar — leave empty to disable locally
    ROLLBAR_ACCESS_TOKEN: str = ""

    # Unsupervised ML PoC (LSTM-Autoencoder + pgvector). Requires: uv sync --group ml
    ML_SEQ_LEN: int = 16
    ML_LATENT_DIM: int = 16
    ML_HIDDEN_DIM: int = 32
    ML_EPOCHS: int = 40
    ML_ANOMALY_THRESHOLD: float = 0.15
    ML_MODEL_DIR: str = "data/models"
    ML_MODEL_VERSION: str = "lstm-ae-v1"

    @model_validator(mode="after")
    def _secure_production_defaults(self) -> Settings:
        if self.ENVIRONMENT.lower() in {"production", "prod"} and self.DEBUG:
            # Prefer explicit DEBUG=false in prod; coerce if someone left the example default.
            object.__setattr__(self, "DEBUG", False)
        return self


settings = Settings()
