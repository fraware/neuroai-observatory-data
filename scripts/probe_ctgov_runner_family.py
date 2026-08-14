#!/usr/bin/env python3
"""One-shot diagnostic isolating ClinicalTrials.gov transport/header behavior."""

from __future__ import annotations

import http.client
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

NCT_ID = "NCT04676854"
USER_AGENT = "NeuroAI-Collector/0.3.0-dev (+https://github.com/fraware/neuroai-workbench)"
URL = f"https://clinicaltrials.gov/api/v2/studies/{NCT_ID}"


def _identity(body: bytes) -> bool:
    return NCT_ID.encode() in body.upper()


def probe_urllib() -> dict[str, object]:
    request = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed official URL only
            body = response.read(5 * 1024 * 1024)
            return {
                "variant": "urllib-default",
                "status": int(response.status),
                "identity_present": _identity(body),
                "final_host": urllib.parse.urlparse(response.geturl()).hostname,
            }
    except urllib.error.HTTPError as exc:
        return {"variant": "urllib-default", "status": int(exc.code), "identity_present": False}


def probe_http_client(variant: str, extra_headers: dict[str, str]) -> dict[str, object]:
    parsed = urllib.parse.urlparse(URL)
    connection = http.client.HTTPSConnection(
        parsed.hostname,
        parsed.port or 443,
        timeout=20,
        context=ssl.create_default_context(),
    )
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **extra_headers}
    try:
        connection.connect()
        if connection.sock is not None:
            connection.sock.settimeout(20)
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        body = response.read(5 * 1024 * 1024)
        return {
            "variant": variant,
            "status": int(response.status),
            "identity_present": _identity(body),
            "content_encoding": response.getheader("content-encoding"),
            "content_type": response.getheader("content-type"),
        }
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        return {
            "variant": variant,
            "status": None,
            "identity_present": False,
            "error_class": type(exc).__name__,
        }
    finally:
        connection.close()


def main() -> int:
    results = [
        probe_urllib(),
        probe_http_client("http-client-gzip-deflate", {"Accept-Encoding": "gzip, deflate"}),
        probe_http_client("http-client-identity", {"Accept-Encoding": "identity"}),
        probe_http_client("http-client-default-encoding", {}),
        probe_http_client("http-client-gzip-deflate-connection-close", {"Accept-Encoding": "gzip, deflate", "Connection": "close"}),
    ]
    print("CTGOV_TRANSPORT_PROBE=" + json.dumps(results, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
