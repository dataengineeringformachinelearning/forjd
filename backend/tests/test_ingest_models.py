"""Unit tests for ingest contracts (metadata allowlist, encryption policy)."""

from __future__ import annotations

import unittest
from uuid import uuid4

from pydantic import ValidationError

from app.core.config import Settings
from app.models.ingest import EncryptedEnvelope, IngestEventRequest


def _envelope(**overrides: object) -> EncryptedEnvelope:
    base = {
        "key_id": "device-1",
        "nonce": "AAAAAAAAAAAAAAAA",  # base64-ish length
        "ciphertext": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "ciphertext_sha256": "a" * 64,
    }
    base.update(overrides)
    return EncryptedEnvelope.model_validate(base)


# --- Metadata allowlist (zero-trust side-channel control) ---
class TestIngestMetadata(unittest.TestCase):
    def test_allows_routing_tags(self) -> None:
        req = IngestEventRequest(
            tenant_id=uuid4(),
            client_event_id="evt-1",
            envelope=_envelope(),
            metadata={"source": "sdk", "region": "us-east-1", "tags": ["a"]},
        )
        self.assertEqual(req.metadata["source"], "sdk")

    def test_rejects_unknown_keys(self) -> None:
        with self.assertRaises(ValidationError):
            IngestEventRequest(
                tenant_id=uuid4(),
                client_event_id="evt-1",
                envelope=_envelope(),
                metadata={"e2ee": True},
            )

    def test_rejects_oversized_metadata(self) -> None:
        with self.assertRaises(ValidationError):
            IngestEventRequest(
                tenant_id=uuid4(),
                client_event_id="evt-1",
                envelope=_envelope(),
                metadata={"source": "x" * 5000},
            )


# --- Production fail-closed defaults ---
class TestProductionDefaults(unittest.TestCase):
    def test_prod_forces_zero_trust_flags(self) -> None:
        s = Settings(
            ENVIRONMENT="production",
            DEBUG=True,
            SOFT_MIGRATE_SCHEMA=True,
            REQUIRE_RLS=False,
            REQUIRE_CRYPTO_SESSION=False,
        )
        self.assertFalse(s.DEBUG)
        self.assertFalse(s.SOFT_MIGRATE_SCHEMA)
        self.assertTrue(s.REQUIRE_RLS)
        self.assertTrue(s.REQUIRE_CRYPTO_SESSION)

    def test_dev_keeps_soft_defaults(self) -> None:
        s = Settings(ENVIRONMENT="development")
        self.assertTrue(s.SOFT_MIGRATE_SCHEMA)
        self.assertFalse(s.REQUIRE_RLS)
        self.assertFalse(s.REQUIRE_CRYPTO_SESSION)

    def test_staging_forces_zero_trust_flags(self) -> None:
        s = Settings(
            ENVIRONMENT="staging",
            DEBUG=True,
            SOFT_MIGRATE_SCHEMA=True,
            REQUIRE_RLS=False,
            REQUIRE_CRYPTO_SESSION=False,
        )
        self.assertFalse(s.DEBUG)
        self.assertFalse(s.SOFT_MIGRATE_SCHEMA)
        self.assertTrue(s.REQUIRE_RLS)
        self.assertTrue(s.REQUIRE_CRYPTO_SESSION)


if __name__ == "__main__":
    unittest.main()
