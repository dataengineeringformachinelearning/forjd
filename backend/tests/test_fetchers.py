"""Fetcher TET unit tests (crt.sh + HIBP; no live network)."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.fetchers.base import FetchResult
from app.services.fetchers.crtsh import CrtShFetcher
from app.services.fetchers.hibp import HibpExtractError, HibpFetcher


# --- Envelope ---
class FetchResultTests(unittest.TestCase):
    def test_to_dict_includes_optional_fields(self) -> None:
        result = FetchResult(
            ok=False,
            provider="test",
            error="boom",
            warnings=["soft"],
            extras={"retry": False},
        )
        payload = result.to_dict()
        self.assertEqual(payload["provider"], "test")
        self.assertEqual(payload["error"], "boom")
        self.assertEqual(payload["warnings"], ["soft"])
        self.assertEqual(payload["extras"], {"retry": False})


# --- crt.sh ---
class CrtShFetcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_domain_fails_query(self) -> None:
        result = await CrtShFetcher().fetch({"domain": "nope"})
        self.assertFalse(result.ok)
        self.assertEqual(result.provider, "crt.sh")
        self.assertIn("invalid", (result.error or "").lower())

    async def test_extract_and_transform_subdomains(self) -> None:
        raw_rows = [
            {"name_value": "a.example.com\n*.example.com"},
            {"name_value": "b.example.com"},
            {"name_value": "other.org"},
        ]
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = raw_rows

        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.fetchers.crtsh.httpx.AsyncClient", return_value=client):
            result = await CrtShFetcher().fetch({"domain": "example.com"})

        self.assertTrue(result.ok)
        assert result.data is not None
        self.assertEqual(result.data.subdomains, ["a.example.com", "b.example.com"])


# --- HIBP ---
class HibpFetcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_email_fails_query(self) -> None:
        result = await HibpFetcher().fetch({"email": "not-an-email"})
        self.assertFalse(result.ok)
        self.assertIn("invalid", (result.error or "").lower())

    async def test_404_is_ok_empty(self) -> None:
        response = MagicMock()
        response.status_code = 404

        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.fetchers.hibp.httpx.AsyncClient", return_value=client):
            result = await HibpFetcher().fetch({"email": "user@example.com"})

        self.assertTrue(result.ok)
        assert result.data is not None
        self.assertTrue(result.data.not_found)
        self.assertEqual(result.data.breaches, [])

    async def test_non_200_maps_to_http_error(self) -> None:
        response = MagicMock()
        response.status_code = 429

        client = AsyncMock()
        client.get = AsyncMock(return_value=response)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.fetchers.hibp.httpx.AsyncClient", return_value=client):
            result = await HibpFetcher().fetch({"email": "user@example.com"})

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "http_429")

    async def test_extract_error_preserves_status(self) -> None:
        with self.assertRaises(HibpExtractError) as ctx:
            raise HibpExtractError(503)
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(str(ctx.exception), "http_503")
