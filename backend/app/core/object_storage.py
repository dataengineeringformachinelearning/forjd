"""S3-compatible object storage for export/report artifacts ."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Final
from urllib.parse import urlparse

from app.core.config import settings

logger = logging.getLogger("forjd.object_storage")

DEFAULT_PRESIGN_SECONDS: Final[int] = 900


class ObjectStorageNotConfiguredError(RuntimeError):
    """Raised when S3/RustFS settings are missing or incomplete."""


@dataclass(frozen=True)
class StoredObject:
    body: Any
    content_type: str
    content_length: int


# --- Lazy boto3 client ---
@lru_cache(maxsize=1)
def _client() -> Any:
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:  # pragma: no cover
        raise ObjectStorageNotConfiguredError(
            "boto3 is not installed. From backend/: uv add boto3"
        ) from exc

    endpoint = (settings.OBJECT_STORAGE_ENDPOINT or "").strip()
    access_key = (settings.OBJECT_STORAGE_ACCESS_KEY or "").strip()
    secret_key = (settings.OBJECT_STORAGE_SECRET_KEY or "").strip()
    region = (settings.OBJECT_STORAGE_REGION or "us-east-1").strip()
    if not endpoint or not access_key or not secret_key:
        raise ObjectStorageNotConfiguredError(
            "OBJECT_STORAGE_ENDPOINT, ACCESS_KEY, and SECRET_KEY must be set"
        )
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ObjectStorageNotConfiguredError("OBJECT_STORAGE_ENDPOINT must be absolute HTTP(S)")
    addressing = (settings.OBJECT_STORAGE_ADDRESSING_STYLE or "path").strip()
    if addressing not in {"path", "virtual"}:
        raise ObjectStorageNotConfiguredError("ADDRESSING_STYLE must be path or virtual")
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": addressing}),
    )


def exports_bucket() -> str:
    bucket = (settings.OBJECT_STORAGE_BUCKET or "forjd-exports").strip()
    if not bucket:
        raise ObjectStorageNotConfiguredError("OBJECT_STORAGE_BUCKET must be set")
    return bucket


def is_configured() -> bool:
    if not (
        (settings.OBJECT_STORAGE_ENDPOINT or "").strip()
        and (settings.OBJECT_STORAGE_ACCESS_KEY or "").strip()
        and (settings.OBJECT_STORAGE_SECRET_KEY or "").strip()
    ):
        return False
    try:
        _client()
    except ObjectStorageNotConfiguredError:
        return False
    return True


def export_object_key(*, tenant_id: str, job_id: str, filename: str) -> str:
    safe_name = filename.replace("..", "").replace("/", "_").lstrip(".")
    return f"tenants/{tenant_id}/exports/{job_id}/{safe_name}"


def put_bytes(
    *,
    key: str,
    body: bytes,
    content_type: str,
    bucket: str | None = None,
    metadata: dict[str, str] | None = None,
) -> str:
    client = _client()
    name = bucket or exports_bucket()
    extra: dict[str, Any] = {"ContentType": content_type}
    if metadata:
        extra["Metadata"] = {str(k): str(v) for k, v in metadata.items()}
    client.put_object(Bucket=name, Key=key, Body=body, **extra)
    return f"s3://{name}/{key}"


def generate_presigned_get(
    *,
    key: str,
    expires_in: int = DEFAULT_PRESIGN_SECONDS,
    bucket: str | None = None,
) -> str:
    client = _client()
    name = bucket or exports_bucket()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": name, "Key": key},
        ExpiresIn=max(60, min(expires_in, 86400)),
    )


def delete_object(*, key: str, bucket: str | None = None) -> None:
    client = _client()
    name = bucket or exports_bucket()
    client.delete_object(Bucket=name, Key=key)
