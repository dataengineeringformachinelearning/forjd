"""Sync YAML workflows → public.use_cases catalog (UI / discovery)."""

from __future__ import annotations

import json
import logging
from typing import Any

import asyncpg

from app.workflows.registry import all_workflows

logger = logging.getLogger("forjd.use_cases")


# --- Upsert enabled workflows into use_cases ---
async def sync_use_cases_from_workflows(pool: asyncpg.Pool) -> int:
    """Mirror workflow YAML into the use_cases table (service-role path)."""
    written = 0
    for wf in all_workflows():
        config: dict[str, Any] = {
            "version": wf.version,
            "default": wf.default,
            "encryption": wf.encryption.model_dump(),
            "pipeline": {
                "processor": wf.pipeline.processor,
                "steps": wf.pipeline.steps,
                "projection_name": wf.pipeline.projection_name,
            },
            "outputs": wf.outputs.model_dump(),
        }
        await pool.execute(
            """
            INSERT INTO use_cases (
                id, name, description, content_types, event_types,
                config, enabled, updated_at
            )
            VALUES (
                $1, $2, $3, $4::text[], $5::text[],
                $6::jsonb, $7, NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                content_types = EXCLUDED.content_types,
                event_types = EXCLUDED.event_types,
                config = EXCLUDED.config,
                enabled = EXCLUDED.enabled,
                updated_at = NOW()
            """,
            wf.id,
            wf.name,
            wf.description or "",
            wf.match.content_types,
            wf.match.event_types,
            json.dumps(config),
            wf.enabled,
        )
        written += 1
    logger.info("synced %d use_cases from workflows", written)
    return written
