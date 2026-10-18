#!/usr/bin/env python3
"""Opt-in isolated Scarlet Wastes biome for *automatic* Java 26.3 vegetation.

Only generates in explicitly selected new-world preset. No override of
minecraft:badlands, barsoom:dead_sea, or previous qualified habitat zip.
The limited feature count is one projected patch per generated chunk.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

PACK = {"pack": {"description": "Barsoom Scarlet Wastes biome autogen RDTE 26.3",
                 "min_format": [121, 0], "max_format": [121, 0]}}
BIOME_ID = "barsoom_habitat:scarlet_wastes"
PRESET_ID = "barsoom_habitat:scarlet_province"
FEATURE_ID = "barsoom_habitat:scarlet_patch"
PLACED_ID = "barsoom_habitat:scarlet_auto"
BIOME = {
    "has_precipitation": False,
    "temperature": 2.0,
    "downfall": 0.0,
    "effects": {
        "fog_color": 11956936, "sky_color": 13472729,
        "water_color": 4159204, "water_fog_color": 329011,
        "grass_color": 11225418, "foliage_color": 10960983
    },
    "carvers": [],
    "features": [[], [], [], [], [], [], [], [], [], [PLACED_ID], []]
}
AUTO_PLACED = {
    "feature": FEATURE_ID,
    "placement": [
        {"type": "minecraft:count", "count": 1},
        {"type": "minecraft:in_square"},
        {"type": "minecraft:heightmap", "heightmap": "WORLD_SURFACE_WG"},
        {"type": "minecraft:biome"}
    ]
}
PRESET = {
    "dimensions": {
        "minecraft:overworld": {
            "type": "minecraft:overworld",
            "generator": {
                "type": "minecraft:noise",
                "biome_source": {"type": "minecraft:fixed", "biome": BIOME_ID},
                "settings": "minecraft:overworld"
            }
        },
        "minecraft:the_nether": {
            "type": "minecraft:the_nether",
            "generator": {
                "type": "minecraft:noise",
                "biome_source": {"type": "minecraft:multi_noise", "preset": "minecraft:nether"},
                "settings": "minecraft:nether"
            }
        },
        "minecraft:the_end": {
            "type": "minecraft:the_end",
            "generator": {
                "type": "minecraft:noise",
                "biome_source": {"type": "minecraft:the_end"},
                "settings": "minecraft:end"
            }
        }
    }
}

def build(output: Path):
    docs = {
        "pack.mcmeta": PACK,
        "data/barsoom_habitat/worldgen/biome/scarlet_wastes.json": BIOME,
        "data/barsoom_habitat/worldgen/placed_feature/scarlet_auto.json": AUTO_PLACED,
        "data/barsoom_habitat/worldgen/world_preset/scarlet_province.json": PRESET,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, obj in sorted(docs.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 18, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, json.dumps(obj, sort_keys=True, indent=2) + "\n")
    return {
        "schema": "supracraft.barsoom.scarlet-autogen/1",
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "members": sorted(docs),
        "biome": BIOME_ID, "preset": PRESET_ID,
        "feature": FEATURE_ID, "placed_feature": PLACED_ID,
        "minecraft": "26.3", "frequency": "one attempt per generated chunk",
        "activation": "fresh_world_explicit_scarlet_province_only",
        "vanilla_biomes_overridden": False,
        "existing_dead_sea_preset_overridden": False
    }

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--receipt", type=Path)
    a = p.parse_args()
    result = build(a.output)
    if a.receipt:
        a.receipt.parent.mkdir(parents=True, exist_ok=True)
        a.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
