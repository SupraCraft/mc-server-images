#!/usr/bin/env python3
"""Whole-world CORE 1.8.8 alternative gameplay implementation channels.

All source blocks, tile entities, and entities are read INSIDE source custody.
Public output: allowlisted family/channel aggregate counters only. No entity
names, NBT, item names, coordinates, authored content or original source.
No inference of native causality from co-presence or saved state.
"""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

SCHEMA="supracraft-legacy-core-gameplay-channel-census/1"
# Numeric IDs are 1.8.8 original-era blocks, not 26.3 IDs. Overlaps deliberate.
CHANNEL_IDS={
    "mechanical_kinematics":{23,27,28,29,33,46,64,65,66,71,96,107,154,157,158,165,167,193,194,195,196,197},
    "electrical_signal_logic":{27,28,55,69,70,72,75,76,77,93,94,123,124,131,132,137,143,146,147,148,149,150,151,152,157,178},
    "inventory_storage_transport":{23,54,61,62,84,117,118,130,138,146,154,158},
    "magical_potions_enchanting":{52,90,116,117,118,119,120,122,130,138},
    "entities_actor_spawning":{52,23,158,90,119},
    "environmental_hazard_physics":{8,9,10,11,12,13,30,46,51,59,60,79,81,88,106,165,174},
    "traversal_navigation":{8,9,27,28,29,30,33,64,65,66,70,71,72,79,88,90,96,106,107,119,120,157,165,167,174,193,194,195,196,197},
    "presentation_signals_and_art":{25,63,68,84,95,123,124,137,176,177},
    "control_commands":{137},  # 1.8.8 original; 210/211 did not yet exist
    "multiplayer_progression_state":{26,54,90,119,120,137,138,146},
}
CHANNELS=tuple(sorted(CHANNEL_IDS))
ENTITY_FAMILIES={
    "item":"inventory_storage_transport",
    "itemframe":"presentation_signals_and_art",
    "painting":"presentation_signals_and_art",
    "armorstand":"entities_actor_spawning",
    "villager":"entities_actor_spawning",
    "witch":"magical_potions_enchanting",
    "thrownpotion":"magical_potions_enchanting",
    "endercrystal":"magical_potions_enchanting",
    "fireball":"environmental_hazard_physics",
    "smallfireball":"environmental_hazard_physics",
    "primedtnt":"environmental_hazard_physics",
    "minecart":"mechanical_kinematics",
    "minecartchest":"inventory_storage_transport",
    "minecarthopper":"inventory_storage_transport",
    "minecartfurnace":"mechanical_kinematics",
    "boat":"traversal_navigation",
    "arrow":"entities_actor_spawning",
}
TILE_FAMILIES={
    "chest":"inventory_storage_transport",
    "trappedchest":"inventory_storage_transport",
    "enderchest":"inventory_storage_transport",
    "hopper":"inventory_storage_transport",
    "dropper":"inventory_storage_transport",
    "dispenser":"inventory_storage_transport",
    "furnace":"inventory_storage_transport",
    "brewingstand":"magical_potions_enchanting",
    "beacon":"magical_potions_enchanting",
    "mobspawner":"entities_actor_spawning",
    "sign":"presentation_signals_and_art",
    "recordplayer":"presentation_signals_and_art",
    "noteblock":"presentation_signals_and_art",
    "note":"presentation_signals_and_art",
    "banner":"presentation_signals_and_art",
    "skull":"presentation_signals_and_art",
    "commandblock":"control_commands",
    "comparator":"electrical_signal_logic",
    "enchanttable":"magical_potions_enchanting",
}
# No arbitrary names from source ever appear in public keys.
def allow_family(raw, known):
    if not isinstance(raw,str):
        return "unclassified"
    token=raw.lower().split(":")[-1].replace("_","").replace(" ","")
    return token if token in known else "unclassified"


def classify_blocks(block_ids):
    """Counts per known implementation channel; overlapping categories expected."""
    evidence=Counter()
    nonair=0
    uncategorized=0
    for raw in block_ids:
        bid=int(raw)
        if bid==0:
            continue
        nonair+=1
        channels=[c for c,ids in CHANNEL_IDS.items() if bid in ids]
        if not channels:
            uncategorized+=1
        for channel in channels:
            evidence[channel]+=1
    return evidence,nonair,uncategorized


