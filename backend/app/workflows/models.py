"""Universal workflow schema — EventType, PipelineConfig, ProjectionDefinition.

YAML/JSON under `backend/workflows/` maps 1:1 onto these models. Adding a SaaS
use case is a config file (+ optional detector/processor registration), never a
fork of ingest or crypto.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# --- EventType (logical class clients may send) ---
class EventType(BaseModel):
    """Typed event class for routing and catalog discovery.

    On the wire, clients still send plain `event_type` / `content_type` strings;
    `WorkflowMatch` resolves them. This model is the SaaS-facing contract.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
        description="Stable event type id (e.g. page.view, threat.alert)",
    )
    content_type: str = Field(
        default="application/forjd-event+v1",
        max_length=128,
        description="MIME-like content type this event travels under",
    )
    description: str = ""

    @field_validator("name")
    @classmethod
    def _lower_name(cls, value: str) -> str:
        return value.strip().lower()


# --- Match rules (content_type / event_type → this workflow) ---
class WorkflowMatch(BaseModel):
    content_types: list[str] = Field(default_factory=list)
    event_types: list[str] = Field(
        default_factory=list,
        description="Empty = match any event_type for the content_types",
    )


# --- Detector params (built-in; custom detectors use detector_params) ---
class SizeAnomalyParams(BaseModel):
    zscore: float = 2.5
    max_cipher_len: int = 262_144


class RateAnomalyParams(BaseModel):
    max_events: int = 500
    window_sec: int = 60  # reserved for continuous projector windows


