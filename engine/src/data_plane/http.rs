//! Data-plane HTTP routes (ingest edge + optional CPE) — merged into forjd-engine.

use std::collections::HashSet;
use std::sync::Arc;

use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, HeaderValue, StatusCode, header},
    response::{IntoResponse, Response},
    routing::post,
};
use base64::{Engine as _, engine::general_purpose::STANDARD};
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use sqlx::PgPool;
use subtle::ConstantTimeEq;
use uuid::Uuid;

use crate::data_plane::config::Config;
use crate::data_plane::cpe;

#[derive(Clone)]
pub struct DataPlaneState {
    pub pool: PgPool,
    pub redis: Option<redis::Client>,
    pub cpe_redis: Option<redis::Client>,
    pub cpe_only: bool,
}

#[derive(Debug, Deserialize)]
struct IngestPayload {
    batch_id: String,
    records: Vec<Value>,
}

struct AuthenticatedAccount {
    account_id: Uuid,
    rate_limit_rpm: i32,
}

#[derive(Debug)]
pub struct ApiError(pub StatusCode, pub String);

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        let mut response = (self.0, Json(json!({"detail": self.1}))).into_response();
        if self.0 == StatusCode::TOO_MANY_REQUESTS {
            response
                .headers_mut()
                .insert(header::RETRY_AFTER, HeaderValue::from_static("60"));
        }
        response
    }
}

// --- Build shared state for ingest / CPE routes ---
pub async fn build_state(pool: PgPool, cfg: &Config) -> anyhow::Result<Arc<DataPlaneState>> {
    let enable_ingest = cfg.role.enable_ingest();
    let enable_cpe = cfg.role.enable_cpe();
    let redis = build_redis_client(cfg.redis_url.as_deref(), cfg.redis_ssl_ca_pem.as_deref())?;
    if enable_ingest && redis.is_none() {
        anyhow::bail!("REDIS_URL is required when FORJD_ROLE enables ingest");
    }
    let cpe_redis = build_redis_client(
        cfg.cpe_redis_url.as_deref(),
        cfg.redis_ssl_ca_pem.as_deref(),
    )?;
    if enable_cpe && cpe_redis.is_none() {
        anyhow::bail!("CPE_REDIS_URL is required when FORJD_ROLE enables cpe");
    }
    Ok(Arc::new(DataPlaneState {
        pool,
        redis,
        cpe_redis,
        cpe_only: enable_cpe && !enable_ingest,
    }))
}

/// Routes mounted under the unified engine HTTP server (no /health — engine owns that).
pub fn build_data_plane_router(state: Arc<DataPlaneState>, cfg: &Config) -> Router {
    let mut router = Router::new();
    if cfg.role.enable_ingest() {
        router = router.route("/api/v1/ingest", post(ingest));
    }
    if cfg.role.enable_cpe() {
        router = router.route("/unique", post(cpe::cpe_unique));
    }
    router
        .layer(DefaultBodyLimit::max(2 * 1024 * 1024))
        .with_state(state)
}

/// Readiness probe for data-plane dependencies (Postgres / CPE index).
pub async fn data_plane_ready(state: &DataPlaneState) -> (StatusCode, Json<Value>) {
    if state.cpe_only {
        return cpe::ready_cpe(state).await;
    }
    let postgres = sqlx::query_scalar::<_, i32>("SELECT 1")
        .fetch_one(&state.pool)
        .await
        .is_ok();
    let redis = match state.redis.as_ref() {
        Some(client) => match client.get_multiplexed_async_connection().await {
            Ok(mut connection) => redis::cmd("PING")
                .query_async::<String>(&mut connection)
                .await
                .is_ok_and(|reply| reply == "PONG"),
            Err(_) => false,
        },
        None => false,
    };
    let ready = postgres && redis;
    (
        if ready {
            StatusCode::OK
        } else {
            StatusCode::SERVICE_UNAVAILABLE
        },
        Json(json!({
            "status": if ready { "ready" } else { "not_ready" },
            "checks": {"postgres": postgres, "redis": redis},
        })),
    )
}

fn build_redis_client(
    url: Option<&str>,
    root_cert: Option<&[u8]>,
) -> anyhow::Result<Option<redis::Client>> {
    let Some(url) = url else {
        return Ok(None);
    };
    let client = if let Some(root_cert) = root_cert {
        redis::Client::build_with_tls(
            url,
            redis::TlsCertificates {
                client_tls: None,
                root_cert: Some(root_cert.to_vec()),
            },
        )?
    } else {
        redis::Client::open(url)?
    };
    Ok(Some(client))
}

