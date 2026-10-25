#!/usr/bin/env python3
"""Whole-CORE original-era command purpose hypotheses; read-only, aggregate-only.

Analyzes EVERY source command block and EVERY typed sensor->command route, not
just previous isolated button trials. Original command text, source coordinates,
target identities and snapshots NEVER cross the source-custody workcell.
All purpose labels are static HYPOTHESES, not observed gameplay semantics.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from tools.rank_legacy_typed_sensor_command_witnesses import _is_typed, rank
from tools.audit_legacy_piston_authored_inputs import _exact_integer_position
from tools.analyze_legacy_causal_machinery import normalize_command, resolve_xyz

SCHEMA = "supracraft-legacy-core-purpose-inference-aggregate/1"
KNOWN_OPS = {"setblock", "fill", "clone", "tp", "teleport", "summon",
             "effect", "give", "clear", "scoreboard", "testfor",
             "testforblock", "execute", "tellraw", "say", "title",
             "playsound", "particle", "kill", "gamemode", "spawnpoint",
             "setworldspawn", "time", "weather", "gamerule", "xp",
             "enchant", "difficulty", "worldborder"}
BY_ACTION = {
    "setblock":"single_block_configuration_candidate",
    "fill":"region_mutation_candidate",
    "clone":"structure_copy_or_reset_candidate",
    "tp":"player_or_entity_relocation_candidate",
    "teleport":"player_or_entity_relocation_candidate",
    "summon":"entity_spawn_candidate",
    "effect":"entity_status_effect_candidate",
    "give":"item_reward_or_provision_candidate",
    "clear":"inventory_reset_or_condition_candidate",
    "scoreboard":"progression_or_game_state_candidate",
    "testfor":"entity_presence_gate_candidate",
    "testforblock":"world_state_gate_candidate",
    "execute":"contextual_command_chain_candidate",
    "tellraw":"player_message_candidate",
    "say":"player_message_candidate",
    "title":"player_message_candidate",
    "playsound":"audio_feedback_candidate",
    "particle":"visual_feedback_candidate",
    "kill":"entity_removal_candidate",
    "gamemode":"player_mode_change_candidate",
    "spawnpoint":"respawn_checkpoint_candidate",
    "setworldspawn":"respawn_checkpoint_candidate",
    "time":"world_time_change_candidate",
    "weather":"world_weather_change_candidate",
    "gamerule":"world_rules_change_candidate",
    "xp":"experience_reward_or_adjustment_candidate",
    "enchant":"equipment_upgrade_candidate",
    "difficulty":"world_difficulty_change_candidate",
    "worldborder":"arena_boundary_candidate",
}
# Deliberately coarse; naming a block does not imply traversal, puzzle or intent.
AIR = {"air", "minecraft:air", "0"}
POWER = {"redstone_block", "minecraft:redstone_block", "152"}
HAZARDS = {"lava", "flowing_lava", "minecraft:lava", "minecraft:flowing_lava", "10", "11",
           "fire", "minecraft:fire", "51", "tnt", "minecraft:tnt", "46"}
WATER = {"water", "flowing_water", "minecraft:water", "minecraft:flowing_water", "8", "9"}
STRUCTURAL = {"stone", "minecraft:stone", "1", "cobblestone", "minecraft:cobblestone", "4",
              "glass", "minecraft:glass", "20", "barrier", "minecraft:barrier", "166",
              "dirt", "minecraft:dirt", "3", "planks", "minecraft:planks", "5",
              "stained_glass", "minecraft:stained_glass", "95", "wool", "minecraft:wool", "35"}


def material_class(token):
    if not isinstance(token, str):
        return "material_unresolved"
    value = token.lower()
    if value in AIR: return "air_removal_candidate"
    if value in POWER: return "redstone_power_source_candidate"
    if value in HAZARDS: return "hazard_or_volatile_block_candidate"
    if value in WATER: return "fluid_placement_candidate"
    if value in STRUCTURAL: return "structural_block_placement_candidate"
    return "other_block_material_unclassified"


def typed_routes(graph):
    """Reconstruct all original typed routes with exact ranker parity."""
    reference = rank(graph)
    byid = {n["node_id"]: n for n in graph["nodes"]}
    groups = defaultdict(set)
    for e in graph["edges"]["direct_redstone_edges"]:
        a, b = byid.get(e.get("source")), byid.get(e.get("target"))
        if not a or not b: continue
        kind = _is_typed(a, b, e)
        if kind:
            groups[kind].add((a["node_id"], b["node_id"]))
    routes = set()
    adjacency = defaultdict(set)
    sinks = defaultdict(set)
    starts = defaultdict(set)
    for a,b in groups["wire_wire"]: adjacency[a].add(b)
    for a,b in groups["wire_command"]: sinks[a].add(b)
    for a,b in groups["sensor_wire"]: starts[a].add(b)
    for a, roots in starts.items():
        depth = {r: 0 for r in roots}
        q = deque(sorted(roots))
        while q:
            now=q.popleft()
            for cmd in sinks[now]:
                routes.add((a,cmd,"wire_path"))
            if depth[now] >= 96: continue
            for nxt in adjacency[now]:
                if nxt not in depth:
                    depth[nxt]=depth[now]+1
                    q.append(nxt)
    for mode in ("button_command_support","plate_command_support"):
        for a,b in groups[mode]:
            routes.add((a,b,"direct_support"))
    count = Counter(("wire_path_" if mode=="wire_path" else "direct_support_")
                    +byid[a]["family"] for a,b,mode in routes)
    if dict(sorted(count.items())) != reference["accepted_sensor_command_path_counts"]:
        raise ValueError("all-route parity with qualified source ranker failed")
    if len(routes) != reference["accepted_path_count"]:
        raise ValueError("all-route total parity failed")
    return sorted(routes), reference


def commands_from_pinned_zip(world_zip, graph):
    """Load exact original tile-entity commands ephemerally, never write them."""
    from tools.analyze_legacy_causal_machinery import (
        iter_chunks, chunk_level, find_world_root, plain,
    )
    expected = {tuple(n["position"]): n for n in graph["nodes"]
                if n["family"] == "command_block"}
    received = {}
    with tempfile.TemporaryDirectory(prefix="core-semantic-source-custody-") as td:
        base = Path(td)
        with zipfile.ZipFile(world_zip) as z:
            infos=z.infolist()
            if len(infos)>10000 or sum(x.file_size for x in infos)>250*1024*1024:
                raise ValueError("source archive exceeds custody bound")
            if z.testzip() is not None:
                raise ValueError("source archive CRC invalid")
            for item in infos:
                p=PurePosixPath(item.filename)
                if p.is_absolute() or ".." in p.parts:
                    raise ValueError("untrusted archive path")
            z.extractall(base)
        world=find_world_root(base)
        for region in sorted((world/"region").glob("r.*.*.mca")):
            for chunk in iter_chunks(region):
                level=chunk_level(chunk)
                for te in level.get("TileEntities", []):
                    try:
                        pos=(int(plain(te["x"])),int(plain(te["y"])),int(plain(te["z"])))
                    except (TypeError, ValueError, KeyError):
                        continue
                    if pos in expected:
                        if pos in received:
                            raise ValueError("ambiguous original command tile entity")
                        received[pos]=str(plain(te.get("Command","")))
    matches = {}
    for pos, n in expected.items():
        original=received.get(pos)
        fingerprint=(n.get("command") or {}).get("sha256")
        valid=(original is not None and isinstance(fingerprint,str) and
               hashlib.sha256(original.encode("utf-8")).hexdigest()==fingerprint)
        matches[n["node_id"]]=original if valid else None
    return matches


def source_intent(graph, raw_byid):
    """Complete coverage of commands and all qualified routes, fail closed."""
    routes, reference = typed_routes(graph)
    nodes={n["node_id"]: n for n in graph["nodes"]}
    expected_commands={k for k,n in nodes.items() if n.get("family")=="command_block"}
    command_families=Counter()
    command_evidence=Counter()
    route_purposes=Counter()
    route_sensor_purposes=Counter()
    route_material=Counter()
    route_inference=Counter()
    route_targets=Counter()
    unverified=Counter()
    decoded={}
    for cid in expected_commands:
        n=nodes[cid]
        raw=raw_byid.get(cid)
        if raw is None:
            unverified["original_command_text_sha_or_tile_missing"]+=1
            decoded[cid]=("unverified_source_command",None,None)
            command_evidence["unverified_original"]+=1
            continue
        verb,parts=normalize_command(raw)
        graph_verb=(n.get("command") or {}).get("verb")
        if verb != (graph_verb or ""):
            unverified["original_command_verb_disagreement"]+=1
            decoded[cid]=("unverified_source_command",None,None)
            command_evidence["unverified_original"]+=1
            continue
        family=BY_ACTION.get(verb,"unknown_or_unclassified_authored_intent")
        if verb not in KNOWN_OPS:
            family="unknown_or_unclassified_authored_intent"
        material=None
        output_point=None
        if verb=="setblock":
            if len(parts)>=5:
                material=material_class(parts[4])
                output=resolve_xyz(parts[1:4],tuple(n["position"]))
                output_point=(_exact_integer_position(list(output))
                              if output is not None else None)
            if output_point is None: unverified["setblock_target_unresolved"]+=1
        elif verb in {"fill","clone"}:
            # Exact region geometry remains static and may be separately audited.
            command_evidence["multi_block_author_syntax"]+=1
        decoded[cid]=(family,material,output_point)
        command_families[family]+=1
        command_evidence["source_fingerprint_matches"]+=1
    for a,b,mode in routes:
        family,material,target=decoded[b]
        sensor=nodes[a]["family"]
        route_purposes[family]+=1
        route_sensor_purposes[sensor+"__"+family]+=1
        if material: route_material[material]+=1
        if family=="unknown_or_unclassified_authored_intent":
            route_inference["undetermined_authored_purpose"]+=1
        elif family=="unverified_source_command":
            route_inference["unverified_original_command"]+=1
        else:
            route_inference["source_syntax_supported_effect_hypothesis_only"]+=1
        if family=="single_block_configuration_candidate":
            route_targets["resolved_single_block_target" if target is not None
                          else "unresolved_single_block_target"]+=1
    # Include other writers outside the 90 qualified sensor routes; the
    # whole-map setblock command population is relevant to reset/state logic.
    source_writers=defaultdict(list)
    for cid,(fam,mat,tgt) in decoded.items():
        if fam=="single_block_configuration_candidate" and tgt is not None:
            source_writers[tgt].append((cid,mat))
    shared_targets={t:w for t,w in source_writers.items() if len(w)>1}
    target_patterns=Counter()
    for writers in shared_targets.values():
        materials={m for _,m in writers}
        if "redstone_power_source_candidate" in materials and "air_removal_candidate" in materials:
            target_patterns["power_on_off_or_reset_hypothesis"]+=1
        elif "air_removal_candidate" in materials and len(materials)>1:
            target_patterns["place_remove_or_reset_hypothesis"]+=1
        elif len(materials)>1:
            target_patterns["multi_state_reconfiguration_hypothesis"]+=1
        else:
            target_patterns["same_class_multi_writer_unknown_intent"]+=1
    route_shared=0
    for a,b,mode in routes:
        fam,mat,tgt=decoded[b]
        if fam=="single_block_configuration_candidate" and tgt in shared_targets:
            route_shared+=1
    if sum(route_purposes.values())!=reference["accepted_path_count"]:
        raise ValueError("source intent failed total coverage check")
    if sum(command_families.values())+unverified["original_command_text_sha_or_tile_missing"]+unverified["original_command_verb_disagreement"]!=len(expected_commands):
        raise ValueError("original command census coverage failed")
    return {
        "schema":SCHEMA,
        "evidence_class":"SOURCE_REVIEW_INFERRED_PURPOSE_NOT_NATIVE_EXECUTION",
        "scope":"EVERY_ORIGINAL_COMMAND_BLOCK_AND_EVERY_QUALIFIED_SENSOR_COMMAND_ROUTE",
        "original_command_block_count":len(expected_commands),
        "original_commands_fingerprint_matched":command_evidence["source_fingerprint_matches"],
        "original_command_purpose_candidate_counts":dict(sorted(command_families.items())),
        "original_command_observation_counts":dict(sorted(command_evidence.items())),
        "directed_source_witness_count":len(routes),
        "distinct_reached_original_command_blocks":len({b for a,b,mode in routes}),
        "distinct_source_sensors":len({a for a,b,mode in routes}),
        "route_purpose_hypothesis_counts":dict(sorted(route_purposes.items())),
        "route_sensor_purpose_hypothesis_counts":dict(sorted(route_sensor_purposes.items())),
        "setblock_source_material_class_route_counts":dict(sorted(route_material.items())),
        "route_inference_strength_counts":dict(sorted(route_inference.items())),
        "route_setblock_target_status_counts":dict(sorted(route_targets.items())),
        "all_source_setblock_shared_target_group_count":len(shared_targets),
        "shared_target_source_hypothesis_counts":dict(sorted(target_patterns.items())),
        "qualified_routes_to_shared_setblock_targets":route_shared,
        "unresolved_source_analysis_counts":dict(sorted(unverified.items())),
        "runtime_source_actuation":"NOT_RUN",
        "runtime_authored_command_execution":"NOT_OBSERVED",
        "runtime_target_effect":"NOT_OBSERVED",
        "original_player_intent":"NOT_PROVEN",
        "causal_exclusivity":"NOT_PROVEN",
        "minecraft_26_3_equivalence":"NOT_RUN",
        "gameplay_primitive_promoted":False,
        "interpretation_limits":[
            "Semantic labels describe possible functions of SOURCE-AUTHORED COMMAND SYNTAX, not proven gameplay.",
            "Shared target writers can implement toggles, resets or redundancy; exact behavior and intent unresolved.",
            "Typed source Redstone ports cannot show powered state, actual command firing or completed effects.",
            "No map locations, authored messages, original commands or original witness identity exported.",
            "Nested execute contexts, external triggers, command chains, solid conduction and runtime events remain unresolved."
        ]
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",type=Path,required=True)
    ap.add_argument("--source-zip",type=Path,required=True)
    ap.add_argument("--expected-graph-sha256",required=True)
    ap.add_argument("--expected-source-sha256",required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    if args.output.exists():
        raise SystemExit("refuse overwrite")
    graph_data=args.graph.read_bytes()
    source_data=args.source_zip.read_bytes()
    gh=hashlib.sha256(graph_data).hexdigest()
    sh=hashlib.sha256(source_data).hexdigest()
    if gh!=args.expected_graph_sha256 or sh!=args.expected_source_sha256:
        raise SystemExit("source/graph identity mismatch")
    graph=json.loads(graph_data)
    raw=commands_from_pinned_zip(args.source_zip,graph)
    result=source_intent(graph,raw)
    result["source_world_sha256"]=sh
    result["source_graph_sha256"]=gh
    text=json.dumps(result,sort_keys=True,indent=2)+"\n"
    for secret in ('"node_id"','"position"','"target_position"','"command"','"sha256":','"raw"','"xPos"'):
        if secret in text: raise SystemExit("source custody/privacy egress refused")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(text,encoding="utf-8")
    print("CORE_PURPOSE_HYPOTHESES_SOURCE_ONLY",json.dumps({
        "qualified_routes":result["directed_source_witness_count"],
        "original_command_blocks":result["original_command_block_count"],
        "verified_command_blocks":result["original_commands_fingerprint_matched"],
        "hypotheses":result["route_purpose_hypothesis_counts"],
        "material_classes":result["setblock_source_material_class_route_counts"],
        "shared_target_groups":result["all_source_setblock_shared_target_group_count"],
        "shared_target_hypotheses":result["shared_target_source_hypothesis_counts"],
        "native":"NOT_RUN"
    },sort_keys=True))


if __name__=="__main__":
    main()
