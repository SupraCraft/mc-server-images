#!/usr/bin/env python3
"""Privacy-safe structural census for modern Minecraft Java region files.

This analyzer recovers block-family, block-entity, and non-player entity counts
from modern paletted Anvil saves. It deliberately does not retain coordinates,
command strings, sign/book text, container contents, UUIDs, names, or other
payloads from third-party worlds.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import math
import struct
import zlib
from collections import Counter
from pathlib import Path

import nbtlib


FAMILY_RULES = {
    "electrical_redstone": {
        "minecraft:redstone_wire","minecraft:redstone_block",
        "minecraft:redstone_torch","minecraft:redstone_wall_torch",
        "minecraft:repeater","minecraft:comparator","minecraft:lever",
        "minecraft:observer","minecraft:target","minecraft:daylight_detector",
        "minecraft:tripwire","minecraft:tripwire_hook",
        "minecraft:sculk_sensor","minecraft:calibrated_sculk_sensor",
    },
    "mechanical_geometry": {
        "minecraft:piston","minecraft:sticky_piston","minecraft:moving_piston",
        "minecraft:piston_head",
    },
    "programmable_control": {
        "minecraft:command_block","minecraft:repeating_command_block",
        "minecraft:chain_command_block","minecraft:structure_block",
        "minecraft:jigsaw",
    },
    "inventory_transport": {
        "minecraft:chest","minecraft:trapped_chest","minecraft:barrel",
        "minecraft:hopper","minecraft:dropper","minecraft:dispenser",
        "minecraft:ender_chest","minecraft:shulker_box",
        "minecraft:white_shulker_box","minecraft:orange_shulker_box",
        "minecraft:magenta_shulker_box","minecraft:light_blue_shulker_box",
        "minecraft:yellow_shulker_box","minecraft:lime_shulker_box",
        "minecraft:pink_shulker_box","minecraft:gray_shulker_box",
        "minecraft:light_gray_shulker_box","minecraft:cyan_shulker_box",
        "minecraft:purple_shulker_box","minecraft:blue_shulker_box",
        "minecraft:brown_shulker_box","minecraft:green_shulker_box",
        "minecraft:red_shulker_box","minecraft:black_shulker_box",
    },
    "transformation_production": {
        "minecraft:crafting_table","minecraft:crafter",
        "minecraft:furnace","minecraft:blast_furnace","minecraft:smoker",
        "minecraft:brewing_stand","minecraft:enchanting_table",
        "minecraft:smithing_table","minecraft:anvil","minecraft:chipped_anvil",
        "minecraft:damaged_anvil","minecraft:grindstone",
        "minecraft:stonecutter","minecraft:loom","minecraft:cartography_table",
        "minecraft:composter",
    },
    "artifact_observation": {
        "minecraft:jukebox","minecraft:note_block","minecraft:lectern",
        "minecraft:decorated_pot","minecraft:bell","minecraft:redstone_lamp",
    },
}

BUTTON_SUFFIXES=("_button",)
PRESSURE_SUFFIXES=("_pressure_plate",)
DOOR_SUFFIXES=("_door",)
TRAPDOOR_SUFFIXES=("_trapdoor",)
GATE_SUFFIXES=("_fence_gate",)
SIGN_SUFFIXES=("_sign","_wall_sign","_hanging_sign","_wall_hanging_sign")
BANNER_SUFFIXES=("_banner","_wall_banner")
SAPLING_SUFFIXES=("_sapling",)
CROP_EXACT={
    "minecraft:wheat","minecraft:carrots","minecraft:potatoes",
    "minecraft:beetroots","minecraft:nether_wart",
    "minecraft:melon_stem","minecraft:attached_melon_stem",
    "minecraft:pumpkin_stem","minecraft:attached_pumpkin_stem",
    "minecraft:cocoa","minecraft:sweet_berry_bush","minecraft:torchflower_crop",
    "minecraft:pitcher_crop",
}
MUSHROOM_EXACT={
    "minecraft:red_mushroom","minecraft:brown_mushroom",
    "minecraft:red_mushroom_block","minecraft:brown_mushroom_block",
    "minecraft:mushroom_stem","minecraft:mycelium",
}


def decompress(payload: bytes, kind: int) -> bytes:
    kind = kind & 0x7F
    if kind == 1:
        return gzip.decompress(payload)
    if kind == 2:
        return zlib.decompress(payload)
    if kind == 3:
        return payload
    raise ValueError(f"unsupported Anvil compression type {kind}")


def iter_region_chunks(path: Path):
    blob=path.read_bytes()
    if len(blob)<8192:
        return
    for slot in range(1024):
        off=slot*4
        sector=int.from_bytes(blob[off:off+3],"big")
        count=blob[off+3]
        if not sector or not count:
            continue
        pos=sector*4096
        if pos+5>len(blob):
            continue
        length=struct.unpack(">I",blob[pos:pos+4])[0]
        compression=blob[pos+4]
        external=bool(compression & 0x80)
        if external:
            # External .mcc chunks are intentionally unsupported in v1 rather
            # than guessed or silently skipped as decoded.
            yield {"_external_chunk": True, "_slot": slot}
            continue
        end=pos+4+length
        if length<1 or end>len(blob):
            continue
        raw=decompress(blob[pos+5:end],compression)
        yield nbtlib.File.parse(io.BytesIO(raw))


def palette_name(entry) -> str:
    if isinstance(entry,str):
        return str(entry)
    if hasattr(entry,"get"):
        for key in ("Name","name","id"):
            v=entry.get(key)
            if v is not None:
                return str(v)
    return str(entry)


def decode_palette_counts(container, entries: int=4096, min_bits: int=4) -> Counter:
    palette=container.get("palette",container.get("Palette"))
    if palette is None:
        return Counter()
    names=[palette_name(x) for x in palette]
    if len(names)==1:
        return Counter({names[0]:entries})
    data=container.get("data",container.get("Data"))
    if data is None:
        raise ValueError("palette has multiple entries but no packed data")
    bits=max(min_bits,math.ceil(math.log2(len(names))))
    per=64//bits
    mask=(1<<bits)-1
    longs=[int(x)&((1<<64)-1) for x in data]
    needed=math.ceil(entries/per)
    if len(longs)<needed:
        raise ValueError(
            f"packed palette too short: palette={len(names)} bits={bits} "
            f"need={needed} got={len(longs)}"
        )
    counts=Counter()
    for i in range(entries):
        word=longs[i//per]
        idx=(word>>((i%per)*bits))&mask
        if idx>=len(names):
            raise ValueError(f"palette index {idx} >= {len(names)}")
        counts[names[idx]]+=1
    return counts


def families_for(block: str) -> set[str]:
    out={name for name,blocks in FAMILY_RULES.items() if block in blocks}
    if block.endswith(BUTTON_SUFFIXES) or block.endswith(PRESSURE_SUFFIXES):
        out.add("electrical_redstone")
    if block.endswith(DOOR_SUFFIXES) or block.endswith(TRAPDOOR_SUFFIXES) or block.endswith(GATE_SUFFIXES):
        out.add("mechanical_geometry")
    if block.endswith(SIGN_SUFFIXES) or block.endswith(BANNER_SUFFIXES):
        out.add("artifact_observation")
    if block.endswith(SAPLING_SUFFIXES) or block in CROP_EXACT or block in MUSHROOM_EXACT:
        out.add("biology_ecology")
    if block=="minecraft:farmland":
        out.add("biology_ecology")
    return out


def id_of(value) -> str:
    if hasattr(value,"get"):
        v=value.get("id",value.get("Id"))
        if v is not None:
            return str(v)
    return "unknown"


def inspect_chunk_region(path: Path, accum: dict):
    for root in iter_region_chunks(path):
        if isinstance(root,dict) and root.get("_external_chunk"):
            accum["external_chunk_count"]+=1
            continue
        accum["chunk_count"]+=1
        chunk=root.get("Level",root) if hasattr(root,"get") else root
        sections=chunk.get("sections",chunk.get("Sections",[]))
        for section in sections:
            bs=section.get("block_states",section.get("BlockStates"))
            if not bs or bs.get("palette",bs.get("Palette")) is None:
                continue
            try:
                counts=decode_palette_counts(bs)
            except Exception:
                accum["decode_error_count"]+=1
                continue
            accum["section_count"]+=1
            accum["blocks"].update(counts)
            for block,count in counts.items():
                for fam in families_for(block):
                    accum["families"][fam]+=count

        block_entities=chunk.get(
            "block_entities",
            chunk.get("TileEntities",chunk.get("BlockEntities",[]))
        )
        for be in block_entities:
            bid=id_of(be)
            accum["block_entities"][bid]+=1
            if bid in {
                "minecraft:command_block","minecraft:repeating_command_block",
                "minecraft:chain_command_block","Control"
            }:
                cmd=be.get("Command",be.get("command","")) if hasattr(be,"get") else ""
                if str(cmd).strip():
                    accum["command_block_nonempty"]+=1
            if "sign" in bid:
                accum["sign_block_entity_count"]+=1
            if bid=="minecraft:lectern":
                accum["lectern_block_entity_count"]+=1


def inspect_entity_region(path: Path, accum: dict):
    for root in iter_region_chunks(path):
        if isinstance(root,dict) and root.get("_external_chunk"):
            accum["external_entity_chunk_count"]+=1
            continue
        chunk=root.get("Level",root) if hasattr(root,"get") else root
        entities=chunk.get("Entities",chunk.get("entities",[]))
        for ent in entities:
            eid=id_of(ent)
            if eid=="minecraft:player":
                accum["player_entity_count_ignored"]+=1
                continue
            accum["entities"][eid]+=1


def classify_region(path: Path) -> str:
    parts=set(path.parts)
    if "entities" in parts:
        return "entity"
    if "poi" in parts:
        return "poi"
    return "chunk"


def analyze(world: Path) -> dict:
    accum={
        "blocks":Counter(),
        "families":Counter(),
        "block_entities":Counter(),
        "entities":Counter(),
        "chunk_count":0,
        "section_count":0,
        "decode_error_count":0,
        "external_chunk_count":0,
        "external_entity_chunk_count":0,
        "command_block_nonempty":0,
        "sign_block_entity_count":0,
        "lectern_block_entity_count":0,
        "player_entity_count_ignored":0,
    }
    region_files=[]
    entity_files=[]
    poi_count=0
    for path in sorted(world.rglob("*.mca")):
        kind=classify_region(path)
        if kind=="entity":
            entity_files.append(path)
        elif kind=="poi":
            poi_count+=1
        else:
            region_files.append(path)

    for path in region_files:
        inspect_chunk_region(path,accum)
    for path in entity_files:
        inspect_entity_region(path,accum)

    non_air=sum(v for k,v in accum["blocks"].items() if k!="minecraft:air")
    total=sum(accum["blocks"].values())

    return {
        "schema":"supracraft-external-modern-world-mechanism-census/1",
        "analysis_kind":"derived_structural_census_no_payloads",
        "region_files":{
            "chunk":len(region_files),
            "entity":len(entity_files),
            "poi":poi_count,
        },
        "decoded":{
            "chunks":accum["chunk_count"],
            "sections":accum["section_count"],
            "block_slots":total,
            "non_air_block_slots":non_air,
            "decode_error_count":accum["decode_error_count"],
            "external_chunk_count":accum["external_chunk_count"],
            "external_entity_chunk_count":accum["external_entity_chunk_count"],
        },
        "domain_family_block_counts":dict(accum["families"].most_common()),
        "top_non_air_blocks":[
            {"block":k,"count":v}
            for k,v in accum["blocks"].most_common()
            if k!="minecraft:air"
        ][:80],
        "block_entity_type_counts":dict(accum["block_entities"].most_common()),
        "entity_type_counts":dict(accum["entities"].most_common(80)),
        "privacy_safe_payload_presence_counts":{
            "nonempty_command_block_entities":accum["command_block_nonempty"],
            "sign_block_entities":accum["sign_block_entity_count"],
            "lectern_block_entities":accum["lectern_block_entity_count"],
            "player_entities_ignored":accum["player_entity_count_ignored"],
        },
        "raw_command_text_retained":False,
        "raw_sign_or_book_text_retained":False,
        "coordinates_retained":False,
        "container_contents_retained":False,
        "entity_uuid_or_name_retained":False,
        "limitations":[
            "Counts describe saved structural state, not runtime behavior or reachability.",
            "POI region payloads are counted but not decoded in v1.",
            "External .mcc chunks are reported but not decoded.",
            "Block-state properties are collapsed to block identity in this census.",
            "Player data and player entity payloads are excluded.",
            "No command/sign/book/container payload content is retained.",
        ],
    }


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--world-root",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    result=analyze(args.world_root.resolve())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "region_files":result["region_files"],
        "decoded":result["decoded"],
        "domain_family_block_counts":result["domain_family_block_counts"],
        "top_non_air_blocks":result["top_non_air_blocks"][:40],
        "block_entity_type_counts":result["block_entity_type_counts"],
        "entity_type_counts":result["entity_type_counts"],
        "privacy_safe_payload_presence_counts":result["privacy_safe_payload_presence_counts"],
    },indent=2,sort_keys=True))
    if result["decoded"]["decode_error_count"]:
        raise SystemExit(
            f"mechanism census saw {result['decoded']['decode_error_count']} decode errors"
        )
    return 0


if __name__=="__main__":
    raise SystemExit(main())
