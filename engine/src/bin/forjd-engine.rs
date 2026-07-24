//! FORJD engine — unified HTTP + optional data plane.
//!
//! Build (Fly / Compose):
//!   cargo build --release --no-default-features --features server,data-plane
//!
//! `FORJD_ROLE` selects data-plane work (unset/`engine`/`none` = process only;
//! `all` = relay+scheduler+probe+normalizer+ingest; `cpe` is opt-in). Process/summarize
//! routes always available when the `server` feature is enabled.

use axum::BoxError;
use axum::Router;
use axum::body::Body;
use axum::error_handling::HandleErrorLayer;
use axum::extract::{DefaultBodyLimit, Json, Request, State};
use axum::http::{HeaderName, HeaderValue, StatusCode, header};
use axum::middleware::{Next, from_fn_with_state};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use forjd_engine::pipeline::{SealedPipelineRequest, run_sealed_pipeline};
use forjd_engine::{
    Event, SummarizeResult, engine_version, process_event, summarize_values, token_matches,
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

const REQUEST_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Clone)]
struct AppState {
    api_token: Option<Arc<str>>,
    /// Resolved `FORJD_ROLE` for readiness / version (ops visibility).
    forjd_role: &'static str,
    #[cfg(feature = "data-plane")]
    data_plane: Option<Arc<forjd_engine::data_plane::DataPlaneState>>,
}

