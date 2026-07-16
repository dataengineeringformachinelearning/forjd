//! FORJD engine — process events and summarize numeric batches via Arrow/Parquet.
//! Exposed to Python as `forjd_engine` (PyO3 / maturin).

use arrow::array::{Float64Array, Int64Array, StringArray};
use arrow::datatypes::{DataType, Field, Schema};
use arrow::record_batch::RecordBatch;
use bytes::Bytes;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use parquet::arrow::ArrowWriter;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3::IntoPyObjectExt;
use serde::{Deserialize, Serialize};
use std::sync::Arc;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    pub id: String,
    pub timestamp: i64,
    pub payload: serde_json::Value,
}

/// Process a single event (placeholder for heavier engine work later).
pub fn process_event(event: Event) -> Event {
    tracing::info!(id = %event.id, "engine processed event");
    event
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SummarizeResult {
    pub count: usize,
    pub sum: f64,
    pub mean: f64,
    pub parquet_bytes: usize,
}

/// Summarize values with an Arrow → Parquet → Arrow round-trip (PoC of columnar I/O).
pub fn summarize_values(values: &[f64]) -> Result<SummarizeResult, String> {
    if values.is_empty() {
        return Err("values must not be empty".into());
    }

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
    .map_err(|e| e.to_string())?;

    let mut buffer: Vec<u8> = Vec::new();
    {
        let mut writer =
            ArrowWriter::try_new(&mut buffer, schema, None).map_err(|e| e.to_string())?;
        writer.write(&batch).map_err(|e| e.to_string())?;
        writer.close().map_err(|e| e.to_string())?;
    }
    let parquet_bytes = buffer.len();

    let reader = ParquetRecordBatchReaderBuilder::try_new(Bytes::from(buffer))
        .map_err(|e| e.to_string())?
        .build()
        .map_err(|e| e.to_string())?;

    let mut count: usize = 0;
    let mut sum = 0.0_f64;
    for batch in reader {
        let batch = batch.map_err(|e| e.to_string())?;
        let col = batch
            .column(1)
            .as_any()
            .downcast_ref::<Float64Array>()
            .ok_or_else(|| "expected float64 value column".to_string())?;
        for i in 0..col.len() {
            sum += col.value(i);
            count += 1;
        }
    }

    let mean = sum / count as f64;
    Ok(SummarizeResult {
        count,
        sum,
        mean,
        parquet_bytes,
    })
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
    });

    let out = PyDict::new(py);
    out.set_item("id", processed.id)?;
    out.set_item("timestamp", processed.timestamp)?;
    out.set_item("payload", json_to_py(py, &processed.payload)?)?;
    out.set_item("engine", "forjd-engine")?;
    Ok(out.into_any().unbind())
}

#[pyfunction]
fn summarize_values_py(values: Vec<f64>) -> PyResult<SummarizeResultPy> {
    let result = summarize_values(&values).map_err(PyValueError::new_err)?;
    Ok(SummarizeResultPy {
        count: result.count,
        sum: result.sum,
        mean: result.mean,
        parquet_bytes: result.parquet_bytes,
    })
}

#[pyfunction]
fn engine_version() -> &'static str {
    env!("CARGO_PKG_VERSION")
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
    parquet_bytes: usize,
}

#[pymethods]
impl SummarizeResultPy {
    fn as_dict<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyDict>> {
        let d = PyDict::new(py);
        d.set_item("count", self.count)?;
        d.set_item("sum", self.sum)?;
        d.set_item("mean", self.mean)?;
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

#[pymodule]
fn forjd_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(process_event_py, m)?)?;
    m.add_function(wrap_pyfunction!(summarize_values_py, m)?)?;
    m.add_function(wrap_pyfunction!(engine_version, m)?)?;
    m.add_class::<SummarizeResultPy>()?;
    m.add("process_event", m.getattr("process_event_py")?)?;
    m.add("summarize_values", m.getattr("summarize_values_py")?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_process_event() {
        let event = Event {
            id: "test-1".to_string(),
            timestamp: 1_700_000_000,
            payload: serde_json::json!({"value": 42}),
        };
        let result = process_event(event);
        assert_eq!(result.id, "test-1");
    }

    #[test]
    fn test_summarize_values() {
        let result = summarize_values(&[1.0, 2.0, 3.0]).unwrap();
        assert_eq!(result.count, 3);
        assert!((result.sum - 6.0).abs() < f64::EPSILON);
        assert!((result.mean - 2.0).abs() < f64::EPSILON);
        assert!(result.parquet_bytes > 0);
    }
}
