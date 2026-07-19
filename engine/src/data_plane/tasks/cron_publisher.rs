//! Durable, replica-safe scheduler for FORJD.
//!
//! Rust-native tasks run in-process. Other tasks publish triggers onto the
//! Dragonfly `internal-tasks` stream (Prefect/Python workers can consume later).

use std::time::Duration;

use anyhow::{Context, Result, bail};
use chrono::{DateTime, Utc};
use redis::Client;
use serde::Serialize;
use sqlx::PgPool;
use tracing::{error, info, warn};
use uuid::Uuid;

use crate::data_plane::bus;
use crate::data_plane::tasks::maintenance;

const RUST_NATIVE_TASKS: &[&str] = &["db_cleanup", "optimize_database"];
const MAX_TASK_ATTEMPTS: i32 = 5;
const HOUR: i64 = 3_600;
const DAY: i64 = 86_400;

struct CronTask {
    name: &'static str,
    interval_seconds: i64,
    offset_seconds: i64,
}

const CRON_TASKS: &[CronTask] = &[
    CronTask {
        name: "forjd_projection_tick",
        interval_seconds: HOUR,
        offset_seconds: 120,
    },
    CronTask {
        name: "forjd_ingest_reconcile",
        interval_seconds: HOUR,
        offset_seconds: 300,
    },
    CronTask {
        name: "db_cleanup",
        interval_seconds: DAY,
        offset_seconds: 10_800,
    },
    CronTask {
        name: "optimize_database",
        interval_seconds: DAY,
        offset_seconds: 14_400,
    },
];

#[derive(Debug, sqlx::FromRow)]
struct ScheduledRun {
    id: Uuid,
    task_name: String,
    scheduled_for: DateTime<Utc>,
    state: String,
}

#[derive(Debug, Serialize)]
struct TaskTrigger<'a> {
    run_id: Uuid,
    task: &'a str,
    scheduled_for: String,
    triggered_at: String,
    source: &'static str,
}

pub async fn run(pool: PgPool, client: Client) -> Result<()> {
    let owner = Uuid::new_v4();
    info!(%owner, tasks = CRON_TASKS.len(), "scheduler: started (Dragonfly bus)");

    loop {
        if let Err(error) = ensure_current_buckets(&pool).await {
            error!(%error, "scheduler: failed to materialize time buckets");
        }
        for _ in 0..20 {
            match claim_runs(&pool, owner, 1).await {
                Ok(runs) if runs.is_empty() => break,
                Ok(runs) => {
                    for run in runs {
                        execute_run(&pool, &client, owner, run).await;
                    }
                }
                Err(error) => {
                    error!(%error, "scheduler: failed to claim run");
                    break;
                }
            }
        }
        tokio::time::sleep(Duration::from_secs(15)).await;
    }
}

async fn ensure_current_buckets(pool: &PgPool) -> Result<()> {
    let now = Utc::now().timestamp();
    for task in CRON_TASKS {
        let scheduled_for = scheduled_for_timestamp(task, now)?;
        sqlx::query(
            r#"
            INSERT INTO scheduled_task_runs
                (id, task_name, scheduled_for, state, attempts, last_error, created_at, updated_at)
            VALUES ($1, $2, $3, 'pending', 0, '', NOW(), NOW())
            ON CONFLICT (task_name, scheduled_for) DO NOTHING
            "#,
        )
        .bind(Uuid::new_v4())
        .bind(task.name)
        .bind(scheduled_for)
        .execute(pool)
        .await?;
    }
    Ok(())
}

fn scheduled_for_timestamp(task: &CronTask, now: i64) -> Result<DateTime<Utc>> {
    let bucket = (now - task.offset_seconds).div_euclid(task.interval_seconds)
        * task.interval_seconds
        + task.offset_seconds;
    DateTime::<Utc>::from_timestamp(bucket, 0).context("scheduler produced an invalid UTC bucket")
}

