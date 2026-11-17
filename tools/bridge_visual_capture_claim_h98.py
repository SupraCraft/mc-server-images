#!/usr/bin/env python3
"""Correlate *claims* about a Minecraft 26.3 tour to media bytes; never certify HIL.

This is a proposed typed bridge. "Source run" metadata is self-reported unless
a reviewer independently fetches the exact run, artifact and world/server proof.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

SCHEMA = "supracraft-h98-26.3-capture-correlation/v1"
CLAIM = "supracraft-h98-tour-claim/v1"
MEDIA = "supracraft-critic-media-probe/v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
RUN = re.compile(r"https://github\.com/SupraCraft/[A-Za-z0-9_.-]+/actions/runs/[0-9]+\Z")
VIEW = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{0,39}\Z")


def correlate(media, claim):
    if not isinstance(media, dict) or media.get("schema") != MEDIA:
        raise ValueError("MEDIA_PROBE_REQUIRED")
    if not isinstance(claim, dict) or claim.get("schema") != CLAIM:
        raise ValueError("ROUTE_CLAIM_SCHEMA_REQUIRED")
    if media.get("review_status") != "REVIEW_REQUIRED":
        raise ValueError("MEDIA_REVIEW_STATUS_FORGED")
    if media.get("minecraft_runtime_verified") is not False or media.get("stock_client_verified") is not False:
        raise ValueError("MEDIA_AUTHORITY_CLAIM_FORGED")
    if claim.get("official_client_verified") is not False or claim.get("human_accepted") is not False:
        raise ValueError("ROUTE_AUTHORITY_CLAIM_FORGED")
    if media.get("kind") != "video" or "video" not in media.get("tracks", []):
        raise ValueError("VIDEO_TOUR_MEDIA_REQUIRED")
    duration = media.get("duration_ms")
    if type(duration) is not int or not 0 < duration <= 3600000:
        raise ValueError("BOUNDED_VIDEO_DURATION_REQUIRED")
    for key in ("sha256",):
        val = media.get(key)
        if not isinstance(val, str) or not HEX.fullmatch(val):
            raise ValueError("INVALID_MEDIA_DIGEST")
    if claim.get("media_sha256") != media["sha256"]:
        raise ValueError("MEDIA_BYTES_HASH_MISMATCH")
    if claim.get("route_contract") != "supracraft.visual-route/v0.2":
        raise ValueError("UNSUPPORTED_ROUTE_CONTRACT")
    if claim.get("claimed_server_version") != "26.3" or claim.get("claimed_protocol") != 777:
        raise ValueError("WRONG_RUNTIME_VERSION_CLAIM")
    for key in ("route_manifest_sha256", "world_sha256", "server_receipt_sha256"):
        value = claim.get(key)
        if not isinstance(value, str) or not HEX.fullmatch(value):
            raise ValueError("INVALID_ROUTE_PROVENANCE_DIGEST")
    run = claim.get("source_run_url")
    if not isinstance(run, str) or not RUN.fullmatch(run):
        raise ValueError("SOURCE_RUN_LINK_UNTRUSTED")
    views = claim.get("views")
    if not isinstance(views, list) or not 2 <= len(views) <= 64:
        raise ValueError("BOUNDED_TOUR_VIEWPOINTS_REQUIRED")
    prev = -1
    ids = set()
    for item in views:
        if not isinstance(item, dict):
            raise ValueError("INVALID_VIEW")
        identifier, ts, xyz = item.get("id"), item.get("frame_ms"), item.get("xyz")
        if not isinstance(identifier, str) or not VIEW.fullmatch(identifier) or identifier in ids:
            raise ValueError("DUPLICATE_OR_INVALID_VIEW_ID")
        ids.add(identifier)
        if type(ts) is not int or not prev < ts <= duration:
            raise ValueError("NONMONOTONIC_OR_OUT_OF_BOUNDS_FRAME")
        prev = ts
        if not isinstance(xyz, list) or len(xyz) != 3:
            raise ValueError("INVALID_VIEW_LOCATION")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in xyz):
            raise ValueError("INVALID_VIEW_LOCATION")
        x, y, z = xyz
        if not -30000000 <= x <= 30000000 or not -128 <= y <= 2048 or not -30000000 <= z <= 30000000:
            raise ValueError("VIEW_LOCATION_OUT_OF_BOUNDS")
    return {
        "schema": SCHEMA,
        "status": "CORRELATED_SOURCE_CLAIMS_REVIEW_REQUIRED",
        "source_run_url_unverified": run,
        "route_contract_claimed": claim["route_contract"],
        "server_version_claimed": claim["claimed_server_version"],
        "protocol_claimed": claim["claimed_protocol"],
        "media_sha256": media["sha256"],
        "route_manifest_sha256_claimed": claim["route_manifest_sha256"],
        "world_sha256_claimed": claim["world_sha256"],
        "server_receipt_sha256_claimed": claim["server_receipt_sha256"],
        "view_count": len(views), "duration_ms": duration,
        "source_run_independently_authenticated": False,
        "official_server_verified": False,
        "stock_client_verified": False,
        "human_story_acceptance": False,
        "critic_model_qualified": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--media-receipt", required=True)
    p.add_argument("--route-claim", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    try:
        mbytes = Path(args.media_receipt).read_bytes()
        cbytes = Path(args.route_claim).read_bytes()
        report = correlate(json.loads(mbytes), json.loads(cbytes))
        report["probe_receipt_sha256"] = hashlib.sha256(mbytes).hexdigest()
        report["route_claim_receipt_sha256"] = hashlib.sha256(cbytes).hexdigest()
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 1
    s = json.dumps(report, sort_keys=True, indent=2) + "\n"
    Path(args.out).write_text(s, encoding="utf-8")
    print(s, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
