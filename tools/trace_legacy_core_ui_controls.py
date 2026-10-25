#!/usr/bin/env python3
"""CORE original-era source-only clickable controller downstream reconstruction.

Original command bodies, original coordinates and source authored strings are
never emitted. This is a structural/source syntax trace, NOT native runtime.
The pinned original and graph are accessed only in the previously qualified
read-only source custody workflow.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path

from tools.infer_legacy_core_gameplay_purposes import commands_from_pinned_zip
from tools.reconstruct_legacy_core_command_controls import (
    _sha_verified_commands, _static_absolute_point,
    click_controls, material_class, normalize_command, reconstruct
)

SCHEMA="supracraft-core-188-click-control-slices-aggregate/1"
NEIGHBORS=((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))
POWER_MATERIAL="redstone_power_source_candidate"
AUTHOR_RESET="air_removal_candidate"
ALLOWED_VERBS={
    "setblock","fill","clone","testfor","testforblock","execute",
    "summon","kill","effect","gamemode","tp","teleport","give","clear",
    "replaceitem","scoreboard","tellraw","say","title","particle",
    "playsound","weather","time","gamerule","spawnpoint"
}
ALLOWED_ENTITIES={"blaze","armorstand","item","skeleton","villager"}


def _position(node):
    p=node.get("position")
    if not isinstance(p,list) or len(p)!=3 or any(type(x) is not int for x in p):
        raise ValueError("bad source node position")
    if node.get("node_id")!=",".join(map(str,p)):
        raise ValueError("forged source node identity")
    return tuple(p)


def _material_command(parts):
    return material_class(parts[4]) if len(parts)>=5 and parts[0]=="setblock" else None


def _entity_action(parts):
    if not parts or parts[0]!="summon" or len(parts)<2: return None
    name=parts[1].lower().split(":")[-1].replace("_","")
    return name if name in ALLOWED_ENTITIES else "other"


def _safe_verb(parts):
    v=parts[0] if parts else ""
    return v if v in ALLOWED_VERBS else "unknown_or_invalid"


def diode_output_candidates(graph,pos,verified,diode_ids):
    """Strongly oriented source geometry, weaker physical propagation hypothesis.

    Requires a *recorded* source-facing output edge, then exact typed dust links.
    Horizontal dust joins do not have a proved runtime propagation direction.
    Never promote these results to proven cause, native actuation or puzzle.
    """
    from tools.rank_legacy_typed_sensor_command_witnesses import _is_typed
    byid={n["node_id"]:n for n in graph["nodes"]}
    oriented=set()
    for e in graph.get("edges",{}).get("oriented_signal_candidates",[]):
        if e.get("edge_type")=="oriented_front_output_candidate":
            oriented.add((e.get("source"),e.get("target")))
    wires=defaultdict(set)
    sinks=defaultdict(set)
    for e in graph.get("edges",{}).get("direct_redstone_edges",[]):
        a,b=e.get("source"),e.get("target")
        if a not in byid or b not in byid:continue
        kind=_is_typed(byid[a],byid[b],e)
        if kind=="wire_wire": wires[a].add(b)
        if kind=="wire_command" and b in verified:sinks[a].add(b)
    seen_commands=set()
    port_classes=Counter()
    max_wire_hops=0
    for ident in diode_ids:
        n=byid[ident]
        facing=(n.get("metadata_semantics") or {}).get("facing_vector")
        q=tuple(n["position"])
        if not (isinstance(facing,list) and len(facing)==3 and
                all(type(x) is int for x in facing)):
            raise ValueError("diode without signed original facing")
        front=tuple(q[i]-facing[i] for i in range(3))
        downstream=pos.get(front)
        if downstream is None:
            port_classes["front_without_named_graph_node"]+=1
            continue
        if (ident,downstream["node_id"]) not in oriented:
            # Don't invent missing source-backed edge even if geometry happens
            # to match a neighboring coordinate.
            port_classes["front_missing_recorded_oriented_edge"]+=1
            continue
        family=downstream["family"]
        if family=="command_block" and downstream["node_id"] in verified:
            seen_commands.add(downstream["node_id"])
            port_classes["front_adjacent_command_candidate"]+=1
        elif family=="redstone_wire":
            port_classes["front_wire_candidate"]+=1
            q=deque([(downstream["node_id"],0)])
            visited={downstream["node_id"]}
            while q:
                wire,depth=q.popleft()
                seen_commands.update(sinks.get(wire,set()))
                max_wire_hops=max(max_wire_hops,depth)
                if depth>=96: continue
                for nxt in wires.get(wire,set()):
                    if nxt not in visited:
                        visited.add(nxt)
                        q.append((nxt,depth+1))
        else:
            port_classes["other_front_component_not_followed"]+=1
            allow={"repeater_on","repeater_off","comparator_on","comparator_off",
                   "redstone_torch_off","redstone_torch_on","hopper","dispenser",
                   "dropper","piston","sticky_piston","redstone_lamp_off",
                   "redstone_lamp_on","note_block","wooden_door","iron_door",
                   "redstone_block","redstone_wire"}
            port_classes["unfollowed_front_family_"+(family if family in allow
                         else "other_known_machinery")]+=1
    return seen_commands,port_classes,max_wire_hops


def trace(graph,original):
    """Compute private relationships, emit aggregate-only mechanism evidence."""
    # Reuse existing independent full-dataset source reconstruction and graph
    # edge validation. Do not run this on a partial/unverified source.
    audit=reconstruct(graph,original)
    verified,expected,bad=_sha_verified_commands(graph,original)
    if bad or expected!=len(verified):
        raise ValueError("source command SHA incomplete")
    nodes={}
    pos={}
    for n in graph["nodes"]:
        p=_position(n)
        if p in pos or n["node_id"] in nodes:
            raise ValueError("duplicate source node identity")
        pos[p]=n
        nodes[n["node_id"]]=n

    authors=defaultdict(set)
    click_events=defaultdict(list)
    original_writers=defaultdict(set)
    writer_kinds=defaultdict(set)
    for cid,(n,raw,parts) in verified.items():
        if parts and parts[0]=="setblock" and len(parts)>=5:
            from tools.reconstruct_legacy_core_command_controls import _point
            p=_point(parts,1,tuple(n["position"]))
            if p is not None:
                original_writers[p].add(cid)
                writer_kinds[p].add(_material_command(parts))
        ctr=click_controls(raw)
        if ctr is None: continue
        for action,trigger,value in ctr["actions"]:
            if action!="run_command" or trigger!="setblock" or not isinstance(value,str):
                continue
            verb,vals=normalize_command(value)
            p=_static_absolute_point(vals,1)
            if p is None or _material_command(vals)!=POWER_MATERIAL:
                continue
            click_events[p].append((cid,value))
            authors[p].add(cid)
    # Reject independently implausible claimed completeness.
    if len(click_events)>1000:
        raise ValueError("unbounded click target cardinality")

    # The upstream disassembler has already checked each underlying
    # source-authored power edge against its actual command SHA/point/port.
    command_forward=defaultdict(set)
    for edge in graph.get("edges",{}).get("command_authored_redstone_edges",[]):
        if edge.get("edge_type")!="legacy_setblock_redstone_block_direct_command_power":
            continue
        a,b=edge.get("source"),edge.get("target")
        if a in verified and b in verified:
            command_forward[a].add(b)

    # Explicit 1.8 source-facing diode port. Do not infer that it actually
    # propagates through opaque blocks, scheduling or dynamic Redstone state.
    target_profiles=[]
    source_reachable=Counter()
    reset_classes=Counter()
    seeds_global=set()
    verbs_reached=Counter()
    diode_verbs=Counter()
    diode_entities=Counter()
    diode_output_ports=Counter()
    diode_max_wire_hops=0
    entity_reached=Counter()
    feedback=Counter()
    source_unknown=Counter()
    for p,values in click_events.items():
        seed=set()
        diodes=set()
        for delta in NEIGHBORS:
            q=tuple(p[i]+delta[i] for i in range(3))
            n=pos.get(q)
            if n is None: continue
            if n.get("family")=="command_block" and n["node_id"] in verified:
                seed.add(n["node_id"])
            elif n.get("family") in {"repeater_off","repeater_on","comparator_off","comparator_on"}:
                facing=(n.get("metadata_semantics") or {}).get("facing_vector")
                if (isinstance(facing,list) and len(facing)==3 and
                    all(type(x) is int for x in facing) and
                    tuple(q[i]+facing[i] for i in range(3))==p):
                    diodes.add(n["node_id"])

        writers=original_writers.get(p,set())
        kinds=writer_kinds.get(p,set())
        profile={
            "has_direct_command_port":bool(seed),
            "has_oriented_diode_rear_port":bool(diodes),
            "has_independent_air_writer":AUTHOR_RESET in kinds,
            "has_other_original_writer":bool(writers),
            "has_original_power_writer":POWER_MATERIAL in kinds,
            "has_reset_writer_in_immediate_direct_commands":bool(
                seed & {cid for cid in writers if
                        _material_command(verified[cid][2])==AUTHOR_RESET}),
            "distinct_original_reset_writers":len({cid for cid in writers
                        if _material_command(verified[cid][2])==AUTHOR_RESET}),
            "source_command_seeds":len(seed),
        }
        diode_commands,diode_ports,wire_hops=diode_output_candidates(
            graph,pos,verified,diodes)
        diode_output_ports.update(diode_ports)
        diode_max_wire_hops=max(diode_max_wire_hops,wire_hops)
        for cid in diode_commands:
            cmd=verified[cid][2]
            diode_verbs[_safe_verb(cmd)]+=1
            if _safe_verb(cmd)=="summon":
                diode_entities["summon_"+_entity_action(cmd)]+=1
        if diode_commands:
            source_reachable["targets_with_diode_source_geometry_commands"]+=1
        profile["diode_output_command_count"]=len(diode_commands)
        profile["diode_output_blaze"]=any(
            _entity_action(verified[cid][2])=="blaze" for cid in diode_commands)
        target_profiles.append(profile)
        seeds_global.update(seed)
        if not seed: source_unknown["no_exact_adjacent_command"]+=1
        if not diodes: source_unknown["no_exact_diodes"]+=1
        if AUTHOR_RESET not in kinds: source_unknown["no_original_air_reset_writer"]+=1
        reset_classes["distinct_targets_with_source_air_reset" if AUTHOR_RESET in kinds
                      else "distinct_targets_without_source_air_reset"]+=1
        if seed and writers:
            source_reachable["targets_with_direct_command_and_alternate_writer"]+=1
        # Bounded trace along proven authored power edges only. A path through
        # a diode is NOT assumed unless a complete exact typed path exists.
        seen=set(seed)
        distance={k:0 for k in seed}
        queue=deque(seed)
        while queue:
            cid=queue.popleft()
            depth=distance[cid]
            if depth>=3: continue
            for nxt in command_forward.get(cid,set()):
                if nxt not in seen:
                    distance[nxt]=depth+1
                    seen.add(nxt)
                    queue.append(nxt)
        profile["trace_size"]=len(seen)
        profile["maximum_authored_power_hops"]=max(distance.values(),default=0)
        for cid in seen:
            parts=verified[cid][2]
            v=_safe_verb(parts)
            verbs_reached[v]+=1
            if v=="summon":
                e=_entity_action(parts)
                entity_reached["summon_"+e]+=1
                if e=="blaze": profile["source_blaze_summon_reachable"]=True
            if v in {"tellraw","say","title","playsound","particle"}:
                feedback[v]+=1
        profile.setdefault("source_blaze_summon_reachable",False)
        # A source-reachable blaze summon is stronger than global inventory,
        # but still cannot prove the scene described by the 2015 author.
        if profile["source_blaze_summon_reachable"]:
            source_reachable["targets_with_source_reachable_blaze_summon"]+=1
    if not click_events:
        source_unknown["no_author_clickable_setblock_redstone_input"]+=1

    summary=Counter()
    size_bands=Counter()
    for x in target_profiles:
        for key in ("has_direct_command_port","has_oriented_diode_rear_port",
                    "has_independent_air_writer","has_other_original_writer",
                    "has_original_power_writer",
                    "has_reset_writer_in_immediate_direct_commands",
                    "source_blaze_summon_reachable"):
            if x[key]: summary["targets_"+key]+=1
        size=x["trace_size"]
        size_bands["no_verified_seed" if size==0 else
                   "1_to_3" if size<=3 else
                   "4_to_8" if size<=8 else "9_or_more"]+=1
    return {
        "schema":SCHEMA,
        "original_source_command_count":expected,
        "source_sha_verified_command_count":len(verified),
        "authored_click_actions_matching_absolute_redstone_setblock":
             sum(len(values) for values in click_events.values()),
        "distinct_clicked_redstone_target_count":len(click_events),
        "unique_source_authoring_commands_with_matching_click_controls":
             len(set().union(*authors.values())) if authors else 0,
        "clicked_target_source_feature_counts":dict(sorted(summary.items())),
        "clicked_target_authored_reset_counts":dict(sorted(reset_classes.items())),
        "original_air_reset_writers_per_clicked_target_total":
             sum(x["distinct_original_reset_writers"] for x in target_profiles),
        "direct_command_seeds_across_targets_occurrences":
             sum(x["source_command_seeds"] for x in target_profiles),
        "distinct_immediate_command_seeds_across_targets":len(seeds_global),
        "source_direct_power_reach_instruction_count_occurrences":
             sum(x["trace_size"] for x in target_profiles),
        "source_power_reach_size_bands":dict(sorted(size_bands.items())),
        "source_power_reach_maximum_hops":max((x["maximum_authored_power_hops"]
                                                 for x in target_profiles),default=0),
        "diode_source_geometry_downstream_ports":dict(sorted(diode_output_ports.items())),
        "diode_source_geometry_wire_path_max_hops":diode_max_wire_hops,
        "diode_source_geometry_downstream_verb_counts_occurrences":
             dict(sorted(diode_verbs.items())),
        "diode_source_geometry_downstream_summon_entity_counts_occurrences":
             dict(sorted(diode_entities.items())),
        "clicked_targets_with_diode_geometry_candidate_blaze_summon":
             sum(bool(x["diode_output_blaze"]) for x in target_profiles),
        "source_reachable_command_verb_counts_occurrences":dict(sorted(verbs_reached.items())),
        "source_reachable_summon_entity_classes_occurrences":
             dict(sorted(entity_reached.items())),
        "source_reachable_player_feedback_command_counts_occurrences":
             dict(sorted(feedback.items())),
        "source_connection_candidates":dict(sorted(source_reachable.items())),
        "unresolved_join_reason_counts":dict(sorted(source_unknown.items())),
        "independently_audited_command_disassembler_schema":audit["schema"],
        "source_link_evidence":"EXACT_STATIC_CLICK_BLOCK_TARGET_ORIENTED_POWER_PORT_AUTHORED_COMMAND_EDGE",
        "creator_reported_blaze_control_relation":"NOT_ESTABLISHED_UNLESS_EXACT_SCENE_JOIN",
        "source_controller_reset_execution":"NOT_OBSERVED",
        "original_java_188_execution":"NOT_RUN",
        "actor_player_semantics":"UNKNOWN",
        "minecraft_263_equivalence":"NOT_RUN",
        "gameplay_primitive_promoted":False,
        "limits":[
            "An authored clickable action may be refused by command permissions or may not have been clicked.",
            "An adjacent original command block may not fire; strong/weak power and update scheduling require 1.8.8 oracle.",
            "A source-authored air writer to the same target is potential reset, not proven event order.",
            "Source graph edges imply possible power connections only, not actual propagation.",
            "Source-reachable command families do not establish corresponding author-described scene identity.",
            "Diode front port and dust path are source geometry, not measured powered propagation; no opaque conduction assumed.",
            "No raw commands, click text, positions, entity names, per-target identities or source hashes exported.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--graph",type=Path,required=True)
    p.add_argument("--source-zip",type=Path,required=True)
    p.add_argument("--expected-graph-sha256",required=True)
    p.add_argument("--expected-source-sha256",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise SystemExit("refuse overwrite")
    graph_bytes=a.graph.read_bytes()
    zip_bytes=a.source_zip.read_bytes()
    if (hashlib.sha256(graph_bytes).hexdigest()!=a.expected_graph_sha256
        or hashlib.sha256(zip_bytes).hexdigest()!=a.expected_source_sha256):
        raise SystemExit("source/graph pin mismatch")
    graph=json.loads(graph_bytes)
    if graph.get("schema")!="supracraft-legacy-causal-machinery/1":
        raise SystemExit("unaccepted graph schema")
    raw=commands_from_pinned_zip(a.source_zip,graph)
    result=trace(graph,raw)
    result["source_world_sha256"]=a.expected_source_sha256
    result["source_graph_sha256"]=a.expected_graph_sha256
    out=json.dumps(result,sort_keys=True,indent=2)+"\n"
    for forbidden in ('"position"','"node_id"','"target_position"','"command"','"raw"',
                      '"selector"','"objective"','"CustomName"','"value"', 'original-world.zip'):
        if forbidden in out:raise SystemExit("source-custody violation")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(out,encoding="utf-8")
    print("CORE_CLICK_CONTROL_DOWNSTREAM_SOURCE_ONLY",json.dumps({
        "clicked_targets":result["distinct_clicked_redstone_target_count"],
        "click_actions":result["authored_click_actions_matching_absolute_redstone_setblock"],
        "feature_counts":result["clicked_target_source_feature_counts"],
        "reset_writers":result["original_air_reset_writers_per_clicked_target_total"],
        "downstream_verbs":result["source_reachable_command_verb_counts_occurrences"],
        "entities":result["source_reachable_summon_entity_classes_occurrences"],
        "feedback":result["source_reachable_player_feedback_command_counts_occurrences"],
        "diode_ports":result["diode_source_geometry_downstream_ports"],
        "diode_verbs":result["diode_source_geometry_downstream_verb_counts_occurrences"],
        "diode_entities":result["diode_source_geometry_downstream_summon_entity_counts_occurrences"],
        "native":"NOT_RUN"},sort_keys=True))


if __name__=="__main__":
    main()
