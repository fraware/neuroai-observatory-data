"""Run bounded official-surface successor discovery without mutating source or assessment state."""

from __future__ import annotations

import argparse
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from source_lifecycle_overlay import DEFAULT_LIFECYCLE_OVERLAY, load_json, sha256

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WATCH_CONFIG = ROOT / "curation" / "successor_discovery_watches_v0.1.json"
STATUS = "DEVELOPMENT_SUCCESSOR_DISCOVERY_WATCHES_NOT_CANONICAL"
REPORT_STATUS = "DEVELOPMENT_SUCCESSOR_DISCOVERY_REPORT_NOT_CANONICAL"


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._href = next(
            (value for key, value in attrs if key.lower() == "href" and value), None
        )
        self._parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        text = " ".join(" ".join(self._parts).split())
        self.links.append((self._href, text))
        self._href = None
        self._parts = []


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def verify_watch_config(
    config: dict[str, Any], overlay: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    metadata = config.get("metadata")
    watches = config.get("watches")
    if not isinstance(metadata, dict) or not isinstance(watches, list):
        raise TypeError("Successor-discovery config requires metadata and watches")
    if metadata.get("status") != STATUS:
        raise ValueError("Successor-discovery config lost its noncanonical status")
    if metadata.get("automatic_source_registration") is not False:
        raise ValueError(
            "Successor discovery must forbid automatic source registration"
        )
    if metadata.get("automatic_assessment_mutation") is not False:
        raise ValueError(
            "Successor discovery must forbid automatic assessment mutation"
        )
    if metadata.get("watch_count") != len(watches):
        raise ValueError("Successor-discovery watch_count mismatch")
    if metadata.get("lifecycle_overlay_sha256") != overlay.get("overlay_sha256"):
        raise ValueError("Successor-discovery lifecycle overlay binding mismatch")

    transitions_raw = overlay.get("transitions")
    if not isinstance(transitions_raw, list):
        raise TypeError("Lifecycle overlay transitions are missing")
    transitions = {
        str(item["source_id"]): item
        for item in transitions_raw
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    by_id: dict[str, dict[str, Any]] = {}
    for watch in watches:
        if not isinstance(watch, dict):
            raise TypeError("Successor-discovery watch must be an object")
        watch_id = str(watch.get("watch_id") or "")
        if not watch_id or watch_id in by_id:
            raise ValueError(
                "Successor-discovery watch_id must be unique and non-empty"
            )
        trigger_source_id = str(watch.get("trigger_source_id") or "")
        transition = transitions.get(trigger_source_id)
        if transition is None:
            raise ValueError(f"Watch {watch_id} lacks lifecycle trigger source")
        if watch.get("trigger_lifecycle_state") != transition.get("lifecycle_state"):
            raise ValueError(f"Watch {watch_id} lifecycle state drift")
        if watch.get("trigger_transition_sha256") != transition.get(
            "transition_sha256"
        ):
            raise ValueError(f"Watch {watch_id} lifecycle transition hash mismatch")
        if watch.get("watch_id") != transition.get("successor_discovery_watch_id"):
            raise ValueError(f"Watch {watch_id} is not bound from lifecycle transition")
        url = str(watch.get("url") or "")
        host = (urlparse(url).hostname or "").lower()
        if (
            not url.startswith("https://")
            or host != str(watch.get("official_host") or "").lower()
        ):
            raise ValueError(
                f"Watch {watch_id} must use its declared official HTTPS host"
            )
        relevance = watch.get("relevance_policy")
        if (
            not isinstance(relevance, dict)
            or relevance.get("rule") != "AT_LEAST_ONE_DOMAIN_AND_ONE_CONTEXT_TERM"
        ):
            raise ValueError(f"Watch {watch_id} has unsupported relevance policy")
        for field in ("domain_terms", "context_terms"):
            terms = relevance.get(field)
            if (
                not isinstance(terms, list)
                or not terms
                or not all(isinstance(item, str) and item.strip() for item in terms)
            ):
                raise ValueError(
                    f"Watch {watch_id}.{field} must be a non-empty string array"
                )
        by_id[watch_id] = watch
    return by_id


def discover_from_html(watch: dict[str, Any], body: bytes) -> list[dict[str, Any]]:
    text = body.decode("utf-8", errors="replace")
    parser = _LinkParser()
    parser.feed(text)
    official_host = str(watch["official_host"]).lower()
    domain_terms = [
        _normalized(item) for item in watch["relevance_policy"]["domain_terms"]
    ]
    context_terms = [
        _normalized(item) for item in watch["relevance_policy"]["context_terms"]
    ]
    candidates: dict[str, dict[str, Any]] = {}
    for href, label in parser.links:
        absolute = urljoin(str(watch["url"]), href)
        parsed = urlparse(absolute)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() != official_host:
            continue
        searchable = _normalized(f"{label} {parsed.path}")
        matched_domain = sorted({term for term in domain_terms if term in searchable})
        matched_context = sorted({term for term in context_terms if term in searchable})
        if not matched_domain or not matched_context:
            continue
        canonical_url = parsed._replace(fragment="").geturl()
        candidate_id = (
            "DISC-CAND-"
            + hashlib.sha256(
                f"{watch['watch_id']}\n{canonical_url}\n{label}".encode()
            ).hexdigest()[:20]
        )
        candidates[candidate_id] = {
            "candidate_id": candidate_id,
            "watch_id": watch["watch_id"],
            "title": label or None,
            "url": canonical_url,
            "matched_domain_terms": matched_domain,
            "matched_context_terms": matched_context,
            "canonical_source_created": False,
            "assessment_mutation_authorized": False,
            "registration_authorized": False,
        }
    return [candidates[key] for key in sorted(candidates)]


def run_discovery(config: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    from neuroai_workbench.collector.config import CollectorConfig
    from neuroai_workbench.collector.http_client import HttpClient
    from neuroai_workbench.collector.transport import StdlibHttpTransport

    watches = verify_watch_config(config, overlay)
    client = HttpClient(
        config=CollectorConfig(
            collector_version="successor-discovery-v0.1",
            configuration_hash="0" * 64,
            max_response_bytes=5 * 1024 * 1024,
            max_redirects=8,
            connect_timeout_seconds=10.0,
            read_timeout_seconds=20.0,
            total_timeout_seconds=30.0,
            max_attempts=1,
            requests_per_host_per_minute=20,
        ),
        transport=StdlibHttpTransport(),
    )
    reports: list[dict[str, Any]] = []
    for watch_id in sorted(watches):
        watch = watches[watch_id]
        response = client.fetch(
            str(watch["url"]),
            conditional_headers={"Accept": "text/html,application/xhtml+xml;q=0.9"},
        )
        final_host = (urlparse(response.url).hostname or "").lower()
        if final_host != str(watch["official_host"]).lower():
            raise ValueError(f"Watch {watch_id} redirected away from official host")
        candidates = discover_from_html(watch, response.body)
        semantic = {
            "watch_id": watch_id,
            "trigger_source_id": watch["trigger_source_id"],
            "trigger_transition_sha256": watch["trigger_transition_sha256"],
            "official_host": watch["official_host"],
            "final_host": final_host,
            "http_status": response.status,
            "candidate_count": len(candidates),
            "candidates": candidates,
            "automatic_source_registration": False,
            "automatic_assessment_mutation": False,
            "scope_boundary": watch["relevance_policy"]["scope_boundary"],
        }
        semantic["watch_report_sha256"] = sha256(semantic)
        reports.append(semantic)
    report: dict[str, Any] = {
        "schema_version": "1",
        "status": REPORT_STATUS,
        "watch_config_sha256": sha256(config),
        "lifecycle_overlay_sha256": overlay["overlay_sha256"],
        "watch_count": len(reports),
        "candidate_count": sum(int(item["candidate_count"]) for item in reports),
        "automatic_source_registration": False,
        "automatic_assessment_mutation": False,
        "watch_reports": reports,
        "boundary": config["metadata"]["boundary"],
    }
    report["report_sha256"] = sha256(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch-config", type=Path, default=DEFAULT_WATCH_CONFIG)
    parser.add_argument(
        "--lifecycle-overlay", type=Path, default=DEFAULT_LIFECYCLE_OVERLAY
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = load_json(args.watch_config.resolve())
    overlay = load_json(args.lifecycle_overlay.resolve())
    report = run_discovery(config, overlay)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "watch_count": report["watch_count"],
                "candidate_count": report["candidate_count"],
                "report_sha256": report["report_sha256"],
                "automatic_source_registration": report[
                    "automatic_source_registration"
                ],
                "automatic_assessment_mutation": report[
                    "automatic_assessment_mutation"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
