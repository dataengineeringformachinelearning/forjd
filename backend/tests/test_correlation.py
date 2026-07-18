"""Unit tests for SOC correlation rules ."""

from __future__ import annotations

import unittest

from app.services.correlation import (
    evaluate_correlation_rules,
    evaluate_playbook_trigger,
)


class TestCorrelation(unittest.TestCase):
    def test_malicious_ip_rule(self) -> None:
        matches = evaluate_correlation_rules({"is_malicious": True})
        self.assertTrue(any(m.rule_id == "malicious_ip" for m in matches))

    def test_high_abuse(self) -> None:
        matches = evaluate_correlation_rules({"abuse_confidence_score": 90})
        self.assertTrue(any(m.rule_id == "high_abuse_score" for m in matches))

    def test_playbook_trigger_requires_conditions(self) -> None:
        self.assertFalse(
            evaluate_playbook_trigger(
                is_active=True,
                trigger_conditions={},
                context={"is_malicious": True},
            )
        )

    def test_playbook_trigger_malicious(self) -> None:
        self.assertTrue(
            evaluate_playbook_trigger(
                is_active=True,
                trigger_conditions={"is_malicious": True},
                context={"is_malicious": True},
            )
        )


if __name__ == "__main__":
    unittest.main()
