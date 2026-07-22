//! Bounded, SSRF-hardened probes against FORJD `status_services.probe_url`.

use std::{
    net::{IpAddr, SocketAddr},
    time::{Duration, Instant},
};

use anyhow::{Context, Result, bail};
use futures::{StreamExt, stream};
use reqwest::{Client, StatusCode, redirect::Policy};
use sqlx::PgPool;
use tokio::net::lookup_host;
use tracing::{error, info, warn};
use url::Url;
use uuid::Uuid;

use crate::data_plane::config::Config;

#[derive(Clone, Debug, sqlx::FromRow)]
struct MonitoredService {
    service_id: Uuid,
    tenant_id: Uuid,
    url: String,
}

#[derive(Debug)]
struct PingResult {
    service: MonitoredService,
    status_code: u16,
    response_time_ms: i64,
    is_active: bool,
    error: String,
}

pub async fn run(pool: PgPool, cfg: Config) -> Result<()> {
    if cfg.skip_tls_verify {
        warn!("probe: TLS verification disabled; this must never be enabled in production");
    }
    info!(concurrency = cfg.max_concurrency, "probe: started");

    loop {
        if let Err(error) = tick(&pool, &cfg).await {
            error!(%error, "probe: cycle failed");
        }
        tokio::time::sleep(Duration::from_secs(cfg.pinger_interval_secs)).await;
    }
}

#[tracing::instrument(name = "probe_cycle", skip_all)]
async fn tick(pool: &PgPool, cfg: &Config) -> Result<()> {
    let services = fetch_services(pool).await?;
    let bucket = chrono::Utc::now()
        .timestamp()
        .div_euclid(cfg.pinger_interval_secs as i64);
    let results = stream::iter(
        services
            .into_iter()
            .map(|service| async move { probe_service(service, cfg.skip_tls_verify).await }),
    )
    .buffer_unordered(cfg.max_concurrency)
    .collect::<Vec<PingResult>>()
    .await;

    let mut inserted = 0usize;
    for result in results {
        let observation_key = format!("{}:{bucket}", result.service.service_id);
        match persist_result(pool, &observation_key, &result).await {
            Ok(true) => inserted += 1,
            Ok(false) => {}
            Err(error) => {
                error!(service_id = %result.service.service_id, %error, "probe: persistence failed")
            }
        }
    }
    info!(inserted, "probe: cycle complete");
    Ok(())
}

async fn fetch_services(pool: &PgPool) -> Result<Vec<MonitoredService>> {
    // Prefer explicit probe_url; fall back to description when it looks like
    // an http(s) target (DEML historically stored the monitor URL there).
    Ok(sqlx::query_as::<_, MonitoredService>(
        r#"
        SELECT id AS service_id,
               tenant_id,
               COALESCE(
                 NULLIF(BTRIM(probe_url), ''),
                 NULLIF(BTRIM(description), '')
               ) AS url
        FROM status_services
        WHERE COALESCE(
                NULLIF(BTRIM(probe_url), ''),
                NULLIF(BTRIM(description), '')
              ) ~* '^https?://'
        ORDER BY id
        "#,
    )
    .fetch_all(pool)
    .await?)
}

async fn probe_service(service: MonitoredService, skip_tls_verify: bool) -> PingResult {
    let start = Instant::now();
    let outcome = async {
        let (client, target) = pinned_client(&service.url, skip_tls_verify).await?;
        let head = client.head(target.clone()).send().await;
        let response = match head {
            Ok(response)
                if response.status() == StatusCode::METHOD_NOT_ALLOWED
                    || response.status() == StatusCode::NOT_IMPLEMENTED =>
            {
                client.get(target).send().await?
            }
            Ok(response) => response,
            Err(_) => client.get(target).send().await?,
        };
        let code = response.status().as_u16();
        Ok::<(u16, bool), anyhow::Error>((code, (200..500).contains(&code)))
    }
    .await;

    let (status_code, is_active, error) = match outcome {
        Ok((code, active)) => (code, active, String::new()),
        Err(error) => (503, false, error.to_string()),
    };
    PingResult {
        service,
        status_code,
        response_time_ms: start.elapsed().as_millis().min(i64::MAX as u128) as i64,
        is_active,
        error,
    }
}

