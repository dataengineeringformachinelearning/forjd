"""Send N sealed smoke events to production FORJD and confirm receipt.

Usage (from backend/):
  FORJD_API_URL=… FORJD_SERVICE_TOKEN=… FORJD_TENANT_ID=… \
    uv run python scripts/smoke_sealed_ingest.py [count]

E2EE contract holds: events are sealed client-side here; the server only ever
sees ciphertext + routing metadata.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
import urllib.request
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.crypto import seal  # noqa: E402

API = os.environ["FORJD_API_URL"].rstrip("/")
TOKEN = os.environ["FORJD_SERVICE_TOKEN"]
TENANT = os.environ["FORJD_TENANT_ID"]


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise SystemExit(f"HTTP {exc.code} on {path}: {detail}") from exc


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    key = secrets.token_bytes(32)
    session_id = f"smoke-session-{TENANT[:8]}"

    # Register the device session (public key only) so key_id passes the
    # active crypto_sessions gate. Server stores public material only.
    from base64 import b64encode

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    identity_pub = (
        X25519PrivateKey.generate()
        .public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    )
    session = _post(
        "/api/v1/sessions",
        {
            "tenant_id": TENANT,
            "session_id": session_id,
            "identity_public_key": b64encode(identity_pub).decode(),
        },
    )
    print(f"session: {json.dumps(session)[:120]}")

    ok = 0
    for i in range(count):
        event_id = f"smoke-{uuid4()}"
        payload = json.dumps({"kind": "telemetry.smoke", "seq": i, "ts": time.time()}).encode()
        env = seal(
            payload,
            key=key,
            key_id=session_id,
            tenant_id=TENANT,
            client_event_id=event_id,
        )
        body = {
            "tenant_id": TENANT,
            "client_event_id": event_id,
            "content_type": "application/forjd-event+v1",
            "event_type": "telemetry.smoke",
            "envelope": {
                "algo": env.algo,
                "key_id": env.key_id,
                "nonce": env.nonce,
                "ciphertext": env.ciphertext,
                "ciphertext_sha256": env.ciphertext_sha256,
            },
            "metadata": {"source": "smoke-script"},
        }
        result = _post("/api/v1/ingest", body)
        ok += 1 if result.get("ok") or result.get("event_id") else 0
        print(f"event {i}: {json.dumps(result)[:160]}")
    print(f"sent={count} accepted={ok}")


if __name__ == "__main__":
    main()
