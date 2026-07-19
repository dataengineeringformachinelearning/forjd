"""Fetcher TET pipeline — transform query, extract, transform data.

Inspired by OpenBB's provider Fetcher pattern, but scoped to FORJD scanners:
no finance providers, no Pandas, no OpenBB runtime. Callers keep existing
HTTP response shapes; fetchers only normalize external I/O.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

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
        out: dict[str, Any] = {
            "ok": self.ok,
            "provider": self.provider,
            "data": self.data,
        }
        if self.error is not None:
            out["error"] = self.error
        if self.warnings:
            out["warnings"] = list(self.warnings)
        if self.extras:
            out["extras"] = dict(self.extras)
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
            logger.warning("fetcher %s query failed: %s", self.name, exc)
            return FetchResult(ok=False, provider=self.name, error=str(exc))
        try:
            raw = await self.aextract(query)
            data = self.transform_data(query, raw)
            return FetchResult(ok=True, provider=self.name, data=data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("fetcher %s extract failed: %s", self.name, exc)
            return FetchResult(ok=False, provider=self.name, error=str(exc))
