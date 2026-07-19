//! Sealed-metadata streaming pipeline (E2EE-safe, ciphertext never enters).
//!
//! Operates only on server-visible fields: tenant_id, event_id, key_id, cipher_len,
//! content_type, event_type, workflow_id. Used by PyO3 and HTTP `/v1/sealed/pipeline`.

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use std::collections::{HashMap, HashSet};

/// Maximum events per sealed pipeline batch (DoS bound).
pub const MAX_SEALED_EVENTS: usize = 10_000;

/// Forbidden keys that must never appear in sanitized metadata (ciphertext blind).
const FORBIDDEN_KEYS: &[&str] = &[
    "ciphertext",
    "plaintext",
    "nonce",
    "ratchet_header",
    "private_key",
    "secret",
    "password",
];

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SealedPipelineRequest {
    pub events: Vec<Value>,
    #[serde(default = "default_steps")]
    pub steps: Vec<String>,
    #[serde(default)]
    pub params: Map<String, Value>,
    #[serde(default)]
    pub tags: Map<String, Value>,
    #[serde(default = "default_projection")]
    pub projection_name: String,
    #[serde(default)]
    pub workflow_id: Option<String>,
}

fn default_steps() -> Vec<String> {
    vec!["rollup".into(), "size_anomaly".into()]
}

