#!/usr/bin/env python3
"""A strictly additive two-biome world-preset candidate for Minecraft Java 26.3.

This is an RDTE fixture, NOT accepted or deployed. It requires the separately
qualified terrain, habitat, and Scarlet Wastes producer packs. The preset is a
spatial falsification oracle rather than Barsoom's eventual planetary map.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

SCHEMA = "supracraft.barsoom.two-province-rdte/1"
PACK = {"pack": {"description": "Scarlet+Badlands checkerboard qualification only (26.3)",
                 "min_format": [121, 0], "max_format": [121, 0]}}
PRESET_ID = "barsoom_habitat:checkerboard_provinces"
BIOMES = ["barsoom_habitat:scarlet_wastes", "minecraft:badlands"]
SCALE = 3  # each stripe cell is 2^(scale+4) = 128 blocks = 8 chunks
PARENT_SHA256 = {
    "terrain": "9d5ad764a2df4786666326e997a3ed724524583fe3191b60305677fbe5fb531e",
    "habitat": "1bfbb244d9a172d00e1357370c464874e2e32a0e55a306e15f4a02dae4a332e7",
    "scarlet": "4a8f2fc5b81d26f56be04dc90254abf7afee076db7d0897b7521c0c00e84d573",
}

WORLD_PRESET = {"dimensions": {
    "minecraft:overworld": {
        "type": "minecraft:overworld",
        "generator": {"type": "minecraft:noise",
            "biome_source": {"type": "minecraft:checkerboard", "biomes": BIOMES, "scale": SCALE},
            "settings": "minecraft:overworld"}},
    "minecraft:the_nether": {
        "type": "minecraft:the_nether",
        "generator": {"type": "minecraft:noise",
            "biome_source": {"type": "minecraft:multi_noise", "preset": "minecraft:nether"},
            "settings": "minecraft:nether"}},
    "minecraft:the_end": {
        "type": "minecraft:the_end",
        "generator": {"type": "minecraft:noise",
            "biome_source": {"type": "minecraft:the_end"},
            "settings": "minecraft:end"}}}}


def cell_size(scale: int = SCALE) -> int:
    """Each cell's side length in blocks; follows quartX >> (scale+2)."""
    return 1 << (scale + 4)


def biome_at(x: int, z: int, scale: int = SCALE) -> str:
    """Independent *expected* checkerboard model; native assertion remains required."""
    size = cell_size(scale)
    return BIOMES[((x // size) + (z // size)) % len(BIOMES)]


def build(path: Path) -> dict:
    files = {
        "pack.mcmeta": PACK,
        "data/barsoom_habitat/worldgen/world_preset/checkerboard_provinces.json": WORLD_PRESET,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, obj in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, json.dumps(obj, sort_keys=True, indent=2) + "\n")
    return {
        "schema": SCHEMA, "minecraft": "26.3", "pack_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "members": sorted(files), "preset": PRESET_ID, "biomes": BIOMES,
        "scale": SCALE, "cell_width_blocks": cell_size(), "cell_width_chunks": cell_size() // 16,
        "parent_pack_sha256": PARENT_SHA256,
        "world_activation": "explicit_new_disposable_world_only",
        "native_acceptance": "NOT_RUN", "production": "HOLD",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    result = build(args.output)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
