"""Human-friendly pipeline step cards for partner UX (YAML steps remain SoT).

Maps detector / processor step ids to short titles and details so BFFs can
render a visual flow without parsing YAML or inventing copy in the browser.
"""

from __future__ import annotations

from typing import Final, Literal

StepKind = Literal["process", "detect", "unknown"]

# --- Built-in step cards (id → visual card) ---
_STEP_CARDS: Final[dict[str, dict[str, str]]] = {
    "rollup": {
        "id": "rollup",
        "title": "Seal & roll up",
        "detail": "Aggregate ciphertext metadata into a durable projection — never opens content.",
        "kind": "process",
    },
    "size_anomaly": {
        "id": "size_anomaly",
        "title": "Size anomaly",
        "detail": "Flag envelopes whose ciphertext length is unusually large for this stream.",
        "kind": "detect",
    },
    "rate_anomaly": {
        "id": "rate_anomaly",
        "title": "Rate anomaly",
        "detail": "Flag bursts that exceed the configured event-rate window.",
        "kind": "detect",
    },
}


# --- Card builder ---
def pipeline_step_cards(steps: list[str]) -> list[dict[str, str]]:
    """Return ordered visual cards for ``pipeline.steps`` (unknown steps get a safe default)."""
    cards: list[dict[str, str]] = []
    for raw in steps:
        step = (raw or "").strip()
        if not step:
            continue
        known = _STEP_CARDS.get(step)
        if known is not None:
            cards.append(dict(known))
            continue
        title = step.replace("_", " ").replace("-", " ").strip().title() or step
        cards.append(
            {
                "id": step,
                "title": title,
                "detail": "Custom pipeline step from workflow YAML.",
                "kind": "unknown",
            }
        )
    return cards
