#!/usr/bin/env python3
"""OP-5: read-only official Minecraft release-pair observation and idempotent DLE notice.

No game artifacts, worlds, snapshots, plugins, TrueNAS control, or promotions.
Issue publication is only admitted on public SupraCraft/mc-server-images main
with an explicit GITHUB_TOKEN, under a serialized GitHub Actions concurrency group.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
GITHUB_ISSUE = "https://api.github.com/repos/SupraCraft/mc-server-images/issues/73/comments"
SCHEMA = "supracraft.minecraft-release-observation/1"
MAX_MANIFEST = 1024 * 1024
MAX_COMMENTS_PAGES = 10


class WatchRefused(Exception):
    pass


def require(condition: bool, why: str) -> None:
    if not condition:
        raise WatchRefused(why)


def get_manifest() -> tuple[dict, str]:
    request = urllib.request.Request(MANIFEST, headers={
        "User-Agent": "SupraCraft-release-watch/1.0",
        "Accept": "application/json"
    })
    with urllib.request.urlopen(request, timeout=25) as response:
        resolved = urllib.parse.urlsplit(response.url)
        require(resolved.scheme == "https" and
                resolved.hostname in ("piston-meta.mojang.com", "launchermeta.mojang.com"),
                "UNEXPECTED_MANIFEST_REDIRECT")
        data = response.read(MAX_MANIFEST + 1)
    require(0 < len(data) <= MAX_MANIFEST, "MANIFEST_SIZE_REFUSED")
    return json.loads(data), hashlib.sha256(data).hexdigest()


def observe(manifest: dict, sha256: str) -> dict:
    require(type(manifest) is dict and type(manifest.get("latest")) is dict
            and type(manifest.get("versions")) is list,
            "UNEXPECTED_OFFICIAL_MANIFEST_SHAPE")
    latest = manifest["latest"]
    release, snapshot = latest.get("release"), latest.get("snapshot")
    require(type(release) is str and type(snapshot) is str and
            re.fullmatch(r"[0-9]{2}\\.[0-9]+", release) and
            re.fullmatch(r"[a-zA-Z0-9._-]{1,90}", snapshot),
            "INVALID_LATEST_RELEASE_PAIR")
    versions = manifest["versions"]
    observed = {}
    for kind, version in (("release", release), ("snapshot", snapshot)):
        entries = [v for v in versions if type(v) is dict and
                   v.get("id") == version and v.get("type") == kind]
        require(len(entries) == 1, "LATEST_NOT_UNIQUELY_IN_MANIFEST_" + kind.upper())
        row = entries[0]
        url = urllib.parse.urlsplit(str(row.get("url")))
        require(url.scheme == "https" and url.hostname in
                ("piston-meta.mojang.com", "launchermeta.mojang.com"),
                "INVALID_VERSION_METADATA_HOST")
        sha1 = row.get("sha1")
        require(type(sha1) is str and re.fullmatch(r"[0-9a-f]{40}", sha1),
                "VERSION_METADATA_SHA1_INVALID")
        observed[kind] = {
            "id": version, "metadata_sha1": sha1, "release_time": row.get("releaseTime")
        }
    identity = f"{release}|{snapshot}"
    marker = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return {
        "schema": SCHEMA,
        "source": MANIFEST,
        "manifest_sha256": sha256,
        "observed": observed,
        "pair_key": marker,
        "current_operational_pin": "26.3",
        "operational_change": "CANDIDATE_REQUALIFICATION_REQUIRED"
            if release != "26.3" else "NO_CHANGE_TO_OPERATIONAL_SELECTION",
        "snapshot_classification": "26.4_RDTE_PREVIEW_ONLY"
            if snapshot.startswith("26.4-") else "UNADMITTED_FRONTIER_REVIEW_REQUIRED",
        "runtime_download_performed": False,
        "world_mutated": False,
        "operational_promotion_allowed": False,
        "physical_truenas_apply": "HOLD"
    }


def github_api(url: str, token: str, method: str = "GET", payload: bytes | None = None):
    request = urllib.request.Request(
        url, data=payload, method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SupraCraft-minecraft-release-watch/1"
        }
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read(2 * 1024 * 1024 + 1)
        require(len(body) < 2 * 1024 * 1024, "GITHUB_RESPONSE_UNBOUNDED")
        return json.loads(body)


def publish_once(record: dict, token: str) -> str:
    require(os.environ.get("GITHUB_REPOSITORY") == "SupraCraft/mc-server-images"
            and os.environ.get("GITHUB_REF") == "refs/heads/main"
            and os.environ.get("GITHUB_EVENT_NAME") in ("schedule", "workflow_dispatch")
            and bool(token), "ISSUE_WRITE_NOT_AUTHORIZED")
    marker = "<!-- supracraft-mc-release-pair:" + record["pair_key"] + " -->"
    for page in range(1, MAX_COMMENTS_PAGES + 1):
        comments = github_api(f"{GITHUB_ISSUE}?per_page=100&page={page}", token)
        require(type(comments) is list, "GITHUB_COMMENT_SHAPE_DRIFT")
        if any(marker in str(item.get("body", "")) for item in comments):
            return "ALREADY_RECORDED"
        if len(comments) < 100:
            break
    else:
        raise WatchRefused("COMMENT_PAGINATION_EXCEEDED")
    body = (
        f"{marker}\n"
        "### Mojang release metadata observation (not deployment)\n\n"
        f"- Stable release: \`{record['observed']['release']['id']}\`\n"
        f"- Snapshot/pre-release: \`{record['observed']['snapshot']['id']}\`\n"
        f"- Official manifest SHA-256: \`{record['manifest_sha256']}\`\n"
        f"- Release metadata SHA-1: \`{record['observed']['release']['metadata_sha1']}\`\n"
        f"- Snapshot metadata SHA-1: \`{record['observed']['snapshot']['metadata_sha1']}\`\n"
        f"- Classification: **{record['operational_change']}**. "
        "No production promotion, game download, world mutation or physical TrueNAS APPLY.\n"
        f"- Source: {MANIFEST}\n"
    )
    result = github_api(
        GITHUB_ISSUE, token, "POST",
        json.dumps({"body": body}).encode("utf-8")
    )
    require(type(result) is dict and type(result.get("id")) is int,
            "GITHUB_ISSUE_COMMENT_NOT_ACKNOWLEDGED")
    return "PUBLISHED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    try:
        manifest, digest = get_manifest()
        record = observe(manifest, digest)
        if args.publish:
            record["issue_notice"] = publish_once(record, os.environ.get("GITHUB_TOKEN", ""))
        record["classification"] = "METADATA_ONLY_RELEASE_OBSERVATION"
        status = 0
    except Exception as exc:
        record = {
            "schema": SCHEMA, "classification": "REFUSED",
            "failure_type": type(exc).__name__, "failure": str(exc)[:160],
            "operational_promotion_allowed": False,
            "world_mutated": False, "physical_truenas_apply": "HOLD"
        }
        status = 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"classification": record["classification"],
                      "issue_notice": record.get("issue_notice"),
                      "failure": record.get("failure")}, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
