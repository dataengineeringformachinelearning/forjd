# Multi-stage FORJD data-plane daemon (role-selected binary).
#
# Build from engine/daemon/:
#   docker build -t forjd-daemon .
# Or from repo root:
#   docker build -f engine/daemon/Dockerfile -t forjd-daemon engine/daemon/
#
# Runtime: set FORJD_ROLE=relay|scheduler|probe|normalizer|ingest|cpe|all
# Bus: REDIS_URL → Dragonfly Streams (no Redpanda/Kafka).

# --- build ---
FROM rust:1.97.0-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libssl-dev \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# --- Dependency cache layer ---
COPY Cargo.toml Cargo.lock* ./
RUN mkdir -p src \
    && echo 'fn main() {}' > src/main.rs \
    && cargo build --release \
    && rm -rf src \
    && rm -f target/release/forjd-daemon target/release/deps/forjd_daemon*

# --- Application build ---
COPY src ./src
RUN cargo build --release \
    && strip /build/target/release/forjd-daemon

# --- runtime: slim, non-root ---
FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1001 forjd \
    && useradd --uid 1001 --gid 1001 --shell /usr/sbin/nologin --create-home forjd

COPY --from=builder /build/target/release/forjd-daemon /usr/local/bin/forjd-daemon

USER 1001

ENV PORT=8080 \
    RUST_LOG=forjd_daemon=info,warn \
    RUST_BACKTRACE=0

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/forjd-daemon"]