# --- ProjectionDefinition (durable consumer contract) ---
class ProjectionDefinition(BaseModel):
    """Named durable projection stamped onto stream_results + checkpoints."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
        description="Stable projection id (e.g. sealed.default)",
    )
    version: int = Field(default=1, ge=1)
    description: str = ""
    # Soft retention hint for consumers / cleanup jobs (None = platform default).
    retention_days: int | None = Field(default=None, ge=1, le=3650)

    @field_validator("name")
    @classmethod
    def _lower_name(cls, value: str) -> str:
        return value.strip().lower()


class PipelineConfig(BaseModel):
    """Declares which registered processor runs and which steps it enables.

    `steps` are free-form registry keys (`rollup` + detector names). Unknown
    detector steps are skipped at runtime and warned at load time — add a
    detector module + REGISTRY entry to activate them.
    """

    processor: str = Field(
        default="sealed_metadata",
        description="Key in app.workflows.processors.REGISTRY",
    )
    steps: list[str] = Field(default_factory=lambda: ["rollup", "size_anomaly"])
    size_anomaly: SizeAnomalyParams = Field(default_factory=SizeAnomalyParams)
    rate_anomaly: RateAnomalyParams = Field(default_factory=RateAnomalyParams)
    # Extensibility: params for custom detectors keyed by step name.
    detector_params: dict[str, dict[str, Any]] = Field(default_factory=dict)
    # Durable projection — prefer `projection`; `projection_name` kept for YAML.
    projection: ProjectionDefinition | None = None
    projection_name: str = Field(default="sealed.default", max_length=128)

    @field_validator("steps")
    @classmethod
    def _normalize_steps(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in value:
            step = str(raw).strip().lower()
            if not step or step in seen:
                continue
            if not all(c.isalnum() or c in "._-" for c in step):
                raise ValueError(f"invalid pipeline step name: {raw!r}")
            seen.add(step)
            out.append(step)
        return out or ["rollup"]

    @model_validator(mode="after")
    def _sync_projection(self) -> PipelineConfig:
        if self.projection is not None:
            object.__setattr__(self, "projection_name", self.projection.name)
        elif self.projection_name:
            object.__setattr__(
                self,
                "projection",
                ProjectionDefinition(name=self.projection_name.strip().lower()),
            )
        return self

    def params_for_detectors(self) -> dict[str, dict[str, Any]]:
        """Merge built-in typed params with open detector_params dict."""
        merged: dict[str, dict[str, Any]] = dict(self.detector_params)
        merged["size_anomaly"] = {
            **self.size_anomaly.model_dump(),
            **(merged.get("size_anomaly") or {}),
        }
        merged["rate_anomaly"] = {
            **self.rate_anomaly.model_dump(),
            **(merged.get("rate_anomaly") or {}),
        }
        return merged


class WorkflowOutputs(BaseModel):
    table: str = "stream_results"
    tags: dict[str, Any] = Field(default_factory=dict)


class EncryptionPolicy(BaseModel):
    """Server-enforced encryption policy for this use case (fail closed)."""

    modes: list[Literal["e2ee"]] = Field(default_factory=lambda: ["e2ee"])
    algos: list[str] = Field(default_factory=lambda: ["aes-256-gcm"])


# --- Partner wire aliases (config only — never product forks in code) ---
class WorkflowAliases(BaseModel):
    """Map partner wire ids onto this workflow's canonical id / event types.

    Product-specific names belong only in YAML under ``workflows/``. The
    registry resolves them before matching or persistence so storage stays
    on the universal family (e.g. ``threat_telemetry`` / ``threat.metric``).
    """

    workflow_ids: list[str] = Field(
        default_factory=list,
        description="Alternate workflow_id values that resolve to this workflow",
    )
    # canonical event_type -> [wire aliases]
    event_types: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Map canonical event_type → partner wire aliases",
    )
    # Alternate MIME / content_type wire values that resolve to match.content_types.
    content_types: list[str] = Field(
        default_factory=list,
        description="Alternate content_type values that match this workflow",
    )

    @field_validator("workflow_ids")
    @classmethod
    def _lower_workflow_ids(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in value:
            key = str(raw).strip().lower()
            if not key or key in seen:
                continue
            if not all(c.isalnum() or c in "._-" for c in key):
                raise ValueError(f"invalid workflow alias: {raw!r}")
            seen.add(key)
            out.append(key)
        return out

    @field_validator("content_types")
    @classmethod
    def _lower_content_types(cls, value: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for raw in value:
            key = str(raw).strip().lower()
            if not key or key in seen:
                continue
            if len(key) > 128 or any(c.isspace() for c in key):
                raise ValueError(f"invalid content_type alias: {raw!r}")
            seen.add(key)
            out.append(key)
        return out

    @field_validator("event_types")
    @classmethod
    def _lower_event_type_map(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for raw_canon, aliases in value.items():
            canon = str(raw_canon).strip().lower()
            if not canon:
                continue
            cleaned: list[str] = []
            seen: set[str] = set()
            for raw in aliases or []:
                alias = str(raw).strip().lower()
                if not alias or alias in seen:
                    continue
                if not all(c.isalnum() or c in "._-" for c in alias):
                    raise ValueError(f"invalid event_type alias: {raw!r}")
                seen.add(alias)
                cleaned.append(alias)
            if cleaned:
                out[canon] = cleaned
        return out


# --- Top-level workflow document ---
class WorkflowDefinition(BaseModel):
    id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    name: str = Field(..., min_length=1, max_length=256)
    description: str = ""
    version: int = Field(default=1, ge=1)
    enabled: bool = True
    default: bool = False
    # Optional catalog of EventTypes this workflow understands (docs / UI).
    event_types: list[EventType] = Field(default_factory=list)
    # Partner wire aliases → this workflow (see WorkflowAliases).
    aliases: WorkflowAliases = Field(default_factory=WorkflowAliases)
    match: WorkflowMatch = Field(default_factory=WorkflowMatch)
    encryption: EncryptionPolicy = Field(default_factory=EncryptionPolicy)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    outputs: WorkflowOutputs = Field(default_factory=WorkflowOutputs)

    @field_validator("id")
    @classmethod
    def _lower_id(cls, value: str) -> str:
        return value.strip().lower()