// --- Retired compatibility edge ---
// The old handler published `app-events`, for which this repository has no
// consumer. It must never claim acceptance. Authenticated callers receive a
// fail-closed migration response and use the canonical FastAPI sealed batch.
#[tracing::instrument(name = "rust_ingest", skip_all, fields(batch_id = %payload.batch_id))]
async fn ingest(
    State(state): State<Arc<DataPlaneState>>,
    headers: HeaderMap,
    Json(payload): Json<IngestPayload>,
) -> Result<Json<Value>, ApiError> {
    validate_payload(&payload)?;
    let account = authenticate(&state.pool, &headers).await?;
    enforce_rate_limit(&state, &account).await?;
    tracing::warn!(
        tenant_id = %account.account_id,
        records = payload.records.len(),
        "retired Rust compatibility ingest rejected; use canonical FastAPI batch"
    );
    Err(ApiError(
        StatusCode::GONE,
        "Rust compatibility ingest is retired; use POST /api/v1/ingest/events:batch on backend.forjd.co"
            .to_string(),
    ))
}

fn validate_payload(payload: &IngestPayload) -> Result<(), ApiError> {
    if payload.batch_id.len() < 8 || payload.batch_id.len() > 128 {
        return Err(ApiError(
            StatusCode::BAD_REQUEST,
            "batch_id must contain 8 to 128 characters".to_string(),
        ));
    }
    if !payload
        .batch_id
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b':'))
    {
        return Err(ApiError(
            StatusCode::BAD_REQUEST,
            "batch_id contains unsupported characters".to_string(),
        ));
    }
    if payload.records.is_empty() || payload.records.len() > 10_000 {
        return Err(ApiError(
            StatusCode::BAD_REQUEST,
            "records must contain between 1 and 10000 items".to_string(),
        ));
    }
    let mut nonces = HashSet::new();
    for record in &payload.records {
        let Some(obj) = record.as_object() else {
            return Err(ApiError(
                StatusCode::BAD_REQUEST,
                "every record must be a JSON object".to_string(),
            ));
        };
        // E2EE policy: daemon ingest accepts sealed envelopes only (no plaintext).
        for forbidden in ["plaintext", "password", "private_key", "secret"] {
            if obj.contains_key(forbidden) {
                return Err(ApiError(
                    StatusCode::BAD_REQUEST,
                    format!("record must not contain {forbidden} (ciphertext-only ingest)"),
                ));
            }
        }
        let cipher = obj
            .get("ciphertext")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty());
        let nonce = obj
            .get("nonce")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty());
        let key_id = obj
            .get("key_id")
            .and_then(|v| v.as_str())
            .filter(|s| !s.is_empty());
        let (Some(cipher), Some(nonce), Some(key_id)) = (cipher, nonce, key_id) else {
            return Err(ApiError(
                StatusCode::BAD_REQUEST,
                "each record requires ciphertext, nonce, and key_id (E2EE envelope)".to_string(),
            ));
        };
        if key_id.len() > 256 || key_id.chars().any(char::is_whitespace) {
            return Err(ApiError(
                StatusCode::BAD_REQUEST,
                "key_id must be a non-whitespace token of at most 256 characters".to_string(),
            ));
        }
        if obj
            .get("algo")
            .and_then(Value::as_str)
            .is_some_and(|algo| algo != "aes-256-gcm")
        {
            return Err(ApiError(
                StatusCode::BAD_REQUEST,
                "only aes-256-gcm envelopes are accepted".to_string(),
            ));
        }
        let nonce_bytes = STANDARD.decode(nonce).map_err(|_| {
            ApiError(
                StatusCode::BAD_REQUEST,
                "nonce must be standard base64".to_string(),
            )
        })?;
        if nonce_bytes.len() != 12 {
            return Err(ApiError(
                StatusCode::BAD_REQUEST,
                "aes-256-gcm nonce must decode to 12 bytes".to_string(),
            ));
        }
        let ciphertext = STANDARD.decode(cipher).map_err(|_| {
            ApiError(
                StatusCode::BAD_REQUEST,
                "ciphertext must be standard base64".to_string(),
            )
        })?;
        if !(16..=786_432).contains(&ciphertext.len()) {
            return Err(ApiError(
                StatusCode::BAD_REQUEST,
                "ciphertext decoded size is outside the accepted range".to_string(),
            ));
        }
        if let Some(expected) = obj.get("ciphertext_sha256").and_then(Value::as_str) {
            let actual = hex::encode(Sha256::digest(&ciphertext));
            if expected.len() != 64 || expected.as_bytes().ct_eq(actual.as_bytes()).unwrap_u8() != 1
            {
                return Err(ApiError(
                    StatusCode::BAD_REQUEST,
                    "ciphertext_sha256 does not match ciphertext".to_string(),
                ));
            }
        }
        if !nonces.insert((key_id.to_string(), nonce_bytes)) {
            return Err(ApiError(
                StatusCode::CONFLICT,
                "nonce reuse within a key_id is forbidden".to_string(),
            ));
        }
    }
    Ok(())
}

