#!/usr/bin/env python3
"""One fixed, public-safe, no-key CPU VLM interview; never self-promotes a critic."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import sys
import time

MODEL_ID = "HuggingFaceTB/SmolVLM-256M-Instruct"
MODEL_REVISION = "d039ab0d4b9311b617e8ffec1d06c8464364aeb3"
PROMPT = "What is the dominant color of the square? Answer with one word: red, blue, or unknown."
SCHEMA = "supracraft-cpu-vlm-interview/v1"


def run():
    import torch
    from PIL import Image
    from huggingface_hub import hf_hub_download
    from transformers import AutoProcessor, Idefics3ForConditionalGeneration

    torch.set_num_threads(2)
    started = time.monotonic()
    processor = AutoProcessor.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    model = Idefics3ForConditionalGeneration.from_pretrained(
        MODEL_ID, revision=MODEL_REVISION, torch_dtype=torch.float32
    ).eval()
    weights_file = hf_hub_download(MODEL_ID, "model.safetensors", revision=MODEL_REVISION)
    with open(weights_file, "rb") as stream:
        hasher = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            hasher.update(chunk)
    results = []
    for label, rgb in (("red", (255, 0, 0)), ("blue", (0, 0, 255))):
        image = Image.new("RGB", (96, 96), rgb)
        # Exact PNG bytes are public-safe original fixtures, never Minecraft art.
        import io
        out = io.BytesIO()
        image.save(out, format="PNG")
        image_digest = hashlib.sha256(out.getvalue()).hexdigest()
        messages = [{"role": "user", "content": [
            {"type": "image", "image": image},
            {"type": "text", "text": PROMPT},
        ]}]
        before = time.monotonic()
        inputs = processor.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=True,
            return_dict=True, return_tensors="pt"
        )
        with torch.inference_mode():
            ids = model.generate(**inputs, do_sample=False, max_new_tokens=32)
        output = processor.batch_decode(
            ids[:, inputs["input_ids"].shape[-1]:], skip_special_tokens=True
        )[0].strip()
        words = re.findall(r"\b(red|blue|unknown)\b", output.lower())
        choice = words[0] if len(words) == 1 else None
        results.append({
            "fixture": label, "fixture_sha256": image_digest,
            "model_response": output, "parsed_choice": choice,
            "exact_color_match": choice == label,
            "inference_seconds": round(time.monotonic() - before, 3),
        })
    return {
        "schema": SCHEMA, "status": "MODEL_OUTPUT_CAPTURED_REVIEW_REQUIRED",
        "provider": "local_open_weights", "model": MODEL_ID,
        "revision": MODEL_REVISION, "model_weights_sha256": hasher.hexdigest(),
        "license": "apache-2.0", "hardware": "standard_public_runner_cpu",
        "torch_version": torch.__version__, "transformers_version": __import__("transformers").__version__,
        "prompt": PROMPT, "results": results, "total_seconds": round(time.monotonic() - started, 3),
        "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "qualified_model": False, "stock_client_verified": False,
        "minecraft_gameplay_verified": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    args = p.parse_args()
    try:
        receipt = run()
    except Exception as exc:
        receipt = {
            "schema": SCHEMA, "status": "NOT_QUALIFIED_RUNTIME_RED",
            "provider": "local_open_weights", "model": MODEL_ID,
            "revision": MODEL_REVISION, "qualified_model": False,
            "error_type": type(exc).__name__, "error": str(exc)[:500],
        }
        Path(args.out).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        raise
    Path(args.out).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
