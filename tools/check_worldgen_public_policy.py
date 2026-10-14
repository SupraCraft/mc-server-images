#!/usr/bin/env python3
"""Fail-closed policy checks for public/free worldgen benchmark workflows."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ALLOWED_STANDARD_RUNNERS = {
    "ubuntu-latest",
    "ubuntu-24.04",
    "ubuntu-26.04",
    "macos-26",
}

RUNS_ON_RE = re.compile(r"^\s*runs-on:\s*['\"]?([^'\"\s#]+)", re.MULTILINE)


def check_runtime(repository_private: str, runner_label: str) -> list[str]:
    errors: list[str] = []
    if repository_private.strip().lower() != "false":
        errors.append("benchmark execution requires a public repository")
    if runner_label not in ALLOWED_STANDARD_RUNNERS:
        errors.append(
            f"runner {runner_label!r} is not in the approved standard-runner allowlist: "
            + ", ".join(sorted(ALLOWED_STANDARD_RUNNERS))
        )
    return errors


def scan_workflows(root: pathlib.Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(root.glob("worldgen-*.y*ml")):
        text = path.read_text(encoding="utf-8")
        labels = RUNS_ON_RE.findall(text)
        if not labels:
            errors.append(f"{path}: no static runs-on label found")
            continue
        for label in labels:
            if label not in ALLOWED_STANDARD_RUNNERS:
                errors.append(f"{path}: disallowed runs-on label {label!r}")
        if "github.event.repository.private" not in text:
            errors.append(f"{path}: missing explicit public-repository guard")
        if "check_worldgen_public_policy.py" not in text:
            errors.append(f"{path}: missing shared policy checker invocation")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-private")
    parser.add_argument("--runner-label")
    parser.add_argument("--scan-workflows", type=pathlib.Path)
    args = parser.parse_args()

    errors: list[str] = []
    if args.repository_private is not None or args.runner_label is not None:
        if args.repository_private is None or args.runner_label is None:
            parser.error("--repository-private and --runner-label must be supplied together")
        errors.extend(check_runtime(args.repository_private, args.runner_label))
    if args.scan_workflows is not None:
        errors.extend(scan_workflows(args.scan_workflows))

    if errors:
        for error in errors:
            print(f"POLICY-FAIL: {error}", file=sys.stderr)
        return 78

    print("WORLDGEN-PUBLIC-POLICY-PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
