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

    def test_empty_prefect_api_url_falls_back_without_probing(self) -> None:
        """Production runs with PREFECT_API_URL='' — never boot the ephemeral server."""
        flow = MagicMock()
        fallback = MagicMock(return_value={"mode": "local-fallback"})

        with (
            patch.object(soft_fail.settings, "PREFECT_API_URL", ""),
            patch.dict(soft_fail.os.environ, {}, clear=False),
            patch.object(soft_fail, "get_client") as probe,
        ):
            soft_fail.os.environ.pop("PREFECT_API_URL", None)
            result = soft_fail.run_with_local_fallback(flow, fallback=fallback)

        self.assertEqual(result, {"mode": "local-fallback"})
        probe.assert_not_called()
        flow.assert_not_called()
        fallback.assert_called_once()

    def test_empty_env_var_beats_pydantic_default(self) -> None:
        """env_ignore_empty makes settings fall back to localhost — env '' must win."""
        flow = MagicMock()
        fallback = MagicMock(return_value={"mode": "local-fallback"})

        with (
            patch.object(soft_fail.settings, "PREFECT_API_URL", "http://127.0.0.1:4200/api"),
            patch.dict(soft_fail.os.environ, {"PREFECT_API_URL": ""}),
            patch.object(soft_fail, "get_client") as probe,
        ):
            result = soft_fail.run_with_local_fallback(flow, fallback=fallback)

        self.assertEqual(result, {"mode": "local-fallback"})
        probe.assert_not_called()
        fallback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
