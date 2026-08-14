#!/usr/bin/env python3
"""One-shot diagnostic isolating ClinicalTrials.gov TLS/transport behavior."""

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


def probe_urllib(*, disable_proxy: bool = False) -> dict[str, object]:
    variant = "urllib-no-proxy" if disable_proxy else "urllib-default"
    request = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if disable_proxy else urllib.request.build_opener()
    try:
        with opener.open(request, timeout=20) as response:
            body = response.read(5 * 1024 * 1024)
            return {
                "variant": variant,
                "status": int(response.status),
                "identity_present": _identity(body),
                "final_host": urllib.parse.urlparse(response.geturl()).hostname,
            }
    except urllib.error.HTTPError as exc:
        return {"variant": variant, "status": int(exc.code), "identity_present": False}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"variant": variant, "status": None, "identity_present": False, "error_class": type(exc).__name__}


def probe_http_client(
    variant: str,
    *,
    context_mode: str,
) -> dict[str, object]:
    parsed = urllib.parse.urlparse(URL)
    context: ssl.SSLContext | None
    if context_mode == "custom-no-alpn":
        context = ssl.create_default_context()
    elif context_mode == "custom-http11-alpn":
        context = ssl.create_default_context()
        context.set_alpn_protocols(["http/1.1"])
    elif context_mode == "implicit-default":
        context = None
    else:
        raise ValueError(context_mode)

    kwargs: dict[str, object] = {"timeout": 20}
    if context is not None:
        kwargs["context"] = context
    connection = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, **kwargs)
    path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Encoding": "gzip, deflate"}
    try:
        connection.connect()
        selected_alpn = None
        if connection.sock is not None:
            connection.sock.settimeout(20)
            selected_alpn = connection.sock.selected_alpn_protocol()
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        body = response.read(5 * 1024 * 1024)
        return {
            "variant": variant,
            "status": int(response.status),
            "identity_present": _identity(body),
            "selected_alpn": selected_alpn,
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
        probe_urllib(disable_proxy=True),
        probe_http_client("http-client-custom-no-alpn", context_mode="custom-no-alpn"),
        probe_http_client("http-client-custom-http11-alpn", context_mode="custom-http11-alpn"),
        probe_http_client("http-client-implicit-default-context", context_mode="implicit-default"),
    ]
    print("CTGOV_TLS_PROBE=" + json.dumps(results, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
