#!/usr/bin/env python3
"""Additive feature-ablated Scarlet biome and world preset, for falsification only.

Never override the original Scarlet Wastes. The ablated biome's climate and
non-vegetation settings equal the parent Scarlet definition; only its registered
feature steps are empty. Compare *same seed / same coordinates* in disposable
worlds, without player actions or edit commands. This is NOT a game mode.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"fixtures/barsoom/biomes"))
sys.path.insert(0,str(ROOT/"fixtures/barsoom/provinces"))
from gen_scarlet_wastes_263 import BIOME
from gen_checkerboard_263 import WORLD_PRESET

ABLATION_BIOME="barsoom_habitat:scarlet_ablated"
ABLATION_PRESET="barsoom_habitat:checkerboard_ablated"

def build(path:Path)->dict:
    biome=copy.deepcopy(BIOME)
    biome["features"]=[[] for _ in BIOME["features"]]
    preset=copy.deepcopy(WORLD_PRESET)
    source=preset["dimensions"]["minecraft:overworld"]["generator"]["biome_source"]
    source["biomes"]=[ABLATION_BIOME,"minecraft:badlands"]
    files={
        "pack.mcmeta":{"pack":{"description":"Barsoom ablation-only RDTE, Java 26.3",
                              "min_format":[121,0],"max_format":[121,0]}},
        "data/barsoom_habitat/worldgen/biome/scarlet_ablated.json":biome,
        "data/barsoom_habitat/worldgen/world_preset/checkerboard_ablated.json":preset,
    }
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as out:
        for name,obj in sorted(files.items()):
            entry=zipfile.ZipInfo(name,(2026,10,19,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED
            out.writestr(entry,json.dumps(obj,indent=2,sort_keys=True)+"\n")
    return {"schema":"supracraft.barsoom.checkerboard-ablation/1",
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "members":sorted(files),"ablation_biome":ABLATION_BIOME,
            "ablation_preset":ABLATION_PRESET,
            "removed":"only_custom_registered_vegetation_feature",
            "vanilla_namespaces_overridden":False,
            "baseline_biome_overridden":False,"native_acceptance":"NOT_RUN"}

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--receipt",type=Path)
    args=parser.parse_args()
    report=build(args.output)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True,exist_ok=True)
        args.receipt.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))
