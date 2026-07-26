"""UGC / third-party sanitization + encoding (ADR-0014 / ADR-0015)."""

from __future__ import annotations

import unittest

from app.core.encoding import encode_html_text, encode_pdf_literal
from app.core.sanitize import sanitize_external, sanitize_text, scrub_for_logs
from app.core.text_fields import Title200
from app.models.siem import _reject_sensitive_text


class SanitizeTextTests(unittest.TestCase):
    def test_strips_html_and_controls(self) -> None:
        self.assertEqual(
            sanitize_text("<b>Hi</b>\x00 there", max_length=64),
            "Hi there",
        )

    def test_unescapes_then_strips_tags(self) -> None:
        self.assertEqual(
            sanitize_text("&lt;script&gt;x&lt;/script&gt;ok", max_length=64),
            "xok",
        )

    def test_pydantic_title_field(self) -> None:
        from pydantic import BaseModel, ValidationError

        class Row(BaseModel):
            title: Title200

        row = Row(title="  <em>Status</em>  ")
        self.assertEqual(row.title, "Status")
        with self.assertRaises(ValidationError):
            Row(title="<script></script>")


class RejectSensitiveLengthTests(unittest.TestCase):
    def test_honors_field_max_length(self) -> None:
        long = "a" * 900
        out = _reject_sensitive_text(long, field_name="summary", max_length=2048)
        self.assertEqual(len(out), 900)
        truncated = _reject_sensitive_text(long, field_name="meta", max_length=512)
        self.assertEqual(len(truncated), 512)


class EncodingTests(unittest.TestCase):
    def test_encode_html_escapes_after_sanitize(self) -> None:
        self.assertEqual(encode_html_text("<b>A&B</b>"), "A&amp;B")

    def test_encode_pdf_literal_escapes_parens(self) -> None:
        self.assertEqual(encode_pdf_literal("hello (world)"), "hello \\(world\\)")


class SanitizeExternalTests(unittest.TestCase):
    def test_filters_secret_keys_and_bounds_depth(self) -> None:
        payload = {
            "Name": "<b>Acme</b>",
            "Authorization": "Bearer abc.def.ghi",
            "nested": {"token": "nope", "ok": "fine"},
        }
        out = sanitize_external(payload)
        assert isinstance(out, dict)
        self.assertEqual(out["Name"], "Acme")
        self.assertEqual(out["Authorization"], "[Filtered]")
        nested = out["nested"]
        assert isinstance(nested, dict)
        self.assertEqual(nested["token"], "[Filtered]")
        self.assertEqual(nested["ok"], "fine")


class ScrubForLogsTests(unittest.TestCase):
    def test_scrubs_bearer_and_fjsvc(self) -> None:
        out = scrub_for_logs(
            {
                "authorization": "secret",
                "msg": "got fjsvc_ABCDEFGHijklmnop and Bearer eyJhbG.ciOi.xx",
            }
        )
        assert isinstance(out, dict)
        self.assertEqual(out["authorization"], "[Filtered]")
        self.assertIn("[Filtered]", str(out["msg"]))

    def test_scrubs_suffix_keys_and_redis_urls(self) -> None:
        from app.core.sanitize import is_secret_key

        self.assertTrue(is_secret_key("webhook_signing_secret"))
        self.assertTrue(is_secret_key("X-API-Key"))
        self.assertFalse(is_secret_key("tenant_id"))
        out = scrub_for_logs(
            {
                "access_token": "should-hide",
                "note": "redis://:hunter2@dragonfly:6379/0",
            }
        )
        assert isinstance(out, dict)
        self.assertEqual(out["access_token"], "[Filtered]")
        self.assertEqual(out["note"], "[Filtered]")


if __name__ == "__main__":
    unittest.main()
