#!/usr/bin/env python3
"""Generate a deterministic SHA-256 manifest for a release tree."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_release_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        files.append(path)
    return files


def render_manifest(root: Path, *, exclude: set[Path]) -> str:
    rows: list[str] = []
    for path in iter_release_files(root):
        resolved = path.resolve()
        if resolved in exclude:
            continue
        relative = path.relative_to(root).as_posix()
        rows.append(f"{sha256_file(path)}  {relative}")
    return "\n".join(rows) + ("\n" if rows else "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Release root directory")
    parser.add_argument("output", type=Path, help="Manifest output path")
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output.resolve()
    if not root.is_dir():
        raise SystemExit(f"root is not a directory: {root}")

    manifest = render_manifest(root, exclude={output})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(manifest, encoding="utf-8")
    file_count = 0 if not manifest.strip() else len(manifest.strip().splitlines())
    print(f"{file_count} files -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
