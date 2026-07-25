"""Unit tests for shared FastAPI deps used by partner-facing routers."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.core.deps import parse_iso_cursor, require_db_pool


# --- Pool gate ---
class TestRequireDbPool(unittest.TestCase):
    def test_returns_pool_when_present(self) -> None:
        pool = object()
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db_pool=pool)))
        self.assertIs(require_db_pool(request), pool)  # type: ignore[arg-type]

    def test_raises_503_when_missing(self) -> None:
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db_pool=None)))
        with self.assertRaises(HTTPException) as ctx:
            require_db_pool(request)  # type: ignore[arg-type]
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "database unavailable")


# --- ISO cursor ---
class TestParseIsoCursor(unittest.TestCase):
    def test_none_and_empty(self) -> None:
        self.assertIsNone(parse_iso_cursor(None))
        self.assertIsNone(parse_iso_cursor(""))

    def test_accepts_z_suffix(self) -> None:
        value = parse_iso_cursor("2026-07-19T00:00:07Z")
        assert value is not None
        self.assertEqual(value.year, 2026)

    def test_rejects_garbage(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            parse_iso_cursor("not-a-timestamp")
        self.assertEqual(ctx.exception.status_code, 400)


# --- OpenAPI summaries on core partner routes ---
class TestCoreRouteOpenApi(unittest.TestCase):
    def test_partner_core_routes_advertise_summaries(self) -> None:
        from app.main import app

        openapi = app.openapi()
        paths = openapi["paths"]
        self.assertIn(
            "List sealed-stream workflow definitions",
            str(paths["/api/v1/workflows"]),
        )
        self.assertIn("Poll durable projection feed", str(paths["/api/v1/projections"]))
        batch_path = paths["/api/v1/ingest/events:batch"]
        self.assertIn("Ingest a bounded sealed event batch", str(batch_path))

    def test_privileged_and_probe_routes_hidden_from_schema(self) -> None:
        from app.main import app

        paths = app.openapi()["paths"]
        self.assertNotIn("/api/v1/partner/provision", paths)
        self.assertNotIn("/health", paths)
        self.assertNotIn("/ready", paths)
        erase_keys = [p for p in paths if p.endswith("/erase")]
        self.assertEqual(erase_keys, [])
        # Mint/create is hidden; list/revoke may remain for operator docs.
        create_ops = paths.get("/api/v1/service-accounts", {})
        self.assertNotIn("post", {str(k).lower() for k in create_ops})
        self.assertNotIn("/api/v1/replay", paths)
        self.assertFalse(any(p.startswith("/api/v1/replay/") for p in paths))
        self.assertFalse(any("/threat-ml" in p for p in paths))


if __name__ == "__main__":
    unittest.main()
