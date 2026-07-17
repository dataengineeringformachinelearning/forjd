use std::sync::Arc;

use axum::{
    body::Body,
    extract::{DefaultBodyLimit, State},
    http::{HeaderMap, Request, StatusCode},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use sqlx::PgPool;
use subtle::ConstantTimeEq;
use tracing::info;
use uuid::Uuid;

use crate::config::Config;

#[derive(Clone)]
struct AppState {
    pool: PgPool,
    redis: Option<redis::Client>,
    cpe_redis: Option<redis::Client>,
    cpe_only: bool,
}

#[derive(Debug, Deserialize)]
struct IngestPayload {
    batch_id: String,
    records: Vec<Value>,
}

#[derive(Debug, Serialize)]
struct IngestResponse {
    status: &'static str,
    message: &'static str,
    processed_records: usize,
}

struct AuthenticatedAccount {
    account_id: Uuid,
    tier: String,
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum CpeQueryInput {
    Text(String),
    Words(Vec<String>),
}

#[derive(Debug, Deserialize)]
struct CpeQuery {
    query: CpeQueryInput,
    #[serde(default)]
    part: Option<String>,
}

#[derive(Debug)]
struct ApiError(StatusCode, String);

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.0, Json(json!({"detail": self.1}))).into_response()
    }
}

pub async fn run(
    pool: PgPool,
    cfg: Config,
    enable_ingest: bool,
    enable_cpe: bool,
) -> anyhow::Result<()> {
    let redis = build_redis_client(cfg.redis_url.as_deref(), cfg.redis_ssl_ca_pem.as_deref())?;
    if enable_ingest && redis.is_none() {
        anyhow::bail!("REDIS_URL is required when FORJD_ROLE=ingest");
    }
    let cpe_redis = build_redis_client(
        cfg.cpe_redis_url.as_deref(),
        cfg.redis_ssl_ca_pem.as_deref(),
    )?;
    if enable_cpe && cpe_redis.is_none() {
        anyhow::bail!("CPE_REDIS_URL is required when FORJD_ROLE=cpe");
    }
    let state = Arc::new(AppState {
        pool,
        redis,
        cpe_redis,
        cpe_only: enable_cpe && !enable_ingest,
    });
    let mut router = Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready));
    if enable_ingest {
        router = router.route("/api/v1/ingest", post(ingest));
    }
    if enable_cpe {
        router = router.route("/unique", post(cpe_unique));
    }
    let router = router
        .layer(DefaultBodyLimit::max(2 * 1024 * 1024))
        .layer(middleware::from_fn(security_headers))
        .with_state(state);
    let listener = tokio::net::TcpListener::bind(&cfg.bind_address).await?;
    info!(address = %cfg.bind_address, enable_ingest, enable_cpe, "http: listening");
    axum::serve(listener, router).await?;
    Ok(())
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

#[tracing::instrument(name = "cpe_lookup", skip_all)]
async fn cpe_unique(
    State(state): State<Arc<AppState>>,
    Json(payload): Json<CpeQuery>,
) -> Result<Json<Value>, ApiError> {
    let part = payload.part.unwrap_or_default().to_ascii_lowercase();
    if !part.is_empty() && !matches!(part.as_str(), "a" | "h" | "o") {
        return Err(ApiError(
            StatusCode::BAD_REQUEST,
            "part must be a, h, or o".to_string(),
        ));
    }
    let words = match payload.query {
        CpeQueryInput::Text(text) => tokenize_cpe_query(&text),
        CpeQueryInput::Words(words) => words
            .into_iter()
            .flat_map(|word| tokenize_cpe_query(&word))
            .collect(),
    };
    if words.is_empty() || words.len() > 20 {
        return Err(ApiError(
            StatusCode::BAD_REQUEST,
            "query must contain between 1 and 20 words".to_string(),
        ));
    }
    let client = state.cpe_redis.as_ref().ok_or_else(|| {
        ApiError(
            StatusCode::SERVICE_UNAVAILABLE,
            "CPE index unavailable".to_string(),
        )
    })?;
    let mut connection = client
        .get_multiplexed_async_connection()
        .await
        .map_err(|_| {
            ApiError(
                StatusCode::SERVICE_UNAVAILABLE,
                "CPE index unavailable".to_string(),
            )
        })?;
    let script = redis::Script::new(
        r#"
        local candidates = redis.call('SINTER', unpack(KEYS))
        local best = false
        local best_score = -1
        for _, cpe in ipairs(candidates) do
          local cpe_part = string.match(cpe, '^cpe:2%.3:([aho]):')
          if ARGV[1] == '' or cpe_part == ARGV[1] then
            local score = tonumber(redis.call('ZSCORE', 'rank:cpe', cpe) or '0')
            for index = 2, #ARGV do
              score = score + tonumber(redis.call('ZSCORE', 's:' .. ARGV[index], cpe) or '0')
            end
            if score > best_score or (score == best_score and (best == false or cpe > best)) then
              best = cpe
              best_score = score
            end
          end
        end
        return best
        "#,
    );
    let mut invocation = script.prepare_invoke();
    for word in &words {
        invocation.key(format!("w:{word}"));
    }
    invocation.arg(&part);
    for word in &words {
        invocation.arg(word);
    }
    let result: Option<String> =
        invocation
            .invoke_async(&mut connection)
            .await
            .map_err(|error| {
                tracing::error!(%error, "cpe: lookup failed");
                ApiError(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "CPE index unavailable".to_string(),
                )
            })?;
    Ok(Json(json!({"cpe_2_3": result})))
}

