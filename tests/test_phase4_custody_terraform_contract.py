from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra" / "aws-phase4-custody"


class Phase4CustodyTerraformStaticContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main = (INFRA / "main.tf").read_text(encoding="utf-8")
        cls.variables = (INFRA / "variables.tf").read_text(encoding="utf-8")
        cls.versions = (INFRA / "versions.tf").read_text(encoding="utf-8")

    def test_toolchain_versions_are_exactly_pinned(self) -> None:
        self.assertIn('required_version = "= 1.15.8"', self.versions)
        self.assertIn('version = "= 6.60.0"', self.versions)

    def test_client_access_outside_declared_access_points_is_explicitly_denied(self) -> None:
        statement = self._statement("DenyClientAccessOutsideApprovedAccessPoints")
        self.assertIn('Effect    = "Deny"', statement)
        self.assertIn('Principal = "*"', statement)
        for action in (
            "elasticfilesystem:ClientMount",
            "elasticfilesystem:ClientWrite",
            "elasticfilesystem:ClientRootAccess",
        ):
            self.assertIn(action, statement)
        self.assertIn("StringNotEquals", statement)
        self.assertIn("aws_efs_access_point.custody.arn", statement)
        self.assertIn("aws_efs_access_point.verifier.arn", statement)

    def test_verifier_access_point_is_globally_non_writable(self) -> None:
        statement = self._statement("DenyWriteThroughVerifierAccessPoint")
        self.assertIn('Effect    = "Deny"', statement)
        self.assertIn('Principal = "*"', statement)
        self.assertIn("elasticfilesystem:ClientWrite", statement)
        self.assertIn("elasticfilesystem:ClientRootAccess", statement)
        self.assertIn("StringEquals", statement)
        self.assertIn("aws_efs_access_point.verifier.arn", statement)

    def test_intended_writer_and_verifier_grants_are_access_point_bound(self) -> None:
        writer = self._statement("AllowAcquisitionWriter")
        verifier = self._statement("AllowReadOnlyVerifier")

        self.assertIn("var.writer_principal_arns", writer)
        self.assertIn("elasticfilesystem:ClientMount", writer)
        self.assertIn("elasticfilesystem:ClientWrite", writer)
        self.assertIn("aws_efs_access_point.custody.arn", writer)
        self.assertIn('"aws:SecureTransport"', writer)
        self.assertIn('"elasticfilesystem:AccessedViaMountTarget"', writer)

        self.assertIn("var.verifier_principal_arns", verifier)
        self.assertIn("elasticfilesystem:ClientMount", verifier)
        self.assertNotIn("elasticfilesystem:ClientWrite", verifier)
        self.assertIn("aws_efs_access_point.verifier.arn", verifier)
        self.assertIn('"aws:SecureTransport"', verifier)
        self.assertIn('"elasticfilesystem:AccessedViaMountTarget"', verifier)

    def test_verifier_principals_have_defense_in_depth_mutation_deny(self) -> None:
        statement = self._statement("DenyVerifierMutation")
        self.assertIn("var.verifier_principal_arns", statement)
        self.assertIn("elasticfilesystem:ClientWrite", statement)
        self.assertIn("elasticfilesystem:ClientRootAccess", statement)

    def test_writer_and_verifier_principal_sets_must_be_disjoint(self) -> None:
        self.assertIn(
            'check "writer_and_verifier_principals_are_disjoint"',
            self.variables,
        )
        self.assertIn(
            "setintersection(var.writer_principal_arns, var.verifier_principal_arns)",
            self.variables,
        )

    def test_policy_avoids_unreviewed_principal_condition_shortcuts(self) -> None:
        self.assertNotIn("NotPrincipal", self.main)
        self.assertNotIn("aws:PrincipalArn", self.main)

    def test_vault_lock_remains_governance_mode(self) -> None:
        lock = self._resource("aws_backup_vault_lock_configuration", "custody")
        self.assertNotIn("changeable_for_days", lock)
        self.assertIn("min_retention_days", lock)
        self.assertIn("max_retention_days", lock)

    def _statement(self, sid: str) -> str:
        marker = f'Sid       = "{sid}"'
        if marker not in self.main:
            marker = f'Sid    = "{sid}"'
        self.assertIn(marker, self.main)
        start = self.main.index(marker)
        next_sid = self.main.find("\n      {\n        Sid", start + len(marker))
        end = len(self.main) if next_sid == -1 else next_sid
        return self.main[start:end]

    def _resource(self, resource_type: str, name: str) -> str:
        marker = f'resource "{resource_type}" "{name}" {{'
        self.assertIn(marker, self.main)
        start = self.main.index(marker)
        next_resource = self.main.find("\nresource ", start + len(marker))
        end = len(self.main) if next_resource == -1 else next_resource
        return self.main[start:end]


if __name__ == "__main__":
    unittest.main()
