"""Built-in correlation rules and playbook trigger evaluation (from DEML, no ORM)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CorrelationMatch:
    rule_id: str
    title: str
    severity: str
    description: str


RuleFn = Callable[[dict[str, Any]], bool]


# --- Rule predicates ---
def _malicious_ip(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("is_malicious"))


def _high_abuse(ctx: dict[str, Any]) -> bool:
    return int(ctx.get("abuse_score") or ctx.get("abuse_confidence_score") or 0) > 75


def _threat_match(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("threat_match") or ctx.get("malicious_ip_detected"))


def _behavioral_anomaly(ctx: dict[str, Any]) -> bool:
    entropy = ctx.get("behavioral_entropy")
    if entropy is not None:
        return float(entropy) > 0.75
    behavioral = ctx.get("behavioral") or {}
    scroll = behavioral.get("scroll_depth_pct", 100)
    duration = behavioral.get("session_duration_s", 60)
    return scroll < 5 and duration < 8


def _high_anomaly_score(ctx: dict[str, Any]) -> bool:
    return float(ctx.get("anomaly_score") or 0) >= 0.7


CORRELATION_RULES: list[tuple[str, str, str, str, RuleFn]] = [
    (
        "malicious_ip",
        "Malicious IP detected",
        "critical",
        "Traffic matched a known malicious indicator feed.",
        _malicious_ip,
    ),
    (
        "high_abuse_score",
        "High abuse confidence",
        "high",
        "IP exceeded abuse confidence threshold (>75).",
        _high_abuse,
    ),
    (
        "threat_correlation",
        "Threat intel correlation",
        "high",
        "Endpoint telemetry correlated with threat intelligence.",
        _threat_match,
    ),
    (
        "behavioral_anomaly",
        "Behavioral session anomaly",
        "medium",
        "Session behavior deviates from expected human patterns.",
        _behavioral_anomaly,
    ),
    (
        "ml_anomaly",
        "ML anomaly threshold exceeded",
        "high",
        "Platform threat model scored above auto-response threshold.",
        _high_anomaly_score,
    ),
]


# --- Evaluate rules / playbook triggers ---
def evaluate_correlation_rules(context: dict[str, Any]) -> list[CorrelationMatch]:
    matches: list[CorrelationMatch] = []
    for rule_id, title, severity, description, fn in CORRELATION_RULES:
        try:
            if fn(context):
                matches.append(
                    CorrelationMatch(
                        rule_id=rule_id,
                        title=title,
                        severity=severity,
                        description=description,
                    )
                )
        except Exception:  # noqa: BLE001 — one bad rule must not abort the set
            continue
    return matches


def evaluate_playbook_trigger(
    *,
    is_active: bool,
    trigger_conditions: Mapping[str, Any] | None,
    context: dict[str, Any],
) -> bool:
    """Evaluate trigger_conditions against context. Empty conditions = never auto-fire."""
    conditions = dict(trigger_conditions or {})
    if not conditions or not is_active:
        return False

    event_type = conditions.get("event_type")
    if event_type and context.get("event_type") != event_type:
        return False

    min_abuse = conditions.get("min_abuse_score")
    if min_abuse is not None:
        score = int(context.get("abuse_score") or context.get("abuse_confidence_score") or 0)
        if score < int(min_abuse):
            return False

    if conditions.get("is_malicious") and not context.get("is_malicious"):
        return False

    if conditions.get("threat_match") and not (
        context.get("threat_match") or context.get("malicious_ip_detected")
    ):
        return False

    min_anomaly = conditions.get("min_anomaly_score")
    if min_anomaly is not None and float(context.get("anomaly_score") or 0) < float(min_anomaly):
        return False

    rule_ids = conditions.get("rule_ids")
    if rule_ids:
        matched = {m.rule_id for m in evaluate_correlation_rules(context)}
        if not set(rule_ids).intersection(matched):
            return False

    return True
