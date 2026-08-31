from __future__ import annotations

import copy
import hashlib
import json
import socket
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import execute_ctgov_first_capture as capture
import review_ctgov_monitoring_onboarding as onboarding
from tests.test_ctgov_monitor_onboarding import _write_decisions, _write_materialization

from neuroai_workbench.collector.dns import DnsGuard
from neuroai_workbench.collector.http_client import HttpRequest

GLOBAL_IP = "93.184.216.34"
NCT_ID = "NCT03333954"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _dns(host: str, port: object, *args: Any, **kwargs: Any) -> list[tuple[Any, ...]]:
    if host != "clinicaltrials.gov":
        raise socket.gaierror("unexpected host")
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (GLOBAL_IP, 0))]


@dataclass
class FakeTransport:
    body: bytes
    content_type: str = "application/json"
    status: int = 200
    calls: list[HttpRequest] = field(default_factory=list)

    def send(
        self,
        request: HttpRequest,
        *,
        connect_timeout: float,
        read_timeout: float,
    ) -> tuple[int, dict[str, str], bytes]:
        self.calls.append(request)
        return self.status, {"Content-Type": self.content_type}, self.body


def _study(nct_id: str = NCT_ID) -> bytes:
    payload = {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": "Test PRIMA study"},
            "statusModule": {
                "overallStatus": "COMPLETED",
                "lastUpdatePostDateStruct": {"date": "2026-04-02"},
                "enrollmentInfo": {"count": 5},
            },
            "designModule": {"studyType": "INTERVENTIONAL", "phases": ["NA"]},
        }
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def _make_onboarding(root: Path) -> Path:
    materialization = root / "materialization"
    onboarding_dir = root / "onboarding"
    _write_materialization(materialization)
    decisions = _write_decisions(root, materialization)
    result = onboarding.build_onboarding(materialization, decisions)
    onboarding.write_outputs(result, onboarding_dir)
    return onboarding_dir


def _authorization(root: Path, onboarding_dir: Path, *, decision: str = "AUTHORIZE_PRIMARY_CAPTURE") -> Path:
    manifest_sha = _sha256((onboarding_dir / "manifest.json").read_bytes())
    package = json.loads((onboarding_dir / "ctgov-monitor-onboarding.json").read_text())
    plan = package["plans"][0]
    packet = {
        "schema_version": "0.1.0",
        "artifact": "ctgov_first_capture_authorization",
        "status": "EXPLICIT_LOCAL_FIRST_CAPTURE_AUTHORIZATION",
        "onboarding_manifest_sha256": manifest_sha,
        "workbench_commit": capture.WORKBENCH_COMMIT,
        "collector_profile_id": capture.COLLECTOR_PROFILE_ID,
        "authorized_by": "local-capture-authorizer",
        "authorized_at": "2026-08-31T13:30:00Z",
        "identity_boundary": "LOCAL_UNAUTHENTICATED_ATTRIBUTION",
        "captures": [
            {
                "draft_monitor_id": plan["draft_monitor_id"],
                "request_id": plan["first_capture_request_template"]["request_id"],
                "source_id": plan["source_id"],
                "nct_id": plan["nct_id"],
                "decision": decision,
                "rationale": "Explicit bounded test authorization.",
            }
        ],
        "network_execution_authorized": True,
        "primary_route_only": True,
        "fallback_route_authorized": False,
        "quarantine_approval_authorized": False,
        "monitoring_handoff_authorized": False,
        "monitor_registry_successor_authorized": False,
        "source_namespace_publication_authorized": False,
        "trial_entity_creation_authorized": False,
        "trial_site_relationship_creation_authorized": False,
        "assessment_mutation_authorized": False,
        "canonical_publication_authorized": False,
        "authority_boundary": "TEST PRIMARY FIRST CAPTURE ONLY",
    }
    path = root / "first-capture-authorization.json"
    path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    return path


