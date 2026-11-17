#!/usr/bin/env python3
"""H97 preregistered counterfactual spatial controls; never a Minecraft acceptance gate."""
import argparse
import hashlib
import io
import json
import resource
import time
from pathlib import Path

MODEL = "google/siglip-base-patch16-224"
REVISION = "d9049814fd748f55717e7f6e8e330574f955bd0a"
WEIGHTS_SHA256 = "2c63cb7d1f2e95ba501893cbb8faeb4ea9a3af295498d35097126228659c2af8"
SCHEMA = "supracraft-h97-spatial-counterfactual/v1"
PROMPTS = {
    "horizontal": [
        "A red circle is to the left of a blue circle.",
        "A red circle is to the right of a blue circle.",
    ],
    "vertical": [
        "A red circle is above a blue circle.",
        "A red circle is below a blue circle.",
    ],
}

# New cases: two-object relationships and mirrors. Never modify after observing first outputs.
CASES = (
    ("h01", "horizontal", "left", (54, 112), (170, 112)),
    ("h02", "horizontal", "right", (170, 112), (54, 112)),
    ("v01", "vertical", "above", (112, 54), (112, 170)),
    ("v02", "vertical", "below", (112, 170), (112, 54)),
    ("h03", "horizontal", "left", (70, 150), (162, 150)),
    ("h04", "horizontal", "right", (162, 150), (70, 150)),
    ("v03", "vertical", "above", (64, 70), (64, 162)),
    ("v04", "vertical", "below", (64, 162), (64, 70)),
)


def fixture_bytes(left_center, right_center):
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (224, 224), (244, 244, 236))
    draw = ImageDraw.Draw(image)
    for (x, y), color in ((left_center, (240, 28, 28)),
                          (right_center, (32, 56, 230))):
        draw.ellipse((x - 19, y - 19, x + 19, y + 19), fill=color)
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    return image, encoded.getvalue()


def validate_plan():
    assert len(CASES) == 8
    assert len({c[0] for c in CASES}) == 8
    for _, kind, expected, red, blue in CASES:
        assert expected in (("left", "right") if kind == "horizontal" else ("above", "below"))
        assert red != blue


def run():
    validate_plan()
    import torch
    from huggingface_hub import hf_hub_download
    from transformers import AutoProcessor, AutoModelForZeroShotImageClassification

    started = time.monotonic()
    torch.set_num_threads(2)
    weights = hf_hub_download(MODEL, "model.safetensors", revision=REVISION)
    h = hashlib.sha256()
    with open(weights, "rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            h.update(block)
    if h.hexdigest() != WEIGHTS_SHA256:
        raise RuntimeError("WEIGHTS_SHA256_MISMATCH")
    processor = AutoProcessor.from_pretrained(MODEL, revision=REVISION)
    model = AutoModelForZeroShotImageClassification.from_pretrained(
        MODEL, revision=REVISION, use_safetensors=True).eval()
    obs = []
    for trial, kind, expected, red_center, blue_center in CASES:
        image, raw = fixture_bytes(red_center, blue_center)
        prompts = PROMPTS[kind]
        started_trial = time.monotonic()
        inputs = processor(text=prompts, images=image, padding="max_length",
                           return_tensors="pt")
        with torch.inference_mode():
            logits = model(**inputs).logits_per_image[0].float().tolist()
        labels = ["left", "right"] if kind == "horizontal" else ["above", "below"]
        top = labels[max(range(len(logits)), key=logits.__getitem__)]
        obs.append({
            "trial": trial, "kind": kind, "expected": expected,
            "fixture_sha256": hashlib.sha256(raw).hexdigest(),
            "raw_logits": dict(zip(labels, logits)), "top1": top,
            "correct": top == expected,
            "trial_seconds": round(time.monotonic() - started_trial, 3),
        })
    return {
        "schema": SCHEMA, "model": MODEL, "revision": REVISION,
        "weights_sha256": WEIGHTS_SHA256,
        "fixture_plan_hash": hashlib.sha256(repr(CASES).encode("utf-8")).hexdigest(),
        "prompt_plan_hash": hashlib.sha256(json.dumps(PROMPTS, sort_keys=True).encode()).hexdigest(),
        "all_original_synthetic": True, "results": obs,
        "correct": sum(t["correct"] for t in obs), "total": len(obs),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "status": "FIRST_FROZEN_REP_REVIEW_REQUIRED",
        "qualified_critic": False,
        "minecraft_26_3_verified": False, "human_accepted": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        result = run()
    except Exception as exc:
        result = {
            "schema": SCHEMA, "status": "FIRST_REP_RUNTIME_RED",
            "error_type": type(exc).__name__, "error": str(exc)[:400],
            "qualified_critic": False,
        }
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        raise
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
