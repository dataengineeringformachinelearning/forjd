"""Regression tests for the canonical service-account remint request."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "remint_service_account.sh"


class TestRemintServiceAccountScript(unittest.TestCase):
    def _run(self, *, include_erase: str | None = None) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_curl = Path(temp_dir) / "curl"
            fake_curl.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                "args = sys.argv[1:]\n"
                "print(args[args.index('--data-binary') + 1])\n"
            )
            fake_curl.chmod(0o755)
            env = {
                **os.environ,
                "PATH": f"{temp_dir}:{os.environ['PATH']}",
                "FORJD_API_URL": "https://example.invalid/",
                "FORJD_HUMAN_JWT": "fake-human-jwt",
                "FORJD_TENANT_ID": "33333333-3333-3333-3333-333333333333",
            }
            if include_erase is not None:
                env["FORJD_INCLUDE_ERASE"] = include_erase
            return subprocess.run(
                [str(SCRIPT), 'partner "quoted"'],
                capture_output=True,
                check=False,
                env=env,
                text=True,
            )

    def test_default_request_omits_scopes_and_erase(self) -> None:
        completed = self._run()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["name"], 'partner "quoted"')
        self.assertFalse(payload["include_tenant_erase"])
        self.assertNotIn("scopes", payload)
        self.assertNotIn('"ingest:write"', SCRIPT.read_text())

    def test_erase_requires_explicit_opt_in(self) -> None:
        completed = self._run(include_erase="1")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["include_tenant_erase"])
        self.assertNotIn("scopes", payload)

    def test_invalid_erase_flag_fails_before_request(self) -> None:
        completed = self._run(include_erase="maybe")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("FORJD_INCLUDE_ERASE must be", completed.stderr)
        self.assertEqual(completed.stdout, "")


if __name__ == "__main__":
    unittest.main()
