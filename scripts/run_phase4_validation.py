from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = "0.1.0"
EXPECTED_PYTHON = (3, 12)
EXPECTED_JSONSCHEMA = "4.26.0"
EXPECTED_PLAN_ID = "SCIENCE-QUERY-PLAN-A9B8B8999861882C4BC7"
EXPECTED_PLAN_SHA256 = "a9b8b8999861882c4bc78b27f40f48e476f7cafbbb347b00a0a6cd897406db56"
EXPECTED_UNIT_COUNT = 768
EXPECTED_PROVIDER_COUNTS = {"CROSSREF": 384, "EUROPE_PMC": 384}

SCIENCE_TEST_MODULES = (
    "tests/test_science_graph_contract.py",
    "tests/test_science_query_compilation.py",
    "tests/test_science_acquisition.py",
    "tests/test_science_response_custody.py",
    "tests/test_science_acquisition_verification.py",
    "tests/test_science_candidate_provenance.py",
    "tests/test_science_retry_custody.py",
    "tests/test_science_http_transport.py",
    "tests/test_run_science_acquisition.py",
    "tests/test_science_custody_preflight.py",
    "tests/test_phase4_custody_terraform_contract.py",
    "tests/test_phase4_validation_harness.py",
)


class ValidationError(RuntimeError):
    """Raised when the strict Phase 4 validation contract is not satisfied."""


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