async fn claim_runs(pool: &PgPool, owner: Uuid, limit: i64) -> Result<Vec<ScheduledRun>> {
    Ok(sqlx::query_as::<_, ScheduledRun>(
        r#"
        WITH candidates AS (
            SELECT id
            FROM scheduled_task_runs
            WHERE (
                    (state IN ('pending', 'failed') AND attempts < $3)
                    OR state = 'published'
                    OR (state = 'running' AND lease_expires_at < NOW() AND attempts < $3)
                  )
              AND scheduled_for <= NOW()
              AND (lease_expires_at IS NULL OR lease_expires_at < NOW())
            ORDER BY scheduled_for, task_name
            FOR UPDATE SKIP LOCKED
            LIMIT $2
        )
        UPDATE scheduled_task_runs AS run
        SET claimed_by = $1,
            lease_expires_at = NOW() + INTERVAL '60 seconds',
            updated_at = NOW()
        FROM candidates
        WHERE run.id = candidates.id
        RETURNING run.id, run.task_name, run.scheduled_for, run.state
        "#,
    )
    .bind(owner)
    .bind(limit)
    .bind(MAX_TASK_ATTEMPTS)
    .fetch_all(pool)
    .await?)
}

#[tracing::instrument(
    name = "execute_or_publish_scheduled_run",
    skip_all,
    fields(run_id = %run.id, task = %run.task_name)
)]
async fn execute_run(pool: &PgPool, client: &Client, owner: Uuid, run: ScheduledRun) {
    if RUST_NATIVE_TASKS.contains(&run.task_name.as_str()) {
        match execute_native_with_heartbeat(pool, owner, &run).await {
            Ok(()) => {
                if let Err(error) = mark_completed(pool, owner, &run).await {
                    error!(run_id = %run.id, %error, "scheduler: native completion update failed");
                } else {
                    info!(run_id = %run.id, task = %run.task_name, "scheduler: native task completed");
                }
            }
            Err(error) => {
                warn!(run_id = %run.id, task = %run.task_name, %error, "scheduler: native task failed");
                let _ = mark_failed(pool, owner, &run, &error.to_string()).await;
            }
        }
        return;
    }

    let trigger = TaskTrigger {
        run_id: run.id,
        task: &run.task_name,
        scheduled_for: run.scheduled_for.to_rfc3339(),
        triggered_at: Utc::now().to_rfc3339(),
        source: "forjd-engine:scheduler",
    };
    let result = async {
        let mut conn = bus::connect(client).await?;
        let payload = serde_json::to_vec(&trigger)?;
        let headers = serde_json::json!({
            "x-forjd-task": run.task_name,
            "x-forjd-run-id": run.id.to_string(),
        });
        bus::publish(
            &mut conn,
            "internal-tasks",
            Some(&run.task_name),
            &payload,
            &headers,
        )
        .await
    }
    .await;

    match result {
        Ok(_) => {
            match sqlx::query(
                r#"
                UPDATE scheduled_task_runs
                SET state = 'published',
                    attempts = attempts + CASE WHEN state = 'published' THEN 0 ELSE 1 END,
                    last_error = '', claimed_by = NULL,
                    lease_expires_at = NOW() + INTERVAL '5 minutes', updated_at = NOW()
                WHERE id = $1 AND claimed_by = $2 AND state = $3
                "#,
            )
            .bind(run.id)
            .bind(owner)
            .bind(&run.state)
            .execute(pool)
            .await
            {
                Ok(result) if result.rows_affected() == 1 => {
                    info!(run_id = %run.id, task = %run.task_name, "scheduler: trigger published");
                }
                Ok(_) => {
                    error!(run_id = %run.id, "scheduler: publish acknowledgement lost lease");
                }
                Err(error) => {
                    error!(run_id = %run.id, %error, "scheduler: completion update failed");
                }
            }
        }
        Err(error) => {
            warn!(run_id = %run.id, task = %run.task_name, %error, "scheduler: publish failed");
            let _ = mark_failed(pool, owner, &run, &error.to_string()).await;
        }
    }
}

async fn mark_completed(pool: &PgPool, owner: Uuid, run: &ScheduledRun) -> Result<()> {
    let result = sqlx::query(
        r#"
        UPDATE scheduled_task_runs
        SET state = 'completed', attempts = attempts + 1,
            last_error = '', completed_at = NOW(),
            claimed_by = NULL, lease_expires_at = NULL, updated_at = NOW()
        WHERE id = $1 AND claimed_by = $2 AND state = $3
        "#,
    )
    .bind(run.id)
    .bind(owner)
    .bind(&run.state)
    .execute(pool)
    .await?;
    if result.rows_affected() != 1 {
        bail!("native completion lost lease ownership");
    }
    Ok(())
}

