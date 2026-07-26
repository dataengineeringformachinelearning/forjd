"""Pydantic plain-text field types — always run through sanitize_text."""

from __future__ import annotations

from typing import Annotated

from pydantic import BeforeValidator, Field, StringConstraints

from app.core.sanitize import sanitize_body, sanitize_label

# --- Slug charset (tenant / status / add-on path params) ---
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{1,62}$"
ADDON_SLUG_PATTERN = r"^[a-z][a-z0-9_-]{0,63}$"


def _required_label(max_length: int):
    def validate(value: object) -> str:
        if value is None:
            return ""
        return sanitize_label(str(value), max_length=max_length)

    return BeforeValidator(validate)


def _optional_label(max_length: int):
    def validate(value: object) -> str | None:
        if value is None:
            return None
        return sanitize_label(str(value), max_length=max_length)

    return BeforeValidator(validate)


def _required_body(max_length: int):
    def validate(value: object) -> str:
        if value is None:
            return ""
        return sanitize_body(str(value), max_length=max_length)

    return BeforeValidator(validate)


def _optional_body(max_length: int):
    def validate(value: object) -> str | None:
        if value is None:
            return None
        return sanitize_body(str(value), max_length=max_length)

    return BeforeValidator(validate)


# --- Common presets (status / domain UGC) ---
Title200 = Annotated[str, _required_label(200), Field(min_length=1, max_length=200)]
Title255 = Annotated[str, _required_label(255), Field(min_length=1, max_length=255)]
Name128 = Annotated[str, _required_label(128), Field(min_length=1, max_length=128)]
OptionalTitle200 = Annotated[
    str | None,
    _optional_label(200),
    Field(default=None, max_length=200),
]
OptionalTitle255 = Annotated[
    str | None,
    _optional_label(255),
    Field(default=None, max_length=255),
]
OptionalName128 = Annotated[
    str | None,
    _optional_label(128),
    Field(default=None, max_length=128),
]
Description4k = Annotated[str, _required_body(4096), Field(default="", max_length=4096)]
OptionalDescription4k = Annotated[
    str | None,
    _optional_body(4096),
    Field(default=None, max_length=4096),
]
Body8k = Annotated[str, _required_body(8192), Field(default="", max_length=8192)]
OptionalBody8k = Annotated[
    str | None,
    _optional_body(8192),
    Field(default=None, max_length=8192),
]

# Path/query slugs — charset only (no HTML strip; already constrained).
Slug64 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, pattern=SLUG_PATTERN),
    Field(min_length=2, max_length=64),
]


def _optional_slug(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


OptionalSlug64 = Annotated[
    str | None,
    BeforeValidator(_optional_slug),
    Field(default=None, min_length=2, max_length=64, pattern=SLUG_PATTERN),
]
AddonSlug = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, pattern=ADDON_SLUG_PATTERN),
    Field(min_length=1, max_length=64),
]