def inspect_tiles(tile_entities):
    counter=Counter()
    channels=Counter()
    for te in tile_entities:
        ident=allow_family(str(te.get("id","")) if te.get("id") is not None else "",TILE_FAMILIES)
        counter["tile_"+ident]+=1
        if ident in TILE_FAMILIES: channels[TILE_FAMILIES[ident]]+=1
        items=te.get("Items") or []
        if isinstance(items,list) or type(items).__name__ in ("List","ListTag"):
            counter["item_stacks"]+=len(items)
            for item in items:
                if not hasattr(item,"get"): continue
                tag=item.get("tag") or {}
                if hasattr(tag,"get"):
                    if tag.get("ench") is not None or tag.get("StoredEnchantments") is not None:
                        counter["enchanted_or_enchantment_book_stacks"]+=1
                        channels["magical_potions_enchanting"]+=1
                    if tag.get("Potion") is not None or tag.get("CustomPotionEffects") is not None:
                        counter["potion_state_stacks"]+=1
                        channels["magical_potions_enchanting"]+=1
                    if tag.get("pages") is not None:
                        counter["books_with_written_pages"]+=1
                        channels["presentation_signals_and_art"]+=1
                numeric=item.get("id")
                try:
                    numeric=int(numeric)
                except (TypeError,ValueError):
                    numeric=-1
                if numeric==373:
                    counter["legacy_potion_stacks"]+=1
                    channels["magical_potions_enchanting"]+=1
                elif numeric==403:
                    counter["enchanted_book_stacks"]+=1
                    channels["magical_potions_enchanting"]+=1
                elif numeric==387:
                    counter["written_book_stacks"]+=1
                    channels["presentation_signals_and_art"]+=1
        if ident=="mobspawner":
            counter["spawner_nbt_instances"]+=1
        if ident=="sign":
            counter["sign_text_sources_redacted"]+=1
    return counter,channels


def inspect_entities(entities):
    counter=Counter()
    channels=Counter()
    for e in entities:
        ident=allow_family(str(e.get("id","")) if e.get("id") is not None else "",ENTITY_FAMILIES)
        counter["entity_"+ident]+=1
        if ident in ENTITY_FAMILIES:
            channels[ENTITY_FAMILIES[ident]]+=1
        if e.get("CustomName") is not None:
            counter["entities_with_custom_name_redacted"]+=1
        if e.get("ActiveEffects") is not None:
            counter["entities_with_active_effects"]+=1
            channels["magical_potions_enchanting"]+=1
        if e.get("Offers") is not None:
            counter["entities_with_trade_offers"]+=1
            channels["inventory_storage_transport"]+=1
        if e.get("Equipment") is not None or e.get("HandItems") is not None:
            counter["entities_with_equipment_metadata"]+=1
        if e.get("Riding") is not None or e.get("Passengers") is not None:
            counter["entities_with_riding_or_passenger_links"]+=1
    return counter,channels