fn default_projection() -> String {
    "sealed.default".into()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SealedMeta {
    pub event_id: String,
    pub tenant_id: String,
    pub key_id: String,
    pub cipher_len: i64,
    pub content_type: String,
    pub event_type: String,
    pub workflow_id: String,
}

// --- Sanitize: strip anything that looks like ciphertext ---
pub fn sanitize_events(events: &[Value]) -> Result<Vec<SealedMeta>, String> {
    if events.len() > MAX_SEALED_EVENTS {
        return Err(format!("events exceed max length of {MAX_SEALED_EVENTS}"));
    }
    let mut out = Vec::with_capacity(events.len());
    for e in events {
        let obj = e
            .as_object()
            .ok_or_else(|| "each event must be a JSON object".to_string())?;
        for key in FORBIDDEN_KEYS {
            if obj.contains_key(*key) {
                return Err(format!(
                    "forbidden field {key:?} in sealed pipeline input (ciphertext-blind)"
                ));
            }
        }
        out.push(SealedMeta {
            event_id: str_field(obj, "event_id"),
            tenant_id: str_field(obj, "tenant_id"),
            key_id: str_field(obj, "key_id"),
            cipher_len: int_field(obj, "cipher_len"),
            content_type: str_field(obj, "content_type"),
            event_type: str_field(obj, "event_type"),
            workflow_id: str_field(obj, "workflow_id"),
        });
    }
    Ok(out)
}

fn str_field(obj: &Map<String, Value>, key: &str) -> String {
    obj.get(key)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

fn int_field(obj: &Map<String, Value>, key: &str) -> i64 {
    obj.get(key)
        .and_then(|v| v.as_i64().or_else(|| v.as_u64().map(|u| u as i64)))
        .unwrap_or(0)
}

// --- Tenant rollup ---
pub fn rollup(events: &[SealedMeta]) -> Value {
    let mut by_tenant: HashMap<String, (i64, i64, i64)> = HashMap::new();
    for e in events {
        let slot = by_tenant.entry(e.tenant_id.clone()).or_insert((0, 0, 0));
        slot.0 += 1;
        slot.1 += e.cipher_len;
        slot.2 = slot.2.max(e.cipher_len);
    }
    let mut map = Map::new();
    for (tid, (count, bytes, max_len)) in &by_tenant {
        map.insert(
            tid.clone(),
            json!({
                "count": count,
                "bytes": bytes,
                "max_cipher_len": max_len,
            }),
        );
    }
    json!({
        "ok": true,
        "engine": "forjd-engine",
        "count": events.len(),
        "tenants": by_tenant.len(),
        "by_tenant": map,
    })
}

// --- Size anomaly (z-score + hard max) ---
pub fn size_anomaly(events: &[SealedMeta], zscore: f64, max_cipher_len: i64) -> Vec<Value> {
    if events.is_empty() {
        return vec![];
    }
    let n = events.len() as f64;
    let mean = events.iter().map(|e| e.cipher_len as f64).sum::<f64>() / n;
    let var = if events.len() > 1 {
        events
            .iter()
            .map(|e| {
                let d = e.cipher_len as f64 - mean;
                d * d
            })
            .sum::<f64>()
            / n
    } else {
        0.0
    };
    let std = var.sqrt();

    events
        .iter()
        .map(|e| {
            let clen = e.cipher_len;
            let z = if std < 1e-9 {
                0.0
            } else {
                (clen as f64 - mean) / std
            };
            let hard = clen >= max_cipher_len;
            let spike = z.abs() >= zscore && std >= 1e-9;
            let is_anom = hard || spike;
            let mut score = if std >= 1e-9 {
                z.abs()
            } else if hard {
                1.0
            } else {
                0.0
            };
            if hard && max_cipher_len > 0 {
                score = score.max(clen as f64 / max_cipher_len as f64);
            }
            let reason = if hard {
                "max_cipher_len"
            } else if spike {
                "z_score"
            } else {
                "ok"
            };
            json!({
                "event_id": e.event_id,
                "tenant_id": e.tenant_id,
                "key_id": e.key_id,
                "cipher_len": clen,
                "z_score": (z * 10000.0).round() / 10000.0,
                "score": (score * 10000.0).round() / 10000.0,
                "is_anomaly": is_anom,
                "detector": "size_anomaly",
                "reason": reason,
            })
        })
        .collect()
}

// --- Rate anomaly (batch-scoped burst) ---
pub fn rate_anomaly(events: &[SealedMeta], max_events: i64) -> Vec<Value> {
    if events.is_empty() {
        return vec![];
    }
    let mut counts: HashMap<String, i64> = HashMap::new();
    for e in events {
        *counts.entry(e.tenant_id.clone()).or_insert(0) += 1;
    }
    let max_events = max_events.max(1);
    events
        .iter()
        .map(|e| {
            let n = *counts.get(&e.tenant_id).unwrap_or(&0);
            let is_anom = n >= max_events;
            let score = n as f64 / max_events as f64;
            json!({
                "event_id": e.event_id,
                "tenant_id": e.tenant_id,
                "key_id": e.key_id,
                "cipher_len": e.cipher_len,
                "batch_count": n,
                "score": (score * 10000.0).round() / 10000.0,
                "is_anomaly": is_anom,
                "detector": "rate_anomaly",
                "reason": if is_anom { "batch_rate" } else { "ok" },
            })
        })
        .collect()
}

fn fparam(params: &Map<String, Value>, step: &str, key: &str, default: f64) -> f64 {
    params
        .get(step)
        .and_then(|v| v.get(key))
        .and_then(|v| v.as_f64())
        .or_else(|| params.get(key).and_then(|v| v.as_f64()))
        .unwrap_or(default)
}

fn iparam(params: &Map<String, Value>, step: &str, key: &str, default: i64) -> i64 {
    params
        .get(step)
        .and_then(|v| v.get(key))
        .and_then(|v| v.as_i64())
        .or_else(|| params.get(key).and_then(|v| v.as_i64()))
        .unwrap_or(default)
}

// --- Full pipeline → stream_results-shaped rows ---
pub fn run_sealed_pipeline(req: SealedPipelineRequest) -> Result<Value, String> {
    let sanitized = sanitize_events(&req.events)?;
    let step_set: HashSet<&str> = req.steps.iter().map(|s| s.as_str()).collect();

    let rollup_out = if step_set.contains("rollup") {
        rollup(&sanitized)
    } else {
        json!({
            "ok": true,
            "engine": "forjd-engine",
            "count": sanitized.len(),
            "tenants": sanitized.iter().map(|e| e.tenant_id.as_str()).collect::<HashSet<_>>().len(),
            "by_tenant": {},
        })
    };

    let mut anomalies: Vec<Value> = Vec::new();
    if step_set.contains("size_anomaly") {
        let z = fparam(&req.params, "size_anomaly", "zscore", 2.5);
        let max_len = iparam(&req.params, "size_anomaly", "max_cipher_len", 262_144);
        anomalies.extend(size_anomaly(&sanitized, z, max_len));
    }
    if step_set.contains("rate_anomaly") {
        let max_events = iparam(&req.params, "rate_anomaly", "max_events", 500);
        anomalies.extend(rate_anomaly(&sanitized, max_events));
    }

    let mut tags = req.tags.clone();
    if let Some(ref wid) = req.workflow_id {
        tags.entry("workflow_id".to_string())
            .or_insert_with(|| json!(wid));
    }
    tags.entry("projection_name".to_string())
        .or_insert_with(|| json!(req.projection_name.clone()));

    let results = to_stream_result_rows(
        &rollup_out,
        &anomalies,
        &tags,
        &step_set,
        &req.projection_name,
    );
    let anomaly_count = anomalies
        .iter()
        .filter(|a| {
            a.get("is_anomaly")
                .and_then(|v| v.as_bool())
                .unwrap_or(false)
        })
        .count();

    Ok(json!({
        "ok": true,
        "engine": "forjd-engine",
        "count": rollup_out.get("count").cloned().unwrap_or(json!(sanitized.len())),
        "tenants": rollup_out.get("tenants").cloned().unwrap_or(json!(0)),
        "by_tenant": rollup_out.get("by_tenant").cloned().unwrap_or(json!({})),
        "anomalies": anomalies,
        "results": results,
        "anomaly_count": anomaly_count,
        "workflow_id": req.workflow_id,
        "projection_name": req.projection_name,
    }))
}

fn to_stream_result_rows(
    rollup: &Value,
    anomalies: &[Value],
    tags: &Map<String, Value>,
    steps: &HashSet<&str>,
    projection_name: &str,
) -> Vec<Value> {
    let engine = "forjd-engine";
    let mut rows = Vec::new();
    let mut base_meta = Map::new();
    base_meta.insert("source".into(), json!("forjd-ingest"));
    for (k, v) in tags {
        base_meta.insert(k.clone(), v.clone());
    }

    if steps.contains("rollup")
        && let Some(by_tenant) = rollup.get("by_tenant").and_then(|v| v.as_object())
    {
        for (tid, stats) in by_tenant {
            rows.push(json!({
                "tenant_id": tid,
                "telemetry_event_id": null,
                "source_event_id": null,
                "kind": "rollup",
                "engine": engine,
                "score": null,
                "is_anomaly": false,
                "projection_name": projection_name,
                "features": {
                    "count": stats.get("count"),
                    "bytes": stats.get("bytes"),
                    "max_cipher_len": stats.get("max_cipher_len"),
                },
                "metadata": base_meta.clone(),
                "workflow_id": tags.get("workflow_id"),
            }));
        }
    }

    for a in anomalies {
        let eid = a.get("event_id").and_then(|v| v.as_str()).unwrap_or("");
        let eid_val = if eid.is_empty() {
            Value::Null
        } else {
            json!(eid)
        };
        rows.push(json!({
            "tenant_id": a.get("tenant_id"),
            "telemetry_event_id": eid_val,
            "source_event_id": eid_val,
            "kind": if a.get("is_anomaly").and_then(|v| v.as_bool()).unwrap_or(false) {
                "anomaly"
            } else {
                "transform"
            },
            "engine": engine,
            "score": a.get("score"),
            "is_anomaly": a.get("is_anomaly"),
            "projection_name": projection_name,
            "features": {
                "key_id": a.get("key_id"),
                "cipher_len": a.get("cipher_len"),
                "z_score": a.get("z_score"),
                "batch_count": a.get("batch_count"),
                "detector": a.get("detector"),
                "reason": a.get("reason"),
            },
            "metadata": base_meta.clone(),
            "workflow_id": tags.get("workflow_id"),
        }));
    }
    rows
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_ciphertext_field() {
        let events = vec![json!({"tenant_id": "t", "ciphertext": "abc"})];
        assert!(sanitize_events(&events).is_err());
    }

    #[test]
    fn size_anomaly_flags_hard_max() {
        let events = vec![
            SealedMeta {
                event_id: "1".into(),
                tenant_id: "t".into(),
                key_id: "k".into(),
                cipher_len: 10,
                content_type: "".into(),
                event_type: "".into(),
                workflow_id: "".into(),
            },
            SealedMeta {
                event_id: "2".into(),
                tenant_id: "t".into(),
                key_id: "k".into(),
                cipher_len: 100_000,
                content_type: "".into(),
                event_type: "".into(),
                workflow_id: "".into(),
            },
        ];
        let out = size_anomaly(&events, 99.0, 1000);
        assert!(out[1]["is_anomaly"].as_bool().unwrap());
    }

    #[test]
    fn rate_anomaly_flags_burst() {
        let events: Vec<_> = (0..5)
            .map(|i| SealedMeta {
                event_id: format!("e{i}"),
                tenant_id: "t".into(),
                key_id: "k".into(),
                cipher_len: 1,
                content_type: "".into(),
                event_type: "".into(),
                workflow_id: "".into(),
            })
            .collect();
        let out = rate_anomaly(&events, 3);
        assert!(out.iter().all(|r| r["is_anomaly"].as_bool().unwrap()));
    }

    #[test]
    fn pipeline_ok() {
        let req = SealedPipelineRequest {
            events: vec![json!({
                "event_id": "e1",
                "tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "key_id": "sess",
                "cipher_len": 128,
            })],
            steps: vec!["rollup".into(), "size_anomaly".into()],
            params: Map::new(),
            tags: Map::new(),
            projection_name: "sealed.default".into(),
            workflow_id: Some("default_sealed".into()),
        };
        let out = run_sealed_pipeline(req).unwrap();
        assert_eq!(out["engine"], "forjd-engine");
        assert_eq!(out["count"], 1);
        assert!(!out["results"].as_array().unwrap().is_empty());
    }
}
