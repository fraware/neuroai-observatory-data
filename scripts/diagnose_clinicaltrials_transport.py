"""Compare body-free ClinicalTrials.gov status observations across transport stacks."""

from __future__ import annotations

import argparse
import http.client
import json
import re
import ssl
import subprocess
from pathlib import Path
from typing import Any

TARGET_URL = "https://clinicaltrials.gov/api/v2/studies/NCT04676854"
TARGET_HOST = "clinicaltrials.gov"
TARGET_PATH = "/api/v2/studies/NCT04676854"
USER_AGENT = (
    "NeuroAI-Collector/0.3.0-dev (+https://github.com/fraware/neuroai-workbench)"
)
BOUNDARY = (
    "This is a non-production transport diagnostic against one pre-registered public ClinicalTrials.gov API route. "
    "It records status/failure metadata only, retains no response body, mutates no Observatory source state, does not "
    "authorize source substitution or a production transport change, and does not establish G0 completion."
)
_HTTP_STATUS_RE = re.compile(r"\bstatus\s+(\d{3})\b", re.IGNORECASE)
_REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
}


def _curl_probe(
    *, force_http11: bool, resolve_address: str | None = None
) -> dict[str, Any]:
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--output",
        "/dev/null",
        "--write-out",
        "%{http_code}",
        "--connect-timeout",
        "10",
        "--max-time",
        "30",
        "--user-agent",
        USER_AGENT,
        "--header",
        "Accept: application/json",
        "--header",
        "Accept-Encoding: gzip, deflate",
        "--header",
        "Connection: close",
    ]
    if force_http11:
        command.append("--http1.1")
    if resolve_address is not None:
        curl_address = (
            f"[{resolve_address}]" if ":" in resolve_address else resolve_address
        )
        command.extend(["--resolve", f"{TARGET_HOST}:443:{curl_address}"])
    command.append(TARGET_URL)
    completed = subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=35
    )
    raw_status = completed.stdout.strip()
    status = int(raw_status) if raw_status.isdigit() and len(raw_status) == 3 else None
    return {
        "outcome": "HTTP_RESPONSE" if status is not None else "TRANSPORT_FAILURE",
        "http_status": status,
        "returncode": completed.returncode,
    }


def _requests_probe() -> dict[str, Any]:
    import requests

    try:
        response = requests.get(
            TARGET_URL,
            headers={**_REQUEST_HEADERS, "Connection": "close"},
            timeout=(10, 20),
            allow_redirects=False,
            stream=True,
        )
        try:
            return {
                "outcome": "HTTP_RESPONSE",
                "http_status": int(response.status_code),
            }
        finally:
            response.close()
    except requests.RequestException as exc:
        return {"outcome": "TRANSPORT_FAILURE", "exception_type": type(exc).__name__}


def _stdlib_hostname_probe() -> dict[str, Any]:
    connection: http.client.HTTPSConnection | None = None
    response: http.client.HTTPResponse | None = None
    try:
        connection = http.client.HTTPSConnection(
            TARGET_HOST, 443, timeout=30, context=ssl.create_default_context()
        )
        connection.request(
            "GET", TARGET_PATH, headers={**_REQUEST_HEADERS, "Connection": "close"}
        )
        response = connection.getresponse()
        return {"outcome": "HTTP_RESPONSE", "http_status": int(response.status)}
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        return {"outcome": "TRANSPORT_FAILURE", "exception_type": type(exc).__name__}
    finally:
        if response is not None:
            response.close()
        if connection is not None:
            connection.close()


def _workbench_http_client_probe() -> dict[str, Any]:
    from neuroai_workbench.collector import PinnedSocketHttpTransport
    from neuroai_workbench.collector.config import CollectorConfig
    from neuroai_workbench.collector.errors import CollectionFailureError
    from neuroai_workbench.collector.http_client import HttpClient

    config = CollectorConfig(
        collector_version="g0-clinicaltrials-transport-diagnostic",
        configuration_hash="0" * 64,
        user_agent=USER_AGENT,
        max_response_bytes=2_000_000,
        max_redirects=0,
        connect_timeout_seconds=10.0,
        read_timeout_seconds=20.0,
        total_timeout_seconds=30.0,
        max_attempts=1,
        requests_per_host_per_minute=1,
    )
    client = HttpClient(
        config=config, transport=PinnedSocketHttpTransport(max_wire_bytes=2_000_000)
    )
    try:
        response = client.fetch(
            TARGET_URL, conditional_headers={"Accept": "application/json"}
        )
        return {
            "outcome": "HTTP_RESPONSE",
            "http_status": int(response.status),
            "redirect_hops": len(response.redirect_chain),
            "connected_address": response.connected_address,
        }
    except CollectionFailureError as exc:
        status = None
        if exc.failure_class == "HTTP_ERROR":
            match = _HTTP_STATUS_RE.search(exc.message)
            if match:
                status = int(match.group(1))
        return {
            "outcome": "COLLECTION_FAILURE",
            "failure_class": exc.failure_class,
            "http_status": status,
        }
    except (OSError, TimeoutError) as exc:
        return {"outcome": "TRANSPORT_FAILURE", "exception_type": type(exc).__name__}


