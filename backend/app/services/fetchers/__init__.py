"""Typed external-source fetchers (OpenBB-style TET, no OpenBB dependency)."""

from app.services.fetchers.base import Fetcher, FetchResult
from app.services.fetchers.crtsh import CrtShFetcher
from app.services.fetchers.hibp import HibpFetcher

__all__ = [
    "CrtShFetcher",
    "FetchResult",
    "Fetcher",
    "HibpFetcher",
]
