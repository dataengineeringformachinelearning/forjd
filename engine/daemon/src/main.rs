//! FORJD data-plane daemon — role-selected background services.
//! Migrated from DEML `rust/deml-daemon`; bus is Dragonfly Streams (no Redpanda).

use anyhow::{bail, Context, Result};
use opentelemetry::trace::TracerProvider as _;
use opentelemetry_otlp::WithExportConfig;
use opentelemetry_sdk::trace::SdkTracerProvider;
use sqlx::postgres::PgPoolOptions;
use tokio::task::JoinSet;
use tracing::{error, info};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

// --- Modules ---
mod bus;
mod config;
mod db;
mod http_server;
mod internode;
mod tasks;

use config::Role;

#[tokio::main]
async fn main() -> Result<()> {
    // --- Crypto provider (rustls) ---
    rustls::crypto::ring::default_provider()
        .install_default()
        .map_err(|_| anyhow::anyhow!("failed to install the rustls ring crypto provider"))?;

    // --- Config + internode keyring ---
    let cfg = config::Config::from_env()?;
    if cfg.role.needs_bus() {
        internode::validate_configuration()?;
    }
    let tracer_provider = init_tracing(&cfg)?;
    info!(version = env!("CARGO_PKG_VERSION"), role = ?cfg.role, "forjd-daemon: starting");

    // --- Postgres pool (lazy for CPE-only) ---
    let pool_options = PgPoolOptions::new()
        .min_connections(1)
        .max_connections(20)
        .acquire_timeout(std::time::Duration::from_secs(10));
    let pool = if cfg.role == Role::Cpe {
        pool_options
            .connect_lazy(&cfg.database_url)
            .context("forjd-cpe received an invalid DATABASE_URL")?
    } else {
        pool_options
            .connect(&cfg.database_url)
            .await
            .context("forjd-daemon could not connect to Postgres")?
    };

    // --- Role-selected background tasks ---
    let mut tasks: JoinSet<(&'static str, Result<()>)> = JoinSet::new();
    {
        let pool = pool.clone();
        let cfg = cfg.clone();
        let enable_ingest = cfg.role.runs(Role::Ingest);
        let enable_cpe = cfg.role.runs(Role::Cpe);
        tasks.spawn(async move {
            (
                "http",
                http_server::run(pool, cfg, enable_ingest, enable_cpe).await,
            )
        });
    }
    if cfg.role.runs(Role::Relay) {
        let client = bus::build_client(&cfg)?;
        let pool = pool.clone();
        let cfg = cfg.clone();
        tasks.spawn(async move { ("relay", tasks::outbox_relay::run(pool, client, cfg).await) });
    }
    if cfg.role.runs(Role::Scheduler) {
        let client = bus::build_client(&cfg)?;
        let pool = pool.clone();
        tasks.spawn(async move { ("scheduler", tasks::cron_publisher::run(pool, client).await) });
    }
    if cfg.role.runs(Role::Probe) {
        let pool = pool.clone();
        let cfg = cfg.clone();
        tasks.spawn(async move { ("probe", tasks::health_pinger::run(pool, cfg).await) });
    }
    if cfg.role.runs(Role::Normalizer) {
        let client = bus::build_client(&cfg)?;
        let pool = pool.clone();
        let cfg = cfg.clone();
        tasks.spawn(async move {
            (
                "normalizer",
                tasks::normalizer::run(pool, client, cfg).await,
            )
        });
    }

    info!(role = ?cfg.role, "forjd-daemon: selected tasks running");

    // --- Shutdown: Ctrl-C or first critical task failure ---
    let outcome = tokio::select! {
        signal = tokio::signal::ctrl_c() => {
            signal.context("failed to register shutdown signal")?;
            info!("forjd-daemon: shutdown requested");
            tasks.abort_all();
            while tasks.join_next().await.is_some() {}
            pool.close().await;
            Ok(())
        }
        completed = tasks.join_next() => {
            match completed {
                Some(Ok((name, Ok(())))) => bail!("critical task {name} exited unexpectedly"),
                Some(Ok((name, Err(task_error)))) => {
                    error!(task = name, error = %task_error, "critical task failed");
                    Err(task_error).with_context(|| format!("critical task {name} failed"))
                }
                Some(Err(join_error)) => Err(join_error).context("critical task panicked"),
                None => bail!("forjd-daemon started no tasks"),
            }
        }
    };
    if let Some(provider) = tracer_provider {
        if let Err(error) = provider.shutdown() {
            eprintln!("OpenTelemetry shutdown failed: {error}");
        }
    }
    outcome
}

// --- Tracing + optional OTLP ---
fn init_tracing(cfg: &config::Config) -> Result<Option<SdkTracerProvider>> {
    let filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new("forjd_daemon=info,warn"));
    let endpoint = std::env::var("OTEL_EXPORTER_OTLP_ENDPOINT")
        .ok()
        .filter(|value| !value.trim().is_empty());
    let provider = if let Some(endpoint) = endpoint {
        let exporter = opentelemetry_otlp::SpanExporter::builder()
            .with_http()
            .with_endpoint(endpoint)
            .build()
            .context("failed to build OTLP span exporter")?;
        let service_name = std::env::var("OTEL_SERVICE_NAME")
            .unwrap_or_else(|_| format!("forjd-{:?}", cfg.role).to_ascii_lowercase());
        let resource = opentelemetry_sdk::Resource::builder()
            .with_service_name(service_name)
            .build();
        let provider = SdkTracerProvider::builder()
            .with_resource(resource)
            .with_batch_exporter(exporter)
            .build();
        if cfg.structured_logs {
            let telemetry =
                tracing_opentelemetry::layer().with_tracer(provider.tracer("forjd-rust-data-plane"));
            tracing_subscriber::registry()
                .with(filter)
                .with(
                    tracing_subscriber::fmt::layer()
                        .json()
                        .with_current_span(false),
                )
                .with(telemetry)
                .init();
        } else {
            let telemetry =
                tracing_opentelemetry::layer().with_tracer(provider.tracer("forjd-rust-data-plane"));
            tracing_subscriber::registry()
                .with(filter)
                .with(tracing_subscriber::fmt::layer())
                .with(telemetry)
                .init();
        }
        Some(provider)
    } else if cfg.structured_logs {
        tracing_subscriber::registry()
            .with(filter)
            .with(
                tracing_subscriber::fmt::layer()
                    .json()
                    .with_current_span(false),
            )
            .init();
        None
    } else {
        tracing_subscriber::registry()
            .with(filter)
            .with(tracing_subscriber::fmt::layer())
            .init();
        None
    };
    Ok(provider)
}
