use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct Event {
    pub id: String,
    pub timestamp: i64,
    pub payload: serde_json::Value,
}

pub fn process_event(event: Event) -> Event {
    tracing::info!("Engine processed event: {}", event.id);
    // Add high-perf logic here later
    event
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_process_event() {
        let event = Event {
            id: "test-1".to_string(),
            timestamp: chrono::Utc::now().timestamp(),
            payload: serde_json::json!({"value": 42}),
        };
        let result = process_event(event);
        assert_eq!(result.id, "test-1");
    }
}