fn tokenize_cpe_query(raw: &str) -> Vec<String> {
    raw.split(|character: char| {
        character.is_whitespace() || matches!(character, '/' | '(' | ')' | ',' | ';')
    })
    .map(|word| {
        word.trim_matches(|character: char| {
            !(character.is_ascii_alphanumeric() || matches!(character, '.' | '-' | '_'))
        })
    })
    .filter(|word| word.len() >= 2)
    .map(str::to_ascii_lowercase)
    .collect()
}

async fn security_headers(request: Request<Body>, next: Next) -> Response {
    let mut response = next.run(request).await;
    response.headers_mut().insert(
        "x-content-type-options",
        "nosniff".parse().expect("static header is valid"),
    );
    response.headers_mut().insert(
        "cache-control",
        "no-store".parse().expect("static header is valid"),
    );
    response
}

async fn health() -> Json<Value> {
    Json(json!({"status": "ok"}))
}

async fn ready(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    if state.cpe_only {
        let available = if let Some(client) = &state.cpe_redis {
            match client.get_multiplexed_async_connection().await {
                Ok(mut connection) => redis::cmd("PING")
                    .query_async::<String>(&mut connection)
                    .await
                    .is_ok(),
                Err(_) => false,
            }
        } else {
            false
        };
        return if available {
            (StatusCode::OK, Json(json!({"status": "ready"})))
        } else {
            (
                StatusCode::SERVICE_UNAVAILABLE,
                Json(json!({"status": "not_ready"})),
            )
        };
    }
    match sqlx::query_scalar::<_, i32>("SELECT 1")
        .fetch_one(&state.pool)
        .await
    {
        Ok(_) => (StatusCode::OK, Json(json!({"status": "ready"}))),
        Err(_) => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"status": "not_ready"})),
        ),
    }
}

#[tracing::instrument(name = "rust_ingest", skip_all, fields(batch_id = %payload.batch_id))]
async fn ingest(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Json(payload): Json<IngestPayload>,
) -> Result<(StatusCode, Json<IngestResponse>), ApiError> {
    validate_payload(&payload)?;
    let account = authenticate(&state.pool, &headers).await?;
    enforce_rate_limit(&state, &account).await?;

    let mut event = json!({
        "batch_id": payload.batch_id,
        "records": payload.records,
        "account_id": account.account_id,
        "event_type": "ingestion",
        "version": "1.0",
    });
    let canonical = serde_json::to_vec(&event)
        .map_err(|_| ApiError(StatusCode::BAD_REQUEST, "invalid JSON payload".to_string()))?;
    let chain_hash = hex::encode(Sha256::digest(&canonical));
    event["chain_of_custody_hash"] = Value::String(chain_hash);
    let idempotency_key = format!("ingest:{}:{}", account.account_id, payload.batch_id);
    let inserted = sqlx::query_scalar::<_, Uuid>(
        r#"
        INSERT INTO outbox_events
            (id, topic, key, payload, headers, idempotency_key, created_at, available_at,
             attempts, is_published)
        VALUES ($1, 'app-events', $2, $3, $4, $5, NOW(), NOW(), 0, false)
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING id
        "#,
    )
    .bind(Uuid::new_v4())
    .bind(account.account_id.to_string())
    .bind(event)
    .bind(json!({"version": "1.0", "event_type": "ingestion", "source": "forjd-rust-ingest"}))
    .bind(idempotency_key)
    .fetch_optional(&state.pool)
    .await
    .map_err(|error| {
        tracing::error!(%error, "ingest: outbox insert failed");
        ApiError(
            StatusCode::SERVICE_UNAVAILABLE,
            "ingestion queue unavailable".to_string(),
        )
    })?;

    let duplicate = inserted.is_none();
    Ok((
        StatusCode::OK,
        Json(IngestResponse {
            status: "success",
            message: if duplicate {
                "Batch was already accepted."
            } else {
                "Batch durably accepted for processing."
            },
            processed_records: payload.records.len(),
        }),
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
    if payload.records.iter().any(|record| !record.is_object()) {
        return Err(ApiError(
            StatusCode::BAD_REQUEST,
            "every record must be a JSON object".to_string(),
        ));
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
    let prefix = &token[..8];
    let presented_hash = hex::encode(Sha256::digest(token.as_bytes()));
    let row = sqlx::query_as::<_, (String, Uuid, String)>(
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
    Ok(AuthenticatedAccount {
        account_id: row.1,
        tier: row.2,
    })
}

async fn enforce_rate_limit(
    state: &AppState,
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
    let limit = if account.tier == "Pro" { 1_000 } else { 60 };
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
    use super::{tokenize_cpe_query, validate_payload, IngestPayload};
    use serde_json::json;

    #[test]
    fn validates_batch_contract() {
        let valid = IngestPayload {
            batch_id: "batch-1234".to_string(),
            records: vec![json!({"x": 1})],
        };
        assert!(validate_payload(&valid).is_ok());
        let invalid = IngestPayload {
            batch_id: "bad key".to_string(),
            records: vec![json!({"x": 1})],
        };
        assert!(validate_payload(&invalid).is_err());
    }

    #[test]
    fn tokenizes_cpe_queries_deterministically() {
        assert_eq!(
            tokenize_cpe_query("Apache HTTP Server 2.4"),
            vec!["apache", "http", "server", "2.4"]
        );
    }
}
