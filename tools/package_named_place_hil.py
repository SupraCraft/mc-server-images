#!/usr/bin/env python3
"""Build a deterministic stock-client HIL packet for one named-place world.

The packet contains only the authored world plus SupraCraft review metadata.
It never bundles a Minecraft client or Mojang asset corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Any

FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def deterministic_zip(world: Path, output: Path) -> None:
    files = sorted(p for p in world.rglob("*") if p.is_file())
    if not files:
        raise ValueError(f"world has no files: {world}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for src in files:
            rel = Path(world.name) / src.relative_to(world)
            info = zipfile.ZipInfo(rel.as_posix(), FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            with src.open("rb") as f:
                zf.writestr(info, f.read(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", type=Path, required=True)
    ap.add_argument("--provenance", type=Path, required=True)
    ap.add_argument("--route", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--place-id", required=True)
    args = ap.parse_args()

    world = args.world.resolve()
    if not world.is_dir():
        raise ValueError(f"world directory not found: {world}")

    provenance = load_json(args.provenance)
    route = load_json(args.route)

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    world_zip = out / f"{args.place_id}-vanilla-26.3-world.zip"
    deterministic_zip(world, world_zip)

    receipt = {
        "schema": "supracraft.named-place-stock-client-hil/v0.1",
        "place_id": args.place_id,
        "minecraft": {"edition": "java", "version": "26.3"},
        "semantic_authority": False,
        "intended_review_authority": "stock_vanilla_client_hil",
        "world_zip": {
            "name": world_zip.name,
            "bytes": world_zip.stat().st_size,
            "sha256": sha256_file(world_zip),
        },
        "provenance": provenance,
        "route": route,
        "review_dimensions": [
            "recognizability",
            "silhouette",
            "palette_material_language",
            "terrain_fit",
            "spatial_grammar",
            "scale_compression",
            "traversal_readability",
            "interior_use_space",
        ],
        "review_result": None,
    }
    receipt_path = out / f"{args.place_id}-hil-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", "utf-8")

    print(json.dumps({
        "world_zip": str(world_zip),
        "receipt": str(receipt_path),
        "sha256": receipt["world_zip"]["sha256"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
