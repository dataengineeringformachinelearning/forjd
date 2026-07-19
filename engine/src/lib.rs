//! FORJD engine — validate/enrich events and summarize numeric batches via Arrow/Parquet.
//!
//! - Library / Python: `forjd_engine` (PyO3 / maturin) when built with `--features python`
//! - HTTP service: `forjd-engine` binary when built with `--features server`
//! - Data plane: outbox / ingest / probes when built with `--features data-plane`

#[cfg(feature = "data-plane")]
pub mod data_plane;

/// Sealed-metadata pipeline (rollup + detectors) — E2EE-safe, always available.
pub mod pipeline;

use arrow::array::{Float64Array, Int64Array, StringArray};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;
use bytes::Bytes;
use parquet::arrow::ArrowWriter;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use thiserror::Error;

/// Wire schema version for processed events (bump when payload shape changes).
pub const SCHEMA_VERSION: u32 = 1;
/// Maximum accepted event id length.
pub const MAX_EVENT_ID_LEN: usize = 128;
/// Maximum values in a summarize batch (DoS bound).
pub const MAX_VALUES: usize = 10_000;
/// Maximum JSON payload depth when scanning nested numbers (defense in depth).
pub const MAX_PAYLOAD_DEPTH: usize = 8;

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum EngineError {
    #[error("id must not be empty")]
    EmptyId,
    #[error("id exceeds {MAX_EVENT_ID_LEN} characters")]
    IdTooLong,
    #[error("id contains invalid characters (use printable ASCII without control chars)")]
    IdInvalidChars,
    #[error("timestamp must be non-negative")]
    NegativeTimestamp,
    #[error("values must not be empty")]
    EmptyValues,
    #[error("values exceed max length of {MAX_VALUES}")]
    TooManyValues,
    #[error("values must be finite (no NaN/Inf)")]
    NonFiniteValue,
    #[error("payload nesting exceeds max depth of {MAX_PAYLOAD_DEPTH}")]
    PayloadTooDeep,
    #[error("columnar I/O error: {0}")]
    Columnar(String),
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    pub id: String,
    pub timestamp: i64,
    pub payload: serde_json::Value,
}

/// Validated + enriched event returned by [`process_event`].
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessedEvent {
    pub id: String,
    pub timestamp: i64,
    pub payload: serde_json::Value,
    pub engine: String,
    pub engine_version: String,
    pub schema_version: u32,
    pub processed_at: i64,
}

fn now_unix_secs() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

fn validate_id(id: &str) -> Result<(), EngineError> {
    if id.is_empty() {
        return Err(EngineError::EmptyId);
    }
    if id.len() > MAX_EVENT_ID_LEN {
        return Err(EngineError::IdTooLong);
    }
    if !id.chars().all(|c| c.is_ascii_graphic() || c == ' ') {
        return Err(EngineError::IdInvalidChars);
    }
    Ok(())
}

