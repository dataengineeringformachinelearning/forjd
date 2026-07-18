//! Optional CPE dictionary lookup (threat-intel plugin, not core platform).
//!
//! Enabled when `FORJD_ROLE=cpe`. Uses a Dragonfly word index (`CPE_REDIS_URL`).
//! Universal SaaS deployments can omit this role entirely.

use std::sync::Arc;

use axum::{extract::State, http::StatusCode, Json};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::data_plane::http::{ApiError, DataPlaneState};

#[derive(Debug, Deserialize)]
#[serde(untagged)]
pub enum CpeQueryInput {
    Text(String),
    Words(Vec<String>),
}

#[derive(Debug, Deserialize)]
pub struct CpeQuery {
    query: CpeQueryInput,
    #[serde(default)]
    part: Option<String>,
}

// --- CPE unique match (Lua score over Dragonfly sets) ---
#[tracing::instrument(name = "cpe_lookup", skip_all)]
pub async fn cpe_unique(
    State(state): State<Arc<DataPlaneState>>,
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
    Ok(Json(json!({ "cpe_2_3": result })))
}

pub fn tokenize_cpe_query(raw: &str) -> Vec<String> {
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

/// Readiness for CPE-only processes (Dragonfly index ping).
pub async fn ready_cpe(state: &DataPlaneState) -> (StatusCode, Json<Value>) {
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
    if available {
        (StatusCode::OK, Json(json!({"status": "ready"})))
    } else {
        (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"status": "not_ready"})),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::tokenize_cpe_query;

    #[test]
    fn tokenizes_cpe_queries_deterministically() {
        assert_eq!(
            tokenize_cpe_query("Apache HTTP Server 2.4"),
            vec!["apache", "http", "server", "2.4"]
        );
    }
}