def _write_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_write(
        path,
        (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def _validate_runtime(
    python_version: tuple[int, int],
    jsonschema_version: str,
) -> None:
    if python_version != EXPECTED_PYTHON:
        raise ValidationError(
            f"expected Python {EXPECTED_PYTHON[0]}.{EXPECTED_PYTHON[1]}, "
            f"observed {python_version[0]}.{python_version[1]}"
        )
    if jsonschema_version != EXPECTED_JSONSCHEMA:
        raise ValidationError(
            f"expected jsonschema {EXPECTED_JSONSCHEMA}, observed {jsonschema_version}"
        )


def _runtime_snapshot() -> dict[str, Any]:
    try:
        jsonschema_version = version("jsonschema")
    except PackageNotFoundError as exc:
        raise ValidationError("jsonschema is not installed") from exc
    _validate_runtime(sys.version_info[:2], jsonschema_version)
    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "jsonschema_version": jsonschema_version,
        "platform": sys.platform,
    }


def _validate_expected_commit(value: str) -> str:
    normalized = value.strip().lower()
    if re.fullmatch(r"[0-9a-f]{40}", normalized) is None:
        raise ValidationError("expected commit must be a full 40-character hexadecimal SHA")
    return normalized


def _require_external_empty_evidence_dir(repo_root: Path, evidence_dir: Path) -> Path:
    repo_root = repo_root.resolve()
    evidence_dir = evidence_dir.resolve()
    if evidence_dir == repo_root or repo_root in evidence_dir.parents:
        raise ValidationError("validation evidence directory must be outside the repository")
    if evidence_dir.exists() and any(evidence_dir.iterdir()):
        raise ValidationError("validation evidence directory must be empty")
    evidence_dir.mkdir(parents=True, exist_ok=True)
    return evidence_dir


def _run_raw(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _git_text(repo_root: Path, *args: str) -> str:
    completed = _run_raw(("git", *args), cwd=repo_root)
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValidationError(f"git {' '.join(args)} failed: {stderr}")
    return completed.stdout.decode("utf-8", errors="strict").strip()


def _verify_repository_state(repo_root: Path, expected_commit: str) -> dict[str, Any]:
    top_level = Path(_git_text(repo_root, "rev-parse", "--show-toplevel")).resolve()
    if top_level != repo_root.resolve():
        raise ValidationError(f"repo_root is not the Git top-level directory: {repo_root}")
    observed = _git_text(repo_root, "rev-parse", "HEAD").lower()
    if observed != expected_commit:
        raise ValidationError(
            f"checked-out commit mismatch: expected {expected_commit}, observed {observed}"
        )
    status = _git_text(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise ValidationError("repository working tree is not clean")
    return {
        "git_top_level": str(top_level),
        "expected_commit": expected_commit,
        "observed_commit": observed,
        "worktree_clean": True,
    }


def _extract_unittest_count(stderr: bytes) -> int | None:
    match = re.search(rb"Ran\s+(\d+)\s+tests?\s+in\s+", stderr)
    return int(match.group(1)) if match else None


def _step_slug(index: int, name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{index:02d}-{normalized or 'step'}"


def _run_step(
    *,
    index: int,
    name: str,
    command: Sequence[str],
    repo_root: Path,
    evidence_dir: Path,
) -> dict[str, Any]:
    started_at = _utc_now()
    started = time.monotonic()
    completed = _run_raw(command, cwd=repo_root)
    duration_seconds = round(time.monotonic() - started, 6)
    slug = _step_slug(index, name)
    stdout_path = evidence_dir / f"{slug}.stdout.txt"
    stderr_path = evidence_dir / f"{slug}.stderr.txt"
    _atomic_write(stdout_path, completed.stdout)
    _atomic_write(stderr_path, completed.stderr)
    record: dict[str, Any] = {
        "index": index,
        "name": name,
        "command": list(command),
        "started_at": started_at,
        "completed_at": _utc_now(),
        "duration_seconds": duration_seconds,
        "return_code": completed.returncode,
        "stdout": {
            "path": stdout_path.name,
            "byte_count": len(completed.stdout),
            "sha256": _sha256_bytes(completed.stdout),
        },
        "stderr": {
            "path": stderr_path.name,
            "byte_count": len(completed.stderr),
            "sha256": _sha256_bytes(completed.stderr),
        },
    }
    test_count = _extract_unittest_count(completed.stderr)
    if test_count is not None:
        record["unittest_count"] = test_count
    if completed.returncode != 0:
        raise StepFailure(record)
    return record


class StepFailure(ValidationError):
    """Validation failure that retains the exact failed-step evidence record."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(f"validation step failed: {record['name']}")
        self.record = record


def _validate_frozen_plan(plan: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "plan_id": EXPECTED_PLAN_ID,
        "plan_sha256": EXPECTED_PLAN_SHA256,
        "unit_count": EXPECTED_UNIT_COUNT,
        "provider_counts": EXPECTED_PROVIDER_COUNTS,
    }
    for key, value in expected.items():
        if plan.get(key) != value:
            raise ValidationError(
                f"frozen query plan mismatch for {key}: expected {value!r}, observed {plan.get(key)!r}"
            )
    return expected


def _load_frozen_plan(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot load compiled query plan: {path}") from exc
    if not isinstance(value, dict):
        raise ValidationError("compiled query plan root must be an object")
    return _validate_frozen_plan(value)


def _finalize_report(report_basis: dict[str, Any]) -> dict[str, Any]:
    digest = _sha256_bytes(_canonical_bytes(report_basis))
    return {
        **report_basis,
        "validation_id": f"PHASE4-VALIDATION-{digest[:24].upper()}",
        "validation_sha256": digest,
    }


def run_validation(repo_root: Path, evidence_dir: Path, expected_commit: str) -> dict[str, Any]:
    expected_commit = _validate_expected_commit(expected_commit)
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        raise ValidationError(f"repository root does not exist: {repo_root}")
    evidence_dir = _require_external_empty_evidence_dir(repo_root, evidence_dir)

    report_basis: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "started_at": _utc_now(),
        "status": "RUNNING",
        "authority_boundary": (
            "This report is execution evidence for the declared validation commands only. "
            "It does not establish provider acquisition, scientific relevance, canonical identity, "
            "release eligibility, or open-world literature completeness."
        ),
        "steps": [],
    }
    report_path = evidence_dir / "phase4-validation-report.json"

    try:
        report_basis["runtime"] = _runtime_snapshot()
        report_basis["repository"] = _verify_repository_state(repo_root, expected_commit)

        commands: list[tuple[str, list[str]]] = [
            ("Validate vNext core graph", [sys.executable, "scripts/validate_vnext_core.py"]),
            (
                "Run vNext core contract tests",
                [sys.executable, "-m", "unittest", "tests/test_vnext_core_contract.py", "-v"],
            ),
            ("Validate science graph contract", [sys.executable, "scripts/validate_science_graph.py"]),
        ]
        for index, (name, command) in enumerate(commands, start=1):
            report_basis["steps"].append(
                _run_step(
                    index=index,
                    name=name,
                    command=command,
                    repo_root=repo_root,
                    evidence_dir=evidence_dir,
                )
            )

        plan_path = evidence_dir / "science-query-plan-v0.2.json"
        compile_record = _run_step(
            index=4,
            name="Compile frozen science query plan",
            command=[
                sys.executable,
                "scripts/compile_science_queries.py",
                "--output",
                str(plan_path),
            ],
            repo_root=repo_root,
            evidence_dir=evidence_dir,
        )
        report_basis["steps"].append(compile_record)
        report_basis["frozen_plan"] = _load_frozen_plan(plan_path)
        report_basis["frozen_plan_file_sha256"] = _sha256_bytes(plan_path.read_bytes())

        science_test_command = [
            sys.executable,
            "-m",
            "unittest",
            *SCIENCE_TEST_MODULES,
            "-v",
        ]
        report_basis["steps"].append(
            _run_step(
                index=5,
                name="Run Phase 4 science validation tests",
                command=science_test_command,
                repo_root=repo_root,
                evidence_dir=evidence_dir,
            )
        )
        report_basis["status"] = "PASS"
    except StepFailure as exc:
        report_basis["steps"].append(exc.record)
        report_basis["status"] = "FAIL"
        report_basis["failure"] = {"type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:  # preserve a machine-readable report for any fail-closed termination
        report_basis["status"] = "FAIL"
        trace = traceback.format_exc().encode("utf-8")
        trace_path = evidence_dir / "exception-traceback.txt"
        _atomic_write(trace_path, trace)
        report_basis["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": {
                "path": trace_path.name,
                "byte_count": len(trace),
                "sha256": _sha256_bytes(trace),
            },
        }

    report_basis["completed_at"] = _utc_now()
    report = _finalize_report(report_basis)
    _write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the strict Phase 4 validation sequence and emit content-addressed execution evidence."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Git repository root. Defaults to the repository containing this script.",
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        required=True,
        help="Empty directory outside the repository in which validation evidence will be written.",
    )
    parser.add_argument(
        "--expected-commit",
        required=True,
        help="Full 40-character commit SHA that must be checked out.",
    )
    args = parser.parse_args()

    report = run_validation(args.repo_root, args.evidence_dir, args.expected_commit)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
