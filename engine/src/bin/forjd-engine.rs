//! FORJD engine HTTP service — Fly.io / container entrypoint.
//!
//! Build: `cargo build --release --no-default-features --features server`
//! Listen: `PORT` (default 8080) on `0.0.0.0`.
//!
//! Security (env):
//! - `ENGINE_API_TOKEN` — when set, mutate routes require `Authorization: Bearer <token>`
//!   or `X-Engine-Token: <token>` (constant-time compare).
//! - Body size capped; request timeout applied to the service stack.

use axum::body::Body;
use axum::error_handling::HandleErrorLayer;
use axum::extract::{DefaultBodyLimit, Json, Request, State};
use axum::http::{header, HeaderName, HeaderValue, StatusCode};
use axum::middleware::{from_fn_with_state, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::BoxError;
use axum::Router;
use forjd_engine::{
    engine_version, process_event, summarize_values, token_matches, Event, SummarizeResult,
};
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;
use tower::ServiceBuilder;
use tower_http::limit::RequestBodyLimitLayer;
use tower_http::request_id::{MakeRequestUuid, PropagateRequestIdLayer, SetRequestIdLayer};
use tower_http::set_header::SetResponseHeaderLayer;
use tower_http::trace::TraceLayer;
use tracing_subscriber::EnvFilter;

/// Default JSON body budget for mutate endpoints (DoS bound).
const BODY_LIMIT_BYTES: usize = 64 * 1024;
const REQUEST_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Clone)]
struct AppState {
    /// When `Some` and non-empty, mutate routes require a matching token.
    api_token: Option<Arc<str>>,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .json()
        .init();

    let port: u16 = std::env::var("PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(8080);
    let addr = SocketAddr::from(([0, 0, 0, 0], port));

    let api_token = std::env::var("ENGINE_API_TOKEN")
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .map(Arc::<str>::from);

    if api_token.is_some() {
        tracing::info!("ENGINE_API_TOKEN set — mutate routes require auth");
    } else {
        tracing::warn!(
            "ENGINE_API_TOKEN unset — /v1/process and /v1/summarize are open (dev only)"
        );
    }

    let state = AppState { api_token };

    let x_request_id = HeaderName::from_static("x-request-id");

    let public = Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready))
        .route("/v1/version", get(version));

    let protected = Router::new()
        .route("/v1/process", post(process))
        .route("/v1/summarize", post(summarize))
        .route_layer(from_fn_with_state(state.clone(), require_token))
        .layer(DefaultBodyLimit::max(BODY_LIMIT_BYTES))
        .layer(RequestBodyLimitLayer::new(BODY_LIMIT_BYTES));

    let app = public
        .merge(protected)
        .layer(
            ServiceBuilder::new()
                .layer(HandleErrorLayer::new(|err: BoxError| async move {
                    if err.is::<tower::timeout::error::Elapsed>() {
                        (
                            StatusCode::REQUEST_TIMEOUT,
                            Json(serde_json::json!({"error": "request timed out"})),
                        )
                            .into_response()
                    } else {
                        (
                            StatusCode::INTERNAL_SERVER_ERROR,
                            Json(serde_json::json!({"error": format!("internal error: {err}")})),
                        )
                            .into_response()
                    }
                }))
                .layer(tower::timeout::TimeoutLayer::new(REQUEST_TIMEOUT))
                .layer(SetRequestIdLayer::new(
                    x_request_id.clone(),
                    MakeRequestUuid,
                ))
                .layer(PropagateRequestIdLayer::new(x_request_id))
                .layer(TraceLayer::new_for_http())
                .layer(SetResponseHeaderLayer::overriding(
                    header::X_CONTENT_TYPE_OPTIONS,
                    HeaderValue::from_static("nosniff"),
                ))
                .layer(SetResponseHeaderLayer::overriding(
                    header::X_FRAME_OPTIONS,
                    HeaderValue::from_static("DENY"),
                ))
                .layer(SetResponseHeaderLayer::overriding(
                    header::REFERRER_POLICY,
                    HeaderValue::from_static("no-referrer"),
                ))
                .layer(SetResponseHeaderLayer::overriding(
                    header::CACHE_CONTROL,
                    HeaderValue::from_static("no-store"),
                )),
        );

    tracing::info!(%addr, version = engine_version(), "forjd-engine listening");
    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("bind failed");
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .expect("server error");
}

async fn require_token(
    State(state): State<AppState>,
    request: Request<Body>,
    next: Next,
) -> Result<Response, ApiError> {
    let configured = state.api_token.as_deref();
    if configured.is_none() {
        return Ok(next.run(request).await);
    }

    let provided = request
        .headers()
        .get("x-engine-token")
        .and_then(|v| v.to_str().ok())
        .map(str::to_string)
        .or_else(|| {
            request
                .headers()
                .get(header::AUTHORIZATION)
                .and_then(|v| v.to_str().ok())
                .and_then(|v| v.strip_prefix("Bearer ").map(str::to_string))
        });

    if token_matches(configured, provided.as_deref()) {
        Ok(next.run(request).await)
    } else {
        Err(ApiError::unauthorized("invalid or missing engine token"))
    }
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
    tracing::info!("shutdown signal received");
}

#[derive(Serialize)]
struct StatusBody {
    status: &'static str,
}

async fn health() -> Json<StatusBody> {
    Json(StatusBody { status: "ok" })
}

async fn ready() -> Json<StatusBody> {
    Json(StatusBody { status: "ready" })
}

#[derive(Serialize)]
struct VersionBody {
    version: &'static str,
    service: &'static str,
    schema_version: u32,
}

async fn version() -> Json<VersionBody> {
    Json(VersionBody {
        version: engine_version(),
        service: "forjd-engine",
        schema_version: forjd_engine::SCHEMA_VERSION,
    })
}

#[derive(Deserialize)]
struct ProcessRequest {
    id: String,
    timestamp: i64,
    payload: serde_json::Value,
}

async fn process(Json(body): Json<ProcessRequest>) -> Result<Json<forjd_engine::ProcessedEvent>, ApiError> {
    let processed = process_event(Event {
        id: body.id,
        timestamp: body.timestamp,
        payload: body.payload,
    })
    .map_err(ApiError::from_engine)?;
    Ok(Json(processed))
}

#[derive(Deserialize)]
struct SummarizeRequest {
    values: Vec<f64>,
}

async fn summarize(Json(body): Json<SummarizeRequest>) -> Result<Json<SummarizeResult>, ApiError> {
    summarize_values(&body.values)
        .map(Json)
        .map_err(ApiError::from_engine)
}

struct ApiError {
    status: StatusCode,
    message: String,
}

impl ApiError {
    fn bad_request(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            message: message.into(),
        }
    }

    fn unauthorized(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::UNAUTHORIZED,
            message: message.into(),
        }
    }

    fn from_engine(err: forjd_engine::EngineError) -> Self {
        match err {
            forjd_engine::EngineError::Columnar(_) => Self {
                status: StatusCode::INTERNAL_SERVER_ERROR,
                message: err.to_string(),
            },
            other => Self::bad_request(other.to_string()),
        }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        #[derive(Serialize)]
        struct ErrBody {
            error: String,
        }
        (self.status, Json(ErrBody { error: self.message })).into_response()
    }
}