class CTGovFirstCaptureExecutionTests(unittest.TestCase):
    def test_authorization_and_summary_schemas_are_valid_for_successful_capture(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            transport = FakeTransport(_study())
            result = capture.execute_first_capture(
                onboarding_dir,
                auth,
                root / "ops",
                execution_mode="INJECTED_TEST_TRANSPORT",
                requested_at="2026-08-31T13:31:00Z",
                transport=transport,
                dns_guard=DnsGuard(getaddrinfo=_dns),
            )
            auth_schema = json.loads((ROOT / "schemas" / "ctgov-first-capture-authorization.schema.json").read_text())
            summary_schema = json.loads((ROOT / "schemas" / "ctgov-first-capture-summary.schema.json").read_text())
            auth_value = json.loads(auth.read_text())
            self.assertEqual(list(Draft202012Validator(auth_schema).iter_errors(auth_value)), [])
            errors = list(Draft202012Validator(summary_schema).iter_errors(result["summary"]))
            self.assertEqual(errors, [], [error.message for error in errors])

    def test_successful_capture_is_pending_quarantine_review_and_exact_nct_verified(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            transport = FakeTransport(_study())
            result = capture.execute_first_capture(
                onboarding_dir,
                auth,
                root / "ops",
                execution_mode="INJECTED_TEST_TRANSPORT",
                requested_at="2026-08-31T13:31:00Z",
                transport=transport,
                dns_guard=DnsGuard(getaddrinfo=_dns),
            )
            summary = result["summary"]
            self.assertEqual(summary["authorized_capture_count"], 1)
            self.assertFalse(summary["network_execution_performed"])
            row = summary["capture_rows"][0]
            self.assertEqual(row["execution_state"], "CAPTURED_IDENTITY_VERIFIED_PENDING_QUARANTINE_REVIEW")
            self.assertEqual(row["expected_nct_id"], NCT_ID)
            self.assertEqual(row["observed_nct_id"], NCT_ID)
            self.assertTrue(row["identity_match"])
            self.assertEqual(row["quarantine_approval_state"], "PENDING_HUMAN_APPROVAL")
            self.assertEqual(row["evidence_state"], "RETRIEVED_BYTES_NOT_SUBSTANTIVELY_ADJUDICATED")
            self.assertFalse(row["handoff_eligible"])
            self.assertFalse(row["raw_bytes_in_summary"])
            self.assertEqual(len(transport.calls), 1)
            request = transport.calls[0]
            self.assertEqual(request.url, f"https://clinicaltrials.gov/api/v2/studies/{NCT_ID}")
            self.assertEqual(request.validated_addresses, (GLOBAL_IP,))
            self.assertFalse(summary["quarantine_approval_performed"])
            self.assertFalse(summary["monitoring_handoff_performed"])
            self.assertFalse(summary["monitor_registry_successor_created"])

    def test_collection_request_uses_onboarding_manifest_and_not_registry_digest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            transport = FakeTransport(_study())
            capture.execute_first_capture(
                onboarding_dir,
                auth,
                root / "ops",
                execution_mode="INJECTED_TEST_TRANSPORT",
                requested_at="2026-08-31T13:31:00Z",
                transport=transport,
                dns_guard=DnsGuard(getaddrinfo=_dns),
            )
            reservations = list((root / "ops" / "first-capture" / "executions").glob("*.json"))
            self.assertEqual(len(reservations), 1)
            reservation = json.loads(reservations[0].read_text())
            self.assertEqual(reservation["onboarding_manifest_sha256"], _sha256((onboarding_dir / "manifest.json").read_bytes()))
            self.assertRegex(reservation["collection_request_sha256"], r"^[0-9a-f]{64}$")
            self.assertNotIn("registry_sha256", reservation)

    def test_wrong_nct_is_quarantined_but_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            result = capture.execute_first_capture(
                onboarding_dir,
                auth,
                root / "ops",
                execution_mode="INJECTED_TEST_TRANSPORT",
                requested_at="2026-08-31T13:31:00Z",
                transport=FakeTransport(_study("NCT12345678")),
                dns_guard=DnsGuard(getaddrinfo=_dns),
            )
            row = result["summary"]["capture_rows"][0]
            self.assertEqual(row["execution_state"], "CAPTURED_IDENTITY_MISMATCH_BLOCKED")
            self.assertEqual(row["observed_nct_id"], "NCT12345678")
            self.assertFalse(row["identity_match"])
            self.assertEqual(row["quarantine_approval_state"], "PENDING_HUMAN_APPROVAL")
            self.assertIsNotNone(row["quarantine_id"])
            self.assertFalse(row["handoff_eligible"])

    def test_invalid_json_is_quarantined_but_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            result = capture.execute_first_capture(
                onboarding_dir,
                auth,
                root / "ops",
                execution_mode="INJECTED_TEST_TRANSPORT",
                requested_at="2026-08-31T13:31:00Z",
                transport=FakeTransport(b"{not-json"),
                dns_guard=DnsGuard(getaddrinfo=_dns),
            )
            row = result["summary"]["capture_rows"][0]
            self.assertEqual(row["execution_state"], "CAPTURED_JSON_INVALID_BLOCKED")
            self.assertEqual(row["quarantine_approval_state"], "PENDING_HUMAN_APPROVAL")
            self.assertIsNone(row["observed_nct_id"])
            self.assertFalse(row["handoff_eligible"])

    def test_non_json_content_type_is_collector_failure_with_no_quarantine(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            result = capture.execute_first_capture(
                onboarding_dir,
                auth,
                root / "ops",
                execution_mode="INJECTED_TEST_TRANSPORT",
                requested_at="2026-08-31T13:31:00Z",
                transport=FakeTransport(b"html", content_type="text/html"),
                dns_guard=DnsGuard(getaddrinfo=_dns),
            )
            row = result["summary"]["capture_rows"][0]
            self.assertEqual(row["execution_state"], "COLLECTOR_FAILURE")
            self.assertIsNotNone(row["failure_id"])
            self.assertIsNone(row["quarantine_id"])

    def test_reservation_prevents_automatic_reexecution(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            first_transport = FakeTransport(_study())
            capture.execute_first_capture(
                onboarding_dir,
                auth,
                root / "ops",
                execution_mode="INJECTED_TEST_TRANSPORT",
                requested_at="2026-08-31T13:31:00Z",
                transport=first_transport,
                dns_guard=DnsGuard(getaddrinfo=_dns),
            )
            second_transport = FakeTransport(_study())
            with self.assertRaisesRegex(ValueError, "FIRST_CAPTURE_REQUEST_ALREADY_RESERVED"):
                capture.execute_first_capture(
                    onboarding_dir,
                    auth,
                    root / "ops",
                    execution_mode="INJECTED_TEST_TRANSPORT",
                    requested_at="2026-08-31T13:31:00Z",
                    transport=second_transport,
                    dns_guard=DnsGuard(getaddrinfo=_dns),
                )
            self.assertEqual(len(first_transport.calls), 1)
            self.assertEqual(second_transport.calls, [])

    def test_manifest_tampering_and_authority_escalation_fail_before_capture(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            package = onboarding_dir / "ctgov-monitor-onboarding.json"
            package.write_text(package.read_text() + "\n")
            transport = FakeTransport(_study())
            with self.assertRaisesRegex(ValueError, "manifest mismatch"):
                capture.execute_first_capture(
                    onboarding_dir,
                    auth,
                    root / "ops-a",
                    execution_mode="INJECTED_TEST_TRANSPORT",
                    transport=transport,
                    dns_guard=DnsGuard(getaddrinfo=_dns),
                )
            self.assertEqual(transport.calls, [])

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            packet = json.loads(auth.read_text())
            packet["quarantine_approval_authorized"] = True
            auth.write_text(json.dumps(packet))
            transport = FakeTransport(_study())
            with self.assertRaisesRegex(ValueError, "authority boundary weakened"):
                capture.execute_first_capture(
                    onboarding_dir,
                    auth,
                    root / "ops-b",
                    execution_mode="INJECTED_TEST_TRANSPORT",
                    transport=transport,
                    dns_guard=DnsGuard(getaddrinfo=_dns),
                )
            self.assertEqual(transport.calls, [])

    def test_incomplete_or_duplicate_authorization_fails_before_capture(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            packet = json.loads(auth.read_text())
            packet["captures"] = []
            auth.write_text(json.dumps(packet))
            with self.assertRaisesRegex(ValueError, "non-empty object array"):
                capture.execute_first_capture(
                    onboarding_dir,
                    auth,
                    root / "ops-a",
                    execution_mode="INJECTED_TEST_TRANSPORT",
                    transport=FakeTransport(_study()),
                    dns_guard=DnsGuard(getaddrinfo=_dns),
                )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            packet = json.loads(auth.read_text())
            packet["captures"].append(copy.deepcopy(packet["captures"][0]))
            auth.write_text(json.dumps(packet))
            with self.assertRaisesRegex(ValueError, "Duplicate first-capture authorization"):
                capture.execute_first_capture(
                    onboarding_dir,
                    auth,
                    root / "ops-b",
                    execution_mode="INJECTED_TEST_TRANSPORT",
                    transport=FakeTransport(_study()),
                    dns_guard=DnsGuard(getaddrinfo=_dns),
                )

    def test_defer_performs_no_capture(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir, decision="DEFER")
            transport = FakeTransport(_study())
            result = capture.execute_first_capture(
                onboarding_dir,
                auth,
                root / "ops",
                execution_mode="INJECTED_TEST_TRANSPORT",
                requested_at="2026-08-31T13:31:00Z",
                transport=transport,
                dns_guard=DnsGuard(getaddrinfo=_dns),
            )
            self.assertEqual(result["summary"]["authorized_capture_count"], 0)
            self.assertEqual(result["summary"]["deferred_capture_count"], 1)
            self.assertFalse(result["summary"]["capture_execution_performed"])
            self.assertEqual(result["summary"]["capture_rows"], [])
            self.assertEqual(transport.calls, [])

    def test_operations_and_sanitized_outputs_must_stay_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            with self.assertRaisesRegex(ValueError, "OPERATIONS_ROOT_INSIDE_S2_REPOSITORY_REFUSED"):
                capture.execute_first_capture(
                    onboarding_dir,
                    auth,
                    ROOT / "tmp-first-capture-ops",
                    execution_mode="INJECTED_TEST_TRANSPORT",
                    transport=FakeTransport(_study()),
                    dns_guard=DnsGuard(getaddrinfo=_dns),
                )

            result = capture.execute_first_capture(
                onboarding_dir,
                auth,
                root / "ops",
                execution_mode="INJECTED_TEST_TRANSPORT",
                requested_at="2026-08-31T13:31:00Z",
                transport=FakeTransport(_study()),
                dns_guard=DnsGuard(getaddrinfo=_dns),
            )
            with self.assertRaisesRegex(ValueError, "FIRST_CAPTURE_SANITIZED_OUTPUT_INSIDE_S2_REPOSITORY_REFUSED"):
                capture.write_sanitized_outputs(result, ROOT / "tmp-first-capture-summary")

    def test_sanitized_output_contains_no_raw_payload_and_is_collision_safe(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _make_onboarding(root)
            auth = _authorization(root, onboarding_dir)
            raw = _study()
            result = capture.execute_first_capture(
                onboarding_dir,
                auth,
                root / "ops",
                execution_mode="INJECTED_TEST_TRANSPORT",
                requested_at="2026-08-31T13:31:00Z",
                transport=FakeTransport(raw),
                dns_guard=DnsGuard(getaddrinfo=_dns),
            )
            output = root / "sanitized"
            first = capture.write_sanitized_outputs(result, output)
            second = capture.write_sanitized_outputs(result, output)
            self.assertEqual(first, second)
            self.assertNotIn(raw.decode("utf-8"), (output / "first-capture-summary.json").read_text())
            self.assertFalse(first["raw_capture_bytes_packaged"])
            (output / "first-capture-summary.json").write_text("{}\n")
            with self.assertRaisesRegex(ValueError, "OUTPUT_COLLISION_REFUSED"):
                capture.write_sanitized_outputs(result, output)

    def test_collector_configuration_hash_is_deterministic_and_profile_bound(self) -> None:
        first = capture.collector_configuration_hash()
        second = capture.collector_configuration_hash()
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        changed = copy.deepcopy(capture.COLLECTOR_PROFILE)
        changed["max_redirects"] = 1
        self.assertNotEqual(first, hashlib.sha256(capture._canonical_bytes(changed)).hexdigest())
        self.assertEqual(capture.COLLECTOR_PROFILE["max_redirects"], 0)
        self.assertEqual(capture.COLLECTOR_PROFILE["allowed_content_types"], ["application/json"])
        self.assertEqual(capture.COLLECTOR_PROFILE["max_attempts"], 1)


if __name__ == "__main__":
    unittest.main()
