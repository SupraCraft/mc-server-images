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
    files = []
    skipped = []
    total_added = 0

    for path in paths:
        old_text = git(repo, "show", f"{old}:{path}")
        new_text = git(repo, "show", f"{new}:{path}")
        added = new_text.count(ALLOW) - old_text.count(ALLOW)
        if added <= 0:
            continue

        supported = False
        for line in old_text.splitlines():
            if DATA_RE.search(line) and RUN_COMMAND_RE.search(line):
                supported = True
                break
            if SET_RE.search(line):
                supported = True
        if not supported:
            skipped.append({"path": path, "reason": "no_supported_command_surface"})
            continue

        files.append({
            "path": path,
            "legacy_file_sha256": hashlib.sha256(old_text.encode("utf-8")).hexdigest(),
            "expected_added_allow_op_features": added,
        })
        total_added += added

    return {
        "schema": "supracraft-sign-op-features-project-recipe/2",
        "project": "Sprint-Racer-Dev",
        "old": old,
        "new": new,
        "files": files,
        "file_count": len(files),
        "expected_added_allow_op_features": total_added,
        "skipped_count": len(skipped),
        "skipped": skipped,
        "operations": [
            "direct_same_payload_sign_run_command",
            "verified_file_privileged_data_merge",
            "verified_file_local_text_copy_target_sign",
        ],
        "policy": (
            "Apply only to the pinned project/source signature. A file recipe is "
            "valid only when repository path and exact legacy file SHA-256 match. "
            "Within that verified file, only the named bounded operations may run."
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
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
