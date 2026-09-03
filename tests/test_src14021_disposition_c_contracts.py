from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GOVERNED_OFFICIAL = "https://sonaafrica.org/"
PARKING_HOST = "sonafrica.org"
SOURCE_ID = "SRC-14-021"
ORG_ID = "ORG-0215"


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _walk_urls(payload: object) -> list[tuple[str | None, str, str]]:
    found: list[tuple[str | None, str, str]] = []

    def visit(node: object) -> None:
        if isinstance(node, dict):
            identity = None
            for key in ("source_id", "organization_id", "monitor_id"):
                value = node.get(key)
                if isinstance(value, str):
                    identity = value
                    break
            for key in ("url", "official_url", "registered_url"):
                value = node.get(key)
                if isinstance(value, str):
                    found.append((identity, key, value))
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(payload)
    return found


class Src14021DispositionCContractTests(unittest.TestCase):
    def test_fixtures_and_releases_only_bind_governed_sonaafrica_official_url(
        self,
    ) -> None:
        paths = [
            ROOT / "fixtures" / "canonical_observatory_release_v1.4.json",
            ROOT / "fixtures" / "source_monitor_registry_v1.5.json",
            ROOT
            / "releases"
            / "data-v0.1.0-public-governing"
            / "records"
            / "canonical_observatory_release_v1.4.json",
            ROOT
            / "releases"
            / "data-v0.1.0-public-governing"
            / "records"
            / "source_monitor_registry_v1.5.json",
        ]
        bound: set[str] = set()
        for path in paths:
            for identity, _key, url in _walk_urls(_load(path)):
                if identity in {SOURCE_ID, ORG_ID, f"MON-{SOURCE_ID}"}:
                    bound.add(url)
                    self.assertEqual(url, GOVERNED_OFFICIAL)
                self.assertNotIn(PARKING_HOST, url.lower())
        self.assertEqual(bound, {GOVERNED_OFFICIAL})

    def test_route_policy_does_not_invent_parking_failover(self) -> None:
        text = (ROOT / "curation" / "source_route_resilience_v0.1.json").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(SOURCE_ID, text)
        self.assertNotIn(PARKING_HOST, text)

    def test_current_control_pointer_records_disposition_c_leave_degraded(self) -> None:
        pointer = _load(ROOT / "curation" / "CURRENT_EXECUTION_CONTROL.json")
        assert isinstance(pointer, dict)
        programme_path = ROOT / str(pointer["current_programme_execution_state"])
        programme = _load(programme_path)
        assert isinstance(programme, dict)
        due = (programme.get("operational_due_cycle") or {}).get("current") or {}
        self.assertEqual(due.get("unresolved_failed_source_ids"), [SOURCE_ID])
        self.assertIs(due.get("source_health_invariants_weakened"), False)
        typed = (due.get("typed_failure_root_causes") or {}).get(SOURCE_ID) or {}
        self.assertEqual(typed.get("classification"), "EXTERNAL_BARRIER_DNS_NXDOMAIN")
        self.assertEqual(
            (typed.get("route_resolution") or {}).get("disposition"),
            "C_LEAVE_DEGRADED",
        )
        self.assertIs(programme.get("g0", {}).get("passed"), False)
        investigation = programme.get("src_14_021_disposition_investigation") or {}
        self.assertEqual(investigation.get("disposition_chosen"), "C")
        governed = investigation.get("governed_s2_identity_bearing_urls") or {}
        self.assertEqual(governed.get("official_url_only"), GOVERNED_OFFICIAL)
        self.assertEqual(governed.get("other_governed_official_urls_for_org"), [])
        self.assertIs(governed.get("in_route_policy"), False)


if __name__ == "__main__":
    unittest.main()
