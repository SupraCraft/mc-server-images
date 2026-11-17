#!/usr/bin/env python3
"""Fail-closed review gate for candidate critic output; never self-promotes a model."""
import argparse
import json
from pathlib import Path
import sys

SCHEMA = "supracraft-critic-observation/v1"
MEDIA_SCHEMA = "supracraft-critic-media-probe/v1"
SEVERITY = {"info", "minor", "major", "critical"}


def accept(media, response):
    if media.get("schema") != MEDIA_SCHEMA or media.get("review_status") != "REVIEW_REQUIRED":
        raise ValueError("UNTRUSTED_MEDIA_RECEIPT")
    if media.get("minecraft_runtime_verified") is not False or media.get("stock_client_verified") is not False:
        raise ValueError("AUTHORITY_CLAIM_UNTRUSTED")
    digest = media.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("MISSING_MEDIA_DIGEST")
    if response.get("schema") != SCHEMA or response.get("input_sha256") != digest:
        raise ValueError("SOURCE_MISMATCH")
    model = response.get("candidate")
    if not isinstance(model, dict) or any(
        not isinstance(model.get(k), str) or not model[k].strip()
        for k in ("provider", "model", "family")
    ):
        raise ValueError("CANDIDATE_IDENTITY_REQUIRED")
    disposition = response.get("disposition")
    observations = response.get("observations")
    if disposition not in ("observe", "abstain") or not isinstance(observations, list):
        raise ValueError("INVALID_DISPOSITION")
    if disposition == "abstain":
        if observations or len(response.get("uncertainty", "")) < 12:
            raise ValueError("ABSTENTION_MUST_BE_EXPLICIT")
    elif not observations:
        raise ValueError("OBSERVATIONS_REQUIRED")
    tracks = media.get("tracks", [])
    kind = media.get("kind")
    duration_ms = media.get("duration_ms")
    for idx, item in enumerate(observations):
        if not isinstance(item, dict):
            raise ValueError("INVALID_OBSERVATION")
        modality = item.get("modality")
        if modality not in ("image", "video", "audio"):
            raise ValueError("INVALID_MODALITY")
        if modality == "audio" and "audio" not in tracks:
            raise ValueError("AUDIO_TRACK_ABSENT")
        if modality in ("image", "video") and "video" not in tracks:
            raise ValueError("VIDEO_TRACK_ABSENT")
        if kind == "image" and modality != "image":
            raise ValueError("IMAGE_ONLY_RECEIPT")
        if item.get("severity") not in SEVERITY:
            raise ValueError("INVALID_SEVERITY")
        if any(not isinstance(item.get(k), str) or len(item[k].strip()) < 12
               for k in ("claim", "evidence")):
            raise ValueError("UNGROUNDED_CLAIM")
        conf = item.get("confidence")
        if type(conf) not in (int, float) or not 0 <= conf <= 1:
            raise ValueError("INVALID_CONFIDENCE")
        if modality in ("video", "audio"):
            t = item.get("time_ms")
            if type(t) is not int or t < 0 or duration_ms is None or t > duration_ms:
                raise ValueError("TIME_OUTSIDE_MEDIA")
        else:
            region = item.get("region")
            if not isinstance(region, list) or len(region) != 4 or any(
                type(v) not in (int, float) or not 0 <= v <= 1 for v in region
            ) or region[0] >= region[2] or region[1] >= region[3]:
                raise ValueError("INVALID_IMAGE_REGION")
    return {
        "schema": "supracraft-critic-admission/v1",
        "status": "EVIDENCE_ADMISSIBLE_REVIEW_REQUIRED",
        "qualified_model": False,
        "official_gameplay_verified": False,
        "input_sha256": digest,
        "candidate": model,
        "disposition": disposition,
        "observation_count": len(observations),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--media-receipt", required=True)
    parser.add_argument("--candidate-output", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        media = json.loads(Path(args.media_receipt).read_text(encoding="utf-8"))
        candidate = json.loads(Path(args.candidate_output).read_text(encoding="utf-8"))
        result = accept(media, candidate)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 1
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