def inventory_channels_snapshot(world_zip:Path):
    from tools.analyze_legacy_causal_machinery import (
        iter_chunks,chunk_level,find_world_root,byte_values,nibble_at,plain
    )
    blocks=Counter()
    tiles=Counter()
    entities=Counter()
    occupancy=Counter()
    known_channel_chunks=Counter()
    missing_data=Counter()
    total_chunks=0
    with tempfile.TemporaryDirectory(prefix="core-full-channel-custody-") as td:
        base=Path(td)
        with zipfile.ZipFile(world_zip) as archive:
            infos=archive.infolist()
            if len(infos)>10000 or sum(i.file_size for i in infos)>250*1024*1024:
                raise ValueError("source exceeds bounded ZIP custody")
            if archive.testzip() is not None:
                raise ValueError("invalid original ZIP CRC")
            for item in infos:
                p=PurePosixPath(item.filename)
                if p.is_absolute() or ".." in p.parts:
                    raise ValueError("unsafe source ZIP member")
            archive.extractall(base)
        world=find_world_root(base)
        for region in sorted((world/"region").glob("r.*.*.mca")):
            for raw in iter_chunks(region):
                level=chunk_level(raw)
                total_chunks+=1
                seen=set()
                for sec in level.get("Sections",[]):
                    array=sec.get("Blocks")
                    if array is None:
                        missing_data["missing_section_block_array"]+=1
                        continue
                    base_values=byte_values(array)
                    if len(base_values)!=4096:
                        raise ValueError("malformed 1.8.8 section length")
                    add=sec.get("Add")
                    if add is not None:
                        if len(add)!=2048: raise ValueError("invalid Add high-nibble array")
                        all_ids=(v|(nibble_at(add,i)<<8) for i,v in enumerate(base_values))
                    else:
                        all_ids=base_values
                    c,nonair,other=classify_blocks(all_ids)
                    blocks.update(c)
                    occupancy["nonair_saved_block_cells"]+=nonair
                    occupancy["not_classified_nonair_cells"]+=other
                    seen.update(k for k,v in c.items() if v)
                tc,tchannels=inspect_tiles(level.get("TileEntities",[]))
                ec,echannels=inspect_entities(level.get("Entities",[]))
                tiles.update(tc)
                entities.update(ec)
                seen.update(c for c,n in tchannels.items() if n)
                seen.update(c for c,n in echannels.items() if n)
                for channel in seen: known_channel_chunks[channel]+=1
                for a,b in combinations(sorted(seen),2):
                    occupancy["shared_chunk_"+a+"__"+b]+=1
    return {
        "schema":SCHEMA,
        "evidence_class":"SAVED_BLOCK_NBT_SOURCE_CENSUS_NOT_CAUSALITY",
        "scope":"ALL_AVAILABLE_ORIGINAL_1_8_8_REGION_CHUNKS_SECTIONS_TILES_ENTITIES",
        "source_chunk_count":total_chunks,
        "channel_saved_block_instance_counts":dict(sorted(blocks.items())),
        "channel_present_chunk_counts":dict(sorted(known_channel_chunks.items())),
        "channel_status":{
            c:("SAVED_SOURCE_PRESENT" if c in known_channel_chunks else
               "NOT_OBSERVED_IN_CENSUSED_SAVED_SOURCES__OTHER_IMPLEMENTATIONS_UNRESOLVED")
            for c in CHANNELS},
        "allowlisted_tile_evidence_counts":dict(sorted(tiles.items())),
        "allowlisted_entity_evidence_counts":dict(sorted(entities.items())),
        "saved_block_coverage_counts":dict(sorted((k,v) for k,v in occupancy.items()
                                                  if not k.startswith("shared_chunk_"))),
        "cross_channel_chunk_co_presence_counts":dict(sorted((k,v) for k,v in occupancy.items()
                                                             if k.startswith("shared_chunk_"))),
        "unresolved_source_decoding_counts":dict(sorted(missing_data.items())),
        "runtime_physical_motion":"NOT_OBSERVED",
        "runtime_power_transfer":"NOT_OBSERVED",
        "runtime_item_transfers":"NOT_OBSERVED",
        "runtime_potions_magic":"NOT_OBSERVED",
        "runtime_actor_behavior":"NOT_OBSERVED",
        "player_gameplay_purpose":"INFERRED_ONLY",
        "modern_26_3_parity":"NOT_RUN",
        "gameplay_promoted":False,
        "limitations":[
            "Overlapping channel counts are not disjoint mechanisms.",
            "Same-chunk co-presence is not causal wiring, inventory transfer, player intent or functional behavior.",
            "Saved block/named tile/entity state excludes dynamic unrecorded transient gameplay and external plugins.",
            "Magic is an interpretive channel for potion, enchant, beacon, portal and effect systems, not proof of authored spells.",
            "Original 1.8.8 does not have modern datapack, advancement or post-1.8 command-block features.",
            "World files, text, NBT, coordinates, inventory contents and entity identities never leave ephemeral custody."
        ]
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--source-zip",type=Path,required=True)
    ap.add_argument("--graph",type=Path,required=True)
    ap.add_argument("--expected-source-sha256",required=True)
    ap.add_argument("--expected-graph-sha256",required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():raise SystemExit("refuse overwrite")
    z=args.source_zip.read_bytes()
    g=args.graph.read_bytes()
    if hashlib.sha256(z).hexdigest()!=args.expected_source_sha256 or hashlib.sha256(g).hexdigest()!=args.expected_graph_sha256:
        raise SystemExit("original source or causal graph digest mismatch")
    graph=json.loads(g)
    if graph.get("schema")!="supracraft-legacy-causal-machinery/1":
        raise SystemExit("unaccepted source graph")
    result=inventory_channels_snapshot(args.source_zip)
    result["source_world_sha256"]=args.expected_source_sha256
    result["source_graph_sha256"]=args.expected_graph_sha256
    text=json.dumps(result,sort_keys=True,indent=2)+"\n"
    for forbidden in ('"node_id"','"position"','"command"','"target_position"',
                      '"CustomName"','"Items"','"id"','original-world.zip'):
        if forbidden in text:raise SystemExit("original source privacy guard failed")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(text,encoding="utf-8")
    print("CORE_ALL_GAMEPLAY_CHANNELS_SOURCE_ONLY",json.dumps({
        "chunks":result["source_chunk_count"],
        "present_channels":[k for k,v in result["channel_status"].items() if v=="SAVED_SOURCE_PRESENT"],
        "source_channel_block_counts":result["channel_saved_block_instance_counts"],
        "tiles":result["allowlisted_tile_evidence_counts"],
        "entities":result["allowlisted_entity_evidence_counts"],
        "native":"NOT_RUN"},sort_keys=True))

if __name__=="__main__":
    main()
