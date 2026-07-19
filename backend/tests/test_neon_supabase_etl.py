"""Unit tests for Neon → Supabase ETL helpers (no live database)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ETL_ROOT = Path(__file__).resolve().parents[2] / "scripts" / "neon_supabase_etl"
sys.path.insert(0, str(_ETL_ROOT))

from forjd_etl.config import TableSpec, TransformSpec, VectorColumn, parse_config
from forjd_etl.db import normalize_dsn
from forjd_etl.transforms import (
    apply_transforms,
    apply_vector_validation,
    resolve_column_map,
)


class TestEtlConfig(unittest.TestCase):
    def test_rejects_public_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "public"):
            parse_config(
                {
                    "target": {"schema": "public"},
                    "tables": [{"source": "t", "primary_key": ["id"]}],
                }
            )

    def test_parse_tables_and_transforms(self) -> None:
        cfg = parse_config(
            {
                "source": {"schema": "public"},
                "target": {"schema": "partner_control"},
                "options": {"mode": "incremental", "batch_size": 50},
                "params": {"tenant_id": "abc"},
                "tables": [
                    {
                        "source": "auth_user",
                        "primary_key": "id",
                        "incremental": {"column": "updated_at"},
                        "transforms": [{"column": "email", "op": "lower"}],
                        "vector_columns": [{"name": "embedding", "dimensions": 3}],
                    }
                ],
            }
        )
        self.assertEqual(cfg.mode, "incremental")
        self.assertEqual(cfg.batch_size, 50)
        self.assertEqual(cfg.params["tenant_id"], "abc")
        self.assertEqual(cfg.tables[0].primary_key, ["id"])
        self.assertIsNotNone(cfg.tables[0].incremental)
        self.assertEqual(cfg.tables[0].transforms[0].op, "lower")
        self.assertEqual(cfg.tables[0].vector_columns[0].dimensions, 3)


class TestTransforms(unittest.TestCase):
    def test_resolve_column_map_exclude_and_rename(self) -> None:
        spec = TableSpec(
            source="t",
            target="t",
            primary_key=["id"],
            columns={"id": "id", "name": "display_name", "secret": "secret"},
            exclude_columns=["secret"],
        )
        mapping = resolve_column_map(["id", "name", "secret", "extra"], spec)
        self.assertEqual(mapping, {"id": "id", "name": "display_name"})

    def test_apply_transforms_strip_map_and_remap(self) -> None:
        transforms = [
            TransformSpec(column="name", op="strip"),
            TransformSpec(column="status", op="map", map={"a": "active"}),
        ]
        out = apply_transforms(
            {"id": 1, "name": "  x  ", "status": "a"},
            transforms,
            column_map={"id": "id", "name": "name", "status": "status"},
        )
        self.assertEqual(out, {"id": 1, "name": "x", "status": "active"})

    def test_vector_validation(self) -> None:
        vc = VectorColumn(name="embedding", dimensions=3)
        column_map = {"embedding": "embedding"}
        ok = apply_vector_validation(
            {"embedding": [0.1, 0.2, 0.3]},
            [vc],
            column_map=column_map,
        )
        self.assertEqual(ok["embedding"], "[0.1,0.2,0.3]")
        with self.assertRaisesRegex(ValueError, "expected 3"):
            apply_vector_validation(
                {"embedding": [1.0, 2.0]},
                [vc],
                column_map=column_map,
            )


class TestDsn(unittest.TestCase):
    def test_normalize_dsn(self) -> None:
        self.assertTrue(normalize_dsn("postgresql+asyncpg://u:p@h/db").startswith("postgresql://"))
        self.assertTrue(normalize_dsn("postgres://u:p@h/db").startswith("postgresql://"))


if __name__ == "__main__":
    unittest.main()