async fn mark_failed(pool: &PgPool, owner: Uuid, run: &ScheduledRun, error: &str) -> Result<()> {
    sqlx::query(
        r#"
        UPDATE scheduled_task_runs
        SET state = 'failed', attempts = attempts + 1, last_error = $3,
            claimed_by = NULL,
            lease_expires_at = NOW() + INTERVAL '15 minutes',
            updated_at = NOW()
        WHERE id = $1 AND claimed_by = $2 AND state = $4
        "#,
    )
    .bind(run.id)
    .bind(owner)
    .bind(error)
    .bind(&run.state)
    .execute(pool)
    .await?;
    Ok(())
}

async fn execute_native_with_heartbeat(
    pool: &PgPool,
    owner: Uuid,
    run: &ScheduledRun,
) -> Result<()> {
    extend_native_lease(pool, owner, run).await?;
    let execution = execute_native_task(pool, &run.task_name);
    tokio::pin!(execution);
    let mut heartbeat = tokio::time::interval(Duration::from_secs(300));
    heartbeat.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    heartbeat.tick().await;

    loop {
        tokio::select! {
            result = &mut execution => return result,
            _ = heartbeat.tick() => extend_native_lease(pool, owner, run).await?,
        }
    }
}

async fn extend_native_lease(pool: &PgPool, owner: Uuid, run: &ScheduledRun) -> Result<()> {
    let result = sqlx::query(
        r#"
        UPDATE scheduled_task_runs
        SET lease_expires_at = NOW() + INTERVAL '30 minutes', updated_at = NOW()
        WHERE id = $1 AND claimed_by = $2 AND state = $3
        "#,
    )
    .bind(run.id)
    .bind(owner)
    .bind(&run.state)
    .execute(pool)
    .await
    .context("failed to extend native task lease")?;
    if result.rows_affected() != 1 {
        bail!("native task lease is no longer owned by this scheduler");
    }
    Ok(())
}

async fn execute_native_task(pool: &PgPool, task_name: &str) -> Result<()> {
    match task_name {
        "db_cleanup" => maintenance::run_db_cleanup(pool).await,
        "optimize_database" => maintenance::run_optimize_database(pool).await,
        _ => bail!("unknown native task: {task_name}"),
    }
}

#[cfg(test)]
mod tests {
    use super::{CRON_TASKS, CronTask, HOUR, TaskTrigger, scheduled_for_timestamp};
    use chrono::{DateTime, Utc};
    use uuid::Uuid;

    #[test]
    fn materializes_offset_utc_bucket() {
        let task = CRON_TASKS
            .iter()
            .find(|task| task.name == "forjd_projection_tick")
            .expect("projection tick task");
        let now = DateTime::parse_from_rfc3339("2026-07-15T16:42:00Z")
            .expect("timestamp should parse")
            .timestamp();
        let scheduled = scheduled_for_timestamp(task, now).expect("bucket");
        assert_eq!(scheduled.to_rfc3339(), "2026-07-15T16:02:00+00:00");
        assert_eq!(task.interval_seconds, HOUR);
    }

    #[test]
    fn trigger_serializes_for_bus_workers() {
        let scheduled_for = DateTime::<Utc>::from_timestamp(1_773_590_700, 0)
            .expect("timestamp")
            .to_rfc3339();
        let trigger = TaskTrigger {
            run_id: Uuid::nil(),
            task: "forjd_projection_tick",
            scheduled_for: scheduled_for.clone(),
            triggered_at: "2026-07-15T16:05:01+00:00".to_owned(),
            source: "forjd-engine:scheduler",
        };
        let payload = serde_json::to_value(trigger).expect("serialize");
        assert_eq!(payload["scheduled_for"], scheduled_for);
        assert_eq!(payload["task"], "forjd_projection_tick");
    }

    #[test]
    fn cron_task_struct_is_constructible() {
        let _ = CronTask {
            name: "x",
            interval_seconds: 1,
            offset_seconds: 0,
        };
    }
}
