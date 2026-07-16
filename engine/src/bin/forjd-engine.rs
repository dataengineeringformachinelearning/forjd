//! FORJD engine HTTP service — Fly.io / container entrypoint.
//!
//! Build: `cargo build --release --no-default-features --features server`
//! Listen: `PORT` (default 8080) on `0.0.0.0`.

use axum::extract::Json;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::Router;
use forjd_engine::{engine_version, process_event, summarize_values, Event, SummarizeResult};
use serde::{Deserialize, Serialize};
use std::net::SocketAddr;
use tower_http::trace::TraceLayer;
use tracing_subscriber::EnvFilter;

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

    let app = Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready))
        .route("/v1/version", get(version))
        .route("/v1/process", post(process))
        .route("/v1/summarize", post(summarize))
        .layer(TraceLayer::new_for_http());

    tracing::info!(%addr, version = engine_version(), "forjd-engine listening");
    let listener = tokio::net::TcpListener::bind(addr)
        .await
        .expect("bind failed");
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
        .expect("server error");
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
    // No external deps yet — process up means ready.
    Json(StatusBody { status: "ready" })
}

#[derive(Serialize)]
struct VersionBody {
    version: &'static str,
    service: &'static str,
}

async fn version() -> Json<VersionBody> {
    Json(VersionBody {
        version: engine_version(),
        service: "forjd-engine",
    })
}

#[derive(Deserialize)]
struct ProcessRequest {
    id: String,
    timestamp: i64,
    payload: serde_json::Value,
}

#[derive(Serialize)]
struct ProcessResponse {
    id: String,
    timestamp: i64,
    payload: serde_json::Value,
    engine: &'static str,
}

async fn process(Json(body): Json<ProcessRequest>) -> Result<Json<ProcessResponse>, ApiError> {
    if body.id.is_empty() {
        return Err(ApiError::bad_request("id must not be empty"));
    }
    let processed = process_event(Event {
        id: body.id,
        timestamp: body.timestamp,
        payload: body.payload,
    });
    Ok(Json(ProcessResponse {
        id: processed.id,
        timestamp: processed.timestamp,
        payload: processed.payload,
        engine: "forjd-engine",
    }))
}

#[derive(Deserialize)]
struct SummarizeRequest {
    values: Vec<f64>,
}

async fn summarize(Json(body): Json<SummarizeRequest>) -> Result<Json<SummarizeResult>, ApiError> {
    summarize_values(&body.values)
        .map(Json)
        .map_err(ApiError::bad_request)
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
