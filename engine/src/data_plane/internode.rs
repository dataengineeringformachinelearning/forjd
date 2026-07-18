//! Authenticated application-layer encryption for durable internode messages (AES-256-GCM).

use std::{
    collections::HashMap,
    env,
    time::{SystemTime, UNIX_EPOCH},
};

use aes_gcm::{
    aead::{Aead, AeadCore, KeyInit, OsRng, Payload},
    Aes256Gcm, Nonce,
};
use anyhow::{bail, Context, Result};
use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

// --- Envelope constants (security boundary) ---
const ENVELOPE_TYPE: &str = "forjd-internode+jwe";
const ENVELOPE_VERSION: u8 = 1;
const ALGORITHM: &str = "dir";
const CONTENT_ENCRYPTION: &str = "A256GCM";
const MAX_CLOCK_SKEW_SECONDS: i64 = 300;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Mode {
    Disabled,
    Optional,
    Required,
}

#[derive(Clone, Debug)]
struct Keyring {
    mode: Mode,
    active_kid: Option<String>,
    keys: HashMap<String, [u8; 32]>,
    sender: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct Envelope {
    typ: String,
    v: u8,
    kid: String,
    alg: String,
    enc: String,
    ctx: String,
    sender: String,
    iat: i64,
    jti: String,
    nonce: String,
    ciphertext: String,
}

fn valid_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"._:/-".contains(&byte))
}

fn validate_identifier(name: &str, value: &str) -> Result<()> {
    if !valid_identifier(value) {
        bail!("{name} contains invalid characters or has an invalid length");
    }
    Ok(())
}

fn is_production() -> bool {
    if env::var("FORJD_ENV")
        .map(|value| value.eq_ignore_ascii_case("production"))
        .unwrap_or(false)
    {
        return true;
    }
    env::var("FLY_APP_NAME").is_ok()
}

fn load_keyring() -> Result<Keyring> {
    let production = is_production();
    let default_mode = if production { "required" } else { "disabled" };
    let mode = match env::var("FORJD_INTERNODE_ENCRYPTION")
        .unwrap_or_else(|_| default_mode.to_string())
        .to_ascii_lowercase()
        .as_str()
    {
        "disabled" => Mode::Disabled,
        "optional" => Mode::Optional,
        "required" => Mode::Required,
        _ => bail!("FORJD_INTERNODE_ENCRYPTION must be disabled, optional, or required"),
    };
    let sender = env::var("FORJD_NODE_ID")
        .or_else(|_| env::var("FLY_APP_NAME"))
        .unwrap_or_else(|_| "forjd-local".to_string());
    validate_identifier("FORJD_NODE_ID", &sender)?;
    let active_kid = env::var("FORJD_INTERNODE_ACTIVE_KID")
        .ok()
        .filter(|value| !value.trim().is_empty());
    let raw_keys = env::var("FORJD_INTERNODE_KEYS").unwrap_or_else(|_| "{}".to_string());
    let encoded_keys: HashMap<String, String> =
        serde_json::from_str(&raw_keys).context("FORJD_INTERNODE_KEYS must be a JSON object")?;
    let mut keys = HashMap::with_capacity(encoded_keys.len());
    for (kid, encoded) in encoded_keys {
        validate_identifier("internode kid", &kid)?;
        let decoded = URL_SAFE_NO_PAD
            .decode(encoded)
            .with_context(|| format!("internode key {kid:?} is not valid base64url"))?;
        let key: [u8; 32] = decoded
            .try_into()
            .map_err(|_| anyhow::anyhow!("internode key {kid:?} must decode to 32 bytes"))?;
        keys.insert(kid, key);
    }
    if let Some(kid) = active_kid.as_deref() {
        validate_identifier("FORJD_INTERNODE_ACTIVE_KID", kid)?;
        if !keys.contains_key(kid) {
            bail!("FORJD_INTERNODE_ACTIVE_KID is not present in FORJD_INTERNODE_KEYS");
        }
    }
    if mode == Mode::Required && active_kid.is_none() {
        bail!(
            "required internode encryption needs FORJD_INTERNODE_ACTIVE_KID and \
             FORJD_INTERNODE_KEYS={{\"kid\":\"<base64url-32-bytes>\"}} \
             (set via ./scripts/sync_engine_dataplane_secrets.sh or fly secrets set)"
        );
    }
    Ok(Keyring {
        mode,
        active_kid,
        keys,
        sender,
    })
}

fn aad(envelope: &Envelope) -> Vec<u8> {
    [
        envelope.typ.as_str(),
        &envelope.v.to_string(),
        envelope.kid.as_str(),
        envelope.alg.as_str(),
        envelope.enc.as_str(),
        envelope.ctx.as_str(),
        envelope.sender.as_str(),
        &envelope.iat.to_string(),
        envelope.jti.as_str(),
    ]
    .join("\n")
    .into_bytes()
}

fn unix_timestamp() -> Result<i64> {
    Ok(SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .context("system clock is before the Unix epoch")?
        .as_secs() as i64)
}

