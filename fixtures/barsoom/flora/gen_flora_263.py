#!/usr/bin/env python3
"""Deterministic, optional, vanilla 26.3 flora demonstration data pack.

Five species are existing-block proxies, NOT new block registries, new biomes,
or a claim of autonomous world distribution. The demo is destructive in a bounded
28x13x9 area: invoke only on a disposable world at a known position.
"""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = re.compile(r"^minecraft:[a-z0-9_]+(?:\[[a-z0-9_=,]+\])?$")
ID = re.compile(r"^[a-z][a-z0-9_]*$")
PACK = {"pack": {"description": "Barsoom flora five-species native 26.3 RDTE canary", "min_format": [121, 0], "max_format": [121, 0]}}


def make(spec: dict) -> dict[str, bytes]:
    assert spec["schema"] == "supracraft.barsoom.flora-species/1" and spec["minecraft"] == "26.3"
    assert len(spec["species"]) == 5
    names = [plant["id"] for plant in spec["species"]]
    assert len(set(names)) == len(names) and all(ID.fullmatch(name) for name in names)
    commands = [
        "# BARSOOM FLORA RDTE. Destructive 28x13x9 fixture: use in a fresh disposable world only.",
        "kill @e[type=minecraft:marker,tag=barsoom_flora.trap,distance=..32]",
        "fill ~-3 ~-1 ~-6 ~24 ~-1 ~6 minecraft:red_terracotta replace",
        "fill ~-3 ~ ~-6 ~24 ~7 ~6 minecraft:air replace",
    ]
    expected = []
    for plant in spec["species"]:
        x, z = plant["origin"]
        assert -1 <= x <= 22 and -1 <= z <= 1
        commands.append("# species: " + plant["id"])
        for block in plant["blocks"]:
            dx, dy, dz = block["at"]
            state = block["state"]
            assert all(type(v) is int and -3 <= v <= 7 for v in (dx, dy, dz))
            assert STATE.fullmatch(state)
            absx, absz = x + dx, z + dz
            assert -3 <= absx <= 24 and -6 <= absz <= 6 and -1 <= dy <= 7
            commands.append(f"setblock ~{absx} ~{dy} ~{absz} {state} replace")
            expected.append({"species": plant["id"], "position": [absx, dy, absz], "state": state})
    assert names == ["red_grass", "thornwood", "glowcap", "canal_reed", "jawbloom"]
    jaw = spec["species"][-1]
    assert jaw["behavior"] == {"kind": "proximity_poison", "radius": 2, "period_ticks": 20, "duration_seconds": 2}
    x, z = jaw["origin"]
    commands.append(f'summon minecraft:marker ~{x} ~0 ~{z} {{Tags:["barsoom_flora.trap"]}}')
    commands.append('tellraw @a {"text":"Barsoom flora demo installed (five vanilla proxies)","color":"gold"}')
    files = {
        "pack.mcmeta": json.dumps(PACK, indent=2, sort_keys=True) + "\n",
        "data/minecraft/tags/function/load.json": json.dumps({"values": ["barsoom_flora:load"]}) + "\n",
        "data/barsoom_flora/function/load.mcfunction": "schedule function barsoom_flora:pulse 20t replace\n",
        "data/barsoom_flora/function/pulse.mcfunction": (
            "execute as @a at @s if entity @e[type=minecraft:marker,tag=barsoom_flora.trap,distance=..2] run effect give @s minecraft:poison 2 0 true\n"
            "schedule function barsoom_flora:pulse 20t replace\n"
        ),
        "data/barsoom_flora/function/demo.mcfunction": "\n".join(commands) + "\n",
    }
    return {name: text.encode("utf-8") for name, text in files.items()}, expected


def build(output: Path, specification: Path = HERE / "species.json") -> dict:
    spec = json.loads(specification.read_text(encoding="utf-8"))
    files, expected = make(spec)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, contents in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 17, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, contents)
    return {"schema": "supracraft.barsoom.flora-build/1", "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "members": sorted(files), "minecraft": "26.3", "species": [plant["id"] for plant in spec["species"]],
            "probes": {s: next(e for e in expected if e["species"] == s and e["position"][1] >= 0) for s in (plant["id"] for plant in spec["species"])},
            "deployment": "opt_in_disposable_only", "vanilla_block_proxies": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    receipt = build(args.output)
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
