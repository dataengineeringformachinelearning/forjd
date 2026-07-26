"""Fetcher TET pipeline — transform query, extract, transform data.

Inspired by OpenBB's provider Fetcher pattern, but scoped to FORJD scanners:
no finance providers, no Pandas, no OpenBB runtime. Callers keep existing
HTTP response shapes; fetchers only normalize external I/O.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from app.core.sanitize import sanitize_external, sanitize_text

logger = logging.getLogger("forjd.fetchers")


# --- Standard result envelope ---
@dataclass(slots=True)
class FetchResult[DataT]:
    """Provider-neutral outcome for scanner / intel extractors."""

    ok: bool
    provider: str
    data: DataT | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for APIs that want the envelope (not legacy shapes)."""
        data: Any = self.data
        if is_dataclass(data) and not isinstance(data, type):
            data = asdict(data)
        out: dict[str, Any] = {
            "ok": self.ok,
            "provider": self.provider,
            "data": sanitize_external(data) if data is not None else None,
        }
        if self.error is not None:
            out["error"] = sanitize_text(self.error, max_length=512)
        if self.warnings:
            out["warnings"] = [sanitize_text(item, max_length=256) for item in self.warnings[:50]]
        if self.extras:
            out["extras"] = sanitize_external(dict(self.extras))
        return out


# --- TET base ---
class Fetcher[QueryT, RawT, DataT](ABC):
    """Transform → Extract → Transform for one external data source."""

    name: str

    def transform_query(self, params: dict[str, Any]) -> QueryT:
        """Validate / normalize caller params into a provider query."""
        raise NotImplementedError

    @abstractmethod
    async def aextract(self, query: QueryT) -> RawT:
        """Fetch raw provider payload (network / process boundary)."""

    @abstractmethod
    def transform_data(self, query: QueryT, raw: RawT) -> DataT:
        """Map raw payload into a stable, tenant-safe DTO."""

    async def fetch(self, params: dict[str, Any]) -> FetchResult[DataT]:
        """Run the full TET pipeline and wrap failures as ``ok=False``."""
        try:
            query = self.transform_query(params)
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetcher %s query failed: %s", self.name, type(exc).__name__)
            return FetchResult(
                ok=False,
                provider=self.name,
                error=sanitize_text(str(exc), max_length=512),
            )
        try:
            raw = await self.aextract(query)
            data = self.transform_data(query, raw)
            return FetchResult(ok=True, provider=self.name, data=self.sanitize_data(data))
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetcher %s extract failed: %s", self.name, exc)
            return FetchResult(
                ok=False,
                provider=self.name,
                error=sanitize_text(str(exc), max_length=512),
            )

    def sanitize_data(self, data: DataT) -> DataT:
        """Sanitize third-party payloads after transform (override when needed)."""
        if isinstance(data, dict | list):
            return sanitize_external(data)  # type: ignore[return-value]
        if is_dataclass(data) and not isinstance(data, type):
            cleaned = sanitize_external(asdict(data))
            return type(data)(**cleaned)  # type: ignore[call-arg, return-value]
        return data
