//! Environment-driven daemon configuration (`FORJD_ROLE` and related secrets).

use std::env;

use anyhow::{bail, Context, Result};

// --- Role selection ---
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Role {
    Relay,
    Scheduler,
    Probe,
    Normalizer,
    Ingest,
    Cpe,
    All,
}

impl Role {
    fn from_env() -> Result<Self> {
        let raw = env::var("FORJD_ROLE").context("FORJD_ROLE must be set explicitly")?;
        match raw.to_ascii_lowercase().as_str() {
            "relay" => Ok(Self::Relay),
            "scheduler" => Ok(Self::Scheduler),
            "probe" => Ok(Self::Probe),
            "normalizer" => Ok(Self::Normalizer),
            "ingest" => Ok(Self::Ingest),
            "cpe" => Ok(Self::Cpe),
            "all" => Ok(Self::All),
            _ => {
                bail!(
                    "FORJD_ROLE must be relay, scheduler, probe, normalizer, ingest, cpe, or all"
                )
            }
        }
    }

    pub fn runs(self, target: Self) -> bool {
        self == Self::All || self == target
    }

    pub fn needs_bus(self) -> bool {
        matches!(
            self,
            Self::Relay | Self::Scheduler | Self::Normalizer | Self::All
        )
    }
}

/// Runtime configuration loaded from FORJD Compose / Fly secrets.
#[derive(Clone, Debug)]
pub struct Config {
    pub role: Role,

    /// Postgres DSN (`DATABASE_URL` or `POSTGRES_DSN`).
    pub database_url: String,

    /// Max events claimed per outbox poll cycle.
    pub batch_size: i64,

    /// Seconds between outbox poll cycles (fallback when LISTEN unavailable).
    pub poll_interval_secs: u64,

    /// Abandon publishing after this many failed attempts.
    pub max_attempts: i32,

    /// Seconds between health probe cycles.
    pub pinger_interval_secs: u64,

    /// Emit JSON log lines when true.
    pub structured_logs: bool,

    /// Skip TLS verification for probes (local only).
    pub skip_tls_verify: bool,

    /// Maximum simultaneous Dragonfly publishes or HTTP probes.
    pub max_concurrency: usize,

    /// Health/ingestion HTTP bind address.
    pub bind_address: String,

    /// Dragonfly/Redis URL (bus + rate limit + CPE).
    pub redis_url: Option<String>,

    /// Optional separate Dragonfly DB for CPE word index.
    pub cpe_redis_url: Option<String>,

    /// Private CA for verified Dragonfly TLS (base64 PEM).
    pub redis_ssl_ca_pem: Option<Vec<u8>>,

    /// Consumer group for the telemetry normalizer.
    pub normalizer_group_id: String,

    /// Optional Prefect API URL (reserved for future HTTP flow triggers).
    #[allow(dead_code)]
    pub prefect_api_url: Option<String>,
}

