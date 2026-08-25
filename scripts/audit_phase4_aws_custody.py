from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

SCHEMA_VERSION = "0.1.0"
FILE_SYSTEM_ID_RE = re.compile(r"^fs-[0-9a-fA-F]{8,40}$")
ACCESS_POINT_ID_RE = re.compile(r"^fsap-[0-9a-fA-F]{8,40}$")
ACCOUNT_ID_RE = re.compile(r"^[0-9]{12}$")
REGION_RE = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d+$")


class AuditError(RuntimeError):
    """Raised when the deployed-custody audit cannot establish a required invariant."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{time.time_ns()}")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(
        path,
        (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def _validate_identifier(value: str, pattern: re.Pattern[str], label: str) -> str:
    normalized = value.strip()
    if pattern.fullmatch(normalized) is None:
        raise AuditError(f"invalid {label}: {value!r}")
    return normalized


def _require_external_empty_evidence_dir(repo_root: Path, evidence_dir: Path) -> Path:
    repo_root = repo_root.resolve()
    evidence_dir = evidence_dir.resolve()
    if evidence_dir == repo_root or repo_root in evidence_dir.parents:
        raise AuditError("audit evidence directory must be outside the repository")
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        raise AuditError("audit evidence directory must be empty")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir


def _run_aws(arguments: Sequence[str]) -> bytes:
    completed = subprocess.run(
        ["aws", *arguments, "--output", "json", "--no-cli-pager"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise AuditError(f"AWS CLI command failed ({' '.join(arguments)}): {stderr}")
    return completed.stdout


def _parse_json(raw: bytes, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditError(f"{label} did not return valid JSON") from exc


def _record_command(
    *,
    name: str,
    arguments: Sequence[str],
    runner: Callable[[Sequence[str]], bytes],
    evidence_dir: Path,
) -> tuple[Any, dict[str, Any]]:
    started_at = _utc_now()
    raw = runner(arguments)
    value = _parse_json(raw, name)
    filename = f"{name}.json"
    _atomic_write(evidence_dir / filename, raw)
    record = {
        "name": name,
        "arguments": list(arguments),
        "started_at": started_at,
        "completed_at": _utc_now(),
        "raw_output": {
            "path": filename,
            "byte_count": len(raw),
            "sha256": _sha256_bytes(raw),
        },
    }
    return value, record


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AuditError(f"{label} must be a JSON object")
    return value


def _extract_policy(response: Any) -> dict[str, Any]:
    response = _require_object(response, "EFS file-system policy response")
    policy_value = response.get("Policy")
    if not isinstance(policy_value, str) or not policy_value.strip():
        raise AuditError("EFS file-system policy response lacks Policy")
    try:
        policy = json.loads(policy_value)
    except json.JSONDecodeError as exc:
        raise AuditError("EFS file-system Policy is not valid JSON") from exc
    if not isinstance(policy, dict):
        raise AuditError("EFS file-system Policy root must be an object")
    return policy


def _validate_file_system(response: Any, file_system_id: str) -> dict[str, Any]:
    response = _require_object(response, "describe-file-systems response")
    rows = response.get("FileSystems")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise AuditError("describe-file-systems must return exactly one file system")
    row = rows[0]
    if row.get("FileSystemId") != file_system_id:
        raise AuditError("describe-file-systems returned an unexpected file-system ID")
    if row.get("Encrypted") is not True:
        raise AuditError("custody EFS file system is not encrypted")
    kms_key_id = row.get("KmsKeyId")
    if not isinstance(kms_key_id, str) or not kms_key_id:
        raise AuditError("encrypted custody EFS file system lacks a KMS key identifier")
    return {
        "file_system_id": file_system_id,
        "encrypted": True,
        "kms_key_id": kms_key_id,
        "life_cycle_state": row.get("LifeCycleState"),
    }


def _validate_access_points(
    response: Any,
    *,
    file_system_id: str,
    writer_access_point_id: str,
    verifier_access_point_id: str,
) -> dict[str, Any]:
    response = _require_object(response, "describe-access-points response")
    rows = response.get("AccessPoints")
    if not isinstance(rows, list):
        raise AuditError("describe-access-points response lacks AccessPoints")
    by_id = {
        row.get("AccessPointId"): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("AccessPointId"), str)
    }
    expected_ids = {writer_access_point_id, verifier_access_point_id}
    missing = sorted(expected_ids - set(by_id))
    if missing:
        raise AuditError(f"expected EFS access point(s) are missing: {missing}")

    result: dict[str, Any] = {}
    for role, access_point_id in (
        ("writer", writer_access_point_id),
        ("verifier", verifier_access_point_id),
    ):
        row = by_id[access_point_id]
        if row.get("FileSystemId") != file_system_id:
            raise AuditError(f"{role} access point belongs to a different file system")
        root = row.get("RootDirectory")
        posix = row.get("PosixUser")
        if not isinstance(root, dict) or root.get("Path") != "/phase4":
            raise AuditError(f"{role} access point root is not /phase4")
        if not isinstance(posix, dict) or str(posix.get("Uid")) != "1000" or str(posix.get("Gid")) != "1000":
            raise AuditError(f"{role} access point does not enforce POSIX uid/gid 1000")
        result[role] = {
            "access_point_id": access_point_id,
            "root_path": "/phase4",
            "uid": 1000,
            "gid": 1000,
            "life_cycle_state": row.get("LifeCycleState"),
        }
    return result


def _validate_public_access_check(response: Any) -> dict[str, Any]:
    response = _require_object(response, "Access Analyzer public-access check")
    if response.get("result") != "PASS":
        raise AuditError(
            "Access Analyzer public-access check did not return PASS: "
            f"{response.get('result')!r}"
        )
    return {
        "result": "PASS",
        "message": response.get("message"),
        "reasons": response.get("reasons", []),
    }


def _validate_policy_findings(response: Any) -> dict[str, Any]:
    response = _require_object(response, "Access Analyzer policy validation")
    findings = response.get("findings", [])
    if not isinstance(findings, list):
        raise AuditError("Access Analyzer policy validation findings must be a list")
    blocking = [
        item
        for item in findings
        if isinstance(item, dict)
        and item.get("findingType") in {"ERROR", "SECURITY_WARNING"}
    ]
    if blocking:
        codes = [item.get("issueCode") for item in blocking]
        raise AuditError(
            "Access Analyzer policy validation returned blocking findings: "
            f"{codes}"
        )
    counts: dict[str, int] = {}
    for item in findings:
        if isinstance(item, dict) and isinstance(item.get("findingType"), str):
            key = item["findingType"]
            counts[key] = counts.get(key, 0) + 1
    return {
        "blocking_findings": 0,
        "finding_counts": counts,
        "finding_count": len(findings),
    }


def _validate_mount_targets(response: Any, file_system_id: str) -> dict[str, Any]:
    response = _require_object(response, "describe-mount-targets response")
    rows = response.get("MountTargets")
    if not isinstance(rows, list) or len(rows) < 2:
        raise AuditError("custody EFS requires at least two mount targets")
    ids: list[str] = []
    availability_zones: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("FileSystemId") != file_system_id:
            raise AuditError("mount-target response contains an unexpected file system")
        mount_target_id = row.get("MountTargetId")
        if not isinstance(mount_target_id, str) or not mount_target_id:
            raise AuditError("mount target lacks MountTargetId")
        ids.append(mount_target_id)
        zone = row.get("AvailabilityZoneName")
        if isinstance(zone, str) and zone:
            availability_zones.add(zone)
    if availability_zones and len(availability_zones) < 2:
        raise AuditError("custody EFS mount targets do not span at least two Availability Zones")
    return {
        "mount_target_ids": sorted(ids),
        "availability_zones": sorted(availability_zones),
        "mount_target_count": len(ids),
    }


def audit_custody(
    *,
    repo_root: Path,
    evidence_dir: Path,
    region: str,
    expected_account_id: str,
    file_system_id: str,
    writer_access_point_id: str,
    verifier_access_point_id: str,
    runner: Callable[[Sequence[str]], bytes] = _run_aws,
) -> dict[str, Any]:
    region = _validate_identifier(region, REGION_RE, "AWS region")
    expected_account_id = _validate_identifier(expected_account_id, ACCOUNT_ID_RE, "AWS account ID")
    file_system_id = _validate_identifier(file_system_id, FILE_SYSTEM_ID_RE, "EFS file-system ID")
    writer_access_point_id = _validate_identifier(
        writer_access_point_id,
        ACCESS_POINT_ID_RE,
        "writer access-point ID",
    )
    verifier_access_point_id = _validate_identifier(
        verifier_access_point_id,
        ACCESS_POINT_ID_RE,
        "verifier access-point ID",
    )
    if writer_access_point_id == verifier_access_point_id:
        raise AuditError("writer and verifier access-point IDs must be distinct")

    evidence_dir = _require_external_empty_evidence_dir(repo_root, evidence_dir)
    commands: list[dict[str, Any]] = []

    caller, record = _record_command(
        name="caller-identity",
        arguments=["sts", "get-caller-identity", "--region", region],
        runner=runner,
        evidence_dir=evidence_dir,
    )
    commands.append(record)
    caller = _require_object(caller, "caller identity")
    if caller.get("Account") != expected_account_id:
        raise AuditError(
            f"AWS account mismatch: expected {expected_account_id}, observed {caller.get('Account')!r}"
        )

    file_system, record = _record_command(
        name="file-system",
        arguments=[
            "efs",
            "describe-file-systems",
            "--file-system-id",
            file_system_id,
            "--region",
            region,
        ],
        runner=runner,
        evidence_dir=evidence_dir,
    )
    commands.append(record)
    file_system_summary = _validate_file_system(file_system, file_system_id)

    access_points, record = _record_command(
        name="access-points",
        arguments=[
            "efs",
            "describe-access-points",
            "--file-system-id",
            file_system_id,
            "--region",
            region,
        ],
        runner=runner,
        evidence_dir=evidence_dir,
    )
    commands.append(record)
    access_point_summary = _validate_access_points(
        access_points,
        file_system_id=file_system_id,
        writer_access_point_id=writer_access_point_id,
        verifier_access_point_id=verifier_access_point_id,
    )

    mount_targets, record = _record_command(
        name="mount-targets",
        arguments=[
            "efs",
            "describe-mount-targets",
            "--file-system-id",
            file_system_id,
            "--region",
            region,
        ],
        runner=runner,
        evidence_dir=evidence_dir,
    )
    commands.append(record)
    mount_target_summary = _validate_mount_targets(mount_targets, file_system_id)

    policy_response, record = _record_command(
        name="file-system-policy-response",
        arguments=[
            "efs",
            "describe-file-system-policy",
            "--file-system-id",
            file_system_id,
            "--region",
            region,
        ],
        runner=runner,
        evidence_dir=evidence_dir,
    )
    commands.append(record)
    policy = _extract_policy(policy_response)
    policy_path = evidence_dir / "file-system-policy.json"
    _write_json(policy_path, policy)
    policy_sha256 = _sha256_bytes(_canonical_bytes(policy))

    validation, record = _record_command(
        name="policy-validation",
        arguments=[
            "accessanalyzer",
            "validate-policy",
            "--policy-document",
            f"file://{policy_path}",
            "--policy-type",
            "RESOURCE_POLICY",
            "--region",
            region,
        ],
        runner=runner,
        evidence_dir=evidence_dir,
    )
    commands.append(record)
    validation_summary = _validate_policy_findings(validation)

    public_access, record = _record_command(
        name="public-access-check",
        arguments=[
            "accessanalyzer",
            "check-no-public-access",
            "--policy-document",
            f"file://{policy_path}",
            "--resource-type",
            "AWS::EFS::FileSystem",
            "--region",
            region,
        ],
        runner=runner,
        evidence_dir=evidence_dir,
    )
    commands.append(record)
    public_access_summary = _validate_public_access_check(public_access)

    report_basis = {
        "schema_version": SCHEMA_VERSION,
        "audited_at": _utc_now(),
        "status": "DEPLOYED_RESOURCE_POLICY_AUDIT_PASS",
        "region": region,
        "expected_account_id": expected_account_id,
        "caller_arn": caller.get("Arn"),
        "file_system": file_system_summary,
        "access_points": access_point_summary,
        "mount_targets": mount_target_summary,
        "file_system_policy": {
            "path": policy_path.name,
            "canonical_sha256": policy_sha256,
        },
        "policy_validation": validation_summary,
        "public_access_check": public_access_summary,
        "commands": commands,
        "authority_boundary": (
            "This report validates selected deployed EFS configuration facts, generic resource-policy findings, "
            "and the EFS public-access policy check. It does not establish the composed effective permissions of "
            "all IAM principals, writer/verifier session provenance, POSIX mutation behavior, backup/restore integrity, "
            "provider acquisition, release eligibility, scientific relevance, or canonical identity."
        ),
    }
    digest = _sha256_bytes(_canonical_bytes(report_basis))
    report = {
        **report_basis,
        "audit_id": f"PHASE4-AWS-CUSTODY-AUDIT-{digest[:24].upper()}",
        "audit_sha256": digest,
    }
    _write_json(evidence_dir / "phase4-aws-custody-audit.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit deployed Phase 4 EFS custody policy/configuration and preserve command evidence."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--expected-account-id", required=True)
    parser.add_argument("--file-system-id", required=True)
    parser.add_argument("--writer-access-point-id", required=True)
    parser.add_argument("--verifier-access-point-id", required=True)
    args = parser.parse_args()

    try:
        report = audit_custody(
            repo_root=args.repo_root,
            evidence_dir=args.evidence_dir,
            region=args.region,
            expected_account_id=args.expected_account_id,
            file_system_id=args.file_system_id,
            writer_access_point_id=args.writer_access_point_id,
            verifier_access_point_id=args.verifier_access_point_id,
        )
    except AuditError as exc:
        print(f"AUDIT_FAIL: {exc}", file=os.sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
