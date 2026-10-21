#!/usr/bin/env python3
"""Deterministic public-safe vanilla Java 26.3 flora prototype.

Five distinct stock-block flora proxies. The demo function MUST only be
invoked in an intentionally disposable, empty staging area.
No new blocks, resource pack, autonomous worldgen, or mod is claimed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

VERSION = "26.3"
FORMAT = [121, 0]
NAMESPACE = "barsoom_flora"
SPECIES = {
    "scarlet_underbrush": {
        "kind": "grass", "offset": [-8, 0, 0],
        "proxy": "minecraft:crimson_roots",
        "behavior": "native decorative vegetation, manually plantable on nylium",
        "commands": [
            "setblock ~ ~-1 ~ minecraft:crimson_nylium",
            "setblock ~ ~ ~ minecraft:crimson_roots",
        ],
    },
    "thorn_shrub": {
        "kind": "shrub", "offset": [-4, 0, 0],
        "proxy": "minecraft:sweet_berry_bush",
        "behavior": "native contact hazard and berry harvest",
        "commands": [
            "setblock ~ ~-1 ~ minecraft:dirt",
            "setblock ~ ~ ~ minecraft:sweet_berry_bush[age=3]",
        ],
    },
    "canopy_tree": {
        "kind": "tree", "offset": [0, 0, 0],
        "proxy": "minecraft:warped_stem,minecraft:warped_wart_block",
        "behavior": "static multiblock alien canopy; tree growth not yet simulated",
        "commands": [
            "setblock ~ ~-1 ~ minecraft:netherrack",
            "fill ~ ~ ~ ~ ~3 ~ minecraft:warped_stem",
            "fill ~-1 ~3 ~-1 ~1 ~4 ~1 minecraft:warped_wart_block",
        ],
    },
    "canal_crop": {
        "kind": "crop", "offset": [5, 0, 0],
        "proxy": "minecraft:wheat",
        "behavior": "mature native wheat, irrigated by adjacent water; ordinary harvest",
        "commands": [
            "setblock ~ ~-1 ~ minecraft:farmland[moisture=7]",
            "setblock ~1 ~-1 ~ minecraft:water",
            "setblock ~ ~ ~ minecraft:wheat[age=7]",
        ],
    },
    "predator_fungus": {
        "kind": "carnivorous", "offset": [9, 0, 0],
        "proxy": "minecraft:crimson_fungus,minecraft:marker",
        "behavior": "bounded once-per-second proximity poison for players",
        "commands": [
            "setblock ~ ~-1 ~ minecraft:crimson_nylium",
            "setblock ~ ~ ~ minecraft:crimson_fungus",
            'execute unless entity @e[type=minecraft:marker,tag=barsoom_flora.predator,distance=..1] run summon minecraft:marker ~ ~ ~ {Tags:["barsoom_flora.demo","barsoom_flora.predator"]}',
        ],
    },
}
assert set(s["kind"] for s in SPECIES.values()) == {
    "grass", "shrub", "tree", "crop", "carnivorous"
}

def as_lines(lines: list[str]) -> bytes:
    return ("\n".join(lines) + "\n").encode("utf-8")

def documents() -> dict[str, bytes]:
    files = {
        "pack.mcmeta": (json.dumps({
            "pack": {
                "description": "Barsoom flora v0 native Java 26.3 research fixture",
                "min_format": FORMAT,
                "max_format": FORMAT,
            }
        }, indent=2, sort_keys=True) + "\n").encode(),
        "data/minecraft/tags/function/load.json": (
            json.dumps({"values": ["barsoom_flora:load"]}, indent=2) + "\n"
        ).encode(),
        "data/barsoom_flora/function/load.mcfunction": as_lines([
            "schedule function barsoom_flora:hazard_tick 20t replace",
        ]),
        "data/barsoom_flora/function/hazard_tick.mcfunction": as_lines([
            "execute as @e[type=minecraft:marker,tag=barsoom_flora.predator,limit=8] at @s run effect give @a[distance=..2] minecraft:poison 2 0 true",
            "schedule function barsoom_flora:hazard_tick 20t replace",
        ]),
    }
    demo = [
        "# DESTRUCTIVE at its five plant sites; for an intentionally disposable test region only.",
        "# Invoke: execute positioned 512 192 512 run function barsoom_flora:demo",
    ]
    for name, species in SPECIES.items():
        x, y, z = species["offset"]
        demo.append(
            f"execute positioned ~{x} ~{y} ~{z} run function barsoom_flora:species/{name}"
        )
        files[f"data/barsoom_flora/function/species/{name}.mcfunction"] = as_lines(species["commands"])
    files["data/barsoom_flora/function/demo.mcfunction"] = as_lines(demo)
    return files

def build(path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = documents()
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(contents.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return {
        "schema": "supracraft.barsoom.flora-fixture/1",
        "minecraft": VERSION, "data_pack_format": FORMAT,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "species": {name: {"kind": s["kind"], "offset": s["offset"], "proxy": s["proxy"], "behavior": s["behavior"]} for name, s in SPECIES.items()},
        "members": sorted(contents),
        "status": "STATIC_ARTIFACT_ONLY_NATIVE_QUALIFICATION_REQUIRED",
    }

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--receipt", type=Path)
    args = ap.parse_args()
    result = build(args.output)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
