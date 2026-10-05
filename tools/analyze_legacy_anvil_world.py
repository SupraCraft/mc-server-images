#!/usr/bin/env python3
"""Static, feedback-blind analyzer for legacy (pre-palette) Minecraft Anvil worlds."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import struct
import tempfile
import zipfile
import zlib
from collections import Counter
from pathlib import Path

import nbtlib


INTERACTION_IDS = {
    23:"dispenser", 54:"chest", 58:"crafting_table", 61:"furnace", 62:"lit_furnace",
    63:"standing_sign", 64:"wooden_door", 65:"ladder", 68:"wall_sign", 69:"lever",
    70:"stone_pressure_plate", 71:"iron_door", 72:"wooden_pressure_plate",
    77:"stone_button", 93:"repeater_off", 94:"repeater_on", 96:"trapdoor",
    107:"fence_gate", 117:"brewing_stand", 118:"cauldron", 130:"ender_chest",
    131:"tripwire_hook", 132:"tripwire", 137:"command_block", 143:"wooden_button",
    145:"anvil", 146:"trapped_chest", 147:"light_weighted_pressure_plate",
    148:"heavy_weighted_pressure_plate", 149:"comparator_off", 150:"comparator_on",
    154:"hopper", 158:"dropper", 167:"iron_trapdoor",
}
REDSTONE_IDS = {
    23,29,33,46,55,69,70,72,75,76,77,93,94,123,124,131,132,137,
    143,147,148,149,150,152,154,158
}
RESOURCE_IDS = {
    "water":{8,9},
    "lava":{10,11},
    "gold_ore":{14},
    "iron_ore":{15},
    "coal_ore":{16},
    "log":{17,162},
    "lapis_ore":{21},
    "diamond_ore":{56},
    "redstone_ore":{73,74},
    "emerald_ore":{129},
    "quartz_ore":{153},
}
AIR=0


def plain(v):
    if hasattr(v,"unpack"):
        try:
            return v.unpack()
        except Exception:
            pass
    return v


def decompress(payload:bytes, kind:int)->bytes:
    if kind==1: return gzip.decompress(payload)
    if kind==2: return zlib.decompress(payload)
    if kind==3: return payload
    raise ValueError(f"unsupported compression {kind}")


def iter_chunks(region:Path):
    blob=region.read_bytes()
    if len(blob)<8192:
        return
    for slot in range(1024):
        off=slot*4
        sector=int.from_bytes(blob[off:off+3],"big")
        count=blob[off+3]
        if not sector or not count:
            continue
        p=sector*4096
        if p+5>len(blob):
            continue
        length=struct.unpack(">I",blob[p:p+4])[0]
        kind=blob[p+4]
        end=p+4+length
        if length<1 or end>len(blob):
            continue
        raw=decompress(blob[p+5:end],kind)
        yield nbtlib.File.parse(io.BytesIO(raw))


def byte_values(tag):
    return [(int(x)&0xFF) for x in tag]


def nibble_at(arr, index:int)->int:
    b=int(arr[index//2]) & 0xFF
    return (b >> (4 if index & 1 else 0)) & 0x0F


def chunk_level(root):
    if hasattr(root,"get") and root.get("Level") is not None:
        return root["Level"]
    return root


def find_world_root(root:Path)->Path:
    levels=sorted(root.rglob("level.dat"))
    if len(levels)!=1:
        raise RuntimeError(f"expected one level.dat, found {len(levels)}")
    return levels[0].parent


def analyze(world:Path)->dict:
    regions=sorted((world/"region").glob("r.*.*.mca"))
    if not regions:
        raise RuntimeError("no legacy region files under world/region")

    block_counts=Counter()
    interaction_counts=Counter()
    resource_counts=Counter()
    tile_entity_counts=Counter()
    entity_counts=Counter()
    biome_counts=Counter()
    chunk_coords=[]
    height_values=[]
    sections=0
    chunks=0
    command_text_nonempty=0
    sign_text_nonempty=0

    for region in regions:
        for root in iter_chunks(region):
            level=chunk_level(root)
            cx=int(plain(level.get("xPos",0)))
            cz=int(plain(level.get("zPos",0)))
            chunk_coords.append((cx,cz))
            chunks+=1

            hm=level.get("HeightMap")
            if hm is not None:
                height_values.extend(int(x) for x in hm)

            biomes=level.get("Biomes")
            if biomes is not None:
                for b in byte_values(biomes):
                    biome_counts[b]+=1

            for sec in level.get("Sections",[]):
                blocks=sec.get("Blocks")
                if blocks is None:
                    continue
                sections+=1
                base=byte_values(blocks)
                add=sec.get("Add")
                for i,low in enumerate(base):
                    bid=low
                    if add is not None:
                        bid |= nibble_at(add,i)<<8
                    block_counts[bid]+=1
                    if bid in INTERACTION_IDS:
                        interaction_counts[INTERACTION_IDS[bid]]+=1
                    if bid in REDSTONE_IDS:
                        interaction_counts["redstone_component_total"]+=1
                    for name,ids in RESOURCE_IDS.items():
                        if bid in ids:
                            resource_counts[name]+=1

            for te in level.get("TileEntities",[]):
                tid=str(plain(te.get("id","unknown")))
                tile_entity_counts[tid]+=1
                if tid in {"Control","minecraft:command_block"}:
                    cmd=str(plain(te.get("Command","")))
                    if cmd.strip():
                        command_text_nonempty+=1
                if tid in {"Sign","minecraft:sign"}:
                    vals=[str(plain(te.get(f"Text{i}",""))) for i in range(1,5)]
                    if any(x not in {"",'""'} for x in vals):
                        sign_text_nonempty+=1

            for ent in level.get("Entities",[]):
                entity_counts[str(plain(ent.get("id","unknown")))]+=1

    non_air=sum(v for k,v in block_counts.items() if k!=AIR)
    total=sum(block_counts.values())
    xs=[x for x,_ in chunk_coords]
    zs=[z for _,z in chunk_coords]
    occupied_ids=[k for k,v in block_counts.items() if v and k!=AIR]

    hsummary=None
    if height_values:
        hsummary={
            "min":min(height_values),
            "max":max(height_values),
            "mean":round(sum(height_values)/len(height_values),3),
            "relief":max(height_values)-min(height_values),
            "sample_count":len(height_values),
        }

    return {
        "schema":"supracraft-legacy-anvil-static-analysis/1",
        "analysis_blind":True,
        "human_feedback_labels_loaded":False,
        "world_format":"legacy_anvil_pre_palette",
        "region_file_count":len(regions),
        "chunk_count":chunks,
        "chunk_bounds":{
            "min_x":min(xs) if xs else None, "max_x":max(xs) if xs else None,
            "min_z":min(zs) if zs else None, "max_z":max(zs) if zs else None,
        },
        "section_count":sections,
        "decoded_block_slots":total,
        "non_air_blocks":non_air,
        "non_air_fraction":round(non_air/total,6) if total else None,
        "block_id_diversity_non_air":len(occupied_ids),
        "heightmap":hsummary,
        "top_block_ids":[{"id":int(k),"count":int(v)} for k,v in block_counts.most_common(40)],
        "interaction_block_counts":dict(sorted(interaction_counts.items())),
        "resource_block_counts":dict(sorted(resource_counts.items())),
        "tile_entity_counts":dict(tile_entity_counts.most_common()),
        "entity_counts":dict(entity_counts.most_common(40)),
        "biome_id_counts":dict(biome_counts.most_common()),
        "biome_id_diversity":len(biome_counts),
        "nonempty_command_block_tile_entities":command_text_nonempty,
        "nonempty_sign_tile_entities":sign_text_nonempty,
        "limitations":[
            "Numeric block/biome IDs use the legacy world's own version semantics.",
            "Counts describe saved-world structure, not route legibility, fairness, fun, immersion, or player experience.",
            "No human feedback corpus or qualitative labels are loaded by this analyzer.",
            "HeightMap semantics are preserved as stored and are not treated as modern 26.3 heightmap semantics.",
        ],
    }


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--world-zip",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="legacy-world-") as td:
        root=Path(td)
        with zipfile.ZipFile(args.world_zip) as zf:
            if zf.testzip() is not None:
                raise RuntimeError("source zip failed CRC")
            zf.extractall(root)
        world=find_world_root(root)
        result=analyze(world)

    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
