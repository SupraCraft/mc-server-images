#!/usr/bin/env python3
"""Classify sign allow_op_features migration dataflow in exact git pairs.

This tool does not rewrite source. It identifies files where the maintained target
adds allow_op_features and classifies whether the legacy file proves a local
same-coordinate sign dataflow:
- direct same-payload setblock sign with run_command click event;
- setblock sign followed by data merge block at the same coordinates containing
  a run_command click event;
- setblock sign followed by front_text.messages copy at the same coordinates;
- unresolved/other.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
from pathlib import Path


SETBLOCK_RE = re.compile(
    r"\bsetblock\s+(\S+)\s+(\S+)\s+(\S+)\s+((?:minecraft:)?\S*sign\S*)"
)
MERGE_RE = re.compile(r"\bdata\s+merge\s+block\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)")
MODIFY_COPY_RE = re.compile(
    r"\bdata\s+modify\s+block\s+(\S+)\s+(\S+)\s+(\S+)\s+front_text\.messages\s+set\s+from\s+block\b"
)
RUN_COMMAND_RE = re.compile(r'click_event\s*:\s*\{[^{}]*action\s*:\s*["\']run_command["\']')


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def exists(repo: Path, spec: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", spec],
        text=True,
        capture_output=True,
    ).returncode == 0


def classify_file(old_text: str, new_text: str) -> dict | None:
    added = new_text.count("allow_op_features") - old_text.count("allow_op_features")
    if added <= 0:
        return None

    sign_coords: dict[tuple[str, str, str], list[int]] = collections.defaultdict(list)
    direct = 0
    merge_local = 0
    copy_local = 0

    lines = old_text.splitlines()
    for i, line in enumerate(lines, 1):
        m = SETBLOCK_RE.search(line)
        if not m:
            continue
        coord = (m.group(1), m.group(2), m.group(3))
        sign_coords[coord].append(i)
        if RUN_COMMAND_RE.search(line):
            direct += 1

    for i, line in enumerate(lines, 1):
        m = MERGE_RE.search(line)
        if m:
            coord = (m.group(1), m.group(2), m.group(3))
            if coord in sign_coords and RUN_COMMAND_RE.search(m.group(4)):
                merge_local += 1
        m = MODIFY_COPY_RE.search(line)
        if m:
            coord = (m.group(1), m.group(2), m.group(3))
            if coord in sign_coords:
                copy_local += 1

    if direct:
        classification = "DIRECT_SAME_PAYLOAD"
    elif merge_local and copy_local:
        classification = "LOCAL_MERGE_AND_COPY"
    elif merge_local:
        classification = "LOCAL_PRIVILEGED_MERGE"
    elif copy_local:
        classification = "LOCAL_TEXT_COPY"
    else:
        classification = "UNRESOLVED_OR_CROSS_FUNCTION"

    return {
        "added_allow_op_features_count": added,
        "direct_same_payload_count": direct,
        "local_privileged_merge_count": merge_local,
        "local_text_copy_count": copy_local,
        "classification": classification,
    }


def analyze(repo: Path, old: str, new: str) -> dict:
    paths = [
        p for p in git(repo, "diff", "--name-only", old, new, "--", "*.mcfunction").splitlines()
        if p and exists(repo, f"{old}:{p}") and exists(repo, f"{new}:{p}")
    ]
    rows = []
    classes = collections.Counter()
    total_added = 0

    for path in paths:
        row = classify_file(
            git(repo, "show", f"{old}:{path}"),
            git(repo, "show", f"{new}:{path}"),
        )
        if row is None:
            continue
        row["path"] = path
        rows.append(row)
        classes[row["classification"]] += 1
        total_added += int(row["added_allow_op_features_count"])

    return {
        "schema": "supracraft-sign-op-features-dataflow-evidence/1",
        "old": old,
        "new": new,
        "candidate_file_count": len(rows),
        "added_allow_op_features_count": total_added,
        "classification_counts": dict(classes.most_common()),
        "rows": sorted(rows, key=lambda x: x["path"]),
        "boundary": (
            "local same-coordinate evidence is classification only; cross-command "
            "materialization remains structural until separately qualified"
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = analyze(args.repo, args.old, args.new)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
