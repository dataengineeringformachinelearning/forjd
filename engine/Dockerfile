# Multi-stage FORJD engine — process/summarize + unified data plane
#
# Build from engine/:
#   docker build -t forjd-engine .
# Or from repo root:
#   docker build -f engine/Dockerfile -t forjd-engine engine/

# --- build ---
FROM rust:1.97.0-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

COPY Cargo.toml Cargo.lock ./
COPY src ./src

RUN cargo build --release --locked --no-default-features --features server,data-plane --bin forjd-engine \
    && strip /src/target/release/forjd-engine

# --- runtime: slim, non-root ---
FROM debian:bookworm-slim AS runtime

RUN groupadd --gid 1001 forjd \
    && useradd --uid 1001 --gid 1001 --shell /usr/sbin/nologin --create-home forjd \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libssl3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/target/release/forjd-engine /usr/local/bin/forjd-engine

USER 1001

# Default process-only; enable data plane via fly secrets / sync script (FORJD_ROLE=all).
ENV PORT=8080 \
    RUST_LOG=info \
    RUST_BACKTRACE=0 \
    FORJD_ROLE=engine

EXPOSE 8080

CMD ["forjd-engine"]
