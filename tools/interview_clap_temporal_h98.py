#!/usr/bin/env python3
"""Preregistered *new* CLAP event-order negatives; not Minecraft sound qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

MODEL_ID = "laion/clap-htsat-unfused"
MODEL_REVISION = "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a"
WEIGHTS_SHA256 = "1cd3c601bc4afe0fa87be3de4c13dd2cfadd249fac1e29acf74a9b296c3219bb"
SCHEMA = "supracraft-h98-clap-temporal-counterfactual/v1"
SR = 48000
SEGMENT_SECONDS = 2
# IMPORTANT: freeze this BEFORE first inference, do not revise to fit any observed logits.
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
SEED = 20261117


def validate_plan():
    assert len(PAIRS) == 4
    assert len(set(x[0] for x in PAIRS)) == 4
    for name, a, b, fwd, reverse in PAIRS:
        assert a != b and fwd != reverse
        assert len(fwd) > 18 and len(reverse) > 18


def fixtures():
    import numpy as np
    validate_plan()
    n = SR * SEGMENT_SECONDS
    t = np.arange(n, dtype=np.float64) / SR
    wave = (0.18 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    pulses = (np.mod(t, 0.4) < 0.12).astype(np.float32)
    beep = wave * pulses
    rng = np.random.default_rng(SEED)
    noise = rng.uniform(-0.18, 0.18, size=n).astype(np.float32)
    signals = {"tone": wave, "beeps": beep, "noise": noise, "quiet": np.zeros(n, dtype=np.float32)}
    out = []
    for name, a, b, forward, reverse in PAIRS:
        for idx, order in enumerate(((a, b), (b, a))):
            source = np.concatenate((signals[order[0]], signals[order[1]])).astype(np.float32)
            out.append({
                "id": name + ("_ab" if idx == 0 else "_ba"),
                "pair": name, "reference": "first_a" if idx == 0 else "first_b",
                "wave": source, "captions": (forward, reverse),
                "first_sound": order[0], "second_sound": order[1],
            })
    return out


def sha_file(path):
    sha = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def run():
    import torch
    from huggingface_hub import hf_hub_download
    from transformers import ClapModel, ClapProcessor
    torch.set_num_threads(2)
    started = time.monotonic()
    weight = hf_hub_download(MODEL_ID, "pytorch_model.bin", revision=MODEL_REVISION)
    actual_sha = sha_file(weight)
    if actual_sha != WEIGHTS_SHA256:
        raise ValueError("WEIGHTS_SHA256_MISMATCH_BEFORE_MODEL_LOAD")
    processor = ClapProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    model = ClapModel.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False,
        use_safetensors=False,
    ).eval()

    receipts = []
    for trial in fixtures():
        wave = trial["wave"]
        elapsed_at = time.monotonic()
        rankings = []
        # Prompt-order reversal is NOT another sample: it is a confound falsifier.
        for order in ((0, 1), (1, 0)):
            texts = [trial["captions"][i] for i in order]
            data = processor(text=texts, audios=[wave], sampling_rate=SR,
                             return_tensors="pt", padding=True)
            with torch.inference_mode():
                result = model(**data)
            logits = result.logits_per_audio[0].float().tolist()
            keyed = {("first_a" if i == 0 else "first_b"): float(logits[j])
                     for j, i in enumerate(order)}
            rankings.append(keyed)
        choices = [
            max(row, key=row.get)
            for row in rankings
        ]
        receipts.append({
            "id": trial["id"], "pair_id": trial["pair"],
            "expected": trial["reference"],
            "input_sha256": hashlib.sha256(wave.astype("<f4").tobytes()).hexdigest(),
            "sample_rate": SR, "samples": len(wave),
            "first_sound": trial["first_sound"],
            "second_sound": trial["second_sound"],
            "captions": list(trial["captions"]),
            "raw_logits_forward_order": rankings[0],
            "raw_logits_reverse_order": rankings[1],
            "predicted_forward_order": choices[0],
            "predicted_reverse_order": choices[1],
            "prompt_order_invariant": choices[0] == choices[1],
            "correct": choices[0] == trial["reference"],
            "seconds": round(time.monotonic() - elapsed_at, 3),
        })
    paired = []
    for pair, *_ in PAIRS:
        items = [x for x in receipts if x["pair_id"] == pair]
        paired.append({
            "pair_id": pair,
            "both_correct": len(items) == 2 and all(x["correct"] for x in items),
            "changed_prediction_when_audio_reversed": items[0]["predicted_forward_order"] != items[1]["predicted_forward_order"],
        })
    return {
        "schema": SCHEMA, "status": "FIRST_FROZEN_REAL_MODEL_OUTPUT_REVIEW_REQUIRED",
        "model": MODEL_ID, "revision": MODEL_REVISION,
        "weights_sha256": actual_sha,
        "fixture_plan_sha256": hashlib.sha256(repr(PAIRS).encode()).hexdigest(),
        "audio_seed": SEED, "audio_origin": "original_synthetic_only",
        "results": receipts, "pairs": paired,
        "correct": sum(x["correct"] for x in receipts),
        "total": len(receipts),
        "fully_correct_counterfactual_pairs": sum(x["both_correct"] for x in paired),
        "counterfactual_pairs_total": len(paired),
        "prompt_order_invariant_count": sum(x["prompt_order_invariant"] for x in receipts),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "qualified_model": False, "authentic_minecraft_audio": False,
        "human_accepted": False, "billed_usd": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    opts = parser.parse_args()
    try:
        receipt = run()
    except Exception as exc:
        receipt = {"schema": SCHEMA, "status": "FIRST_REP_RUNTIME_RED",
                   "error_type": type(exc).__name__, "error": str(exc)[:500],
                   "qualified_model": False, "authentic_minecraft_audio": False}
        Path(opts.out).write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
        raise
    Path(opts.out).write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
