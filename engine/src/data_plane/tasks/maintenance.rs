//! Postgres maintenance for FORJD data-plane tables.

use anyhow::{Context, Result};
use chrono::Utc;
use sqlx::PgPool;
use tracing::info;

const OUTBOX_PUBLISHED_RETENTION_DAYS: i64 = 30;
const OUTBOX_DLQ_RETENTION_DAYS: i64 = 7;
const OBSERVATION_RETENTION_DAYS: i64 = 30;
const SCHEDULED_TASK_RETENTION_DAYS: i64 = 90;
const RECEIPT_RETENTION_DAYS: i64 = 30;

const ANALYZE_TABLES: &[&str] = &[
    "outbox_events",
    "scheduled_task_runs",
    "telemetry_ingest_receipts",
    "endpoint_observations",
    "health_probe_observations",
    "telemetry_events",
    "stream_results",
    "projection_checkpoints",
    "projection_dlq",
    "status_services",
];

// --- Retention cleanup ---
#[tracing::instrument(name = "db_cleanup", skip_all)]
pub async fn run_db_cleanup(pool: &PgPool) -> Result<()> {
    let outbox_cutoff = Utc::now() - chrono::Duration::days(OUTBOX_PUBLISHED_RETENTION_DAYS);
    let outbox_dlq_cutoff = Utc::now() - chrono::Duration::days(OUTBOX_DLQ_RETENTION_DAYS);
    let observation_cutoff = Utc::now() - chrono::Duration::days(OBSERVATION_RETENTION_DAYS);
    let scheduled_cutoff = Utc::now() - chrono::Duration::days(SCHEDULED_TASK_RETENTION_DAYS);
    let receipt_cutoff = Utc::now() - chrono::Duration::days(RECEIPT_RETENTION_DAYS);

    let outbox_published =
        sqlx::query("DELETE FROM outbox_events WHERE is_published = true AND published_at < $1")
            .bind(outbox_cutoff)
            .execute(pool)
            .await
            .context("failed to delete published outbox events")?
            .rows_affected();

    let outbox_dlq =
        sqlx::query("DELETE FROM outbox_events WHERE dlq_at IS NOT NULL AND dlq_at < $1")
            .bind(outbox_dlq_cutoff)
            .execute(pool)
            .await
            .context("failed to delete DLQ outbox events")?
            .rows_affected();

    let endpoints = sqlx::query("DELETE FROM endpoint_observations WHERE observed_at < $1")
        .bind(observation_cutoff)
        .execute(pool)
        .await
        .context("failed to delete old endpoint observations")?
        .rows_affected();

    let probes = sqlx::query("DELETE FROM health_probe_observations WHERE observed_at < $1")
        .bind(observation_cutoff)
        .execute(pool)
        .await
        .context("failed to delete old probe observations")?
        .rows_affected();

    let receipts = sqlx::query("DELETE FROM telemetry_ingest_receipts WHERE processed_at < $1")
        .bind(receipt_cutoff)
        .execute(pool)
        .await
        .context("failed to delete old ingest receipts")?
        .rows_affected();

    let scheduled = sqlx::query(
        r#"
        DELETE FROM scheduled_task_runs
        WHERE state IN ('completed', 'failed')
          AND COALESCE(completed_at, updated_at) < $1
        "#,
    )
    .bind(scheduled_cutoff)
    .execute(pool)
    .await
    .context("failed to delete old scheduled task runs")?
    .rows_affected();

    let dlq = sqlx::query(
        "DELETE FROM projection_dlq WHERE resolved_at IS NOT NULL AND resolved_at < $1",
    )
    .bind(observation_cutoff)
    .execute(pool)
    .await
    .context("failed to delete resolved projection DLQ rows")?
    .rows_affected();

    info!(
        outbox_published,
        outbox_dlq, endpoints, probes, receipts, scheduled, dlq, "db_cleanup: completed"
    );
    Ok(())
}

// --- ANALYZE hot tables ---
#[tracing::instrument(name = "optimize_database", skip_all)]
pub async fn run_optimize_database(pool: &PgPool) -> Result<()> {
    for table in ANALYZE_TABLES {
        let statement = format!("ANALYZE {table}");
        if let Err(error) = sqlx::query(&statement).execute(pool).await {
            tracing::warn!(table, %error, "optimize_database: ANALYZE skipped");
        }
    }
    info!(
        tables = ANALYZE_TABLES.len(),
        "optimize_database: completed"
    );
    Ok(())
}
