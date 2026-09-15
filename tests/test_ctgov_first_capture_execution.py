from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator

from neuroai_workbench.collector import PinnedSocketHttpTransport
from neuroai_workbench.collector.dns import DnsGuard
from neuroai_workbench.collector.http_client import TransportResponse

ROOT = Path(__file__).parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import execute_ctgov_first_capture as capture
import review_ctgov_monitoring_onboarding as onboarding
from tests.test_ctgov_monitor_onboarding import _write_decisions, _write_materialization


GLOBAL_IP = "93.184.216.34"


def _study(nct_id: str = "NCT03333954") -> dict:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": "Synthetic PRIMA test"},
            "statusModule": {
                "overallStatus": "COMPLETED",
                "lastUpdatePostDateStruct": {"date": "2026-04-02"},
            },
            "designModule": {"studyType": "INTERVENTIONAL", "phases": ["NA"]},
        }
    }


class FakeTransport:
    def __init__(self, *, body: bytes, status: int = 200, content_type: str = "application/json") -> None:
        self.body = body
        self.status = status
        self.content_type = content_type
        self.requests = []

    def send(self, request, *, connect_timeout: float, read_timeout: float):
        self.requests.append(request)
        return TransportResponse(
            status=self.status,
            headers={"Content-Type": self.content_type},
            body=self.body,
            connected_address=GLOBAL_IP,
        )


def _dns_guard() -> DnsGuard:
    def resolve(host, port, *, type=socket.SOCK_STREAM):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (GLOBAL_IP, 0))]

    return DnsGuard(getaddrinfo=resolve)


def _build_onboarding(root: Path) -> Path:
    materialization = root / "materialization"
    _write_materialization(materialization)
    decisions = _write_decisions(root, materialization)
    result = onboarding.build_onboarding(materialization, decisions)
    out = root / "onboarding"
    onboarding.write_outputs(result, out)
    return out


