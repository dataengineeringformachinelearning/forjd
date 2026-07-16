# --- build Rust engine wheel + Python deps ---
# Keep the project at /app so uv venv shebangs match the runtime image.
# 3.12 — Pathway (beartype pin) does not import on CPython 3.14 yet.
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

# Rust toolchain for maturin / forjd-engine (PyO3) — pin to match engine/rust-toolchain.toml
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential pkg-config \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain 1.97.0 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:$PATH" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

# Layout mirrors the repo: /app = backend, /engine = engine (pyproject path = ../engine).
COPY engine/ /engine/
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/README.md /app/

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    uv sync --locked --no-install-project

COPY backend/ /app/

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    uv sync --locked --no-editable

# --- runtime: slim image, non-root, no uv/rust ---
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv

WORKDIR /app

RUN groupadd --gid 1001 forjd \
    && useradd --uid 1001 --gid 1001 --shell /usr/sbin/nologin --create-home forjd

COPY --from=builder --chown=1001:1001 /app /app

USER 1001

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
