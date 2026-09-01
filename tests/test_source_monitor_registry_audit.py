from __future__ import annotations

import unittest

from scripts.audit_source_monitor_registry import audit_registry


class SourceMonitorRegistryAuditTests(unittest.TestCase):
    def test_counts_external_local_and_duplicate_locators(self) -> None:
        rows = [
            {
                "monitor_id": "MON-1",
                "source_id": "SRC-1",
                "url": "https://Example.org/path/",
                "publisher": "Example",
                "source_class": "OFFICIAL_PAGE",
                "cadence": "MONTHLY",
                "last_successful_retrieval": "2026-07-29",
                "baseline_evidence_state": "CURRENT_SOURCE_RETRIEVED",
                "baseline_verification_state": "CURRENT_VERIFIED",
                "network_access_required": True,
            },
            {
                "monitor_id": "MON-2",
                "source_id": "SRC-2",
                "url": "https://example.org/path",
                "publisher": "Example",
                "source_class": "OFFICIAL_PAGE",
                "cadence": "QUARTERLY",
                "last_successful_retrieval": "2026-07-29",
                "baseline_evidence_state": "CURRENT_SOURCE_RETRIEVED",
                "baseline_verification_state": "CURRENT_VERIFIED",
                "network_access_required": True,
            },
            {
                "monitor_id": "MON-3",
                "source_id": "SRC-3",
                "url": "/mnt/data/controlled.json",
                "publisher": "Controlled project input",
                "source_class": "CONTROLLED_LOCAL_INPUT",
                "cadence": "QUARTERLY",
                "last_successful_retrieval": "2026-07-29",
                "baseline_evidence_state": "PUBLIC_RESEARCH_ARTIFACT",
                "baseline_verification_state": "CURRENT_VERIFIED",
                "network_access_required": True,
            },
        ]

        result = audit_registry(rows)

        self.assertEqual(result["counts"]["registry_record_count"], 3)
        self.assertEqual(result["counts"]["external_http_record_count"], 2)
        self.assertEqual(result["counts"]["controlled_local_input_record_count"], 1)
        self.assertEqual(result["counts"]["unique_exact_locator_count"], 3)
        self.assertEqual(
            result["counts"]["unique_external_normalized_locator_count"], 1
        )
        self.assertEqual(
            result["counts"]["normalized_external_duplicate_locator_group_count"],
            1,
        )
        self.assertEqual(
            result["anomalies"][0]["code"], "LOCAL_INPUT_MARKED_NETWORK_REQUIRED"
        )
        self.assertFalse(result["metadata"]["network_requests_performed"])
        self.assertFalse(result["metadata"]["retrieval_success_reverified"])

    def test_duplicate_source_id_fails_closed(self) -> None:
        rows = [
            {"monitor_id": "MON-1", "source_id": "SRC-1", "url": "https://a.example/"},
            {"monitor_id": "MON-2", "source_id": "SRC-1", "url": "https://b.example/"},
        ]
        with self.assertRaisesRegex(ValueError, "Duplicate source_id"):
            audit_registry(rows)

    def test_missing_required_identity_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires monitor_id, source_id, and url"):
            audit_registry([{"monitor_id": "MON-1", "source_id": "SRC-1"}])


if __name__ == "__main__":
    unittest.main()
