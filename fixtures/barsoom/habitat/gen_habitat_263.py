#!/usr/bin/env python3
"""Java 26.3 native, separately composable Barsoom terrain vegetation feature.

No blanket override of vanilla biome, no persistent runtime tick loop, no new
registered blocks. Uses new 26.3 projected random patch worldgen primitive.
Operator/build-time actuator (/place feature) is a separate qualification gate
from automatic biome/chunk generation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

PACK = {"pack": {"description": "Barsoom scarlet scatter native 26.3 worldgen RDTE",
                 "min_format": [121, 0], "max_format": [121, 0]}}
FEATURE = {
    "type": "minecraft:projected_random_patchy_square",
    "block": {"type": "minecraft:simple", "state": {"Name": "minecraft:dead_bush"}},
    "project_through": {"type": "minecraft:matching_blocks", "blocks": ["minecraft:air"]},
    "size": 5,
    "max_projection_height": 24
}
PLACED = {"feature": "barsoom_habitat:scarlet_patch", "placement": []}


def build(path: Path) -> dict:
    files = {
        "pack.mcmeta": PACK,
        "data/barsoom_habitat/worldgen/feature/scarlet_patch.json": FEATURE,
        "data/barsoom_habitat/worldgen/placed_feature/scarlet_patch.json": PLACED,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (2026, 10, 18, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, json.dumps(data, indent=2, sort_keys=True) + "\n")
    return {"schema": "supracraft.barsoom.habitat-feature/1", "version": "26.3",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "members": sorted(files), "feature": "barsoom_habitat:scarlet_patch",
            "activation": "operator_place_feature_only", "automatic_biome_injection": False}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--manifest", type=Path)
    a = p.parse_args()
    receipt = build(a.output)
    if a.manifest:
        a.manifest.parent.mkdir(parents=True, exist_ok=True)
        a.manifest.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