def _authorization(root: Path, onboarding_dir: Path, *, decision: str = "AUTHORIZE_PRIMARY_CAPTURE") -> Path:
    verified = capture.verify_onboarding(onboarding_dir)
    rows = []
    for monitor_id, plan in sorted(verified["plans"].items()):
        rows.append(
            {
                "draft_monitor_id": monitor_id,
                "source_id": plan["source_id"],
                "nct_id": plan["nct_id"],
                "request_id": plan["first_capture_request_template"]["request_id"],
                "primary_route_id": plan["initial_capture_route_id"],
                "primary_url": plan["first_capture_request_template"]["requested_url"],
                "decision": decision,
                "rationale": "Synthetic explicit test authorization.",
            }
        )
    packet = {
        "schema_version": "0.1.0",
        "artifact": "ctgov_first_capture_authorization_packet",
        "status": "EXPLICIT_LOCAL_FIRST_CAPTURE_AUTHORIZATION",
        "onboarding_manifest_sha256": verified["manifest_sha256"],
        "workbench_commit": capture.WORKBENCH_COMMIT,
        "collector_profile_id": capture.PROFILE_ID,
        "collector_configuration_sha256": capture.collector_configuration_hash(),
        "authorized_by": "synthetic-test-authorizer",
        "authorized_at": "2026-09-15T12:00:00Z",
        "identity_boundary": "LOCAL_UNAUTHENTICATED_ATTRIBUTION",
        "rationale": "Synthetic authorization packet for offline fake-transport tests.",
        "decisions": rows,
        "network_execution_authorized": True,
        "primary_route_only": True,
        "fallback_capture_authorized": False,
        "quarantine_approval_authorized": False,
        "monitor_registry_successor_authorized": False,
        "source_namespace_publication_authorized": False,
        "trial_entity_creation_authorized": False,
        "trial_site_relationship_creation_authorized": False,
        "assessment_mutation_authorized": False,
        "canonical_publication_authorized": False,
        "authority_boundary": "Synthetic test authorization only.",
    }
    path = root / "first-capture-authorization.json"
    path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _rewrite_onboarding(onboarding_dir: Path, mutate) -> None:
    package_path = onboarding_dir / "ctgov-monitor-onboarding.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    mutate(package)
    payload = (json.dumps(package, indent=2, sort_keys=True) + "\n").encode("utf-8")
    package_path.write_bytes(payload)
    manifest_path = onboarding_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["path"] == "ctgov-monitor-onboarding.json":
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
            entry["bytes"] = len(payload)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class CTGovFirstCaptureControlTests(unittest.TestCase):
    def test_authorization_schema_accepts_exact_packet(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            auth_path = _authorization(root, onboarding_dir)
            packet = json.loads(auth_path.read_text(encoding="utf-8"))
            schema = json.loads((ROOT / "schemas" / "ctgov-first-capture-authorization.schema.json").read_text())
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(packet)), [])

    def test_profile_is_fixed_and_production_defaults_to_pinned_transport(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            collector = capture._build_collector(Path(td) / "quarantine")
            self.assertIsInstance(collector.http_client.transport, PinnedSocketHttpTransport)
            self.assertEqual(collector.config.max_redirects, 0)
            self.assertEqual(collector.config.max_attempts, 1)
            self.assertEqual(collector.config.allowed_content_types, frozenset({"application/json"}))
            self.assertEqual(capture.collector_profile()["workbench_commit"], capture.WORKBENCH_COMMIT)
            self.assertEqual(len(capture.collector_configuration_hash()), 64)

    def test_successful_fake_capture_persists_pending_quarantine_and_sanitized_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            auth_path = _authorization(root, onboarding_dir)
            operations = root / "operations"
            body = json.dumps(_study(), sort_keys=True).encode("utf-8")
            transport = FakeTransport(body=body)
            with patch.dict(os.environ, {"NEUROAI_LIVE_COLLECTION": "1"}, clear=False):
                result = capture.execute_first_captures(
                    onboarding_dir,
                    auth_path,
                    operations,
                    allow_network=True,
                    transport=transport,
                    dns_guard=_dns_guard(),
                    requested_at="2026-09-15T12:05:00Z",
                )
            self.assertEqual(result["success_count"], 1)
            self.assertEqual(result["blocked_count"], 0)
            receipt = result["receipts"][0]
            self.assertEqual(receipt["status"], "SUCCESS_IDENTITY_VERIFIED")
            self.assertEqual(receipt["observed_nct_id"], "NCT03333954")
            self.assertEqual(receipt["quarantine_approval_state"], "PENDING_HUMAN_APPROVAL")
            self.assertTrue(receipt["identity_verified"])
            self.assertFalse(receipt["quarantine_approval_performed"])
            self.assertFalse(receipt["monitor_registry_successor_created"])
            serialized = json.dumps(result, sort_keys=True)
            self.assertNotIn("Synthetic PRIMA test", serialized)
            self.assertNotIn("protocolSection", serialized)
            self.assertFalse(result["raw_response_bytes_embedded"])
            self.assertEqual(len(transport.requests), 1)
            self.assertEqual(transport.requests[0].validated_addresses, (GLOBAL_IP,))
            qpath = operations / "quarantine" / receipt["quarantine_path"]
            self.assertEqual(qpath.read_bytes(), body)
            records = list((operations / "quarantine" / "records").glob("*.json"))
            self.assertEqual(len(records), 1)
            qrecord = json.loads(records[0].read_text())
            self.assertEqual(qrecord["approval_state"], "PENDING_HUMAN_APPROVAL")
            self.assertIsNone(qrecord["approved_by"])
            self.assertFalse((operations / "discovery" / "registry_successors").exists())

    def test_pre_registry_request_binds_onboarding_not_registry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            verified = capture.verify_onboarding(onboarding_dir)
            plan = next(iter(verified["plans"].values()))
            request = capture.build_collection_request(
                plan, verified["manifest_sha256"], requested_at="2026-09-15T12:05:00Z"
            )
            self.assertEqual(request["onboarding_manifest_sha256"], verified["manifest_sha256"])
            self.assertNotIn("registry_sha256", request)
            self.assertEqual(request["requested_url"], f"https://clinicaltrials.gov/api/v2/studies/{plan['nct_id']}")

    def test_network_requires_all_explicit_gates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            auth_path = _authorization(root, onboarding_dir)
            operations = root / "operations"
            with self.assertRaisesRegex(PermissionError, "--allow-network"):
                capture.execute_first_captures(onboarding_dir, auth_path, operations, allow_network=False)
            with patch.dict(os.environ, {"NEUROAI_LIVE_COLLECTION": ""}, clear=False):
                with self.assertRaisesRegex(PermissionError, "NEUROAI_LIVE_COLLECTION"):
                    capture.execute_first_captures(onboarding_dir, auth_path, operations, allow_network=True)

    def test_operations_and_authorization_inside_repository_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            auth_path = _authorization(root, onboarding_dir)
            with self.assertRaisesRegex(ValueError, "OPERATIONS_ROOT_INSIDE_REPOSITORY_REFUSED"):
                capture.execute_first_captures(onboarding_dir, auth_path, ROOT / "_forbidden_ops", allow_network=True)

    def test_authority_escalation_and_incomplete_coverage_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            auth_path = _authorization(root, onboarding_dir)
            packet = json.loads(auth_path.read_text())
            packet["quarantine_approval_authorized"] = True
            auth_path.write_text(json.dumps(packet))
            verified = capture.verify_onboarding(onboarding_dir)
            with self.assertRaisesRegex(ValueError, "authority escalation"):
                capture.load_first_capture_authorization(auth_path, verified)

            auth_path = _authorization(root, onboarding_dir)
            packet = json.loads(auth_path.read_text())
            packet["decisions"] = []
            auth_path.write_text(json.dumps(packet))
            with self.assertRaisesRegex(ValueError, "decisions are required"):
                capture.load_first_capture_authorization(auth_path, verified)

    def test_wrong_workbench_commit_and_profile_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            verified = capture.verify_onboarding(onboarding_dir)
            auth_path = _authorization(root, onboarding_dir)
            packet = json.loads(auth_path.read_text())
            packet["workbench_commit"] = "0" * 40
            auth_path.write_text(json.dumps(packet))
            with self.assertRaisesRegex(ValueError, "Workbench commit mismatch"):
                capture.load_first_capture_authorization(auth_path, verified)

            auth_path = _authorization(root, onboarding_dir)
            packet = json.loads(auth_path.read_text())
            packet["collector_profile_id"] = "OTHER"
            auth_path.write_text(json.dumps(packet))
            with self.assertRaisesRegex(ValueError, "collector profile mismatch"):
                capture.load_first_capture_authorization(auth_path, verified)

    def test_primary_route_drift_fails_before_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            _rewrite_onboarding(
                onboarding_dir,
                lambda package: package["plans"][0]["routes"][0].__setitem__(
                    "url", "https://clinicaltrials.gov/study/NCT03333954"
                ),
            )
            with self.assertRaisesRegex(ValueError, "PRIMARY route drift"):
                capture.verify_onboarding(onboarding_dir)

    def test_wrong_nct_is_retained_but_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            auth_path = _authorization(root, onboarding_dir)
            transport = FakeTransport(body=json.dumps(_study("NCT99999999")).encode())
            with patch.dict(os.environ, {"NEUROAI_LIVE_COLLECTION": "1"}, clear=False):
                result = capture.execute_first_captures(
                    onboarding_dir,
                    auth_path,
                    root / "operations",
                    allow_network=True,
                    transport=transport,
                    dns_guard=_dns_guard(),
                    requested_at="2026-09-15T12:05:00Z",
                )
            receipt = result["receipts"][0]
            self.assertEqual(receipt["status"], "BLOCKED_NCT_IDENTITY_MISMATCH")
            self.assertFalse(receipt["identity_verified"])
            self.assertEqual(result["blocked_count"], 1)
            self.assertTrue((root / "operations" / "quarantine" / receipt["quarantine_path"]).is_file())

    def test_invalid_json_and_rejected_content_type_do_not_create_success(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            auth_path = _authorization(root, onboarding_dir)
            with patch.dict(os.environ, {"NEUROAI_LIVE_COLLECTION": "1"}, clear=False):
                invalid = capture.execute_first_captures(
                    onboarding_dir,
                    auth_path,
                    root / "ops-json",
                    allow_network=True,
                    transport=FakeTransport(body=b"{bad json"),
                    dns_guard=_dns_guard(),
                    requested_at="2026-09-15T12:05:00Z",
                )
            self.assertEqual(invalid["receipts"][0]["status"], "BLOCKED_INVALID_JSON")

            auth_path2 = _authorization(root, onboarding_dir)
            with patch.dict(os.environ, {"NEUROAI_LIVE_COLLECTION": "1"}, clear=False):
                rejected = capture.execute_first_captures(
                    onboarding_dir,
                    auth_path2,
                    root / "ops-type",
                    allow_network=True,
                    transport=FakeTransport(body=b"<html/>", content_type="text/html"),
                    dns_guard=_dns_guard(),
                    requested_at="2026-09-15T12:05:00Z",
                )
            self.assertEqual(rejected["receipts"][0]["status"], "BLOCKED_COLLECTION_FAILURE")
            self.assertEqual(rejected["receipts"][0]["failure_class"], "CONTENT_TYPE_REJECTED")

    def test_result_quarantine_mismatch_fails_closed(self) -> None:
        result = {
            "result_id": "CRES-" + "1" * 32,
            "source_id": "SRC-X",
            "monitor_id": "DMON-" + "2" * 32,
            "sha256": "3" * 64,
            "size_bytes": 10,
            "quarantine_path": "incoming/SRC-X/x",
        }
        quarantine = {
            **result,
            "sha256": "4" * 64,
            "approval_state": "PENDING_HUMAN_APPROVAL",
            "approved_at": None,
            "approved_by": None,
        }
        with self.assertRaisesRegex(ValueError, "mismatch: sha256"):
            capture.verify_result_quarantine_binding(result, quarantine)

    def test_repeat_successful_capture_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            auth_path = _authorization(root, onboarding_dir)
            operations = root / "operations"
            kwargs = {
                "allow_network": True,
                "transport": FakeTransport(body=json.dumps(_study()).encode()),
                "dns_guard": _dns_guard(),
                "requested_at": "2026-09-15T12:05:00Z",
            }
            with patch.dict(os.environ, {"NEUROAI_LIVE_COLLECTION": "1"}, clear=False):
                first = capture.execute_first_captures(onboarding_dir, auth_path, operations, **kwargs)
            self.assertEqual(first["success_count"], 1)
            with patch.dict(os.environ, {"NEUROAI_LIVE_COLLECTION": "1"}, clear=False):
                with self.assertRaisesRegex(ValueError, "REPEAT_SUCCESSFUL_FIRST_CAPTURE_REFUSED"):
                    capture.execute_first_captures(
                        onboarding_dir,
                        auth_path,
                        operations,
                        allow_network=True,
                        transport=FakeTransport(body=json.dumps(_study()).encode()),
                        dns_guard=_dns_guard(),
                        requested_at="2026-09-15T12:06:00Z",
                    )

    def test_defer_performs_zero_transport_requests(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            onboarding_dir = _build_onboarding(root)
            auth_path = _authorization(root, onboarding_dir, decision="DEFER")
            transport = FakeTransport(body=json.dumps(_study()).encode())
            with patch.dict(os.environ, {"NEUROAI_LIVE_COLLECTION": "1"}, clear=False):
                result = capture.execute_first_captures(
                    onboarding_dir,
                    auth_path,
                    root / "operations",
                    allow_network=True,
                    transport=transport,
                    dns_guard=_dns_guard(),
                )
            self.assertEqual(len(transport.requests), 0)
            self.assertEqual(result["receipts"][0]["status"], "DEFERRED_NO_NETWORK")
            self.assertEqual(result["success_count"], 0)


if __name__ == "__main__":
    unittest.main()
