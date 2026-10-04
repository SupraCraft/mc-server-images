#!/usr/bin/env python3
"""Derive a provenance-bound Sprint sign allow_op_features recipe.

Only derived signatures are emitted: repository paths, 1-based line numbers,
legacy line SHA-256, command kind, and block coordinates. Third-party source
text is never stored in the recipe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


ALLOW = "allow_op_features"
DATA_RE = re.compile(r"\bdata\s+merge\s+block\s+(\S+)\s+(\S+)\s+(\S+)\s+")
SET_RE = re.compile(r"\bsetblock\s+(\S+)\s+(\S+)\s+(\S+)\s+")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, text=True, capture_output=True,
    ).stdout


def exists(repo: Path, spec: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", spec],
        text=True, capture_output=True,
    ).returncode == 0


def sha_line(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def derive(repo: Path, old: str, new: str) -> dict:
    paths = [
        p for p in git(repo, "diff", "--name-only", old, new, "--", "*.mcfunction").splitlines()
        if p and exists(repo, f"{old}:{p}") and exists(repo, f"{new}:{p}")
    ]
    entries = []
    skipped = []

    for path in paths:
        old_lines = git(repo, "show", f"{old}:{path}").splitlines()
        new_lines = git(repo, "show", f"{new}:{path}").splitlines()
        for i, new_line in enumerate(new_lines):
            if ALLOW not in new_line:
                continue
            old_line = old_lines[i] if i < len(old_lines) else None
            if old_line is None or ALLOW in old_line:
                continue

            m = DATA_RE.search(old_line) or SET_RE.search(old_line)
            if not m:
                skipped.append({"path": path, "line": i + 1, "reason": "unsupported_command"})
                continue

            kind = "data_merge_block" if DATA_RE.search(old_line) else "setblock"
            entries.append({
                "path": path,
                "line": i + 1,
                "legacy_line_sha256": sha_line(old_line),
                "command_kind": kind,
                "coordinates": list(m.groups()),
            })

    return {
        "schema": "supracraft-sign-op-features-project-recipe/1",
        "project": "Sprint-Racer-Dev",
        "old": old,
        "new": new,
        "entries": entries,
        "entry_count": len(entries),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "policy": (
            "Apply only to the pinned project/source signature. An entry is valid "
            "only when path, line number, command kind, coordinates, and legacy "
            "line SHA-256 all match."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = derive(args.repo, args.old, args.new)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "entries"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
