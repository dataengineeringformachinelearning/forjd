//! Unified data plane — outbox relay, ingest edge, probes, normalizer, scheduler.
//!
//! Compiled into `forjd-engine` behind `--features data-plane`. Select work with
//! `FORJD_ROLE` (unset/`engine`/`none` = process HTTP only; `all` = full plane).

pub mod bus;
pub mod config;
pub mod cpe;
pub mod db;
pub mod http;
pub mod internode;
pub mod tasks;

pub use config::{Config, Role};
pub use http::{DataPlaneState, build_data_plane_router, build_state};

use anyhow::{Context, Result, bail};
use sqlx::postgres::PgPoolOptions;
use tokio::task::JoinSet;
use tracing::{error, info};

// --- Spawn role-selected background tasks (caller owns the HTTP server) ---
pub async fn spawn_background(
    cfg: Config,
) -> Result<(JoinSet<(&'static str, Result<()>)>, Option<sqlx::PgPool>)> {
    if !cfg.role.is_active() {
        return Ok((JoinSet::new(), None));
    }

    if cfg.role.needs_bus() {
        internode::validate_configuration().context(
            "bus roles (relay/scheduler/normalizer/all) on Fly require \
             FORJD_INTERNODE_ENCRYPTION=required, FORJD_INTERNODE_ACTIVE_KID, and \
             FORJD_INTERNODE_KEYS as JSON {\"kid\":\"<base64url-32-bytes>\"} — \
             run ./scripts/sync_engine_dataplane_secrets.sh",
        )?;
    }

    let pool_options = PgPoolOptions::new()
        .min_connections(1)
        .max_connections(20)
        .acquire_timeout(std::time::Duration::from_secs(10));
    let pool = if cfg.role == Role::Cpe {
        pool_options
            .connect_lazy(&cfg.database_url)
            .context("invalid DATABASE_URL for CPE role")?
    } else {
        pool_options
            .connect(&cfg.database_url)
            .await
            .context("forjd-engine data plane could not connect to Postgres")?
    };

    let mut tasks: JoinSet<(&'static str, Result<()>)> = JoinSet::new();

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

    info!(role = ?cfg.role, "data plane: background tasks running");
    Ok((tasks, Some(pool)))
}

/// Watch background tasks; return on first unexpected exit (caller shuts down HTTP).
pub async fn supervise(mut tasks: JoinSet<(&'static str, Result<()>)>) -> Result<()> {
    if tasks.is_empty() {
        // No background work — park until cancelled by the HTTP server shutdown.
        std::future::pending::<()>().await;
        return Ok(());
    }
    match tasks.join_next().await {
        Some(Ok((name, Ok(())))) => bail!("critical task {name} exited unexpectedly"),
        Some(Ok((name, Err(task_error)))) => {
            error!(task = name, error = %task_error, "critical task failed");
            Err(task_error).with_context(|| format!("critical task {name} failed"))
        }
        Some(Err(join_error)) => Err(join_error).context("critical task panicked"),
        None => Ok(()),
    }
}
