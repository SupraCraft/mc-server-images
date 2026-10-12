#!/usr/bin/env python3
"""Read-only release candidate discovery: operational 26.3 and isolated 26.4 canary.

Do not download executables, promote an artifact, mutate a world, or silently
change approved versions. These results are an external catalog observation
and require subsequent digest-pinned real runtime qualification.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import urllib.request
from urllib.parse import urlparse

POLICY = pathlib.Path(__file__).resolve().parents[1] / "spec/operational-runtime-lanes-v1.json"
UA = "SupraCraft-RDTE/1.0 (https://github.com/SupraCraft/mc-server-images)"
MAX_JSON = 2 * 1024 * 1024


class Refused(Exception):
    pass


def require(value: bool, code: str) -> None:
    if not value:
        raise Refused(code)


def official_url(url: object, domain: str) -> bool:
    if not isinstance(url, str):
        return False
    p = urlparse(url)
    return p.scheme == "https" and p.username is None and p.password is None and (
        p.hostname == domain or (p.hostname or "").endswith("." + domain)
    )


def fetch(url: str) -> object:
    require(official_url(url, "papermc.io") or
            official_url(url, "mojang.com"), "UNTRUSTED_SOURCE_URL")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=25) as result:
        require(official_url(result.url, "papermc.io") or
                official_url(result.url, "mojang.com"), "UNTRUSTED_REDIRECT")
        b = result.read(MAX_JSON + 1)
    require(0 < len(b) <= MAX_JSON, "UPSTREAM_JSON_SIZE")
    return json.loads(b)


def paper_build(builds: object, version: str) -> dict:
    require(isinstance(builds, list) and len(builds) <= 10000,
            "PAPER_RESPONSE_DRIFT")
    stable = []
    for row in builds:
        require(type(row) is dict, "PAPER_RESPONSE_DRIFT")
        if row.get("channel") != "STABLE":
            continue
        bid = row.get("id")
        require(isinstance(bid, int) and not isinstance(bid, bool)
                and bid > 0, "PAPER_BUILD_ID_DRIFT")
        download = row.get("downloads", {}).get("server:default")
        require(isinstance(download, dict), "PAPER_DOWNLOAD_MISSING")
        url = download.get("url")
        require(official_url(url, "papermc.io"),
                "PAPER_DOWNLOAD_UNTRUSTED")
        checksums = download.get("checksums") or {}
        require(isinstance(checksums, dict), "PAPER_DIGEST_DRIFT")
        checksum = checksums.get("sha256")
        if checksum is not None:
            require(isinstance(checksum, str) and
                    re.fullmatch(r"[0-9a-f]{64}", checksum),
                    "PAPER_DIGEST_DRIFT")
        stable.append({"build": bid, "version": version, "url": url,
                       "reported_sha256": checksum})
    require(bool(stable), "NO_STABLE_PAPER_BUILD")
    require(len({r["build"] for r in stable}) == len(stable),
            "DUPLICATE_PAPER_BUILDS")
    return max(stable, key=lambda row: row["build"])


def velocity_build(builds: object, version: str, required: int) -> dict:
    require(isinstance(builds, list) and len(builds) <= 10000,
            "VELOCITY_RESPONSE_DRIFT")
    matches = []
    for row in builds:
        require(type(row) is dict, "VELOCITY_RESPONSE_DRIFT")
        if row.get("id") != required:
            continue
        require(row.get("channel") == "STABLE", "VELOCITY_NOT_STABLE")
        dl = row.get("downloads", {}).get("server:default")
        require(isinstance(dl, dict)
                and official_url(dl.get("url"), "papermc.io"),
                "VELOCITY_DOWNLOAD_UNTRUSTED")
        c = dl.get("checksums") or {}
        sha = c.get("sha256") if isinstance(c, dict) else None
        require(sha is None or (isinstance(sha, str) and
                re.fullmatch(r"[0-9a-f]{64}", sha)), "VELOCITY_DIGEST_DRIFT")
        matches.append({"version": version, "build": required,
                        "url": dl["url"], "reported_sha256": sha})
    require(len(matches) == 1, "PINNED_VELOCITY_BUILD_NOT_AVAILABLE")
    return matches[0]


def mojang_release(manifest: object, release: str, canary_prefix: str) -> dict:
    require(isinstance(manifest, dict)
            and type(manifest.get("latest")) is dict
            and type(manifest.get("versions")) is list,
            "MOJANG_MANIFEST_DRIFT")
    entries = [v for v in manifest["versions"]
               if isinstance(v, dict) and v.get("id") == release]
    require(len(entries) == 1 and entries[0].get("type") == "release",
            "PINNED_MINECRAFT_RELEASE_MISSING")
    require(official_url(entries[0].get("url"), "mojang.com"),
            "MOJANG_RELEASE_UNTRUSTED")
    latest = manifest["latest"]
    snapshot = latest.get("snapshot")
    require(isinstance(snapshot, str), "MOJANG_SNAPSHOT_DRIFT")
    # Only 26.4 qualifies as the declared canary series. If latest changes,
    # report an upgrade/reconciliation requirement, not implicit admission.
    return {
        "approved_release": release,
        "observed_latest_release": latest.get("release"),
        "version_metadata_url": entries[0]["url"],
        "observed_latest_snapshot": snapshot,
        "snapshot_matches_26_4_canary": snapshot.startswith(canary_prefix),
        "release_changed": latest.get("release") != release,
    }


def resolve(policy: dict, mojang: object, paper: object, velocity: object) -> dict:
    require(policy.get("schema") == "supracraft.operational-runtime-lanes/1",
            "POLICY_DRIFT")
    minecraft = policy["stable"]["minecraft_java"]
    expected_version = minecraft["version"]
    velocity_pin = policy["stable"]["velocity"]
    p = paper_build(paper, expected_version)
    v = velocity_build(velocity, velocity_pin["version"],
                       velocity_pin["release_build"])
    m = mojang_release(mojang, expected_version, policy["preview"]["series"])
    return {
        "schema": "supracraft.release-candidate-discovery/1",
        "classification": "READ_ONLY_CANDIDATES_DISCOVERED",
        "stable": {"vanilla": m, "paper": p, "velocity": v},
        "preview": {"observed_snapshot": m["observed_latest_snapshot"],
                    "allowed_for": "rdte_only",
                    "snapshot_matches_expected_series":
                        m["snapshot_matches_26_4_canary"]},
        "candidate_verified_by_real_runtime": False,
        "version_selected_for_operations": False,
        "auto_deploy_authorized": False,
        "world_mutated": False,
        "physical_truenas_apply": "HOLD",
        "next_gate": "DIGEST_VERIFY_AND_INDEPENDENT_BACKEND_PROXY_RUNTIME",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True, type=pathlib.Path)
    a = ap.parse_args()
    try:
        policy = json.loads(POLICY.read_text())
        m = fetch("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json")
        p = fetch("https://fill.papermc.io/v3/projects/paper/versions/26.3/builds")
        v = fetch("https://fill.papermc.io/v3/projects/velocity/versions/4.2.0/builds")
        result = resolve(policy, m, p, v)
        exit_code = 0
    except (Refused, OSError, ValueError, KeyError, TypeError) as err:
        result = {"schema": "supracraft.release-candidate-discovery/1",
                  "classification": "INCONCLUSIVE",
                  "reason": str(err) if isinstance(err, Refused)
                      else "UPSTREAM_OR_SCHEMA_UNAVAILABLE",
                  "auto_deploy_authorized": False,
                  "world_mutated": False}
        exit_code = 2
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"classification": result["classification"],
                      "output": str(a.output)}, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
