#!/usr/bin/env python3
"""E2EE smoke: session upsert → sealed ingest → projections (service token).

Usage (never print the token):
  export FORJD_API_URL=https://backend.forjd.co
  export FORJD_SERVICE_TOKEN=fjsvc_…
  export FORJD_TENANT_ID=…
  cd backend && uv run python ../scripts/e2e_sealed_ingest_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

# --- Allow running from repo root via uv in backend/ ---
_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
  sys.path.insert(0, str(_BACKEND))

from app.core.crypto import generate_x25519_keypair, seal  # noqa: E402


def _call(
  api: str,
  method: str,
  path: str,
  *,
  token: str,
  body: dict | None = None,
) -> tuple[int, dict | list | str]:
  data = None if body is None else json.dumps(body).encode()
  req = urllib.request.Request(
    api + path,
    data=data,
    method=method,
    headers={
      "Authorization": f"Bearer {token}",
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
  )
  try:
    with urllib.request.urlopen(req, timeout=30) as resp:
      raw = resp.read().decode()
      try:
        return resp.status, json.loads(raw)
      except json.JSONDecodeError:
        return resp.status, raw
  except urllib.error.HTTPError as exc:
    raw = exc.read().decode()
    try:
      return exc.code, json.loads(raw)
    except json.JSONDecodeError:
      return exc.code, raw


def main() -> int:
  api = os.environ["FORJD_API_URL"].rstrip("/")
  token = os.environ["FORJD_SERVICE_TOKEN"]
  tenant = os.environ["FORJD_TENANT_ID"]
  if not token.startswith("fjsvc_"):
    print("FAIL: FORJD_SERVICE_TOKEN must be an opaque fjsvc_ token")
    return 1

  session_id = f"e2e-{uuid.uuid4().hex[:16]}"
  client_event_id = f"evt-{uuid.uuid4().hex}"
  kp = generate_x25519_keypair()

  # --- Register public session ---
  code, session_body = _call(
    api,
    "POST",
    "/api/v1/sessions",
    token=token,
    body={
      "tenant_id": tenant,
      "session_id": session_id,
      "identity_public_key": kp.public_key_b64,
    },
  )
  print(f"session_upsert: {code}")
  if code >= 400:
    print(session_body)
    return 1

  # --- Seal ciphertext locally (FORJD stores ciphertext only) ---
  key = os.urandom(32)
  envelope = seal(
    b'{"kind":"e2e_smoke","n":1}',
    key=key,
    key_id=session_id,
    tenant_id=tenant,
    client_event_id=client_event_id,
  )

  code, ingest_body = _call(
    api,
    "POST",
    "/api/v1/ingest",
    token=token,
    body={
      "tenant_id": tenant,
      "client_event_id": client_event_id,
      "content_type": "application/forjd-event+v1",
      "envelope": {
        "algo": envelope.algo,
        "key_id": envelope.key_id,
        "nonce": envelope.nonce,
        "ciphertext": envelope.ciphertext,
        "ratchet_header": envelope.ratchet_header,
        "ciphertext_sha256": envelope.ciphertext_sha256,
      },
      "metadata": {"source": "e2e_smoke", "env": "prod"},
    },
  )
  print(f"sealed_ingest: {code}")
  if code >= 400:
    print(ingest_body)
    return 1
  print(
    "ingest_ok:",
    {
      k: ingest_body.get(k)
      for k in ("ok", "accepted", "event_id", "workflow_id", "duplicate")
      if isinstance(ingest_body, dict) and k in ingest_body
    }
    or (ingest_body if isinstance(ingest_body, dict) else str(ingest_body)[:200]),
  )

  # --- Projections / run (metadata-only) ---
  code, proj = _call(
    api,
    "GET",
    f"/api/v1/projections?tenant_id={tenant}",
    token=token,
  )
  print(f"projections: {code}")
  if isinstance(proj, dict):
    print("projection_count:", len(proj.get("projections") or []))

  code, run = _call(
    api,
    "POST",
    "/api/v1/projections/run",
    token=token,
    body={"tenant_id": tenant},
  )
  print(f"projections_run: {code}")
  if code >= 400:
    print(run)

  # --- Cleanup: revoke session ---
  code, _ = _call(
    api,
    "DELETE",
    f"/api/v1/sessions/{session_id}?tenant_id={tenant}",
    token=token,
  )
  print(f"session_revoke: {code}")
  print("E2E_SEALED_OK")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