impl Config {
    // --- Load + validate from env ---
    pub fn from_env() -> Result<Self> {
        let max_concurrency = env::var("MAX_CONCURRENCY")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(64);
        if max_concurrency == 0 {
            bail!("MAX_CONCURRENCY must be greater than zero");
        }

        let database_url = env::var("DATABASE_URL")
            .or_else(|_| env::var("POSTGRES_DSN"))
            .context("DATABASE_URL or POSTGRES_DSN must be set")?;
        // sqlx wants postgresql://; backend often uses postgresql+asyncpg://
        let database_url = database_url.replace("postgresql+asyncpg://", "postgresql://");

        let config = Self {
            role: Role::from_env()?,
            database_url,
            batch_size: env::var("BATCH_SIZE")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(100),
            poll_interval_secs: env::var("POLL_INTERVAL_SECS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(5),
            max_attempts: env::var("MAX_ATTEMPTS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(5),
            pinger_interval_secs: env::var("PINGER_INTERVAL_SECS")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(30),
            structured_logs: env::var("STRUCTURED_LOGS")
                .map(|v| v.eq_ignore_ascii_case("true"))
                .unwrap_or(false),
            skip_tls_verify: env::var("HEALTH_PINGER_SKIP_TLS_VERIFY")
                .map(|v| v.eq_ignore_ascii_case("true"))
                .unwrap_or(false),
            max_concurrency,
            bind_address: format!(
                "0.0.0.0:{}",
                env::var("PORT").unwrap_or_else(|_| "8080".to_string())
            ),
            redis_url: env::var("REDIS_URL").ok().filter(|v| !v.is_empty()),
            cpe_redis_url: env::var("CPE_REDIS_URL").ok().filter(|v| !v.is_empty()),
            redis_ssl_ca_pem: decode_bytes_env("REDIS_SSL_CA_B64")?,
            normalizer_group_id: env::var("NORMALIZER_GROUP_ID")
                .unwrap_or_else(|_| "forjd-telemetry-normalizer-v1".to_string()),
            prefect_api_url: env::var("PREFECT_API_URL").ok().filter(|v| !v.is_empty()),
        };
        config.validate_transport_security()?;
        if config.role.needs_bus() && config.redis_url.is_none() {
            bail!("REDIS_URL (Dragonfly) is required for role {:?}", config.role);
        }
        Ok(config)
    }

    fn validate_transport_security(&self) -> Result<()> {
        // --- Production gate (Fly / FORJD_ENV) ---
        if !is_production() {
            return Ok(());
        }
        if !env::var("FORJD_TRANSPORT_SECURITY")
            .unwrap_or_else(|_| "required".to_string())
            .eq_ignore_ascii_case("required")
        {
            bail!("FORJD_TRANSPORT_SECURITY must be required in production");
        }
        let database = url::Url::parse(&self.database_url).context("DATABASE_URL is invalid")?;
        let sslmode = database
            .query_pairs()
            .find(|(name, _)| name == "sslmode")
            .map(|(_, value)| value.into_owned())
            .unwrap_or_default();
        if !matches!(sslmode.as_str(), "verify-ca" | "verify-full" | "require") {
            bail!("production DATABASE_URL must set sslmode=require|verify-ca|verify-full");
        }
        for (name, value) in [
            ("REDIS_URL", self.redis_url.as_deref()),
            ("CPE_REDIS_URL", self.cpe_redis_url.as_deref()),
        ] {
            if let Some(url) = value {
                // Fly 6PN often uses redis:// with requirepass; allow redis://*.internal
                let internal = url.contains(".internal");
                if !url.starts_with("rediss://") && !internal {
                    bail!("production {name} must use rediss:// or Fly *.internal redis://");
                }
            }
        }
        if self.skip_tls_verify {
            bail!("HEALTH_PINGER_SKIP_TLS_VERIFY cannot be enabled in production");
        }
        if let Ok(endpoint) = env::var("OTEL_EXPORTER_OTLP_ENDPOINT") {
            if !endpoint.is_empty() && !endpoint.starts_with("https://") {
                bail!("production OTEL_EXPORTER_OTLP_ENDPOINT must use https://");
            }
        }
        Ok(())
    }
}

/// True when `FORJD_ENV=production` or the process is running on Fly.io.
fn is_production() -> bool {
    if env::var("FORJD_ENV")
        .map(|value| value.eq_ignore_ascii_case("production"))
        .unwrap_or(false)
    {
        return true;
    }
    env::var("FLY_APP_NAME").is_ok()
}

fn decode_bytes_env(name: &str) -> Result<Option<Vec<u8>>> {
    use base64::{engine::general_purpose::STANDARD, Engine as _};

    let Some(encoded) = env::var(name).ok().filter(|value| !value.is_empty()) else {
        return Ok(None);
    };
    STANDARD
        .decode(encoded)
        .with_context(|| format!("{name} must be valid base64"))
        .map(Some)
}
