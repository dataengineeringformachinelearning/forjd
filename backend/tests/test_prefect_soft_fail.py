"""Prefect fallback must never replay partially executed business work."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import httpx

from app.pipelines import soft_fail


class TestPrefectSoftFail(unittest.TestCase):
    def test_transport_unavailability_falls_back_before_flow_starts(self) -> None:
        flow = MagicMock()
        fallback = MagicMock(return_value={"mode": "local-fallback"})
        unavailable = httpx.ConnectError("prefect unavailable")

        with patch.object(soft_fail, "_prefect_api_error", return_value=unavailable):
            result = soft_fail.run_with_local_fallback(flow, fallback=fallback)

        self.assertEqual(result, {"mode": "local-fallback"})
        flow.assert_not_called()
        fallback.assert_called_once_with(unavailable)

    def test_business_exception_is_not_rerun_through_fallback(self) -> None:
        flow = MagicMock(side_effect=RuntimeError("processor failed after side effect"))
        fallback = MagicMock()

        with (
            patch.object(soft_fail, "_prefect_api_error", return_value=None),
            self.assertRaisesRegex(RuntimeError, "processor failed"),
        ):
            soft_fail.run_with_local_fallback(flow, fallback=fallback)

        flow.assert_called_once_with()
        fallback.assert_not_called()

    def test_non_transport_prefect_configuration_error_fails_closed(self) -> None:
        flow = MagicMock()
        fallback = MagicMock()
        configuration_error = ValueError("invalid Prefect API configuration")

        with (
            patch.object(
                soft_fail,
                "_prefect_api_error",
                return_value=configuration_error,
            ),
            self.assertRaisesRegex(ValueError, "invalid Prefect API"),
        ):
            soft_fail.run_with_local_fallback(flow, fallback=fallback)

        flow.assert_not_called()
        fallback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
