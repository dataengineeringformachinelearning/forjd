"""422 validation handler drops request input echoes (ADR-0015)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fastapi.exceptions import RequestValidationError

from app.core.http_errors import validation_exception_handler


class ValidationHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_strips_input_from_errors(self) -> None:
        exc = RequestValidationError(
            [
                {
                    "type": "string_too_long",
                    "loc": ("body", "title"),
                    "msg": "String should have at most 255 characters",
                    "input": "fjsvc_SHOULD_NOT_ECHO" + ("x" * 40),
                }
            ]
        )
        response = await validation_exception_handler(MagicMock(), exc)
        self.assertEqual(response.status_code, 422)
        body = response.body
        self.assertIsInstance(body, (bytes, memoryview))
        text = bytes(body).decode()
        self.assertNotIn("fjsvc_", text)
        self.assertIn("title", text)
        self.assertIn("string_too_long", text)


if __name__ == "__main__":
    unittest.main()