async fn authenticate(
    pool: &PgPool,
    headers: &HeaderMap,
) -> Result<AuthenticatedAccount, ApiError> {
    let token = headers
        .get("authorization")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .or_else(|| {
            headers
                .get("x-api-key")
                .and_then(|value| value.to_str().ok())
        })
        .ok_or_else(|| ApiError(StatusCode::UNAUTHORIZED, "missing API key".to_string()))?;
    if token.len() < 16 {
        return Err(ApiError(
            StatusCode::UNAUTHORIZED,
            "invalid API key".to_string(),
        ));
    }
    let (prefix, service_principal) = credential_prefix(token)
        .ok_or_else(|| ApiError(StatusCode::UNAUTHORIZED, "invalid API key".to_string()))?;
    let presented_hash = hex::encode(Sha256::digest(token.as_bytes()));
    if service_principal {
        let row = sqlx::query_as::<_, (String, Uuid)>(
            r#"
            SELECT key_hash, tenant_id
            FROM service_accounts
            WHERE prefix = $1
              AND is_active = true
              AND revoked_at IS NULL
              AND ('ingest:write' = ANY(scopes) OR '*' = ANY(scopes))
            "#,
        )
        .bind(prefix)
        .fetch_optional(pool)
        .await
        .map_err(|_| {
            ApiError(
                StatusCode::SERVICE_UNAVAILABLE,
                "authentication unavailable".to_string(),
            )
        })?
        .ok_or_else(|| ApiError(StatusCode::UNAUTHORIZED, "invalid API key".to_string()))?;
        if row
            .0
            .as_bytes()
            .ct_eq(presented_hash.as_bytes())
            .unwrap_u8()
            != 1
        {
            return Err(ApiError(
                StatusCode::UNAUTHORIZED,
                "invalid API key".to_string(),
            ));
        }
        return Ok(AuthenticatedAccount {
            account_id: row.1,
            rate_limit_rpm: 1_000,
        });
    }
    let modern = sqlx::query_as::<_, (String, Uuid, i32)>(
        r#"
        SELECT key_hash, tenant_id, rate_limit_rpm
        FROM daemon_api_keys
        WHERE prefix = $1 AND is_active = true
        "#,
    )
    .bind(prefix)
    .fetch_optional(pool)
    .await;

    let (key_hash, account_id, rpm) = match modern {
        Ok(Some((hash, tid, rpm))) => (hash, tid, rpm),
        Ok(None) => {
            return Err(ApiError(
                StatusCode::UNAUTHORIZED,
                "invalid API key".to_string(),
            ));
        }
        Err(_) => {
            let legacy = sqlx::query_as::<_, (String, Uuid, String)>(
                r#"
                SELECT key_hash, tenant_id, tier
                FROM daemon_api_keys
                WHERE prefix = $1 AND is_active = true
                "#,
            )
            .bind(prefix)
            .fetch_optional(pool)
            .await
            .map_err(|_| {
                ApiError(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "authentication unavailable".to_string(),
                )
            })?
            .ok_or_else(|| ApiError(StatusCode::UNAUTHORIZED, "invalid API key".to_string()))?;
            (legacy.0, legacy.1, tier_default_rpm(&legacy.2))
        }
    };

    if key_hash
        .as_bytes()
        .ct_eq(presented_hash.as_bytes())
        .unwrap_u8()
        != 1
    {
        return Err(ApiError(
            StatusCode::UNAUTHORIZED,
            "invalid API key".to_string(),
        ));
    }
    Ok(AuthenticatedAccount {
        account_id,
        rate_limit_rpm: rpm.max(1),
    })
}

