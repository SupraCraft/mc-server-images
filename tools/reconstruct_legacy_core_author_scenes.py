#!/usr/bin/env python3
"""Read-only CORE 1.8.8 creator-grounded finale and chess forensic source pass.

NO native Minecraft execution. Original commands, selectors, named entities,
inventory, world coordinates, local nodes and storyline text stay ephemeral
inside the previously admitted pinned source-custody cell. The derivative
contains allowlisted aggregate facts, limits and non-promotion flags only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from tools.infer_legacy_core_gameplay_purposes import (
    commands_from_pinned_zip, normalize_command
)
from tools.reconstruct_legacy_core_command_controls import (
    _sha_verified_commands, reconstruct, scoreboard_access, selector_reads
)

SCHEMA="supracraft-core-188-creator-scenes-static/1"
DIRECT_LINK_TYPES={
    "legacy_setblock_redstone_block_direct_command_power",
    "conditional_predecessor_success_dependency",
    "chain_facing_successor_candidate",
}
KNOWN_SCENES=("dr_h_finale","chess_head_hint")
# Terms are publicly attributed story clues, not confidential source strings.
DR_CUE=re.compile(r"(?<!\w)dr[ ._\-]*h(?!\w)",re.I)
CHESS_CUE=re.compile(r"(?<!\w)(chess|checkmate|chessboard)(?!\w)",re.I)
ALLOWED_ENTITY_TYPES={"armorstand","item","blaze","villager","skeleton","player"}
SELECTOR=re.compile(r"@e\[[^\]\r\n]{1,512}\]")
NAME_PARAM=re.compile(r"(?:^|,)\s*name\s*=\s*([^,\]]{1,128})",re.I)
TYPE_PARAM=re.compile(r"(?:^|,)\s*type\s*=\s*([^,\]]{1,128})",re.I)

def safe_entity_type(raw):
    value=(raw or "").lower().split(":")[-1].replace("_","").lstrip("!")
    return value if value in ALLOWED_ENTITY_TYPES else "other_or_unspecified"


def source_selector_signature(raw):
    """Only a canonical, exact entity name-filter signature, private transient."""
    if not isinstance(raw,str):return set()
    out=set()
    for match in SELECTOR.findall(raw):
        body=match[3:-1]
        name=NAME_PARAM.search(body)
        if not name:continue
        key=name.group(1).strip().strip('"')
        if not key:continue
        et=TYPE_PARAM.search(body)
        out.add((key, safe_entity_type(et.group(1) if et else "")))
    return out


def source_command_families(original):
    """Author command categories, not asserted gameplay operation."""
    classes=set()
    raw=original or ""
    verb,parts=normalize_command(raw)
    if verb in {"tellraw","say","title"}:
        classes.add("dialogue")
    if verb=="testfor":
        classes.add("entity_presence_gate")
    if verb=="kill":
        classes.add("entity_kill")
    if verb=="summon" and len(parts)>=2:
        entity=safe_entity_type(parts[1])
        classes.add("summon_"+entity)
    if verb=="particle":
        classes.add("particle_feedback")
        if len(parts)>1 and "smoke" in parts[1].lower():
            classes.add("smoke_hint_candidate")
    if verb in {"setblock","fill","replaceitem","give","summon"}:
        # "skull" and legacy numeric item 397 require contextual parsing.
        # This is source *mention*, not proof of skull item creation.
        if re.search(r"(?i)(?:minecraft:)?(?:skull|skull_item|skull_owner)\b",raw):
            classes.add("skull_token_in_action")
        elif re.search(r"(?i)(?<!\d)397(?=\D|$)",raw):
            classes.add("possible_legacy_skull_numeric_item")
    if verb in {"setblock","fill","clone"}:
        classes.add("world_mutation")
    if verb=="scoreboard":
        classes.add("scoreboard_operation")
    if verb=="execute":
        classes.add("nested_execute")
    if DR_CUE.search(raw):
        classes.add("dr_h_author_text_cue")
    if CHESS_CUE.search(raw):
        classes.add("chess_author_text_cue")
    return classes


def source_exact_join_audit(graph,verified,classes):
    """Only directed graph edges independently attributable to original commands."""
    directed=set()
    rejected=Counter()
    edges=graph.get("edges",{})
    for name in ("command_authored_redstone_edges","command_chain_candidates"):
        for row in edges.get(name,[]):
            if not isinstance(row,dict):continue
            kind=row.get("edge_type")
            if kind not in DIRECT_LINK_TYPES:continue
            a,b=row.get("source"),row.get("target")
            if a not in verified or b not in verified:
                rejected["unqualified_or_noncommand_endpoint"]+=1
                continue
            # Independent decoder already verified authored power exact target
            # in reconstruct(), including command SHA and diode orientation.
            directed.add((a,b,kind))
    forward=defaultdict(set)
    for a,b,kind in directed: forward[a].add(b)
    class_pair_paths=Counter()
    max_depth=16
    # Source-derived graph reachability is not runtime command success.
    for cid,source_classes in classes.items():
        if not ({"dr_h_author_text_cue","chess_author_text_cue",
                 "entity_presence_gate","smoke_hint_candidate",
                 "summon_armorstand"} & source_classes):
            continue
        seen={cid}
        frontier=deque([(cid,0)])
        while frontier:
            node,depth=frontier.popleft()
            if depth>=max_depth:continue
            for dest in forward.get(node,()):
                if dest in seen:continue
                seen.add(dest)
                dc=classes[dest]
                for source_tag,destination_tag,label in (
                    ("entity_presence_gate","skull_token_in_action",
                     "presence_gate_to_skull_action_token"),
                    ("dr_h_author_text_cue","entity_presence_gate",
                     "dr_h_cue_to_presence_gate"),
                    ("entity_presence_gate","dialogue",
                     "presence_gate_to_dialogue"),
                    ("chess_author_text_cue","smoke_hint_candidate",
                     "chess_text_to_smoke_hint"),
                    ("smoke_hint_candidate","summon_armorstand",
                     "smoke_to_armor_stand_spawn"),
                    ("summon_armorstand","skull_token_in_action",
                     "armor_stand_spawn_to_skull_token"),
                ):
                    if source_tag in source_classes and destination_tag in dc:
                        class_pair_paths[label]+=1
                frontier.append((dest,depth+1))
    return {
        "exact_source_directed_command_edge_count":len(directed),
        "source_graph_rejection_counts":dict(sorted(rejected.items())),
        "bounded_source_command_class_join_counts":dict(sorted(class_pair_paths.items())),
        "max_source_command_hops":max_depth,
        "edge_authority":"EXACT_ORIGINAL_AUTHORED_POWER_OR_COMMAND_CHAIN_STATIC",
        "actual_command_execution":"NOT_OBSERVED",
    }


def inspect_saved_scene_chunk(level):
    """Synthetic-testable NBT-only source evidence; no actor identity or location."""
    # Keep synthetic/no-world CI dependency-free; source-custody parser is
    # imported only when opening the pinned original file in its approved cell.
    def plain(v):
        if hasattr(v,"unpack"):
            try: return v.unpack()
            except Exception: pass
        return v
    result=Counter()
    for item in level.get("Entities",[]):
        if safe_entity_type(str(plain(item.get("id",""))))!="armorstand":
            continue
        result["saved_armor_stand_instances"]+=1
        if item.get("CustomName") is not None:
            result["saved_armor_stand_custom_names_redacted"]+=1
        equipment=item.get("Equipment") or item.get("HandItems") or []
        if not isinstance(equipment,(list,tuple)) and type(equipment).__name__ not in {"List","ListTag"}:
            continue
        if len(equipment)>0:
            result["saved_armor_stands_with_equipment_entries"]+=1
        zero=False
        head=False
        for slot in equipment:
            if not hasattr(slot,"get"):continue
            try: count=int(plain(slot.get("Count",0)))
            except (TypeError,ValueError):count=-1
            try: numeric=int(plain(slot.get("id",-1)))
            except (TypeError,ValueError):numeric=-1
            item_id=str(plain(slot.get("id",""))).lower()
            if numeric==397 or item_id.endswith(":skull") or item_id=="skull":
                head=True
                result["saved_armor_stand_skull_equipment_slots"]+=1
                if count==0:
                    zero=True
                    result["saved_armor_stand_zero_count_skull_slots"]+=1
        if head:result["saved_armor_stands_with_skull_equipment"]+=1
        if zero:result["saved_armor_stands_with_zero_count_skull"]+=1
    for te in level.get("TileEntities",[]):
        ident=str(plain(te.get("id",""))).lower()
        if ident in {"skull","minecraft:skull"}:
            result["saved_skull_block_tile_entities"]+=1
        if ident in {"sign","minecraft:sign"}:
            result["saved_signs_author_text_redacted"]+=1
    return result


def audit_actor_inventory(world_zip):
    """Count saved 1.8 armor-stand equipment and skulls without exporting NBT."""
    from tools.analyze_legacy_causal_machinery import (
        iter_chunks,chunk_level,find_world_root,plain
    )
    result=Counter()
    with tempfile.TemporaryDirectory(prefix="core-scene-nbt-custody-") as td:
        base=Path(td)
        with zipfile.ZipFile(world_zip) as arc:
            infos=arc.infolist()
            if len(infos)>10000 or sum(i.file_size for i in infos)>250*1024*1024:
                raise ValueError("unbounded original world archive")
            if arc.testzip() is not None:
                raise ValueError("source ZIP CRC mismatch")
            for item in infos:
                p=PurePosixPath(item.filename)
                if p.is_absolute() or ".." in p.parts:
                    raise ValueError("unsafe original source path")
            arc.extractall(base)
        world=find_world_root(base)
        for region in sorted((world/"region").glob("r.*.*.mca")):
            for raw in iter_chunks(region):
                level=chunk_level(raw)
                result.update(inspect_saved_scene_chunk(level))
    return dict(sorted(result.items()))


def analyze(graph,original,nbt=None):
    full=reconstruct(graph,original)
    verified,expected,bad=_sha_verified_commands(graph,original)
    if bad or expected!=len(verified):
        raise ValueError("unmatched source command SHA")
    classes={}
    actors=defaultdict(set)
    commands=Counter()
    scenes=Counter()
    selectors_by_role=defaultdict(set)
    for cid,(node,raw,parts) in verified.items():
        cc=source_command_families(raw)
        classes[cid]=cc
        for name in cc:
            commands[name]+=1
        selector=source_selector_signature(raw)
        if "entity_presence_gate" in cc:
            selectors_by_role["presence_gate"].update(selector)
        if "entity_kill" in cc:
            selectors_by_role["kill"].update(selector)
        for sig in selector:
            actors[sig].add(cid)
        if "dr_h_author_text_cue" in cc: scenes["dr_h_cue_commands"]+=1
        if "chess_author_text_cue" in cc:scenes["chess_cue_commands"]+=1
    common=selectors_by_role["presence_gate"] & selectors_by_role["kill"]
    exact=source_exact_join_audit(graph,verified,classes)
    # Two commands using the same named selector does not mean their operations
    # execute in the same scene or resolve to the same living entity.
    return {
        "schema":SCHEMA,
        "source_verification":"EVERY_ORIGINAL_COMMAND_SHA_MATCHED",
        "original_commands_sha_verified":len(verified),
        "source_command_family_counts":dict(sorted(commands.items())),
        "creator_story_cue_command_counts":dict(sorted(scenes.items())),
        "entity_named_selector_potential_shared_presence_kill_signatures":len(common),
        "entity_named_selector_signature_total":len(actors),
        "command_static_links":exact,
        "saved_actor_inventory_evidence":nbt or {},
        "dr_h_finale":{
            "creator_intent":"2015_AUTHOR_EXTERNAL_REPORT_ONLY__RELEASE_MATCH_UNKNOWN",
            "presence_dialogue_skull_and_death_chain":"NOT_VERIFIED_BY_AUTHOR_CUE_OR_GLOBAL_COMPONENT_PRESENCE",
            "source_proven_exact_logic":"ONLY_BOUNDED_DIRECTED_COMMAND_EDGES_IF_REPORTED",
            "clock_actual_behavior":"NOT_OBSERVED",
        },
        "chess":{
            "creator_intent":"2015_AUTHOR_EXTERNAL_REPORT_ONLY__RELEASE_MATCH_UNKNOWN",
            "head_armorstand_and_smoke_puzzle":"NOT_VERIFIED_BY_GLOBAL_COMPONENT_PRESENCE",
            "saved_armor_stand_items":"SOURCE_NBT_SNAPSHOT_NOT_ACTUATION",
            "player_hint_activation":"NOT_OBSERVED",
        },
        "reconstruction_scope":"SOURCE_STATIC_MULTI_CHANNEL_NOT_CREATOR_VERSION_MATCHED",
        "original_java_188_native":"NOT_RUN",
        "modern_minecraft_263_parity":"NOT_RUN",
        "gameplay_promoted":False,
        "limits":[
            "Matching author story terms is evidence of authored dialogue, not a valid 1.8.8 causal edge.",
            "Names and selector equality do not prove that the same actor or exact player slot is alive/selected at runtime.",
            "Global skull, particle, armor stand and scoreboard counts do not prove a chess or ending scene.",
            "Only SHA-qualified command and typed graph edges are eligible for source static joins.",
            "Mechanics may exist via physical/Redstone/inventory/AI behavior absent author commands.",
            "Creator's published later v1.4.1 behavior cannot be projected into pinned v1.4 without version parity.",
            "No source coordinates, raw instructions, items, player text, entity identities or per-scene reversible identifiers leave custody.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--graph",type=Path,required=True)
    p.add_argument("--source-zip",type=Path,required=True)
    p.add_argument("--expected-source-sha256",required=True)
    p.add_argument("--expected-graph-sha256",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise SystemExit("refuse overwrite")
    zipped=a.source_zip.read_bytes()
    graphbytes=a.graph.read_bytes()
    if (hashlib.sha256(zipped).hexdigest()!=a.expected_source_sha256 or
        hashlib.sha256(graphbytes).hexdigest()!=a.expected_graph_sha256):
        raise SystemExit("source pin/graph pin violation")
    graph=json.loads(graphbytes)
    if graph.get("schema")!="supracraft-legacy-causal-machinery/1":
        raise SystemExit("unaccepted original source graph schema")
    raw=commands_from_pinned_zip(a.source_zip,graph)
    result=analyze(graph,raw,audit_actor_inventory(a.source_zip))
    result["source_world_sha256"]=a.expected_source_sha256
    result["source_graph_sha256"]=a.expected_graph_sha256
    serialized=json.dumps(result,indent=2,sort_keys=True)+"\n"
    for forbidden in ('"node_id"','"position"','"target_position"','"command"',
                      '"raw"','"selector"','"objective"','"value"','"CustomName"',
                      'original-world.zip'):
        if forbidden in serialized:
            raise SystemExit("original source escape detected")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(serialized,encoding="utf-8")
    print("CORE_CREATOR_FINALE_CHESS_SOURCE_ONLY",json.dumps({
        "source_commands":result["original_commands_sha_verified"],
        "creator_cues":result["creator_story_cue_command_counts"],
        "command_classes":result["source_command_family_counts"],
        "exact_static_links":result["command_static_links"]["bounded_source_command_class_join_counts"],
        "saved_actor_inventory":result["saved_actor_inventory_evidence"],
        "native":"NOT_RUN",
    },sort_keys=True))


if __name__=="__main__":
    main()
