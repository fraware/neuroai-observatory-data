#!/usr/bin/env python3
"""Verify a SHA-256 manifest against a release tree."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_manifest(manifest_path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line_number, raw in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ValueError(f"{manifest_path}:{line_number}: malformed manifest line")
        digest, relative = parts
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"{manifest_path}:{line_number}: invalid SHA-256 digest")
        entries.append((digest, relative.replace("\\", "/")))
    return entries


def iter_release_files(root: Path, *, exclude: set[Path]) -> dict[str, Path]:
    observed: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        resolved = path.resolve()
        if resolved in exclude:
            continue
        relative = path.relative_to(root).as_posix()
        observed[relative] = path
    return observed


def verify_manifest(root: Path, manifest_path: Path) -> tuple[bool, list[str]]:
    root = root.resolve()
    manifest_path = manifest_path.resolve()
    if not root.is_dir():
        return False, [f"root is not a directory: {root}"]
    if not manifest_path.is_file():
        return False, [f"manifest not found: {manifest_path}"]

    errors: list[str] = []
    entries = parse_manifest(manifest_path)
    expected = {relative: digest for digest, relative in entries}
    observed = iter_release_files(root, exclude={manifest_path})

    for relative, digest in expected.items():
        path = observed.get(relative)
        if path is None:
            errors.append(f"missing file: {relative}")
            continue
        actual = sha256_file(path)
        if actual != digest:
            errors.append(f"digest mismatch: {relative} expected {digest} got {actual}")

    for relative in sorted(set(observed) - set(expected)):
        errors.append(f"unexpected file not in manifest: {relative}")

    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Release root directory")
    parser.add_argument("manifest", type=Path, help="Manifest path")
    args = parser.parse_args()

    ok, errors = verify_manifest(args.root, args.manifest)
    if ok:
        print(f"manifest verified: {args.manifest}")
        return 0

    for error in errors:
        print(error, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
