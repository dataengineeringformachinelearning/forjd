"""Security + throughput hardening checks (no live DB)."""

from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services import sessions as session_svc
from app.services.service_accounts import authenticate_opaque

ROOT = Path(__file__).resolve().parents[1]


class TestAuthHotPath(unittest.IsolatedAsyncioTestCase):
    async def test_authenticate_opaque_skips_ensure_schema(self) -> None:
        row = {
            "id": uuid4(),
            "tenant_id": uuid4(),
            "name": "partner",
            "subprocessor": "partner",
            "scopes": ["ingest:write"],
            "key_hash": "deadbeef",
            "is_active": True,
            "revoked_at": None,
        }
        pool = MagicMock()
        pool.fetchrow = AsyncMock(return_value=row)
        pool.execute = AsyncMock()

        with (
            patch(
                "app.services.service_accounts.hash_service_token",
                return_value="deadbeef",
            ),
            patch(
                "app.services.service_accounts.ensure_schema",
                new_callable=AsyncMock,
            ) as ensure,
        ):
            out = await authenticate_opaque(pool, prefix="abcd1234", token="fjsvc_abcd1234_secret")

        self.assertIsNotNone(out)
        ensure.assert_not_called()
        pool.execute.assert_awaited()  # debounced last_used_at touch


class TestSessionBatchCheck(unittest.IsolatedAsyncioTestCase):
    async def test_require_active_sessions_one_query(self) -> None:
        tid = uuid4()
        pairs = {(tid, "sess-a"), (tid, "sess-b")}
        pool = MagicMock()
        pool.fetch = AsyncMock(
            return_value=[
                {"tid": str(tid), "session_id": "sess-a"},
                {"tid": str(tid), "session_id": "sess-b"},
            ]
        )
        with patch.object(session_svc.settings, "REQUIRE_CRYPTO_SESSION", True):
            await session_svc.require_active_sessions(pool, pairs=pairs)
        pool.fetch.assert_awaited_once()

    async def test_require_active_sessions_fail_closed(self) -> None:
        tid = uuid4()
        pool = MagicMock()
        pool.fetch = AsyncMock(return_value=[{"tid": str(tid), "session_id": "sess-a"}])
        with (
            patch.object(session_svc.settings, "REQUIRE_CRYPTO_SESSION", True),
            self.assertRaises(ValueError),
        ):
            await session_svc.require_active_sessions(
                pool, pairs={(tid, "sess-a"), (tid, "missing")}
            )


class TestCursorTenantBinding(unittest.TestCase):
    def test_list_stream_results_cursor_binds_tenant(self) -> None:
        src = (ROOT / "app/services/ingest.py").read_text()
        self.assertIn(
            "WHERE id = ${len(args)}::uuid AND tenant_id = $1::uuid",
            src,
        )

    def test_list_projections_cursor_binds_tenant(self) -> None:
        src = (ROOT / "app/services/projections.py").read_text()
        self.assertIn(
            "WHERE id = ${len(args)}::uuid AND tenant_id = $1::uuid",
            src,
        )


class TestRevokeStickySource(unittest.TestCase):
    def test_service_upsert_does_not_clear_revoked_at(self) -> None:
        src = inspect.getsource(session_svc.upsert_session)
        self.assertNotIn("revoked_at = NULL", src)
        self.assertIn("WHERE crypto_sessions.revoked_at IS NULL", src)


class TestEngineClientReuse(unittest.TestCase):
    def test_engine_module_exposes_shared_clients(self) -> None:
        from app.services import engine as engine_svc

        self.assertTrue(callable(engine_svc.close_engine_clients))
        src = Path(engine_svc.__file__).read_text()
        tree = ast.parse(src)
        names = {
            node.name
            for node in tree.body
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        self.assertIn("_ensure_async_client", names)
        self.assertIn("_ensure_sync_client", names)


if __name__ == "__main__":
    unittest.main()
