#!/usr/bin/env python3
"""Disassemble original Java 1.8.8 CORE command control/state dependencies.

Only immutable, pinned world/graph original inputs; never execute commands.
Transient command texts, scoreboard names, selectors, world coordinates, JSON
and source identities do not leave the source-custody workcell. Derivative
contains allowlisted aggregate counts, no reversible witness identifiers.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from tools.infer_legacy_core_gameplay_purposes import (
    commands_from_pinned_zip, normalize_command, resolve_xyz, typed_routes
)

SCHEMA="supracraft-core-188-control-program-static-aggregate/1"
ALLOWED_CLICK={"run_command","suggest_command","open_url","change_page"}
STORY_FEATURES={
    "creator_end_dialogue_clock_presence_skull":{
        "testfor_entity","skull_or_head_summon","presentation_message","source_clock_loop_verified"
    },
    "creator_blaze_potion_click_control":{
        "blaze_summon","click_run_command","gamemode_change","effect_change"
    },
    "creator_chess_heads_smoke_hint":{
        "armor_stand_saved_actor","skull_saved_tile","particle_feedback","button_input"
    },
}
SAFE_ENTITY={
    "armorstand":"armor_stand","blaze":"blaze","item":"item","villager":"villager",
    "wither":"wither","entityhorse":"horse","skeleton":"skeleton",
    "itemframe":"item_frame","primedtnt":"primed_tnt"
}
SELECTOR_SCORE=re.compile(r"(?<![A-Za-z0-9_])score_([A-Za-z0-9_.+-]{1,128}?)(?:_min)?=")
SELECTOR_TOKEN=re.compile(r"@[pare]\[[^\]\r\n]{0,2048}\]")


def _point(parts, start, origin):
    if len(parts)<start+3: return None
    resolved=resolve_xyz(parts[start:start+3],origin)
    if resolved is None or len(resolved)!=3 or not all(type(x) is int for x in resolved):
        return None
    return tuple(resolved)


def scoreboard_access(parts):
    """Conservative 1.8 scoreboard grammar; no unverified wildcard expansion."""
    reads=set()
    writes=set()
    if len(parts)>=5 and parts[0]=="scoreboard" and parts[1]=="players":
        op=parts[2]
        if op in {"set","add","remove","enable","reset"}:
            writes.add(parts[4])
        elif op=="test":
            reads.add(parts[4])
        elif op=="operation" and len(parts)>=8:
            writes.add(parts[4])
            reads.add(parts[7])
            if parts[5] != "=": reads.add(parts[4])
    elif len(parts)>=4 and parts[0]=="scoreboard" and parts[1]=="objectives":
        if parts[2] in {"add","remove"}:
            writes.add(parts[3])
        elif parts[2]=="setdisplay" and len(parts)>=5:
            reads.add(parts[4])
    return reads,writes


def selector_reads(raw):
    # Selector score is a state read even when the verb is 'tp' or 'summon'.
    # Do not expose objective names, literal player/UUID, or selector parameters.
    if not isinstance(raw,str): return set()
    out=set()
    for token in SELECTOR_TOKEN.findall(raw):
        out.update(SELECTOR_SCORE.findall(token))
    return out


def click_controls(raw):
    """Parse tellraw JSON components, recurse only within strict bounded JSON."""
    verb,parts=normalize_command(raw)
    if verb!="tellraw": return None
    fields=raw.strip().lstrip("/").split(None,2)
    if len(fields)!=3:
        return {"status":"missing_json","actions":[]}
    if len(fields[2])>100_000:
        return {"status":"oversize_json","actions":[]}
    try:
        obj=json.loads(fields[2])
    except (ValueError,TypeError,RecursionError):
        return {"status":"malformed_json","actions":[]}
    pending=[obj]
    actions=[]
    checked=0
    while pending:
        item=pending.pop()
        checked+=1
        if checked>4096:
            return {"status":"unbounded_json_tree","actions":[]}
        if isinstance(item,list):
            pending.extend(item)
        elif isinstance(item,dict):
            event=item.get("clickEvent")
            if isinstance(event,dict):
                action=event.get("action")
                value=event.get("value")
                if action in ALLOWED_CLICK and isinstance(value,str):
                    trigger=""
                    if action in {"run_command","suggest_command"}:
                        trigger=normalize_command(value)[0]
                    actions.append((action,trigger,value))
                else:
                    actions.append(("unknown_or_invalid_click","",None))
            # recurse through structured JSON components, NOT arbitrary string text
            for k in ("extra","with"):
                if k in item: pending.append(item[k])
    return {"status":"parsed","actions":actions}


def nested_execute(parts):
    """Return only shape of 1.8.8 execute command, bounded to one level."""
    if not parts or parts[0]!="execute": return "not_execute",None
    if len(parts)<6:
        return "malformed_or_short",None
    # execute <entity> <x> <y> <z> [detect <x> <y> <z> <block> <data>] <command>
    ix=5
    mode="plain"
    if parts[ix]=="detect":
        if len(parts)<12: return "malformed_or_short",None
        ix=11
        mode="detect"
    if ix>=len(parts): return "malformed_or_short",None
    return mode,parts[ix].lower().lstrip("/")


def _sha_verified_commands(graph, raw):
    result={}
    expected=0
    bad=Counter()
    for n in graph.get("nodes",[]):
        if n.get("family")!="command_block": continue
        expected+=1
        cid=n["node_id"]
        text=raw.get(cid)
        sha=(n.get("command") or {}).get("sha256")
        if not isinstance(text,str) or not isinstance(sha,str) or hashlib.sha256(text.encode()).hexdigest()!=sha:
            bad["original_command_sha_or_tile_missing"]+=1
            continue
        verb,parts=normalize_command(text)
        if verb != ((n.get("command") or {}).get("verb") or ""):
            bad["command_verb_mismatch"]+=1
            continue
        result[cid]=(n, text, parts)
    return result, expected, bad


def reconstruct(graph, raw):
    verified, expected, bad=_sha_verified_commands(graph,raw)
    # Every source command must match. Never infer from incomplete original.
    if bad or len(verified)!=expected:
        raise ValueError("cannot qualify partial/forged original command contents")
    routes,source_rank=typed_routes(graph)
    reached={b for a,b,mode in routes}
    roles=Counter()
    click=Counter()
    source_reads=defaultdict(set)
    source_writes=defaultdict(set)
    point_readers=defaultdict(set)
    point_writers=defaultdict(set)
    query=Counter()
    features=set()
    parsed_actions=[]
    for cid,(n,raw_text,parts) in verified.items():
        verb=parts[0] if parts else ""
        origin=tuple(n["position"])
        if verb=="testfor":
            features.add("testfor_entity")
        if verb in {"tellraw","say","title"}:
            features.add("presentation_message")
        if verb=="particle": features.add("particle_feedback")
        if verb=="gamemode": features.add("gamemode_change")
        if verb=="effect": features.add("effect_change")
        if verb=="summon" and len(parts)>=2:
            entity=SAFE_ENTITY.get(parts[1].lower().split(":")[-1].replace("_",""))
            roles["summon_"+(entity or "other_or_unknown")]+=1
            if entity=="blaze": features.add("blaze_summon")
            if entity in {"armor_stand"}: features.add("armor_stand_summon")
            if entity=="item":
                # Source author may generate a skull as an item, but cannot
                # assert this from generic item command without NBT validation.
                features.add("item_summon_unspecified")
        r,w=scoreboard_access(parts)
        r|=selector_reads(raw_text)
        for obj in r:
            source_reads[obj].add(cid)
        for obj in w:
            source_writes[obj].add(cid)
        if r: query["commands_with_state_reads"]+=1
        if w: query["commands_with_state_writes"]+=1
        if verb=="testforblock":
            p=_point(parts,1,origin)
            if p is not None: point_readers[p].add(cid)
            else: query["unresolved_testforblock_target"]+=1
        if verb=="setblock":
            p=_point(parts,1,origin)
            if p is not None: point_writers[p].add(cid)
            else: query["unresolved_setblock_target"]+=1
        if verb=="execute":
            mode,inner=nested_execute(parts)
            roles["execute_"+mode]+=1
            if inner: roles["execute_inner_"+(inner if inner in
                {"testfor","setblock","scoreboard","summon","tp","teleport",
                 "effect","give","clear","particle","tellraw","gamemode"} else "other")]+=1
        ctr=click_controls(raw_text)
        if ctr is not None:
            click["tellraw_"+ctr["status"]]+=1
            for action,trigger,value in ctr["actions"]:
                click["action_"+action]+=1
                if action=="run_command":
                    features.add("click_run_command")
                    allowed=trigger if trigger in {
                        "scoreboard","tp","teleport","gamemode","tellraw",
                        "effect","kill","execute","setblock","fill","clone",
                        "trigger","summon","give","clear","say","title",
                        "testfor","testforblock","particle","playsound"
                    } else "other"
                    click["run_verb_"+allowed]+=1
                if action in {"run_command","suggest_command"}:
                    parsed_actions.append((cid,action,trigger,value))
    objective_overlap=set(source_reads)&set(source_writes)
    exact_score_pairs=set()
    for obj in objective_overlap:
        for writer in source_writes[obj]:
            for reader in source_reads[obj]:
                if writer != reader:
                    exact_score_pairs.add((writer,reader))
    exact_point_pairs=set()
    for point in set(point_readers)&set(point_writers):
        for writer in point_writers[point]:
            for reader in point_readers[point]:
                if writer != reader:
                    exact_point_pairs.add((writer,reader))
    command_roles=Counter()
    for src,dst in exact_score_pairs: command_roles["scoreboard_state_writer_to_reader"]+=1
    for src,dst in exact_point_pairs: command_roles["setblock_writer_to_testforblock_reader"]+=1
    # Explicit actionable chat commands are potential *player* input edges,
    # never observations of clicks. Resolve only exact objective cross-references.
    chat_score=Counter()
    for origin_id,action,verb,value in parsed_actions:
        v,parts=normalize_command(value)
        if action=="run_command":
            r,w=scoreboard_access(parts)
            r|=selector_reads(value)
            if r or w:
                chat_score["click_score_input_candidate"]+=1
            for obj in r|w:
                if obj in source_reads or obj in source_writes:
                    chat_score["click_score_reference_matched_existing_objective"]+=1
                    break
            if verb=="gamemode": chat_score["click_mode_change_candidate"]+=1
            if verb in {"tp","teleport"}: chat_score["click_relocation_candidate"]+=1
    edges=graph.get("edges",{})
    command_ids=set(verified)
    # Graph links need exact source/target command identities, not adjacency.
    typed_chain_pairs=set()
    for item in edges.get("command_chain_candidates",[]):
        if not isinstance(item,dict): continue
        if item.get("source") in command_ids and item.get("target") in command_ids:
            if item.get("edge_type") in {"chain_facing_successor_candidate","conditional_predecessor_success_dependency"}:
                typed_chain_pairs.add((item["source"],item["target"],item["edge_type"]))
    # Original-authored block writes can *power other instructions* or diode
    # inputs. Independently inspect the exact source write and destination port
    # rather than treating all proximity to a redstone block as conduction.
    authored_edges=Counter()
    authored_pairs=set()
    byid={n["node_id"]:n for n in graph.get("nodes",[])}
    for e in edges.get("command_authored_redstone_edges",[]):
        if not isinstance(e,dict):
            raise ValueError("malformed authored power edge")
        kind=e.get("edge_type")
        if kind not in {"legacy_setblock_redstone_block_direct_command_power",
                        "legacy_setblock_redstone_block_diode_rear_input"}:
            continue
        a,b=e.get("source"),e.get("target")
        if a not in verified or b not in byid:
            raise ValueError("source-unsupported authored redstone edge")
        src,_,parts=verified[a]
        p=_point(parts,1,tuple(src["position"]))
        material=parts[4].lower() if len(parts)>4 else ""
        if (not p or not (material=="152" or material in
                          {"minecraft:redstone_block","redstone_block"})
             or list(p)!=e.get("authored_target_position")):
            raise ValueError("authored power edge lacks exact original command support")
        dst=byid[b]
        q=tuple(dst["position"])
        if kind=="legacy_setblock_redstone_block_direct_command_power":
            if b not in verified or sum(abs(u-v) for u,v in zip(p,q))!=1:
                raise ValueError("unauthenticated direct powered command adjacency")
        else:
            if dst["family"] not in {"repeater_on","repeater_off","comparator_on","comparator_off"}:
                raise ValueError("authored diode target family invalid")
            facing=(dst.get("metadata_semantics") or {}).get("facing_vector")
            if not isinstance(facing,list) or len(facing)!=3 or any(type(v) is not int for v in facing):
                raise ValueError("no exact diode input direction")
            if tuple(q[i]+facing[i] for i in range(3))!=p:
                raise ValueError("diode rear does not match authored point")
        authored_pairs.add((a,b,kind))
    for _,_,kind in authored_pairs:
        authored_edges[kind]+=1
    graph_family=graph.get("family_counts",{})
    if graph_family.get("redstone_wire",0)>0 and (
            graph_family.get("repeater_on",0)+graph_family.get("repeater_off",0)>0):
        features.add("physical_wire_and_repeater_co_present_not_clock_verified")
    # Presence of saved physical props via graph is a necessary but never
    # sufficient condition; actual individual rooms not joined in this pass.
    if graph_family.get("wooden_button",0)+graph_family.get("stone_button",0)>0:
        features.add("button_input")
    # We did not analyze uncounted source entity NBT here. Do not fabricate
    # corresponding chess or skull subgraph support from earlier aggregate counts.
    story_status={}
    for scenario,required in STORY_FEATURES.items():
        present=sorted(required & features)
        absent=sorted(required - features)
        story_status[scenario]={
            "source_candidate_feature_families_present":present,
            "source_candidate_feature_families_unresolved":absent,
            "candidate_relation":"SOURCE_FEATURE_INVENTORY_ONLY_NO_VERIFIED_SCENE_JOIN",
            "creator_claim_version_matched_to_pinned_zip":False,
            "native_runtime_verified":False,
        }
    return {
        "schema":SCHEMA,
        "scope":"ALL_ORIGINAL_VERIFIED_COMMANDS_AND_TYPED_STATIC_DEPENDENCIES",
        "original_commands_sha_verified":len(verified),
        "source_command_count":expected,
        "qualified_directed_sensor_routes":len(routes),
        "reached_original_command_blocks":len(reached),
        "source_state_read_commands":len({x for xs in source_reads.values() for x in xs}),
        "source_state_write_commands":len({x for xs in source_writes.values() for x in xs}),
        "scoreboard_state_objectives_with_exact_read_write":len(objective_overlap),
        "scoreboard_exact_cross_command_possible_edges":len(exact_score_pairs),
        "block_states_written_and_tested_exact_point_count":len(set(point_readers)&set(point_writers)),
        "block_state_exact_cross_command_possible_edges":len(exact_point_pairs),
        "source_direct_command_chain_candidate_edges":len(typed_chain_pairs),
        "source_authored_power_dependency_counts":dict(sorted(authored_edges.items())),
        "source_authored_power_dependency_total":len(authored_pairs),
        "typed_chain_edge_family_counts":dict(sorted(Counter(t for _,_,t in typed_chain_pairs).items())),
        "command_family_counts":dict(sorted(roles.items())),
        "source_clickable_chat_counts":dict(sorted(click.items())),
        "source_chat_to_scoreboard_candidate_counts":dict(sorted(chat_score.items())),
        "source_state_operand_counts":dict(sorted(query.items())),
        "author_claim_source_feature_status":story_status,
        "dependency_proof":"EXACT_SOURCE_SCORE_OBJECTIVE_OR_BLOCK_POINT_JOIN__NOT_RUNTIME",
        "scoreboard_selector_resolution":"UNRESOLVED_PLAYER_AND_ENTITY_BINDINGS",
        "click_event_execution":"NOT_RUN",
        "original_native":"NOT_RUN",
        "mechanism_purpose":"UNPROVEN",
        "original_world_18_to_263_parity":"NOT_RUN",
        "gameplay_promoted":False,
        "limitations":[
            "State objective equality is only a potential dependency, not actual same player/actor scoreboard slot.",
            "Original Java 1.8 selector binding, clock timing, command success and object lifetimes remain unknown.",
            "Source graph command chains are authoring/static candidates, not actual 1.8.8 chain execution.",
            "Player chat JSON click actions are authored controls, not observed player clicks.",
            "Creator-confirmed scenarios require exact source slice and historical release match.",
            "World parts outside command-block nodes (inventory, actor equipment, physical mechanics) need separate qualified joins."
        ]
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--graph",type=Path,required=True)
    p.add_argument("--source-zip",type=Path,required=True)
    p.add_argument("--expected-graph-sha256",required=True)
    p.add_argument("--expected-source-sha256",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists(): raise SystemExit("refuse overwrite")
    raw_graph=a.graph.read_bytes()
    raw_zip=a.source_zip.read_bytes()
    if hashlib.sha256(raw_graph).hexdigest()!=a.expected_graph_sha256 or hashlib.sha256(raw_zip).hexdigest()!=a.expected_source_sha256:
        raise SystemExit("original source/graph SHA mismatch")
    graph=json.loads(raw_graph)
    byid=commands_from_pinned_zip(a.source_zip,graph)
    result=reconstruct(graph,byid)
    result["source_world_sha256"]=a.expected_source_sha256
    result["source_graph_sha256"]=a.expected_graph_sha256
    serialized=json.dumps(result,sort_keys=True,indent=2)+"\n"
    for restricted in ('"node_id"','"position"','"target_position"','"command"','"raw"','"selector"','"objective"','"value"','"CustomName"','original-world.zip'):
        if restricted in serialized: raise SystemExit("source source-custody leak detected")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(serialized,encoding="utf-8")
    print("CORE_ORIGINAL_CONTROL_DEPENDENCIES_SOURCE_ONLY",json.dumps({
        "commands":result["source_command_count"],
        "score_objective_joined":result["scoreboard_state_objectives_with_exact_read_write"],
        "score_cross_command_edges":result["scoreboard_exact_cross_command_possible_edges"],
        "block_target_joined":result["block_states_written_and_tested_exact_point_count"],
        "block_cross_command_edges":result["block_state_exact_cross_command_possible_edges"],
        "click_counts":result["source_clickable_chat_counts"],
        "power_edges":result["source_authored_power_dependency_counts"],
        "nested_execute":result["command_family_counts"],
        "state_operands":result["source_state_operand_counts"],
        "chat_score":result["source_chat_to_scoreboard_candidate_counts"],
        "native":"NOT_RUN",
    },sort_keys=True))


if __name__=="__main__":
    main()
