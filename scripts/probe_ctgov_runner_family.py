#!/usr/bin/env python3
"""One-shot diagnostic for ClinicalTrials.gov official routes across runner families."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

NCT_ID = "NCT04676854"
USER_AGENT = "NeuroAI-Collector/0.3.0-dev (+https://github.com/fraware/neuroai-workbench)"
ROUTES = [
    ("api-v2-single", f"https://clinicaltrials.gov/api/v2/studies/{NCT_ID}", "application/json"),
    (
        "api-v2-id-query",
        f"https://clinicaltrials.gov/api/v2/studies?query.id={NCT_ID}&pageSize=1&format=json",
        "application/json",
    ),
    ("official-study-page", f"https://clinicaltrials.gov/study/{NCT_ID}", "text/html,application/xhtml+xml;q=0.9"),
]


def probe(route_id: str, url: str, accept: str) -> dict[str, object]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed official URLs only
            body = response.read(5 * 1024 * 1024)
            return {
                "route_id": route_id,
                "status": int(response.status),
                "identity_present": NCT_ID.encode() in body.upper(),
                "final_host": urllib.parse.urlparse(response.geturl()).hostname,
            }
    except urllib.error.HTTPError as exc:
        return {"route_id": route_id, "status": int(exc.code), "identity_present": False}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"route_id": route_id, "status": None, "identity_present": False, "error_class": type(exc).__name__}


def main() -> int:
    results = [probe(*route) for route in ROUTES]
    print("CTGOV_RUNNER_PROBE=" + json.dumps(results, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