def _validated_addresses() -> tuple[list[str], str]:
    from neuroai_workbench.collector.dns import DnsGuard

    resolution = DnsGuard().resolve(TARGET_URL)
    return list(resolution.addresses), resolution.rebinding_check


def _workbench_single_address_probe(address: str) -> dict[str, Any]:
    from neuroai_workbench.collector import PinnedSocketHttpTransport
    from neuroai_workbench.collector.http_client import (
        HttpRequest,
        coerce_transport_response,
    )

    transport = PinnedSocketHttpTransport(max_wire_bytes=2_000_000)
    try:
        response = coerce_transport_response(
            transport.send(
                HttpRequest("GET", TARGET_URL, dict(_REQUEST_HEADERS), (address,)),
                connect_timeout=10.0,
                read_timeout=20.0,
            )
        )
        return {
            "outcome": "HTTP_RESPONSE",
            "http_status": int(response.status),
            "connected_address": response.connected_address,
        }
    except (OSError, TimeoutError) as exc:
        return {"outcome": "TRANSPORT_FAILURE", "exception_type": type(exc).__name__}


def _urllib3_single_address_probe(
    address: str, *, stdlib_default_context: bool
) -> dict[str, Any]:
    """Hold urllib3 pool/request semantics fixed and vary only TLS context ownership."""
    import urllib3
    from urllib3.util import Timeout

    pool_kwargs: dict[str, Any] = {
        "port": 443,
        "timeout": Timeout(connect=10.0, read=20.0),
        "maxsize": 1,
        "block": True,
        "server_hostname": TARGET_HOST,
        "assert_hostname": TARGET_HOST,
        "cert_reqs": ssl.CERT_REQUIRED,
    }
    if stdlib_default_context:
        pool_kwargs["ssl_context"] = ssl.create_default_context()

    pool = urllib3.HTTPSConnectionPool(address, **pool_kwargs)
    response = None
    try:
        response = pool.urlopen(
            "GET",
            TARGET_PATH,
            headers={**_REQUEST_HEADERS, "Host": TARGET_HOST, "Connection": "close"},
            retries=False,
            redirect=False,
            assert_same_host=False,
            preload_content=False,
            decode_content=False,
        )
        return {"outcome": "HTTP_RESPONSE", "http_status": int(response.status)}
    except (urllib3.exceptions.HTTPError, OSError, TimeoutError) as exc:
        return {"outcome": "TRANSPORT_FAILURE", "exception_type": type(exc).__name__}
    finally:
        if response is not None:
            response.close()
        pool.close()


def execute() -> dict[str, Any]:
    addresses, rebinding_check = _validated_addresses()
    per_address = []
    for address in addresses:
        per_address.append(
            {
                "address": address,
                "curl_resolve_http1_1": _curl_probe(
                    force_http11=True, resolve_address=address
                ),
                "urllib3_managed_context_pinned_http1_1": _urllib3_single_address_probe(
                    address, stdlib_default_context=False
                ),
                "urllib3_stdlib_context_pinned_http1_1": _urllib3_single_address_probe(
                    address, stdlib_default_context=True
                ),
                "workbench_single_address_http1_1": _workbench_single_address_probe(
                    address
                ),
            }
        )

    return {
        "schema_version": "4",
        "boundary": BOUNDARY,
        "target": {
            "host": TARGET_HOST,
            "path": TARGET_PATH,
            "method": "GET",
            "accept": "application/json",
        },
        "dns_validated_address_count": len(addresses),
        "dns_rebinding_check": rebinding_check,
        "probes": {
            "curl_default": _curl_probe(force_http11=False),
            "curl_http1_1": _curl_probe(force_http11=True),
            "python_requests_http1_1": _requests_probe(),
            "python_stdlib_hostname_http1_1": _stdlib_hostname_probe(),
            "workbench_pinned_http1_1": _workbench_http_client_probe(),
        },
        "per_validated_address": per_address,
        "response_body_retained": False,
        "source_state_mutated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = execute()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "SANITIZED_CLINICALTRIALS_TRANSPORT_DIAGNOSTIC="
        + json.dumps(report, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