fn assert_finite_json(value: &serde_json::Value, depth: usize) -> Result<(), EngineError> {
    if depth > MAX_PAYLOAD_DEPTH {
        return Err(EngineError::PayloadTooDeep);
    }
    match value {
        serde_json::Value::Number(n) => {
            if let Some(f) = n.as_f64()
                && !f.is_finite()
            {
                return Err(EngineError::NonFiniteValue);
            }
            Ok(())
        }
        serde_json::Value::Array(items) => {
            for item in items {
                assert_finite_json(item, depth + 1)?;
            }
            Ok(())
        }
        serde_json::Value::Object(map) => {
            for v in map.values() {
                assert_finite_json(v, depth + 1)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

/// Validate and enrich a single event (schema checks + engine metadata).
pub fn process_event(event: Event) -> Result<ProcessedEvent, EngineError> {
    validate_id(&event.id)?;
    if event.timestamp < 0 {
        return Err(EngineError::NegativeTimestamp);
    }
    assert_finite_json(&event.payload, 0)?;

    let processed_at = now_unix_secs();
    tracing::info!(id = %event.id, schema_version = SCHEMA_VERSION, "engine processed event");

    Ok(ProcessedEvent {
        id: event.id,
        timestamp: event.timestamp,
        payload: event.payload,
        engine: "forjd-engine".into(),
        engine_version: engine_version().into(),
        schema_version: SCHEMA_VERSION,
        processed_at,
    })
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SummarizeResult {
    pub count: usize,
    pub sum: f64,
    pub mean: f64,
    pub min: f64,
    pub max: f64,
    pub parquet_bytes: usize,
}

/// Reject empty / oversized / non-finite batches before columnar work.
pub fn validate_values(values: &[f64]) -> Result<(), EngineError> {
    if values.is_empty() {
        return Err(EngineError::EmptyValues);
    }
    if values.len() > MAX_VALUES {
        return Err(EngineError::TooManyValues);
    }
    if values.iter().any(|v| !v.is_finite()) {
        return Err(EngineError::NonFiniteValue);
    }
    Ok(())
}

/// Summarize values with an Arrow → Parquet → Arrow round-trip (columnar I/O PoC).
pub fn summarize_values(values: &[f64]) -> Result<SummarizeResult, EngineError> {
    validate_values(values)?;

    let schema = Arc::new(Schema::new(vec![
        Field::new("idx", DataType::Int64, false),
        Field::new("value", DataType::Float64, false),
        Field::new("label", DataType::Utf8, false),
    ]));

    let idx: Int64Array = (0..values.len() as i64).collect();
    let vals = Float64Array::from(values.to_vec());
    let labels = StringArray::from(
        values
            .iter()
            .enumerate()
            .map(|(i, _)| format!("v{i}"))
            .collect::<Vec<_>>(),
    );

    let batch = RecordBatch::try_new(
        schema.clone(),
        vec![Arc::new(idx), Arc::new(vals), Arc::new(labels)],
    )
    .map_err(|e| EngineError::Columnar(e.to_string()))?;

    let mut buffer: Vec<u8> = Vec::new();
    {
        let mut writer = ArrowWriter::try_new(&mut buffer, schema, None)
            .map_err(|e| EngineError::Columnar(e.to_string()))?;
        writer
            .write(&batch)
            .map_err(|e| EngineError::Columnar(e.to_string()))?;
        writer
            .close()
            .map_err(|e| EngineError::Columnar(e.to_string()))?;
    }
    let parquet_bytes = buffer.len();

    let reader = ParquetRecordBatchReaderBuilder::try_new(Bytes::from(buffer))
        .map_err(|e| EngineError::Columnar(e.to_string()))?
        .build()
        .map_err(|e| EngineError::Columnar(e.to_string()))?;

    let mut count: usize = 0;
    let mut sum = 0.0_f64;
    let mut min = f64::INFINITY;
    let mut max = f64::NEG_INFINITY;
    for batch in reader {
        let batch = batch.map_err(|e| EngineError::Columnar(e.to_string()))?;
        let col = batch
            .column(1)
            .as_any()
            .downcast_ref::<Float64Array>()
            .ok_or_else(|| EngineError::Columnar("expected float64 value column".into()))?;
        for i in 0..col.len() {
            let v = col.value(i);
            sum += v;
            min = min.min(v);
            max = max.max(v);
            count += 1;
        }
    }

    let mean = sum / count as f64;
    Ok(SummarizeResult {
        count,
        sum,
        mean,
        min,
        max,
        parquet_bytes,
    })
}

/// Crate version string (shared by Python bindings and HTTP service).
pub fn engine_version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Constant-time compare for API tokens (empty configured token → auth disabled).
pub fn token_matches(configured: Option<&str>, provided: Option<&str>) -> bool {
    match configured {
        None | Some("") => true,
        Some(expected) => {
            let Some(got) = provided else {
                return false;
            };
            use subtle::ConstantTimeEq;
            if expected.len() != got.len() {
                return false;
            }
            expected.as_bytes().ct_eq(got.as_bytes()).into()
        }
    }
}

#[cfg(feature = "python")]
mod python_api {
    use super::*;
    use pyo3::IntoPyObjectExt;
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;
    use pyo3::types::{PyDict, PyList};

    fn engine_err(err: EngineError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }

    #[pyfunction]
    fn process_event_py(py: Python<'_>, event: Bound<'_, PyDict>) -> PyResult<Py<PyAny>> {
        let id: String = event
            .get_item("id")?
            .ok_or_else(|| PyValueError::new_err("missing id"))?
            .extract()?;
        let timestamp: i64 = event
            .get_item("timestamp")?
            .ok_or_else(|| PyValueError::new_err("missing timestamp"))?
            .extract()?;
        let payload_obj = event
            .get_item("payload")?
            .ok_or_else(|| PyValueError::new_err("missing payload"))?;
        let payload: serde_json::Value = pythonize_value(&payload_obj)?;

        let processed = process_event(Event {
            id,
            timestamp,
            payload,
        })
        .map_err(engine_err)?;

        let out = PyDict::new(py);
        out.set_item("id", processed.id)?;
        out.set_item("timestamp", processed.timestamp)?;
        out.set_item("payload", json_to_py(py, &processed.payload)?)?;
        out.set_item("engine", processed.engine)?;
        out.set_item("engine_version", processed.engine_version)?;
        out.set_item("schema_version", processed.schema_version)?;
        out.set_item("processed_at", processed.processed_at)?;
        Ok(out.into_any().unbind())
    }

    #[pyfunction]
    fn summarize_values_py(values: Vec<f64>) -> PyResult<SummarizeResultPy> {
        let result = summarize_values(&values).map_err(engine_err)?;
        Ok(SummarizeResultPy {
            count: result.count,
            sum: result.sum,
            mean: result.mean,
            min: result.min,
            max: result.max,
            parquet_bytes: result.parquet_bytes,
        })
    }

    #[pyfunction(name = "engine_version")]
    fn engine_version_py() -> &'static str {
        engine_version()
    }

    #[pyclass]
    struct SummarizeResultPy {
        #[pyo3(get)]
        count: usize,
        #[pyo3(get)]
        sum: f64,
        #[pyo3(get)]
        mean: f64,
        #[pyo3(get)]
        min: f64,
        #[pyo3(get)]
        max: f64,
        #[pyo3(get)]
        parquet_bytes: usize,
    }

    #[pymethods]
    impl SummarizeResultPy {
        fn as_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
            let d = PyDict::new(py);
            d.set_item("count", self.count)?;
            d.set_item("sum", self.sum)?;
            d.set_item("mean", self.mean)?;
            d.set_item("min", self.min)?;
            d.set_item("max", self.max)?;
            d.set_item("parquet_bytes", self.parquet_bytes)?;
            Ok(d)
        }
    }

    fn pythonize_value(obj: &Bound<'_, PyAny>) -> PyResult<serde_json::Value> {
        if obj.is_none() {
            return Ok(serde_json::Value::Null);
        }
        if let Ok(b) = obj.extract::<bool>() {
            return Ok(serde_json::Value::Bool(b));
        }
        if let Ok(i) = obj.extract::<i64>() {
            return Ok(serde_json::json!(i));
        }
        if let Ok(f) = obj.extract::<f64>() {
            return Ok(serde_json::json!(f));
        }
        if let Ok(s) = obj.extract::<String>() {
            return Ok(serde_json::Value::String(s));
        }
        if let Ok(dict) = obj.cast::<PyDict>() {
            let mut map = serde_json::Map::new();
            for (k, v) in dict.iter() {
                let key: String = k.extract()?;
                map.insert(key, pythonize_value(&v)?);
            }
            return Ok(serde_json::Value::Object(map));
        }
        if let Ok(list) = obj.cast::<PyList>() {
            let mut arr = Vec::with_capacity(list.len());
            for item in list.iter() {
                arr.push(pythonize_value(&item)?);
            }
            return Ok(serde_json::Value::Array(arr));
        }
        Ok(serde_json::Value::String(obj.str()?.to_string()))
    }

    fn json_to_py(py: Python<'_>, value: &serde_json::Value) -> PyResult<Py<PyAny>> {
        match value {
            serde_json::Value::Null => Ok(py.None()),
            serde_json::Value::Bool(b) => b.into_py_any(py),
            serde_json::Value::Number(n) => {
                if let Some(i) = n.as_i64() {
                    i.into_py_any(py)
                } else if let Some(f) = n.as_f64() {
                    f.into_py_any(py)
                } else {
                    n.to_string().into_py_any(py)
                }
            }
            serde_json::Value::String(s) => s.as_str().into_py_any(py),
            serde_json::Value::Array(arr) => {
                let list = PyList::empty(py);
                for item in arr {
                    list.append(json_to_py(py, item)?)?;
                }
                Ok(list.into_any().unbind())
            }
            serde_json::Value::Object(map) => {
                let dict = PyDict::new(py);
                for (k, v) in map {
                    dict.set_item(k, json_to_py(py, v)?)?;
                }
                Ok(dict.into_any().unbind())
            }
        }
    }

    /// Run sealed-metadata pipeline (ciphertext-blind). Prefer this for ingest/project.
    #[pyfunction]
    #[pyo3(name = "run_sealed_pipeline", signature = (events, steps=None, params=None, tags=None, projection_name=None, workflow_id=None))]
    fn run_sealed_pipeline_py(
        py: Python<'_>,
        events: Bound<'_, PyAny>,
        steps: Option<Bound<'_, PyAny>>,
        params: Option<Bound<'_, PyAny>>,
        tags: Option<Bound<'_, PyAny>>,
        projection_name: Option<String>,
        workflow_id: Option<String>,
    ) -> PyResult<Py<PyAny>> {
        let events_json = pythonize_value(&events)?;
        let events_vec = events_json
            .as_array()
            .cloned()
            .ok_or_else(|| PyValueError::new_err("events must be a list"))?;

        let steps_vec: Vec<String> = if let Some(s) = steps {
            match pythonize_value(&s)? {
                serde_json::Value::Array(arr) => arr
                    .into_iter()
                    .filter_map(|v| v.as_str().map(str::to_string))
                    .collect(),
                _ => {
                    return Err(PyValueError::new_err("steps must be a list of strings"));
                }
            }
        } else {
            vec!["rollup".into(), "size_anomaly".into()]
        };

        let params_map = if let Some(p) = params {
            match pythonize_value(&p)? {
                serde_json::Value::Object(m) => m,
                _ => return Err(PyValueError::new_err("params must be a dict")),
            }
        } else {
            serde_json::Map::new()
        };
        let tags_map = if let Some(t) = tags {
            match pythonize_value(&t)? {
                serde_json::Value::Object(m) => m,
                _ => return Err(PyValueError::new_err("tags must be a dict")),
            }
        } else {
            serde_json::Map::new()
        };

        let req = crate::pipeline::SealedPipelineRequest {
            events: events_vec,
            steps: steps_vec,
            params: params_map,
            tags: tags_map,
            projection_name: projection_name.unwrap_or_else(|| "sealed.default".into()),
            workflow_id,
        };
        let out = crate::pipeline::run_sealed_pipeline(req).map_err(PyValueError::new_err)?;
        json_to_py(py, &out)
    }

    #[pymodule]
    fn forjd_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
        m.add_function(wrap_pyfunction!(process_event_py, m)?)?;
        m.add_function(wrap_pyfunction!(summarize_values_py, m)?)?;
        m.add_function(wrap_pyfunction!(engine_version_py, m)?)?;
        m.add_function(wrap_pyfunction!(run_sealed_pipeline_py, m)?)?;
        m.add_class::<SummarizeResultPy>()?;
        m.add("process_event", m.getattr("process_event_py")?)?;
        m.add("summarize_values", m.getattr("summarize_values_py")?)?;
        m.add("run_sealed_pipeline", m.getattr("run_sealed_pipeline_py")?)?;
        m.add("SCHEMA_VERSION", SCHEMA_VERSION)?;
        m.add("MAX_VALUES", MAX_VALUES)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_process_event_ok() {
        let event = Event {
            id: "test-1".to_string(),
            timestamp: 1_700_000_000,
            payload: serde_json::json!({"value": 42}),
        };
        let result = process_event(event).unwrap();
        assert_eq!(result.id, "test-1");
        assert_eq!(result.engine, "forjd-engine");
        assert_eq!(result.schema_version, SCHEMA_VERSION);
        assert_eq!(result.engine_version, engine_version());
        assert!(result.processed_at > 0);
    }

    #[test]
    fn test_process_event_rejects_empty_id() {
        let event = Event {
            id: "".into(),
            timestamp: 1,
            payload: serde_json::json!({}),
        };
        assert_eq!(process_event(event).unwrap_err(), EngineError::EmptyId);
    }

    #[test]
    fn test_process_event_rejects_control_chars() {
        let event = Event {
            id: "bad\nid".into(),
            timestamp: 1,
            payload: serde_json::json!({}),
        };
        assert_eq!(
            process_event(event).unwrap_err(),
            EngineError::IdInvalidChars
        );
    }

    #[test]
    fn test_summarize_values() {
        let result = summarize_values(&[1.0, 2.0, 3.0]).unwrap();
        assert_eq!(result.count, 3);
        assert!((result.sum - 6.0).abs() < f64::EPSILON);
        assert!((result.mean - 2.0).abs() < f64::EPSILON);
        assert!((result.min - 1.0).abs() < f64::EPSILON);
        assert!((result.max - 3.0).abs() < f64::EPSILON);
        assert!(result.parquet_bytes > 0);
    }

    #[test]
    fn test_summarize_rejects_nan() {
        assert_eq!(
            summarize_values(&[1.0, f64::NAN]).unwrap_err(),
            EngineError::NonFiniteValue
        );
    }

    #[test]
    fn test_summarize_rejects_empty() {
        assert_eq!(summarize_values(&[]).unwrap_err(), EngineError::EmptyValues);
    }

    #[test]
    fn test_engine_version() {
        assert_eq!(engine_version(), "0.3.0");
    }

    #[test]
    fn test_token_matches() {
        assert!(token_matches(None, None));
        assert!(token_matches(Some(""), Some("anything")));
        assert!(token_matches(Some("secret"), Some("secret")));
        assert!(!token_matches(Some("secret"), Some("wrong")));
        assert!(!token_matches(Some("secret"), None));
    }
}
