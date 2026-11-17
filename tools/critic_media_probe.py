#!/usr/bin/env python3
"""Source-neutral media provenance probe; never asserts Minecraft gameplay acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

SCHEMA = "supracraft-critic-media-probe/v1"
MAX_BYTES = 100 * 1024 * 1024


def inspect(path, kind, require_audio=False):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("MEDIA_MISSING_OR_SYMLINK")
    size = path.stat().st_size
    if not 0 < size <= MAX_BYTES:
        raise ValueError("MEDIA_EMPTY_OR_OVER_LIMIT")
    with path.open("rb") as media_stream:
        header = media_stream.read(16)
    is_still = (header.startswith(b"\x89PNG\r\n\x1a\n")
                or header.startswith(b"\xff\xd8\xff")
                or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
                or header.startswith(b"BM")
                or header.startswith(b"II*\x00")
                or header.startswith(b"MM\x00*"))
    if kind == "image" and not is_still:
        raise ValueError("STILL_IMAGE_SIGNATURE_REQUIRED")
    if kind == "video" and is_still:
        raise ValueError("VIDEO_MUST_NOT_BE_STILL_IMAGE")
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=index,codec_type,codec_name,width,height,sample_rate,channels:"
             "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=20, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("FFPROBE_UNAVAILABLE_OR_FAILED") from exc
    try:
        decoded = json.loads(result.stdout)
        streams = decoded["streams"]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("MEDIA_METADATA_INVALID") from exc
    if not isinstance(streams, list) or not streams:
        raise ValueError("MEDIA_NO_TRACKS")
    tracks = sorted({stream.get("codec_type") for stream in streams})
    if kind == "image" and (
        len(streams) != 1 or streams[0].get("codec_type") != "video"
        or streams[0].get("codec_name") not in {"png", "mjpeg", "webp", "bmp", "tiff"}
    ):
        raise ValueError("STILL_IMAGE_STREAM_INVALID")
    if kind in ("image", "video") and "video" not in tracks:
        raise ValueError("NO_VIDEO_TRACK")
    if kind == "audio" and "audio" not in tracks:
        raise ValueError("NO_AUDIO_TRACK")
    if require_audio and "audio" not in tracks:
        raise ValueError("NO_AUDIO_TRACK")
    hasher = hashlib.sha256()
    with path.open("rb") as media_stream:
        for chunk in iter(lambda: media_stream.read(1 << 20), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    duration = decoded.get("format", {}).get("duration")
    try:
        duration_ms = round(float(duration) * 1000) if duration not in (None, "N/A") else None
    except (ValueError, OverflowError, TypeError):
        raise ValueError("INVALID_DURATION")
    return {
        "schema": SCHEMA, "kind": kind, "sha256": digest, "bytes": size,
        "duration_ms": duration_ms, "tracks": tracks,
        "streams": [
            {key: stream[key] for key in
             ("codec_type", "codec_name", "width", "height", "sample_rate", "channels")
             if key in stream}
            for stream in streams
        ],
        "source_authority": "media_bytes_plus_ffprobe_only",
        "minecraft_runtime_verified": False,
        "stock_client_verified": False,
        "review_status": "REVIEW_REQUIRED",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--media", required=True)
    parser.add_argument("--kind", choices=("image", "video", "audio"), required=True)
    parser.add_argument("--require-audio", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()
    try:
        data = inspect(args.media, args.kind, args.require_audio)
    except ValueError as exc:
        print(json.dumps({"schema": SCHEMA, "status": "REFUSED", "reason": str(exc)}))
        return 1
    encoded = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
