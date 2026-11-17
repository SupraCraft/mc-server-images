#!/usr/bin/env python3
"""Bounded acoustic signal probe (not an audio-semantic or gameplay critic)."""
import argparse
from array import array
import json
import math
from pathlib import Path
import subprocess
import sys

from critic_media_probe import inspect

SCHEMA = "supracraft-critic-acoustic-preflight/v1"
MAX_DURATION_MS = 30000
SAMPLE_RATE = 16000
WINDOW = SAMPLE_RATE // 4


def probe(path):
    evidence = inspect(path, "audio")
    duration = evidence.get("duration_ms")
    if duration is None or not 0 < duration <= MAX_DURATION_MS:
        raise ValueError("AUDIO_DURATION_OUT_OF_BOUNDS")
    try:
        result = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
             "-map", "0:a:0", "-t", "30", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
             "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"],
            capture_output=True, timeout=30, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("AUDIO_DECODE_FAILED") from exc
    raw = result.stdout
    if not raw or len(raw) % 2 or len(raw) > MAX_DURATION_MS * SAMPLE_RATE * 2 // 1000:
        raise ValueError("AUDIO_DECODE_SIZE_INVALID")
    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    n = len(samples)
    peak = max(abs(s) for s in samples)
    rms = math.sqrt(sum(s * s for s in samples) / n)
    clipping = sum(abs(s) >= 32760 for s in samples) / n
    windows = [samples[i:i + WINDOW] for i in range(0, n, WINDOW)]
    silent_windows = sum(
        all(abs(sample) < 100 for sample in w) for w in windows if w
    )
    return {
        "schema": SCHEMA,
        "source_sha256": evidence["sha256"],
        "source_track_types": evidence["tracks"],
        "sample_rate_hz": SAMPLE_RATE, "decoded_samples": n,
        "decoded_duration_ms": round(n * 1000 / SAMPLE_RATE),
        "peak_dbfs": round(20 * math.log10(max(peak / 32768, 1e-12)), 3),
        "rms_dbfs": round(20 * math.log10(max(rms / 32768, 1e-12)), 3),
        "clipping_sample_fraction": round(clipping, 8),
        "silence_windows": silent_windows,
        "window_count": len(windows),
        "acoustic_signal_present": rms > 100,
        "source_audio_origin_authenticated": False,
        "minecraft_audio_verified": False,
        "status": "SIGNAL_ONLY_REVIEW_REQUIRED",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--media", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        receipt = probe(args.media)
    except ValueError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "REFUSED", "reason": str(exc)}))
        return 1
    encoded = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
