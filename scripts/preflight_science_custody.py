from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any, Callable

import acquire_science_candidates as acquisition

SCHEMA_VERSION = "0.1.0"
PREFLIGHT_DIRNAME = "preflight"
MANIFEST_NAME = "preflight-manifest.json"
PERSISTENCE_REPORT_NAME = "persistence-verification.json"
RESTORE_REPORT_NAME = "restore-comparison.json"
_DENIED_ERRNOS = {errno.EACCES, errno.EPERM, errno.EROFS}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    acquisition._atomic_write(
        path,
        (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def _resolve_preflight(root: Path, preflight_id: str) -> Path:
    if not preflight_id.startswith("SCIENCE-CUSTODY-PREFLIGHT-"):
        raise ValueError("invalid preflight_id")
    root_resolved = root.resolve()
    path = (root_resolved / PREFLIGHT_DIRNAME / preflight_id).resolve()
    if root_resolved not in path.parents:
        raise ValueError("preflight path escapes custody root")
    return path


def _file_record(preflight_root: Path, relative_path: str) -> dict[str, Any]:
    path = (preflight_root / relative_path).resolve()
    if preflight_root.resolve() not in path.parents:
        raise ValueError(f"preflight file escapes root: {relative_path}")
    raw = path.read_bytes()
    return {
        "relative_path": relative_path,
        "byte_count": len(raw),
        "sha256": _sha256_bytes(raw),
    }


def prepare_preflight(
    custody_root: Path,
    *,
    payload_size: int = 4096,
    clock_fn: Callable[[], str] = acquisition._utc_now,
) -> dict[str, Any]:
    if payload_size < 1:
        raise ValueError("payload_size must be positive")
    acquisition.validate_output_root(custody_root)
    custody_root.mkdir(parents=True, exist_ok=True)

    nonce = secrets.token_hex(10).upper()
    preflight_id = f"SCIENCE-CUSTODY-PREFLIGHT-{nonce}"
    preflight_root = _resolve_preflight(custody_root, preflight_id)
    preflight_root.mkdir(parents=True, exist_ok=False)

    payload = secrets.token_bytes(payload_size)
    acquisition._atomic_write(preflight_root / "payload.bin", payload)

    replacement_path = preflight_root / "atomic-replace.txt"
    acquisition._atomic_write(replacement_path, b"phase-one\n")
    acquisition._atomic_write(replacement_path, b"phase-two\n")

    nested_state = {
        "preflight_id": preflight_id,
        "state": "SYNTHETIC_STORAGE_PREFLIGHT",
        "canonical_effect": "NONE",
    }
    _write_json(preflight_root / "nested" / "state.json", nested_state)

    files = [
        _file_record(preflight_root, "payload.bin"),
        _file_record(preflight_root, "atomic-replace.txt"),
        _file_record(preflight_root, "nested/state.json"),
    ]
    manifest_basis = {
        "schema_version": SCHEMA_VERSION,
        "preflight_id": preflight_id,
        "prepared_at": clock_fn(),
        "custody_root_resolved": str(custody_root.resolve()),
        "filesystem_test": "ATOMIC_WRITE_PERSISTENCE_AND_EXACT_BYTE_READBACK",
        "synthetic": True,
        "files": files,
        "expected_atomic_replace_sha256": _sha256_bytes(b"phase-two\n"),
        "authority_boundary": (
            "This is synthetic storage-semantic evidence only. It establishes no provider retrieval, "
            "production durability, backup success, release authority, or scientific claim."
        ),
    }
    manifest_sha = _sha256_bytes(_canonical_bytes(manifest_basis))
    manifest = {
        **manifest_basis,
        "manifest_sha256": manifest_sha,
    }
    _write_json(preflight_root / MANIFEST_NAME, manifest)
    return manifest


def _verify_manifest_files(
    root: Path,
    manifest: dict[str, Any],
    *,
    require_original_root: bool,
) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported preflight schema version")
    preflight_id = manifest.get("preflight_id")
    if not isinstance(preflight_id, str):
        raise ValueError("preflight manifest lacks preflight_id")
    if require_original_root and manifest.get("custody_root_resolved") != str(root.resolve()):
        raise ValueError("preflight manifest is not bound to this custody root")

    basis = dict(manifest)
    claimed_manifest_sha = basis.pop("manifest_sha256", None)
    if claimed_manifest_sha != _sha256_bytes(_canonical_bytes(basis)):
        raise ValueError("preflight manifest digest mismatch")

    preflight_root = _resolve_preflight(root, preflight_id)
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("preflight manifest requires files")

    verified: list[dict[str, Any]] = []
    for expected in files:
        if not isinstance(expected, dict):
            raise ValueError("preflight file record must be an object")
        relative = expected.get("relative_path")
        if not isinstance(relative, str) or not relative:
            raise ValueError("preflight file record lacks relative_path")
        actual = _file_record(preflight_root, relative)
        if actual != expected:
            raise ValueError(f"preflight file integrity mismatch: {relative}")
        verified.append(actual)

    replacement = next(
        (row for row in verified if row["relative_path"] == "atomic-replace.txt"),
        None,
    )
    if replacement is None or replacement["sha256"] != manifest.get("expected_atomic_replace_sha256"):
        raise ValueError("atomic replacement final-state mismatch")
    return verified


def verify_persistence(
    custody_root: Path,
    preflight_id: str,
    *,
    clock_fn: Callable[[], str] = acquisition._utc_now,
) -> dict[str, Any]:
    acquisition.validate_output_root(custody_root)
    preflight_root = _resolve_preflight(custody_root, preflight_id)
    manifest_path = preflight_root / MANIFEST_NAME
    manifest = _read_json(manifest_path)
    verified = _verify_manifest_files(custody_root, manifest, require_original_root=True)

    report_basis = {
        "schema_version": SCHEMA_VERSION,
        "preflight_id": preflight_id,
        "verified_at": clock_fn(),
        "manifest_file_sha256": _sha256_bytes(manifest_path.read_bytes()),
        "manifest_sha256": manifest["manifest_sha256"],
        "verified_files": verified,
        "status": "PERSISTENCE_AND_EXACT_BYTES_VERIFIED_IN_CURRENT_PROCESS",
        "authority_boundary": (
            "The operator must run this command in a fresh process/session after the required restart. "
            "This report cannot prove that a restart occurred merely because verification succeeded."
        ),
    }
    report_sha = _sha256_bytes(_canonical_bytes(report_basis))
    report = {**report_basis, "verification_sha256": report_sha}
    _write_json(preflight_root / PERSISTENCE_REPORT_NAME, report)
    return report


def compare_restore(
    primary_root: Path,
    restored_root: Path,
    preflight_id: str,
    *,
    clock_fn: Callable[[], str] = acquisition._utc_now,
) -> dict[str, Any]:
    acquisition.validate_output_root(primary_root)
    acquisition.validate_output_root(restored_root)
    primary_dir = _resolve_preflight(primary_root, preflight_id)
    restored_dir = _resolve_preflight(restored_root, preflight_id)
    primary_manifest_path = primary_dir / MANIFEST_NAME
    restored_manifest_path = restored_dir / MANIFEST_NAME

    primary_manifest_bytes = primary_manifest_path.read_bytes()
    restored_manifest_bytes = restored_manifest_path.read_bytes()
    if primary_manifest_bytes != restored_manifest_bytes:
        raise ValueError("restored preflight manifest bytes differ from primary")

    manifest = _read_json(primary_manifest_path)
    primary_files = _verify_manifest_files(primary_root, manifest, require_original_root=True)
    restored_files = _verify_manifest_files(restored_root, manifest, require_original_root=False)
    if primary_files != restored_files:
        raise ValueError("restored file records differ from primary")

    report_basis = {
        "schema_version": SCHEMA_VERSION,
        "preflight_id": preflight_id,
        "compared_at": clock_fn(),
        "primary_root_resolved": str(primary_root.resolve()),
        "restored_root_resolved": str(restored_root.resolve()),
        "manifest_file_sha256": _sha256_bytes(primary_manifest_bytes),
        "verified_files": primary_files,
        "status": "RESTORE_PATHS_AND_EXACT_BYTES_MATCH_PRIMARY",
        "authority_boundary": (
            "This compares a supplied restored tree with the primary preflight tree. It does not itself prove "
            "which backup service, recovery point, or administrative identity produced the restore."
        ),
    }
    report_sha = _sha256_bytes(_canonical_bytes(report_basis))
    report = {**report_basis, "comparison_sha256": report_sha}
    _write_json(primary_dir / RESTORE_REPORT_NAME, report)
    return report


def _is_permission_denied(exc: OSError) -> bool:
    return isinstance(exc, PermissionError) or exc.errno in _DENIED_ERRNOS


def _probe_create(preflight_root: Path) -> bool:
    probe = preflight_root / f".verifier-create-probe-{os.getpid()}-{secrets.token_hex(4)}"
    try:
        with probe.open("xb") as handle:
            handle.write(b"create-probe\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        if _is_permission_denied(exc):
            return False
        raise
    try:
        probe.unlink()
    except OSError as exc:
        raise RuntimeError(
            "verifier create probe succeeded but its synthetic probe file could not be removed"
        ) from exc
    return True


def _probe_write_existing(path: Path) -> bool:
    original = path.read_bytes()
    if not original:
        raise ValueError(f"write probe requires non-empty file: {path}")
    try:
        with path.open("r+b", buffering=0) as handle:
            handle.seek(0)
            handle.write(original[:1])
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        if _is_permission_denied(exc):
            return False
        raise
    if path.read_bytes() != original:
        raise RuntimeError("same-byte verifier write probe changed file content")
    return True


def _probe_truncate(path: Path) -> bool:
    original = path.read_bytes()
    if len(original) < 2:
        raise ValueError(f"truncate probe requires at least two bytes: {path}")
    mutated = False
    try:
        with path.open("r+b", buffering=0) as handle:
            handle.truncate(len(original) - 1)
            handle.flush()
            os.fsync(handle.fileno())
            mutated = True
    except OSError as exc:
        if _is_permission_denied(exc):
            return False
        raise
    finally:
        if mutated:
            try:
                acquisition._atomic_write(path, original)
            except Exception as exc:
                raise RuntimeError(
                    "verifier truncate probe succeeded and original synthetic bytes could not be restored"
                ) from exc
    return True


def _probe_rename(path: Path) -> bool:
    target = path.with_name(f".{path.name}.verifier-rename-probe-{secrets.token_hex(4)}")
    renamed = False
    try:
        path.rename(target)
        renamed = True
    except OSError as exc:
        if _is_permission_denied(exc):
            return False
        raise
    finally:
        if renamed:
            try:
                target.rename(path)
            except Exception as exc:
                raise RuntimeError(
                    "verifier rename probe succeeded and original synthetic path could not be restored"
                ) from exc
    return True


def _probe_delete(path: Path) -> bool:
    original = path.read_bytes()
    deleted = False
    try:
        path.unlink()
        deleted = True
    except OSError as exc:
        if _is_permission_denied(exc):
            return False
        raise
    finally:
        if deleted:
            try:
                acquisition._atomic_write(path, original)
            except Exception as exc:
                raise RuntimeError(
                    "verifier delete probe succeeded and original synthetic bytes could not be restored"
                ) from exc
    return True


def assert_read_only(
    custody_root: Path,
    preflight_id: str,
    *,
    clock_fn: Callable[[], str] = acquisition._utc_now,
) -> dict[str, Any]:
    acquisition.validate_output_root(custody_root)
    preflight_root = _resolve_preflight(custody_root, preflight_id)
    manifest_path = preflight_root / MANIFEST_NAME
    manifest = _read_json(manifest_path)
    _verify_manifest_files(custody_root, manifest, require_original_root=True)

    probes: list[tuple[str, Callable[[], bool]]] = [
        ("CREATE_FILE", lambda: _probe_create(preflight_root)),
        (
            "WRITE_EXISTING_FILE",
            lambda: _probe_write_existing(preflight_root / "atomic-replace.txt"),
        ),
        ("TRUNCATE_FILE", lambda: _probe_truncate(preflight_root / "atomic-replace.txt")),
        ("RENAME_FILE", lambda: _probe_rename(preflight_root / "nested" / "state.json")),
        ("DELETE_FILE", lambda: _probe_delete(preflight_root / "payload.bin")),
    ]

    unexpectedly_allowed: list[str] = []
    blocked: list[str] = []
    for name, probe in probes:
        if probe():
            unexpectedly_allowed.append(name)
        else:
            blocked.append(name)

    # Destructive probes restore their synthetic targets when a misconfiguration
    # permits mutation. Re-verify exact bytes before reporting the authorization result.
    _verify_manifest_files(custody_root, manifest, require_original_root=True)

    if unexpectedly_allowed:
        raise RuntimeError(
            "verifier identity permits custody mutation operations: "
            + ", ".join(unexpectedly_allowed)
        )

    report_basis = {
        "schema_version": SCHEMA_VERSION,
        "preflight_id": preflight_id,
        "verified_at": clock_fn(),
        "manifest_file_sha256": _sha256_bytes(manifest_path.read_bytes()),
        "manifest_sha256": manifest["manifest_sha256"],
        "blocked_operations": blocked,
        "status": "READ_ONLY_MUTATION_BOUNDARY_VERIFIED",
        "authority_boundary": (
            "This proves only that the executing identity was denied the tested create, existing-file write, "
            "truncate, rename, and delete operations on this mounted preflight tree. It does not establish "
            "the identity's IAM provenance, administrator separation, backup immutability, or provider acquisition."
        ),
    }
    report_sha = _sha256_bytes(_canonical_bytes(report_basis))
    return {**report_basis, "verification_sha256": report_sha}


def _print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exercise Phase 4 custody filesystem persistence, exact-byte, restore, and read-only invariants."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--custody-root", type=Path, required=True)
    prepare.add_argument("--payload-size", type=int, default=4096)

    verify = subparsers.add_parser("verify-persistence")
    verify.add_argument("--custody-root", type=Path, required=True)
    verify.add_argument("--preflight-id", required=True)

    restore = subparsers.add_parser("compare-restore")
    restore.add_argument("--primary-root", type=Path, required=True)
    restore.add_argument("--restored-root", type=Path, required=True)
    restore.add_argument("--preflight-id", required=True)

    read_only = subparsers.add_parser("assert-read-only")
    read_only.add_argument("--custody-root", type=Path, required=True)
    read_only.add_argument("--preflight-id", required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        _print_report(prepare_preflight(args.custody_root, payload_size=args.payload_size))
    elif args.command == "verify-persistence":
        _print_report(verify_persistence(args.custody_root, args.preflight_id))
    elif args.command == "compare-restore":
        _print_report(compare_restore(args.primary_root, args.restored_root, args.preflight_id))
    elif args.command == "assert-read-only":
        _print_report(assert_read_only(args.custody_root, args.preflight_id))
    else:
        raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    main()
