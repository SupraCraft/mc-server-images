#!/usr/bin/env python3
"""Independently replay actual archived H98 CLAP output against frozen audio oracle.

Never reruns CLAP. Byte-validates the GitHub Actions artifact and derives
ground truth from regenerated PCM, NOT from model-supplied expected fields.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

from adapt_clap_h98_to_critic_score import adapt

SCHEMA = "supracraft-h99-independent-real-clap-replay/v1"
REPO = "SupraCraft/mc-server-images"
SOURCE_RUN_ID = 44194189722
SOURCE_HEAD_SHA = "7551aab17290ed1a7e62e4a1714d7c0c46221ed6"
SOURCE_ARTIFACT_ID = 14378655909
SOURCE_ARTIFACT_NAME = "h98-clap-temporal-first-frozen-rep"
SOURCE_ARTIFACT_ZIP_SHA256 = "8b94bd395c347df08e3490f2820b22c3fff1b69782a3666a05d3e80c00e09311"
MODEL = "laion/clap-htsat-unfused"
MODEL_REVISION = "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a"
WEIGHTS_SHA256 = "1cd3c601bc4afe0fa87be3de4c13dd2cfadd249fac1e29acf74a9b296c3219bb"
SR = 48000
SEED = 20261117
PAIRS = (
    ("tone_noise", "tone", "noise", "A continuous electronic tone, followed by white noise.",
     "White noise, followed by a continuous electronic tone."),
    ("beep_noise", "beeps", "noise", "Short electronic beeps, followed by white noise.",
     "White noise, followed by short electronic beeps."),
    ("tone_quiet", "tone", "quiet", "An electronic tone, followed by complete silence.",
     "Complete silence, followed by an electronic tone."),
    ("beep_quiet", "beeps", "quiet", "Electronic beeps, followed by silence.",
     "Silence, followed by electronic beeps."),
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def get_manifest():
    # Independently authored version-frozen oracle of the model input, not outputs.
    import numpy as np
    t = np.arange(SR * 2, dtype=np.float64) / SR
    wave = (0.18 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    beep = (wave * (np.mod(t, 0.4) < 0.12).astype(np.float32)).astype(np.float32)
    noise = np.random.default_rng(SEED).uniform(-0.18, 0.18, size=len(t)).astype(np.float32)
    signals = {"tone": wave, "beeps": beep, "noise": noise,
               "quiet": np.zeros(len(t), dtype=np.float32)}
    cases = []
    for pair, a, b, first_prompt, second_prompt in PAIRS:
        for suffix, src, expected in (
            ("_ab", (a, b), "first_a"),
            ("_ba", (b, a), "first_b"),
        ):
            pcm = np.concatenate([signals[src[0]], signals[src[1]]]).astype("<f4")
            cases.append({
                "id": pair + suffix,
                "pair_id": pair,
                "sha256": sha(pcm.tobytes()),
                "expected": expected,
                "allowed_labels": ["first_a", "first_b"],
                "captions": [first_prompt, second_prompt],
            })
    return {
        "schema": "supracraft-critic-frozen-manifest/v1",
        "campaign": "h99-independent-h98-frozen-real-model-replay",
        "model_constraints": {
            "model": MODEL,
            "revision": MODEL_REVISION,
            "weights_sha256": WEIGHTS_SHA256,
            "fixture_plan_sha256": sha(repr(PAIRS).encode("utf-8")),
        },
        "cases": cases,
    }


def validate_run(run):
    if not isinstance(run, dict) or (
        run.get("id") != SOURCE_RUN_ID or
        run.get("head_sha") != SOURCE_HEAD_SHA or
        run.get("event") != "pull_request" or
        run.get("status") != "completed" or
        run.get("conclusion") != "success"
    ):
        raise ValueError("SOURCE_RUN_IDENTITY_OR_STATUS_MISMATCH")
    if run.get("repository", {}).get("full_name") != REPO:
        raise ValueError("SOURCE_REPOSITORY_MISMATCH")


def validate_archive(meta, archive_bytes):
    if not isinstance(meta, dict):
        raise ValueError("ARTIFACT_METADATA_UNTRUSTED")
    if meta.get("id") != SOURCE_ARTIFACT_ID or meta.get("name") != SOURCE_ARTIFACT_NAME:
        raise ValueError("ARTIFACT_IDENTITY_MISMATCH")
    if meta.get("expired") is not False or meta.get("workflow_run", {}).get("id") != SOURCE_RUN_ID:
        raise ValueError("ARTIFACT_RUN_LINK_OR_EXPIRY_MISMATCH")
    if meta.get("digest") != "sha256:" + SOURCE_ARTIFACT_ZIP_SHA256:
        raise ValueError("ARTIFACT_PUBLISHED_DIGEST_MISMATCH")
    if not isinstance(archive_bytes, bytes) or not 0 < len(archive_bytes) <= 100_000:
        raise ValueError("ARTIFACT_BYTES_UNSAFE")
    if sha(archive_bytes) != SOURCE_ARTIFACT_ZIP_SHA256:
        raise ValueError("ARTIFACT_ZIP_SHA256_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            if zf.namelist() != ["model-receipt.json"]:
                raise ValueError("ARTIFACT_CONTENTS_UNEXPECTED")
            info = zf.infolist()[0]
            if info.file_size > 50000:
                raise ValueError("ARTIFACT_MODEL_RECEIPT_TOO_LARGE")
            data = zf.read(info)
            return json.loads(data)
    except (zipfile.BadZipFile, UnicodeError) as exc:
        raise ValueError("ARTIFACT_ZIP_INVALID") from exc


def replay(run, meta, archive_bytes):
    validate_run(run)
    raw_model_receipt = validate_archive(meta, archive_bytes)
    manifest = get_manifest()
    if raw_model_receipt.get("total") != len(manifest["cases"]):
        raise ValueError("SOURCE_MODEL_CARDINALITY_INVALID")
    report = adapt(manifest, raw_model_receipt)
    return {
        "schema": SCHEMA,
        "status": "REAL_GITHUB_ARTIFACT_BYTES_REPLAYED_REVIEW_REQUIRED",
        "source_run_url": f"https://github.com/{REPO}/actions/runs/{SOURCE_RUN_ID}",
        "source_run_head_sha": SOURCE_HEAD_SHA,
        "artifact_id": SOURCE_ARTIFACT_ID,
        "artifact_zip_sha256": sha(archive_bytes),
        "source_model_weight_digest_reported": WEIGHTS_SHA256,
        "frozen_manifest_sha256": sha(json.dumps(manifest, sort_keys=True).encode()),
        "source_result_count": len(raw_model_receipt["results"]),
        "score_correct": report["correct"],
        "score_total": report["total"],
        "complete_order_pairs_correct": report["counterfactual_pairs_correct"],
        "complete_order_pairs_total": report["counterfactual_pairs_total"],
        "abstentions_or_invalid": report["abstentions_or_invalid"],
        "source_receipt_authenticated_to_github_artifact": True,
        "model_weights_independently_reexecuted": False,
        "model_promoted": False,
        "minecraft_audio_verified": False,
        "stock_client_verified": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-json", required=True)
    parser.add_argument("--artifact-json", required=True)
    parser.add_argument("--artifact-zip", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        receipt = replay(
            json.loads(Path(args.run_json).read_text()),
            json.loads(Path(args.artifact_json).read_text()),
            Path(args.artifact_zip).read_bytes(),
        )
    except (OSError, ValueError, TypeError, KeyError, ImportError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 1
    encoded = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    Path(args.out).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
