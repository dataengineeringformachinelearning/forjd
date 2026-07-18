//! Horizontally scalable transactional-outbox relay → Dragonfly Streams.

use std::time::Duration;

use futures::{stream, StreamExt};
use redis::Client;
use serde_json::{Map, Value};
use sqlx::{postgres::PgListener, PgPool};
use tracing::{error, info, warn};
use uuid::Uuid;

use crate::data_plane::{bus, config::Config, db};

pub async fn run(pool: PgPool, client: Client, cfg: Config) -> anyhow::Result<()> {
    let owner = Uuid::new_v4();
    let mut listener = match PgListener::connect(&cfg.database_url).await {
        Ok(mut listener) => {
            listener.listen("forjd_outbox").await?;
            Some(listener)
        }
        Err(error) => {
            warn!(%error, "outbox_relay: LISTEN unavailable; using bounded polling");
            None
        }
    };
    info!(%owner, "outbox_relay: started (Postgres outbox → Dragonfly Streams)");

    loop {
        match tick(&pool, &client, &cfg, owner).await {
            Ok(0) => {}
            Ok(n) => info!(published = n, "outbox_relay: batch published"),
            Err(error) => error!(%error, "outbox_relay: tick failed"),
        }
        let poll_interval = Duration::from_secs(cfg.poll_interval_secs);
        let mut disable_listener = false;
        if let Some(active_listener) = listener.as_mut() {
            match tokio::time::timeout(poll_interval, active_listener.recv()).await {
                Ok(Ok(_)) | Err(_) => {}
                Ok(Err(error)) => {
                    warn!(%error, "outbox_relay: LISTEN failed; reverting to polling");
                    disable_listener = true;
                }
            }
        } else {
            tokio::time::sleep(poll_interval).await;
        }
        if disable_listener {
            listener = None;
        }
    }
}

#[tracing::instrument(name = "outbox_relay_tick", skip_all, fields(owner = %owner))]
async fn tick(pool: &PgPool, client: &Client, cfg: &Config, owner: Uuid) -> anyhow::Result<usize> {
    let events = db::claim_pending(pool, owner, cfg.batch_size, cfg.max_attempts).await?;
    let max_attempts = cfg.max_attempts;

    let results = stream::iter(events.into_iter().map(|event| {
        let pool = pool.clone();
        let client = client.clone();
        async move {
            let event_id = event.id;
            let topic = event.topic.clone();
            let mut header_map = event.headers.as_object().cloned().unwrap_or_else(Map::new);
            header_map.insert(
                "x-forjd-event-id".to_string(),
                Value::String(event_id.to_string()),
            );
            if let Some(idempotency_key) = &event.idempotency_key {
                header_map.insert(
                    "x-forjd-idempotency-key".to_string(),
                    Value::String(idempotency_key.clone()),
                );
            }
            let headers = Value::Object(header_map);

            let outcome = async {
                let mut conn = bus::connect(&client).await?;
                let payload = serde_json::to_vec(&event.payload)?;
                bus::publish(&mut conn, &topic, event.key.as_deref(), &payload, &headers).await?;
                anyhow::Ok(())
            }
            .await;

            match outcome {
                Ok(()) => match db::mark_published(&pool, owner, event_id).await {
                    Ok(true) => true,
                    Ok(false) => {
                        warn!(%event_id, "outbox_relay: lease expired before completion update");
                        false
                    }
                    Err(error) => {
                        error!(%event_id, %error, "outbox_relay: completion update failed");
                        false
                    }
                },
                Err(error) => {
                    let message = error.to_string();
                    warn!(%event_id, %topic, %message, "outbox_relay: publish failed");
                    if let Err(db_error) =
                        db::record_failure(&pool, owner, event_id, &message, max_attempts).await
                    {
                        error!(%event_id, %db_error, "outbox_relay: failure update failed");
                    }
                    false
                }
            }
        }
    }))
    .buffer_unordered(cfg.max_concurrency)
    .collect::<Vec<bool>>()
    .await;

    Ok(results.into_iter().filter(|published| *published).count())
}
