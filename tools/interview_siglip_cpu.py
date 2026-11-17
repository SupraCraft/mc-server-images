#!/usr/bin/env python3
"""Independent open-weight SigLIP image critic interview, fail closed and unpromoted."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import resource
import time

MODEL_ID = "google/siglip-base-patch16-224"
MODEL_REVISION = "d9049814fd748f55717e7f6e8e330574f955bd0a"
EXPECTED_WEIGHTS_SHA256 = "2c63cb7d1f2e95ba501893cbb8faeb4ea9a3af295498d35097126228659c2af8"
SCHEMA = "supracraft-critic-siglip-interview/v1"

COLORS = [
    ("red", (255, 0, 0)),
    ("blue", (0, 0, 255)),
    ("green", (0, 255, 0)),
    ("yellow", (255, 255, 0)),
]
COLOR_PROMPTS = [
    "A photograph of a solid red square.",
    "A photograph of a solid blue square.",
    "A photograph of a solid green square.",
    "A photograph of a solid yellow square.",
]
POSITION_PROMPTS = [
    "A black square on the left side of a white background.",
    "A black square on the right side of a white background.",
]


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run():
    import torch
    from PIL import Image, ImageDraw
    from huggingface_hub import hf_hub_download
    from transformers import AutoProcessor, AutoModelForZeroShotImageClassification

    torch.set_num_threads(2)
    started = time.monotonic()
    weights = hf_hub_download(MODEL_ID, "model.safetensors", revision=MODEL_REVISION)
    actual_weights = sha_file(weights)
    if actual_weights != EXPECTED_WEIGHTS_SHA256:
        raise RuntimeError("WEIGHTS_DIGEST_MISMATCH")
    processor = AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    model = AutoModelForZeroShotImageClassification.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, use_safetensors=True
    ).eval()

    def interrogate(image, expected, labels, prompts, kind):
        raw = io.BytesIO()
        image.save(raw, format="PNG")
        digest = hashlib.sha256(raw.getvalue()).hexdigest()
        begin = time.monotonic()
        inputs = processor(text=prompts, images=image, padding="max_length",
                           return_tensors="pt")
        with torch.inference_mode():
            result = model(**inputs)
            # SigLIP is sigmoid (not softmax) trained. Scores are NOT calibrated confidence.
            logits = result.logits_per_image[0].float().tolist()
        rankings = sorted(zip(labels, logits), key=lambda t: t[1], reverse=True)
        return {
            "kind": kind, "expected": expected, "fixture_sha256": digest,
            "prompt_texts": prompts, "raw_logits": dict(zip(labels, logits)),
            "ranked_labels": [name for name, _ in rankings],
            "top1": rankings[0][0], "top1_matches_reference": rankings[0][0] == expected,
            "relative_logit_margin": round(rankings[0][1] - rankings[1][1], 6),
            "seconds": round(time.monotonic() - begin, 3),
        }

    results = []
    labels = [name for name, _ in COLORS]
    for name, rgb in COLORS:
        results.append(interrogate(Image.new("RGB", (96, 96), rgb),
                                   name, labels, COLOR_PROMPTS, "color-square"))
    for position in ("left", "right"):
        image = Image.new("RGB", (224, 224), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        x0 = 18 if position == "left" else 162
        draw.rectangle((x0, 80, x0 + 44, 124), fill=(0, 0, 0))
        results.append(interrogate(image, position, ["left", "right"],
                                   POSITION_PROMPTS, "spatial-relation"))

    return {
        "schema": SCHEMA, "status": "MODEL_OUTPUT_CAPTURED_REVIEW_REQUIRED",
        "candidate": {"provider": "local_open_weights", "family": "SigLIP",
                      "model": MODEL_ID, "revision": MODEL_REVISION},
        "weights_sha256": actual_weights, "license": "apache-2.0",
        "python_framework": "transformers", "torch_version": torch.__version__,
        "test_total": len(results),
        "correct_count": sum(item["top1_matches_reference"] for item in results),
        "results": results,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "estimated_cost_usd": 0, "model_promoted": False,
        "minecraft_runtime_verified": False,
        "stock_client_verified": False,
        "audio_or_video_qualified": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        receipt = run()
    except Exception as exc:
        receipt = {
            "schema": SCHEMA, "status": "MODEL_INTERVIEW_RED",
            "candidate": {"model": MODEL_ID, "revision": MODEL_REVISION, "family": "SigLIP"},
            "error_type": type(exc).__name__, "error": str(exc)[:450],
            "model_promoted": False,
        }
        Path(args.out).write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        raise
    Path(args.out).write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
