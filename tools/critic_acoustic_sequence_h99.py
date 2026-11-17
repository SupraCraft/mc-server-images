#!/usr/bin/env python3
"""Deterministic bounded event-order oracle for synthetic PCM. NOT game-audio proof.

The primitive here is deliberately narrow: 440 Hz spectral energy and gated
silence. It cannot recognize footsteps, combat, spoken dialogue, or game events.
"""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import sys
import wave

SCHEMA = "supracraft-h99-deterministic-audio-order/v1"
RATE = 48000
SEGMENT_SECONDS = 2
WINDOW_SAMPLES = RATE // 20  # 50 ms, 22 cycles at 440 Hz
LABELS = ("tone", "beeps", "noise", "quiet")
MAX_BYTES = 2_000_000


def _goertzel_ratio(samples):
    # Exact 22 cycles per 50-ms window, no external FFT/numeric dependencies.
    omega = 2.0 * math.pi * 440.0 / RATE
    coeff = 2.0 * math.cos(omega)
    first, second = 0.0, 0.0
    energy = 0.0
    for x in samples:
        normalized = float(x) / 32768.0
        third = normalized + coeff * first - second
        second, first = first, third
        energy += normalized * normalized
    if energy <= 0:
        return 0.0
    power = first * first + second * second - coeff * first * second
    return max(0.0, min(1.0, power / (energy * len(samples) / 2.0)))


def classify(samples):
    if len(samples) != RATE * SEGMENT_SECONDS:
        raise ValueError("SEGMENT_LENGTH_INVALID")
    active = 0
    ratios = []
    peaks = 0
    for start in range(0, len(samples), WINDOW_SAMPLES):
        block = samples[start:start + WINDOW_SAMPLES]
        peak = max(abs(x) for x in block)
        peaks = max(peak, peaks)
        rms = math.sqrt(sum(float(x) * x for x in block) / len(block)) / 32768
        if rms >= 0.012:
            active += 1
            ratios.append(_goertzel_ratio(block))
    fraction = active / (len(samples) / WINDOW_SAMPLES)
    mean_tone = sum(ratios) / len(ratios) if ratios else 0.0
    if peaks >= 32760:
        raise ValueError("CLIPPED_SOURCE_UNQUALIFIED")
    if fraction <= 0.02:
        kind = "quiet"
    elif mean_tone >= 0.70 and fraction >= 0.85:
        kind = "tone"
    elif mean_tone >= 0.70 and 0.08 <= fraction <= 0.75:
        kind = "beeps"
    elif mean_tone < 0.15 and fraction >= 0.80:
        kind = "noise"
    else:
        kind = "unknown"
    return {"class": kind, "active_window_fraction": round(fraction, 5),
            "tone_440hz_ratio": round(mean_tone, 5)}


def read_pcm(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("MEDIA_UNAVAILABLE_OR_SYMLINK")
    if not 44 < p.stat().st_size <= MAX_BYTES:
        raise ValueError("MEDIA_SIZE_UNSAFE")
    try:
        with wave.open(str(p), "rb") as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(),
                    stream.getcomptype()) != (1, 2, RATE, "NONE"):
                raise ValueError("ONLY_MONO_48KHZ_PCM16_ACCEPTED")
            if stream.getnframes() != RATE * SEGMENT_SECONDS * 2:
                raise ValueError("REQUIRES_EXACT_TWO_2S_SEGMENTS")
            raw = stream.readframes(stream.getnframes())
    except (wave.Error, EOFError, OSError) as exc:
        raise ValueError("WAVE_DECODE_REFUSED") from exc
    if len(raw) != RATE * SEGMENT_SECONDS * 2 * 2:
        raise ValueError("PCM_BYTES_TRUNCATED")
    decoded = array("h")
    decoded.frombytes(raw)
    if sys.byteorder != "little":
        decoded.byteswap()
    return p, decoded


def inspect(path):
    p, samples = read_pcm(path)
    cut = RATE * SEGMENT_SECONDS
    first = classify(samples[:cut])
    second = classify(samples[cut:])
    return {
        "schema": SCHEMA,
        "status": "NARROW_SIGNAL_ORACLE_REVIEW_REQUIRED",
        "media_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "sample_rate_hz": RATE, "duration_ms": 4000,
        "events": [{"start_ms": 0, "end_ms": 2000, **first},
                   {"start_ms": 2000, "end_ms": 4000, **second}],
        "ordered_labels": [first["class"], second["class"]],
        "known_synthetic_tone_family_only": True,
        "model_inference_performed": False,
        "authentic_minecraft_audio": False,
        "temporal_model_qualified": False,
        "stock_client_verified": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--media", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    try:
        receipt = inspect(args.media)
    except ValueError as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 1
    s = json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    Path(args.out).write_text(s, encoding="utf-8")
    print(s, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