async fn pinned_client(raw: &str, skip_tls_verify: bool) -> Result<(Client, Url)> {
    let url = Url::parse(raw).context("invalid monitored URL")?;
    if !matches!(url.scheme(), "http" | "https") {
        bail!("only http and https monitored URLs are allowed");
    }
    if !url.username().is_empty() || url.password().is_some() {
        bail!("monitored URLs may not contain credentials");
    }
    let host = url.host_str().context("monitored URL has no host")?;
    let port = url
        .port_or_known_default()
        .context("monitored URL has no port")?;
    let addresses: Vec<SocketAddr> = lookup_host((host, port))
        .await
        .context("target DNS lookup failed")?
        .collect();
    if addresses.is_empty() {
        bail!("target DNS lookup returned no addresses");
    }
    for address in &addresses {
        if !is_public_ip(address.ip()) {
            bail!("target resolves to a non-public address");
        }
    }

    // Pin the already-validated addresses into reqwest's resolver. TLS SNI and
    // certificate checks still use the original hostname, while a second DNS
    // lookup cannot redirect the connection to a private address.
    let mut builder = Client::builder()
        .connect_timeout(Duration::from_secs(3))
        .timeout(Duration::from_secs(8))
        .redirect(Policy::none())
        .user_agent("FORJD-StatusProbe/1.0 (forjd-rust-probe)")
        .resolve_to_addrs(host, &addresses);
    if skip_tls_verify {
        builder = builder.danger_accept_invalid_certs(true);
    }
    let client = builder
        .build()
        .context("failed to build pinned probe HTTP client")?;
    Ok((client, url))
}

fn is_public_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(ip) => {
            !(ip.is_private()
                || ip.is_loopback()
                || ip.is_link_local()
                || ip.is_broadcast()
                || ip.is_documentation()
                || ip.is_multicast()
                || ip.is_unspecified())
        }
        IpAddr::V6(ip) => {
            if let Some(mapped) = ip.to_ipv4_mapped() {
                return is_public_ip(IpAddr::V4(mapped));
            }
            !(ip.is_loopback()
                || ip.is_unspecified()
                || ip.is_unique_local()
                || ip.is_unicast_link_local()
                || ip.is_multicast()
                || is_ipv6_documentation(ip))
        }
    }
}

fn is_ipv6_documentation(ip: std::net::Ipv6Addr) -> bool {
    let segments = ip.segments();
    segments[0] == 0x2001 && segments[1] == 0x0db8
}

async fn persist_result(pool: &PgPool, observation_key: &str, result: &PingResult) -> Result<bool> {
    let mut transaction = pool.begin().await?;
    let inserted = sqlx::query_scalar::<_, Uuid>(
        r#"
        INSERT INTO health_probe_observations
            (id, observation_key, service_id, tenant_id, url, status_code,
             response_time_ms, is_active, error, observed_at, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
        ON CONFLICT (observation_key) DO NOTHING
        RETURNING id
        "#,
    )
    .bind(Uuid::new_v4())
    .bind(observation_key)
    .bind(result.service.service_id)
    .bind(result.service.tenant_id)
    .bind(&result.service.url)
    .bind(i32::from(result.status_code))
    .bind(result.response_time_ms)
    .bind(result.is_active)
    .bind(&result.error)
    .fetch_optional(&mut *transaction)
    .await?;

    if inserted.is_none() {
        transaction.rollback().await?;
        return Ok(false);
    }

    // Reflect latest probe status onto the status service row.
    let status = if result.is_active {
        "operational"
    } else if result.status_code >= 500 {
        "major_outage"
    } else {
        "degraded"
    };
    sqlx::query(
        r#"
        UPDATE status_services
        SET status = $2, updated_at = NOW()
        WHERE id = $1
        "#,
    )
    .bind(result.service.service_id)
    .bind(status)
    .execute(&mut *transaction)
    .await?;

    transaction.commit().await?;
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::is_public_ip;
    use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};

    #[test]
    fn rejects_private_and_loopback_addresses() {
        assert!(!is_public_ip(IpAddr::V4(Ipv4Addr::new(127, 0, 0, 1))));
        assert!(!is_public_ip(IpAddr::V4(Ipv4Addr::new(10, 0, 0, 1))));
        assert!(is_public_ip(IpAddr::V4(Ipv4Addr::new(8, 8, 8, 8))));
        assert!(!is_public_ip(IpAddr::V6(Ipv6Addr::new(
            0, 0, 0, 0, 0, 0xffff, 0x7f00, 1,
        ))));
        assert!(!is_public_ip(IpAddr::V6(Ipv6Addr::new(
            0x2001, 0x0db8, 0, 0, 0, 0, 0, 1,
        ))));
    }
}