fn credential_prefix(token: &str) -> Option<(&str, bool)> {
    if let Some(rest) = token.strip_prefix("fjsvc_") {
        let (prefix, secret) = rest.split_once('_')?;
        return (prefix.len() == 8 && !secret.is_empty()).then_some((prefix, true));
    }
    token
        .get(..8)
        .filter(|prefix| prefix.is_ascii())
        .map(|prefix| (prefix, false))
}

fn tier_default_rpm(tier: &str) -> i32 {
    match tier.to_ascii_lowercase().as_str() {
        "pro" | "enterprise" => 1_000,
        _ => 60,
    }
}

async fn enforce_rate_limit(
    state: &DataPlaneState,
    account: &AuthenticatedAccount,
) -> Result<(), ApiError> {
    let client = state.redis.as_ref().ok_or_else(|| {
        ApiError(
            StatusCode::SERVICE_UNAVAILABLE,
            "rate limiter unavailable".to_string(),
        )
    })?;
    let mut connection = client
        .get_multiplexed_async_connection()
        .await
        .map_err(|_| {
            ApiError(
                StatusCode::SERVICE_UNAVAILABLE,
                "rate limiter unavailable".to_string(),
            )
        })?;
    let limit = account.rate_limit_rpm;
    let now_ms = chrono::Utc::now().timestamp_millis();
    let key = format!("rate_limit:account:{}", account.account_id);
    let member = Uuid::new_v4().to_string();
    let script = redis::Script::new(
        r#"
        redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[1] - 60000)
        local count = redis.call('ZCARD', KEYS[1])
        if count >= tonumber(ARGV[2]) then return -1 end
        redis.call('ZADD', KEYS[1], ARGV[1], ARGV[3])
        redis.call('PEXPIRE', KEYS[1], 60000)
        return count + 1
        "#,
    );
    let count: i64 = script
        .key(key)
        .arg(now_ms)
        .arg(limit)
        .arg(member)
        .invoke_async(&mut connection)
        .await
        .map_err(|_| {
            ApiError(
                StatusCode::SERVICE_UNAVAILABLE,
                "rate limiter unavailable".to_string(),
            )
        })?;
    if count < 0 {
        return Err(ApiError(
            StatusCode::TOO_MANY_REQUESTS,
            "rate limit exceeded".to_string(),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{IngestPayload, credential_prefix, validate_payload};
    use serde_json::json;

    #[test]
    fn validates_batch_contract() {
        // Ciphertext-only ingest: each record needs a sealed envelope shape.
        let sealed = json!({
            "ciphertext": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYX",
            "nonce": "AAECAwQFBgcICQoL",
            "key_id": "sess-1",
        });
        let valid = IngestPayload {
            batch_id: "batch-1234".to_string(),
            records: vec![sealed.clone()],
        };
        assert!(validate_payload(&valid).is_ok());

        let bad_batch_id = IngestPayload {
            batch_id: "bad key".to_string(),
            records: vec![sealed.clone()],
        };
        assert!(validate_payload(&bad_batch_id).is_err());

        let plaintext_shaped = IngestPayload {
            batch_id: "batch-1234".to_string(),
            records: vec![json!({"x": 1})],
        };
        assert!(validate_payload(&plaintext_shaped).is_err());
    }

    #[test]
    fn parses_tenant_service_token_prefix_without_utf8_panics() {
        assert_eq!(
            credential_prefix("fjsvc_abcd1234_long-secret"),
            Some(("abcd1234", true))
        );
        assert_eq!(
            credential_prefix("legacy12_more-secret"),
            Some(("legacy12", false))
        );
        assert_eq!(credential_prefix("éééééééé_more-secret"), None);
        assert_eq!(credential_prefix("fjsvc_short_secret"), None);
    }

    #[test]
    fn rejects_nonce_reuse_and_bad_base64() {
        let sealed = json!({
            "ciphertext": "AAECAwQFBgcICQoLDA0ODxAREhMUFRYX",
            "nonce": "AAECAwQFBgcICQoL",
            "key_id": "sess-1",
        });
        let reused = IngestPayload {
            batch_id: "batch-1234".to_string(),
            records: vec![sealed.clone(), sealed],
        };
        assert!(validate_payload(&reused).is_err());

        let invalid = IngestPayload {
            batch_id: "batch-5678".to_string(),
            records: vec![json!({
                "ciphertext": "not-base64!",
                "nonce": "AAECAwQFBgcICQoL",
                "key_id": "sess-1",
            })],
        };
        assert!(validate_payload(&invalid).is_err());
    }
}