fn encrypt_with(
    plaintext: &[u8],
    context: &str,
    keyring: &Keyring,
    issued_at: i64,
    message_id: Uuid,
    nonce: [u8; 12],
) -> Result<Vec<u8>> {
    if keyring.mode == Mode::Disabled {
        return Ok(plaintext.to_vec());
    }
    validate_identifier("internode context", context)?;
    let Some(kid) = keyring.active_kid.as_deref() else {
        if keyring.mode == Mode::Optional {
            return Ok(plaintext.to_vec());
        }
        bail!("internode encryption has no active key");
    };
    let key = keyring
        .keys
        .get(kid)
        .context("internode encryption active key is unavailable")?;
    let mut envelope = Envelope {
        typ: ENVELOPE_TYPE.to_string(),
        v: ENVELOPE_VERSION,
        kid: kid.to_string(),
        alg: ALGORITHM.to_string(),
        enc: CONTENT_ENCRYPTION.to_string(),
        ctx: context.to_string(),
        sender: keyring.sender.clone(),
        iat: issued_at,
        jti: message_id.to_string(),
        nonce: URL_SAFE_NO_PAD.encode(nonce),
        ciphertext: String::new(),
    };
    let cipher = Aes256Gcm::new_from_slice(key).context("invalid AES-256-GCM key")?;
    let ciphertext = cipher
        .encrypt(
            Nonce::from_slice(&nonce),
            Payload {
                msg: plaintext,
                aad: &aad(&envelope),
            },
        )
        .map_err(|_| anyhow::anyhow!("internode encryption failed"))?;
    envelope.ciphertext = URL_SAFE_NO_PAD.encode(ciphertext);
    serde_json::to_vec(&envelope).context("failed to serialize internode envelope")
}

fn decrypt_with(value: &[u8], context: &str, keyring: &Keyring, now: i64) -> Result<Vec<u8>> {
    if keyring.mode == Mode::Disabled {
        return Ok(value.to_vec());
    }
    let envelope = serde_json::from_slice::<Envelope>(value);
    let Ok(envelope) = envelope else {
        if keyring.mode == Mode::Optional {
            return Ok(value.to_vec());
        }
        bail!("plaintext internode message rejected in required mode");
    };
    if envelope.typ != ENVELOPE_TYPE {
        if keyring.mode == Mode::Optional {
            return Ok(value.to_vec());
        }
        bail!("plaintext internode message rejected in required mode");
    }
    if envelope.v != ENVELOPE_VERSION
        || envelope.alg != ALGORITHM
        || envelope.enc != CONTENT_ENCRYPTION
    {
        bail!("unsupported internode envelope algorithm or version");
    }
    validate_identifier("internode context", context)?;
    if envelope.ctx != context {
        bail!("internode envelope context mismatch");
    }
    validate_identifier("internode kid", &envelope.kid)?;
    validate_identifier("internode sender", &envelope.sender)?;
    Uuid::parse_str(&envelope.jti).context("internode envelope message id is invalid")?;
    if envelope.iat > now + MAX_CLOCK_SKEW_SECONDS {
        bail!("internode envelope timestamp is in the future");
    }
    let key = keyring
        .keys
        .get(&envelope.kid)
        .with_context(|| format!("internode key {:?} is not available", envelope.kid))?;
    let nonce = URL_SAFE_NO_PAD
        .decode(&envelope.nonce)
        .context("internode envelope nonce is invalid")?;
    if nonce.len() != 12 {
        bail!("internode envelope nonce must be 12 bytes");
    }
    let ciphertext = URL_SAFE_NO_PAD
        .decode(&envelope.ciphertext)
        .context("internode envelope ciphertext is invalid")?;
    let cipher = Aes256Gcm::new_from_slice(key).context("invalid AES-256-GCM key")?;
    cipher
        .decrypt(
            Nonce::from_slice(&nonce),
            Payload {
                msg: &ciphertext,
                aad: &aad(&envelope),
            },
        )
        .map_err(|_| anyhow::anyhow!("internode envelope authentication failed"))
}

pub fn validate_configuration() -> Result<()> {
    load_keyring().map(|_| ())
}

/// Encrypt a Dragonfly Streams payload (context bound to stream name).
pub fn encrypt_bus_value(value: &[u8], stream: &str) -> Result<Vec<u8>> {
    let nonce = Aes256Gcm::generate_nonce(&mut OsRng);
    encrypt_with(
        value,
        &format!("stream:{stream}"),
        &load_keyring()?,
        unix_timestamp()?,
        Uuid::new_v4(),
        nonce.into(),
    )
}

/// Decrypt a Dragonfly Streams payload.
pub fn decrypt_bus_value(value: &[u8], stream: &str) -> Result<Vec<u8>> {
    decrypt_with(
        value,
        &format!("stream:{stream}"),
        &load_keyring()?,
        unix_timestamp()?,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn keyring(mode: Mode) -> Keyring {
        Keyring {
            mode,
            active_kid: Some("test-2026-07".to_string()),
            keys: HashMap::from([("test-2026-07".to_string(), std::array::from_fn(|i| i as u8))]),
            sender: "test-node".to_string(),
        }
    }

    #[test]
    fn round_trips_and_rejects_context_swaps() {
        let encrypted = encrypt_with(
            br#"{"tenant":"00000000-0000-0000-0000-000000000001"}"#,
            "stream:app-events",
            &keyring(Mode::Required),
            1_783_728_000,
            Uuid::parse_str("12345678-1234-5678-1234-567812345678").unwrap(),
            std::array::from_fn(|i| i as u8),
        )
        .unwrap();
        assert_eq!(
            decrypt_with(
                &encrypted,
                "stream:app-events",
                &keyring(Mode::Required),
                1_783_728_000,
            )
            .unwrap(),
            br#"{"tenant":"00000000-0000-0000-0000-000000000001"}"#
        );
        assert!(decrypt_with(
            &encrypted,
            "stream:user-issues",
            &keyring(Mode::Required),
            1_783_728_000,
        )
        .is_err());
    }

    #[test]
    fn required_mode_rejects_plaintext_downgrades() {
        assert!(decrypt_with(
            br#"{"legacy":true}"#,
            "stream:app-events",
            &keyring(Mode::Required),
            1_783_728_000,
        )
        .is_err());
    }
}
