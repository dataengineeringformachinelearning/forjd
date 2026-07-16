# --- build Rust engine wheel + Python deps ---
FROM python:3.14-slim-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

# Rust toolchain for maturin / forjd-engine (PyO3)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential pkg-config \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:$PATH" \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

WORKDIR /src

# Engine first so Docker can cache the Rust layer when only Python app changes.
COPY engine/ /src/engine/
COPY backend/pyproject.toml backend/uv.lock backend/README.md /src/backend/

WORKDIR /src/backend

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    uv sync --locked --no-install-project

COPY backend/ /src/backend/

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cargo/registry \
    --mount=type=cache,target=/root/.cargo/git \
    uv sync --locked --no-editable

# --- runtime: slim image, non-root, no uv/rust ---
FROM python:3.14-slim-trixie AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --gid 1001 forjd \
    && useradd --uid 1001 --gid 1001 --shell /usr/sbin/nologin --create-home forjd

COPY --from=builder --chown=1001:1001 /src/backend /app

USER 1001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
