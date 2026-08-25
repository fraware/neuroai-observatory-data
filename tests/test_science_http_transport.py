from __future__ import annotations

import importlib.util
import io
import sys
import unittest
import urllib.error
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


acquisition = _load_module("acquire_science_candidates", SCRIPTS / "acquire_science_candidates.py")
sys.modules["acquire_science_candidates"] = acquisition
transport_module = _load_module("science_http_transport", SCRIPTS / "science_http_transport.py")


class RedirectingOpener:
    def open(self, request, timeout=None):
        headers = Message()
        headers["Location"] = "https://example.invalid/redirected"
        raise urllib.error.HTTPError(
            request.full_url,
            302,
            "Found",
            headers,
            io.BytesIO(b"redirect-body"),
        )


class ScienceHttpTransportTests(unittest.TestCase):
    def test_redirect_is_returned_as_http_result_not_followed(self):
        transport = transport_module.NoRedirectUrllibTransport(timeout_seconds=1.0)
        transport._opener = RedirectingOpener()
        result = transport.fetch("https://example.invalid/original")
        self.assertEqual(result.status, 302)
        self.assertEqual(result.body, b"redirect-body")
        self.assertEqual(result.headers["location"], "https://example.invalid/redirected")
        self.assertEqual(transport.redirect_policy, "FAIL_CLOSED_NO_AUTO_FOLLOW")

    def test_default_user_agent_remains_frozen(self):
        transport = transport_module.NoRedirectUrllibTransport()
        self.assertEqual(transport.user_agent, acquisition.DEFAULT_USER_AGENT)


if __name__ == "__main__":
    unittest.main()