#[tokio::main]
async fn main() {
    #[cfg(feature = "data-plane")]
    {
        rustls::crypto::ring::default_provider()
            .install_default()
            .expect("failed to install rustls ring crypto provider");
    }

    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .json()
        .init();

    let port: u16 = std::env::var("PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(8080);
    // Fly private DNS (*.internal) is IPv6-only.
    let addr = SocketAddr::from(([0, 0, 0, 0, 0, 0, 0, 0], port));

    let api_token = std::env::var("ENGINE_API_TOKEN")
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .map(Arc::<str>::from);

    // Fail closed on Fly / ENVIRONMENT=prod when mutate routes would be open.
    let is_production = std::env::var("ENVIRONMENT")
        .map(|e| {
            let e = e.to_ascii_lowercase();
            e == "prod" || e == "production"
        })
        .unwrap_or(false)
        || std::env::var("FLY_APP_NAME").is_ok();
    if api_token.is_some() {
        tracing::info!("ENGINE_API_TOKEN set — mutate routes require auth");
    } else if is_production {
        panic!("ENGINE_API_TOKEN required in production (ENVIRONMENT=prod or FLY_APP_NAME)");
    } else {
        tracing::warn!(
            "ENGINE_API_TOKEN unset — /v1/process and /v1/summarize are open (dev only)"
        );
    }

    // --- Optional data plane (FORJD_ROLE) ---
    #[cfg(feature = "data-plane")]
    let (dp_cfg, bg_tasks, dp_state) = {
        let cfg = match forjd_engine::data_plane::Config::from_env() {
            Ok(cfg) => cfg,
            Err(error) => {
                tracing::error!(error = %error, "invalid data-plane configuration");
                eprintln!("forjd-engine: invalid data-plane configuration: {error:#}");
                std::process::exit(1);
            }
        };
        tracing::info!(role = ?cfg.role, "data plane role");
        let (tasks, pool) = match forjd_engine::data_plane::spawn_background(cfg.clone()).await {
            Ok(started) => started,
            Err(error) => {
                tracing::error!(error = %error, "data plane failed to start");
                eprintln!("forjd-engine: data plane failed to start: {error:#}");
                std::process::exit(1);
            }
        };
        let state = if let Some(pool) = pool {
            match forjd_engine::data_plane::build_state(pool, &cfg).await {
                Ok(state) => Some(state),
                Err(error) => {
                    tracing::error!(error = %error, "data plane HTTP state failed");
                    eprintln!("forjd-engine: data plane HTTP state failed: {error:#}");
                    std::process::exit(1);
                }
            }
        } else {
            None
        };
        (cfg, tasks, state)
    };

    #[cfg(not(feature = "data-plane"))]
    let dp_state: Option<()> = None;

    let forjd_role: &'static str = {
        #[cfg(feature = "data-plane")]
        {
            // Leak is fine — process-lifetime role label for /ready + /v1/version.
            Box::leak(format!("{:?}", dp_cfg.role).into_boxed_str())
        }
        #[cfg(not(feature = "data-plane"))]
        {
            "process-only"
        }
    };

    let state = AppState {
        api_token,
        forjd_role,
        #[cfg(feature = "data-plane")]
        data_plane: dp_state.clone(),
    };

    let x_request_id = HeaderName::from_static("x-request-id");

    let public = Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready))
        .route("/v1/version", get(version));

    // Sealed pipeline accepts metadata batches (larger than single-event process).
    const SEALED_BODY_LIMIT: usize = 1024 * 1024;

    let protected = Router::new()
        .route("/v1/process", post(process))
        .route("/v1/summarize", post(summarize))
        .route("/v1/sealed/pipeline", post(sealed_pipeline))
        .route_layer(from_fn_with_state(state.clone(), require_token))
        .layer(DefaultBodyLimit::max(SEALED_BODY_LIMIT))
        .layer(RequestBodyLimitLayer::new(SEALED_BODY_LIMIT));

    #[cfg_attr(not(feature = "data-plane"), allow(unused_mut))]
    let mut app = public.merge(protected).with_state(state);

    #[cfg(feature = "data-plane")]
    if let Some(ref dp) = dp_state {
        let plane = forjd_engine::data_plane::build_data_plane_router(dp.clone(), &dp_cfg);
        app = app.merge(plane);
    }

    let app = app.layer(
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

    let server = axum::serve(listener, app).with_graceful_shutdown(shutdown_signal());

    #[cfg(feature = "data-plane")]
    {
        tokio::select! {
            result = server => {
                result.expect("server error");
            }
            result = forjd_engine::data_plane::supervise(bg_tasks) => {
                if let Err(err) = result {
                    tracing::error!(error = %err, "data plane task failed — shutting down");
                    std::process::exit(1);
                }
            }
        }
    }

    #[cfg(not(feature = "data-plane"))]
    {
        let _ = dp_state;
        server.await.expect("server error");
    }
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

async fn ready(State(state): State<AppState>) -> Response {
    #[cfg(feature = "data-plane")]
    if let Some(ref dp) = state.data_plane {
        let (status, mut body) = forjd_engine::data_plane::http::data_plane_ready(dp).await;
        if let serde_json::Value::Object(ref mut map) = body.0 {
            map.insert(
                "forjd_role".into(),
                serde_json::Value::String(state.forjd_role.to_string()),
            );
        }
        return (status, body).into_response();
    }
    (
        axum::http::StatusCode::OK,
        Json(serde_json::json!({
            "status": "ready",
            "forjd_role": state.forjd_role,
            "mode": "process",
        })),
    )
        .into_response()
}

#[derive(Serialize)]
struct VersionBody {
    version: &'static str,
    service: &'static str,
    schema_version: u32,
    forjd_role: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    data_plane: Option<&'static str>,
}

async fn version(State(state): State<AppState>) -> Json<VersionBody> {
    Json(VersionBody {
        version: engine_version(),
        service: "forjd-engine",
        schema_version: forjd_engine::SCHEMA_VERSION,
        forjd_role: state.forjd_role,
        data_plane: if cfg!(feature = "data-plane") {
            Some("enabled")
        } else {
            None
        },
    })
}

#[derive(Deserialize)]
struct ProcessRequest {
    id: String,
    timestamp: i64,
    payload: serde_json::Value,
}

async fn process(
    Json(body): Json<ProcessRequest>,
) -> Result<Json<forjd_engine::ProcessedEvent>, ApiError> {
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

/// Ciphertext-blind sealed-metadata rollup + detectors (universal SaaS pipeline).
async fn sealed_pipeline(
    Json(body): Json<SealedPipelineRequest>,
) -> Result<Json<serde_json::Value>, ApiError> {
    run_sealed_pipeline(body)
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
        (
            self.status,
            Json(ErrBody {
                error: self.message,
            }),
        )
            .into_response()
    }
}
