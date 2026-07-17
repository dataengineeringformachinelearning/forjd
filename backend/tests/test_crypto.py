"""Unit tests for AES-256-GCM + X25519 session key derivation."""

from __future__ import annotations

import unittest

from app.core.crypto import (
    CryptoError,
    derive_session_key,
    generate_x25519_keypair,
    open_envelope,
    seal,
    seal_with_x25519,
    validate_x25519_public_b64,
)


# --- AES-256-GCM ---
class TestAesGcm(unittest.TestCase):
    def test_seal_roundtrip(self) -> None:
        key = b"\x11" * 32
        env = seal(
            b"sensitive telemetry",
            key=key,
            key_id="sess-1",
            tenant_id="11111111-1111-1111-1111-111111111111",
            client_event_id="evt-1",
            ratchet_header="opaque",
        )
        env.validate_sizes()
        pt = open_envelope(
            env,
            key=key,
            tenant_id="11111111-1111-1111-1111-111111111111",
            client_event_id="evt-1",
        )
        self.assertEqual(pt, b"sensitive telemetry")

    def test_aad_binds_tenant(self) -> None:
        key = b"\x22" * 32
        env = seal(
            b"payload",
            key=key,
            key_id="k",
            tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            client_event_id="e1",
        )
        with self.assertRaises(CryptoError):
            open_envelope(
                env,
                key=key,
                tenant_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                client_event_id="e1",
            )


# --- X25519 ECDH + HKDF ---
class TestX25519(unittest.TestCase):
    def test_ecdh_symmetric(self) -> None:
        a = generate_x25519_keypair()
        b = generate_x25519_keypair()
        k_ab = derive_session_key(
            private_key=a.private_key,
            peer_public_key=b.public_key,
            session_id="session-42",
        )
        k_ba = derive_session_key(
            private_key=b.private_key,
            peer_public_key=a.public_key,
            session_id="session-42",
        )
        self.assertEqual(k_ab, k_ba)
        self.assertEqual(len(k_ab), 32)

    def test_session_id_domain_separation(self) -> None:
        a = generate_x25519_keypair()
        b = generate_x25519_keypair()
        k1 = derive_session_key(
            private_key=a.private_key,
            peer_public_key=b.public_key,
            session_id="s1",
        )
        k2 = derive_session_key(
            private_key=a.private_key,
            peer_public_key=b.public_key,
            session_id="s2",
        )
        self.assertNotEqual(k1, k2)

    def test_seal_with_x25519_roundtrip(self) -> None:
        alice = generate_x25519_keypair()
        bob = generate_x25519_keypair()
        tenant = "cccccccc-cccc-cccc-cccc-cccccccccccc"
        env = seal_with_x25519(
            b"e2ee event",
            private_key=alice.private_key,
            peer_public_key=bob.public_key,
            session_id="sess-x",
            tenant_id=tenant,
            client_event_id="c1",
        )
        key = derive_session_key(
            private_key=bob.private_key,
            peer_public_key=alice.public_key,
            session_id="sess-x",
        )
        self.assertEqual(
            open_envelope(env, key=key, tenant_id=tenant, client_event_id="c1"),
            b"e2ee event",
        )

    def test_validate_public_key(self) -> None:
        pair = generate_x25519_keypair()
        self.assertEqual(validate_x25519_public_b64(pair.public_key_b64), pair.public_key_b64)
        with self.assertRaises(CryptoError):
            validate_x25519_public_b64("not-valid-b64!!!")


if __name__ == "__main__":
    unittest.main()
