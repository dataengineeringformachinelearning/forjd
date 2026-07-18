//! Dragonfly Streams bus — FORJD internode messaging (Streams, not Kafka).

use anyhow::{bail, Context, Result};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use redis::aio::MultiplexedConnection;
use redis::streams::{StreamId, StreamKey, StreamReadOptions, StreamReadReply};
use redis::{AsyncCommands, Client, Value as RedisValue};
use serde_json::Value;
use std::collections::HashMap;

use crate::data_plane::{config::Config, internode};

/// Stream message claimed from a consumer group.
#[derive(Debug, Clone)]
pub struct BusMessage {
    pub stream: String,
    pub id: String,
    pub key: Option<String>,
    pub payload: Vec<u8>,
    #[allow(dead_code)] // reserved for consumer-side header routing
    pub headers: Value,
}

// --- Client factory ---
/// Shared Dragonfly connection factory for bus roles.
pub fn build_client(cfg: &Config) -> Result<Client> {
    let url = cfg
        .redis_url
        .as_deref()
        .context("REDIS_URL is required for Dragonfly bus roles")?;
    if let Some(root_cert) = cfg.redis_ssl_ca_pem.as_deref() {
        Client::build_with_tls(
            url,
            redis::TlsCertificates {
                client_tls: None,
                root_cert: Some(root_cert.to_vec()),
            },
        )
        .context("failed to build Dragonfly TLS client")
    } else {
        Client::open(url).context("failed to open Dragonfly client")
    }
}

pub async fn connect(client: &Client) -> Result<MultiplexedConnection> {
    client
        .get_multiplexed_async_connection()
        .await
        .context("failed to connect to Dragonfly")
}

/// Ensure a consumer group exists (idempotent).
pub async fn ensure_group(
    conn: &mut MultiplexedConnection,
    stream: &str,
    group: &str,
) -> Result<()> {
    let result: Result<String, redis::RedisError> = redis::cmd("XGROUP")
        .arg("CREATE")
        .arg(stream)
        .arg(group)
        .arg("0")
        .arg("MKSTREAM")
        .query_async(conn)
        .await;
    match result {
        Ok(_) => Ok(()),
        Err(error) if error.to_string().contains("BUSYGROUP") => Ok(()),
        Err(error) => Err(error).context("failed to create Dragonfly consumer group"),
    }
}

// --- Publish / consume ---
/// Publish one message to a Dragonfly stream (internode-encrypted payload).
pub async fn publish(
    conn: &mut MultiplexedConnection,
    stream: &str,
    key: Option<&str>,
    payload: &[u8],
    headers: &Value,
) -> Result<String> {
    let encrypted = internode::encrypt_bus_value(payload, stream)?;
    let encoded = STANDARD.encode(encrypted);
    let headers_json = serde_json::to_string(headers).context("headers must serialize")?;
    let id: String = redis::cmd("XADD")
        .arg(stream)
        .arg("*")
        .arg("payload")
        .arg(encoded)
        .arg("key")
        .arg(key.unwrap_or(""))
        .arg("headers")
        .arg(headers_json)
        .query_async(conn)
        .await
        .with_context(|| format!("Dragonfly XADD failed for stream {stream}"))?;
    Ok(id)
}

/// Read up to `count` new messages for a consumer group (blocking).
pub async fn read_group(
    conn: &mut MultiplexedConnection,
    stream: &str,
    group: &str,
    consumer: &str,
    count: usize,
    block_ms: usize,
) -> Result<Vec<BusMessage>> {
    let opts = StreamReadOptions::default()
        .group(group, consumer)
        .count(count)
        .block(block_ms);
    let reply: Option<StreamReadReply> = conn
        .xread_options(&[stream], &[">"], &opts)
        .await
        .context("Dragonfly XREADGROUP failed")?;
    let Some(reply) = reply else {
        return Ok(Vec::new());
    };
    let mut messages = Vec::new();
    for StreamKey { key, ids } in reply.keys {
        for StreamId { id, map } in ids {
            match decode_message(&key, &id, &map) {
                Ok(message) => messages.push(message),
                Err(error) => {
                    tracing::error!(stream = %key, id = %id, %error, "bus: skip undecodable message");
                }
            }
        }
    }
    Ok(messages)
}

/// Acknowledge a processed stream message.
pub async fn ack(
    conn: &mut MultiplexedConnection,
    stream: &str,
    group: &str,
    id: &str,
) -> Result<()> {
    let _: i64 = redis::cmd("XACK")
        .arg(stream)
        .arg(group)
        .arg(id)
        .query_async(conn)
        .await
        .context("Dragonfly XACK failed")?;
    Ok(())
}

fn redis_value_as_string(value: &RedisValue) -> Result<String> {
    match value {
        RedisValue::BulkString(bytes) => {
            String::from_utf8(bytes.clone()).context("stream field is not valid UTF-8")
        }
        RedisValue::SimpleString(status) => Ok(status.clone()),
        RedisValue::Okay => Ok("OK".into()),
        RedisValue::Int(n) => Ok(n.to_string()),
        RedisValue::Nil => Ok(String::new()),
        other => bail!("unsupported Redis stream field type: {other:?}"),
    }
}

fn decode_message(stream: &str, id: &str, map: &HashMap<String, RedisValue>) -> Result<BusMessage> {
    let encoded = map
        .get("payload")
        .context("stream message missing payload field")?;
    let encoded = redis_value_as_string(encoded)?;
    let raw = STANDARD
        .decode(&encoded)
        .unwrap_or_else(|_| encoded.into_bytes());
    let payload = internode::decrypt_bus_value(&raw, stream)?;
    let key = map
        .get("key")
        .and_then(|value| redis_value_as_string(value).ok())
        .filter(|value| !value.is_empty());
    let headers = map
        .get("headers")
        .and_then(|value| redis_value_as_string(value).ok())
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_else(|| Value::Object(Default::default()));
    Ok(BusMessage {
        stream: stream.to_string(),
        id: id.to_string(),
        key,
        payload,
        headers,
    })
}
