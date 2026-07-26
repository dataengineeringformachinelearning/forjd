"""Context-aware output encoding — companion to ``sanitize.py`` (input).

JSON responses are encoded by Starlette/FastAPI serializers (no HTML context).
Use these helpers only when interpolating into a specific sink:

- ``encode_html_text`` — HTML document shells / attributes
- ``encode_pdf_literal`` — PDF string literals ``(…)``

ADR: docs/adr/0015-rate-limit-validation-output-encoding.md
"""

from __future__ import annotations

import html
from typing import Any

from app.core.sanitize import sanitize_text

# --- PDF literal escapes ---
_PDF_REPLACEMENTS: dict[str, str] = {
    "\u00a0": " ",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2022": "-",
    "\u2026": "...",
}


# --- HTML context ---
def encode_html_text(
    value: str | None,
    *,
    max_length: int | None = None,
    allow_newlines: bool = False,
) -> str:
    """Sanitize then HTML-escape for document/attribute interpolation."""
    plain = sanitize_text(value, max_length=max_length, allow_newlines=allow_newlines)
    return html.escape(plain, quote=True)


# --- PDF context ---
def encode_pdf_plain(value: Any, *, max_length: int = 4096) -> str:
    """Normalize untrusted text for PDF layout (not yet escaped for literals)."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = sanitize_text(str(value), max_length=max_length, allow_newlines=False)
    for source, replacement in _PDF_REPLACEMENTS.items():
        text = text.replace(source, replacement)
    return " ".join(text.split()) or "-"


def encode_pdf_literal(value: Any, *, max_length: int = 4096) -> str:
    """PDF string-literal escape for ``(…) Tj`` / Info dict values."""
    plain = encode_pdf_plain(value, max_length=max_length)
    return plain.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
