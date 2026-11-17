#!/usr/bin/env python3
"""First, frozen, free public CPU CLAP sound-language interview; not game-audio acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time

MODEL_ID = "laion/clap-htsat-unfused"
MODEL_REVISION = "8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a"
WEIGHTS_SHA256 = "1cd3c601bc4afe0fa87be3de4c13dd2cfadd249fac1e29acf74a9b296c3219bb"
SCHEMA = "supracraft-h97-clap-audio-interview/v1"
SR = 48000
DURATION_SECONDS = 5
CAPTIONS = [
    "The sound of a continuous pure high pitched electronic tone.",
    "The sound of short repeating electronic beeps separated by silence.",
    "The sound of continuous broadband static or white noise.",
    "Silence, with no audible sound.",
]
LABELS = ["tone", "beeps", "noise", "silence"]


def produce_frozen_fixtures():
    import numpy as np
    tick = np.arange(SR * DURATION_SECONDS, dtype=np.float32) / SR
    wave = 0.25 * np.sin(2 * np.pi * 440 * tick)
    # 0.20s on, 0.30s off: ten acoustic bursts in five seconds.
    duty = (np.mod(tick, 0.5) < 0.20).astype(np.float32)
    beeps = (wave * duty).astype(np.float32)
    noise = np.random.default_rng(20261117).uniform(-0.23, 0.23, size=len(tick)).astype(np.float32)
    return [
        ("tone", wave),
        ("beeps", beeps),
        ("noise", noise),
        ("silence", np.zeros_like(tick)),
    ]


def run():
    import numpy as np
    import torch
    from huggingface_hub import hf_hub_download
    from transformers import ClapModel, ClapProcessor

    torch.set_num_threads(2)
    t0 = time.monotonic()
    weight = hf_hub_download(MODEL_ID, "pytorch_model.bin", revision=MODEL_REVISION)
    sha = hashlib.sha256()
    with open(weight, "rb") as src:
        for block in iter(lambda: src.read(1 << 20), b""):
            sha.update(block)
    if sha.hexdigest() != WEIGHTS_SHA256:
        raise ValueError("WEIGHTS_SHA256_MISMATCH_BEFORE_MODEL_LOAD")
    processor = ClapProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    # Torch 2.6+/transformers safeload: no trust_remote_code, exact known model revision.
    model = ClapModel.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, trust_remote_code=False,
        use_safetensors=False,
    ).eval()
    fixtures = produce_frozen_fixtures()
    assert [name for name, _ in fixtures] == LABELS
    receipts = []
    for name, wave in fixtures:
        start = time.monotonic()
        inputs = processor(
            text=CAPTIONS, audios=[wave],
            sampling_rate=SR, return_tensors="pt", padding=True,
        )
        with torch.inference_mode():
            result = model(**inputs)
        logits = result.logits_per_audio[0].float().tolist()
        top = LABELS[max(range(len(logits)), key=logits.__getitem__)]
        receipts.append({
            "fixture": name, "sample_rate": SR,
            "audio_sha256_float32le": hashlib.sha256(wave.astype("<f4").tobytes()).hexdigest(),
            "raw_logits": dict(zip(LABELS, logits)),
            "top1": top, "correct": top == name,
            "inference_seconds": round(time.monotonic() - start, 3),
        })
    return {
        "schema": SCHEMA, "status": "FIRST_REAL_MODEL_AUDIO_OUTPUT_REVIEW_REQUIRED",
        "candidate": {"model": MODEL_ID, "revision": MODEL_REVISION, "family": "CLAP",
                      "provider": "local_open_weights", "license": "apache-2.0"},
        "model_weights_sha256": sha.hexdigest(), "prompts": CAPTIONS,
        "prompt_sha256": hashlib.sha256(json.dumps(CAPTIONS).encode()).hexdigest(),
        "fixtures": receipts, "correct": sum(r["correct"] for r in receipts),
        "total": len(receipts),
        "elapsed_seconds": round(time.monotonic() - t0, 3),
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "model_qualified": False, "authentic_game_audio": False,
        "minecraft_verified": False, "human_accepted": False,
        "estimated_billed_usd": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    opts = parser.parse_args()
    try:
        result = run()
    except Exception as exc:
        result = {
            "schema": SCHEMA, "status": "FIRST_REP_RUNTIME_RED",
            "error_type": type(exc).__name__, "error": str(exc)[:500],
            "model_qualified": False, "minecraft_verified": False,
        }
        Path(opts.out).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        raise
    Path(opts.out).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
