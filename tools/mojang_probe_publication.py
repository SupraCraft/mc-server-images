#!/usr/bin/env python3
"""Validate data-only dispatch input and lease publication to the original push."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

BRANCH = "probe/mojang-release-identity"
DEFAULT_VERSION = "26.3"


def validate_version(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", value) or ".." in value:
        raise ValueError("invalid Minecraft release id")
    return value


def validate_receipt(result: dict) -> None:
    if not isinstance(result, dict) or result.get("schema") != "supracraft-mojang-release-identity/1" or result.get("minecraft_version") != DEFAULT_VERSION:
        raise ValueError("result schema/version mismatch")
    def digest(value, length):
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{%d}" % length, value) is not None
    provenance = result.get("provenance")
    if not isinstance(provenance, dict) or not all(digest(provenance.get(key), 64) for key in ("launcher_manifest_sha256", "version_metadata_sha256")):
        raise ValueError("missing provenance hashes")
    for key in ("server_artifact", "client_artifact"):
        artifact = result.get(key)
        if not isinstance(artifact, dict) or not digest(artifact.get("sha256"), 64) or not digest(artifact.get("expected_sha1"), 40) or artifact.get("expected_sha1") != artifact.get("actual_sha1") or type(artifact.get("size")) is not int or artifact["size"] <= 0:
            raise ValueError("invalid artifact digest/size")
    identity = result.get("artifact_version_json")
    if not isinstance(identity, dict) or (identity.get("id") or identity.get("name")) != DEFAULT_VERSION:
        raise ValueError("artifact identity mismatch")


def resolve() -> None:
    version = validate_version(os.environ.get("REQUESTED_VERSION") or DEFAULT_VERSION)
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as output:
        output.write(f"MC_VERSION={version}\n")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def persist() -> str:
    if os.environ.get("GITHUB_EVENT_NAME") != "push" or os.environ.get("GITHUB_REF") != f"refs/heads/{BRANCH}":
        raise ValueError("publication requires the probe branch push event")
    expected = os.environ["GITHUB_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", expected) or git("rev-parse", "HEAD") != expected:
        raise ValueError("checkout is not the event commit")
    source = Path(os.environ["PROBE_RESULT"])
    if source.is_symlink() or not source.is_file():
        raise ValueError("missing or symlink result")
    if source.stat().st_size > 1024 * 1024:
        raise ValueError("oversized result")
    data = source.read_bytes()
    if len(data) > 1024 * 1024:
        raise ValueError("oversized result")
    result = json.loads(data)
    validate_receipt(result)
    if git("status", "--porcelain"):
        raise ValueError("publication checkout must be clean")
    remote = git("ls-remote", "--heads", "origin", f"refs/heads/{BRANCH}").split()
    if not remote or remote[0] != expected:
        return "STALE_EVENT_SKIPPED"
    target = Path("probes") / f"{DEFAULT_VERSION}-release-identity.json"
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError("symlink publication target or directory")
    if target.exists() and target.read_bytes() == data:
        return "UNCHANGED"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    git("add", "--", target.as_posix())
    git("commit", "-m", f"probe: record Mojang {DEFAULT_VERSION} release identity")
    # Ordinary fast-forward push rejects concurrent updates; never force/overwrite them.
    git("push", "origin", f"HEAD:refs/heads/{BRANCH}")
    return "PUBLISHED"


if __name__ == "__main__":
    if sys.argv[1:] == ["resolve"]:
        resolve()
    elif sys.argv[1:] == ["persist"]:
        print(persist())
    else:
        raise SystemExit("expected resolve or persist")
