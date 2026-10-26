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
    commands_from_pinned_zip, normalize_command, typed_routes
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
    if "summon_armorstand" in classes:
        if "skull_token_in_action" in classes:
            classes.add("armor_stand_summon_with_skull_token")
            if not re.search(r"(?i)\bcount\s*:",raw):
                classes.add("armor_stand_summon_skull_without_explicit_any_count")
        if re.search(r"(?i)\bcount\s*:\s*0[bBsS]?\b",raw):
            classes.add("armor_stand_summon_with_zero_count_token")
    return classes


def summarize_shared_strict_input_roots(routes,classes):
    """Same independently typed sensor drives different source instruction roles.

    Shared source input is a candidate shared stimulus. It is not a command
    order, actual power state, actor match, or verified gameplay event.
    """
    roots=defaultdict(set)
    for sensor,command,mode in routes:
        for role in classes.get(command,set()):
            if role in {"dr_h_author_text_cue","entity_kill","entity_presence_gate",
                        "smoke_hint_candidate","summon_armorstand",
                        "armor_stand_summon_with_skull_token","chess_author_text_cue"}:
                roots[role].add(sensor)
    comparisons={
        "dr_h_text_and_entity_kill":("dr_h_author_text_cue","entity_kill"),
        "dr_h_text_and_presence_gate":("dr_h_author_text_cue","entity_presence_gate"),
        "smoke_hint_and_armor_stand_spawn":("smoke_hint_candidate","summon_armorstand"),
        "chess_text_and_armor_stand_skull_spawn":(
            "chess_author_text_cue","armor_stand_summon_with_skull_token"),
    }
    return {label:len(roots[a]&roots[b]) for label,(a,b) in comparisons.items()}


def classify_legacy_kill_subject(parts):
    """Classify original /kill operand; do not export selectors or names."""
    if not parts or parts[0]!="kill":return "not_kill"
    if len(parts)==1:return "implicit_executor_self"
    subject=parts[1]
    if subject.startswith("@e"):
        if subject=="@e":return "all_entities_selector"
        if not (subject.startswith("@e[") and subject.endswith("]")):
            return "malformed_entity_selector"
        raw=subject[3:-1]
        has_type=TYPE_PARAM.search(raw) is not None
        has_name=NAME_PARAM.search(raw) is not None
        if has_name:return "entity_selector_with_name_filter"
        if has_type:return "entity_selector_with_type_filter"
        return "entity_selector_other_filters"
    if subject.startswith("@p"):return "nearest_player_selector"
    if subject.startswith("@a"):return "all_players_selector"
    if subject.startswith("@r"):return "random_player_selector"
    if subject.startswith("@"):return "unknown_selector"
    return "literal_target_not_disclosed"


def shared_dr_h_sensor_effects(routes,classes,verified):
    """Only a known typed sensor root shared by Dr H text and kill action."""
    sensor_to_dialogue=defaultdict(set)
    sensor_to_removal=defaultdict(set)
    for sensor,cid,mode in routes:
        roles=classes.get(cid,set())
        if "dr_h_author_text_cue" in roles:sensor_to_dialogue[sensor].add(cid)
        if "entity_kill" in roles:sensor_to_removal[sensor].add(cid)
    keys=set(sensor_to_dialogue)&set(sensor_to_removal)
    out=Counter()
    for sensor in keys:
        out["shared_sensor_count"]+=1
        for cid in sensor_to_dialogue[sensor]:
            op=verified[cid][2][0]
            out["dr_h_cue_verb_"+(op if op in {"say","tellraw","title","kill","testfor",
                    "summon","execute","scoreboard","setblock","tp","teleport",
                    "particle","playsound","gamemode"} else "other")]+=1
        for cid in sensor_to_removal[sensor]:
            kind=classify_legacy_kill_subject(verified[cid][2])
            out["removal_target_"+kind]+=1
    return dict(sorted(out.items()))


def _kill_type_filter(parts):
    """Private source-only parse: exact positive 1.8 @e[type=...] operand."""
    if not parts or parts[0]!="kill" or len(parts)<2:
        return None,"missing_or_implicit"
    token=parts[1]
    if not (token.startswith("@e[") and token.endswith("]")):
        return None,"not_bounded_entity_selector"
    match=TYPE_PARAM.search(token[3:-1])
    if not match: return None,"no_type_filter"
    raw=match.group(1).strip()
    if not raw or raw.startswith("!"):
        return None,"negated_or_empty_type"
    return raw.lower().split(":")[-1].replace("_",""),"positive_type_filter"


def same_sensor_actor_type_compatibility(routes,classes,verified):
    """Only source type compatibility of co-rooted author commands, never actor identity."""
    groups=defaultdict(lambda:{"summon":set(),"kill":set()})
    for sensor,cid,_ in routes:
        roles=classes.get(cid,set())
        if "dr_h_author_text_cue" in roles and verified[cid][2][0]=="summon":
            groups[sensor]["summon"].add(cid)
        if "entity_kill" in roles:
            groups[sensor]["kill"].add(cid)
    out=Counter()
    for items in groups.values():
        if not items["summon"] or not items["kill"]:continue
        out["shared_input_groups_with_summon_and_kill"]+=1
        for sid in items["summon"]:
            summoned=verified[sid][2]
            summoned_type=(summoned[1].lower().split(":")[-1].replace("_","")
                           if len(summoned)>=2 else None)
            out["summon_original_custom_name_field_present" if
                re.search(r"(?i)\bCustomName\s*:",verified[sid][1]) else
                "summon_original_custom_name_field_absent"]+=1
            for kid in items["kill"]:
                target_type,filter_status=_kill_type_filter(verified[kid][2])
                out["paired_kill_selector_"+filter_status]+=1
                if not summoned_type or not target_type:
                    out["source_type_join_UNRESOLVED"]+=1
                elif summoned_type==target_type:
                    out["source_spawn_and_kill_type_compatible"]+=1
                else:
                    out["source_spawn_and_kill_type_disjoint"]+=1
    return dict(sorted(out.items()))


def _read_item_shape(item):
    """Parse already-decoded original NBT item only; no item values are returned."""
    def unpack(v):
        if hasattr(v,"unpack"):
            try:return v.unpack()
            except Exception:return v
        return v
    if not hasattr(item,"get"):return "non_compound",False
    identity=str(unpack(item.get("id",""))).lower().split(":")[-1]
    if identity not in {"skull","skull_item"} and identity!="397":
        return "other_item",False
    if "Count" not in item:
        return "skull_without_count_tag",True
    try: count=int(unpack(item["Count"]))
    except (TypeError,ValueError):
        return "skull_count_unparseable",True
    if count==0:return "skull_explicit_zero_count",True
    if count>0:return "skull_explicit_positive_count",True
    return "skull_negative_count",True


def normalize_legacy_unquoted_item_ids(payload):
    """Narrow in-memory compatibility transform, NOT original NBT evidence.

    Changes only unquoted id:minecraft namespace item values into quoted
    SNBT string values. Never rewrites source world or arbitrary values.
    """
    token=re.compile(
        r'(?<![A-Za-z0-9_])(\bid\s*:\s*)(minecraft:[A-Za-z0-9_.\-/]+)'
        r'(?=\s*[,}\]])',re.I)
    return token.sub(lambda m:m.group(1)+'"'+m.group(2)+'"',payload)


def armorstand_summon_item_shapes(raw,parser):
    """Parse original standalone SNBT only when the approved custody parser is present.

    The parser is injected in synthetic tests and supplied by existing nbtlib
    only in pinned original workcell. Failure is explicit, not an inferred item.
    """
    verb,parts=normalize_command(raw)
    if verb!="summon" or len(parts)<2 or safe_entity_type(parts[1])!="armorstand":
        return {"not_armorstand_summon":1}
    beginning=raw.find("{")
    if beginning<0:return {"summon_without_compound":1}
    payload=raw[beginning:]
    compatible_parse=False
    normalized_candidate_present=False
    try:
        nbt=parser(payload)
    except Exception as exc:
        # Old source syntax may use bare namespaced item IDs. Modern nbtlib
        # may reject them. This does NOT rewrite or execute original world.
        amended=normalize_legacy_unquoted_item_ids(payload)
        normalized_candidate_present=(amended!=payload)
        if normalized_candidate_present and type(exc).__name__=="InvalidLiteral":
            try:
                nbt=parser(amended)
                compatible_parse=True
            except Exception as second_error:
                exc=second_error
        if not compatible_parse:
            # Never serialize errors/messages: they may include private source.
            allowed={"ValueError","TypeError","KeyError","IndexError",
                     "AttributeError","InvalidLiteral","InvalidToken",
                     "InvalidTag","UnexpectedToken","SyntaxError"}
            category=type(exc).__name__
            if category not in allowed:category="other_parse_exception"
            return {
                "source_snbt_parse_unresolved":1,
                "source_snbt_parser_error_class_"+category:1,
                "source_snbt_compat_item_id_normalization_attempted" if
                    normalized_candidate_present else
                    "source_snbt_no_eligible_unquoted_item_id_normalization":1,
                "source_snbt_payload_braces_unbalanced" if payload.count("{")!=payload.count("}")
                  else "source_snbt_payload_braces_balanced":1,
                "source_snbt_payload_square_brackets_unbalanced" if payload.count("[")!=payload.count("]")
                  else "source_snbt_payload_square_brackets_balanced":1,
            }
    if not hasattr(nbt,"get"):return {"source_snbt_not_compound":1}
    equipment=nbt.get("Equipment")
    if equipment is None:
        return {"source_snbt_without_equipment_field":1}
    if not hasattr(equipment,"__iter__"):
        return {"source_snbt_equipment_nonlist":1}
    counter=Counter({"source_snbt_parsed_equipment":1})
    if compatible_parse:
        counter["source_snbt_compat_item_id_normalized_parse_success"]+=1
    for slot in equipment:
        classification,is_skull=_read_item_shape(slot)
        counter["equipment_slot_"+classification]+=1
        if is_skull:counter["equipment_skull_slot_seen"]+=1
    if not counter["equipment_skull_slot_seen"]:
        counter["no_parsed_skull_slot"]+=1
    return dict(sorted(counter.items()))


def chess_source_effect_geometry(verified,classes):
    """Original command target overlap for chess candidates, not causal proof.

    Compute only ephemeral exact coordinates from SHA-verified source command
    origins. 1.8 summon uses xyz at [2:5]; particle uses xyz at [2:5].
    Never return any actual coordinate, raw command, node identity, or pairing.
    """
    from tools.infer_legacy_core_gameplay_purposes import resolve_xyz
    smoke=[]
    heads=[]
    failures=Counter()
    for ident,(node,raw,parts) in verified.items():
        role=classes.get(ident,set())
        if "smoke_hint_candidate" not in role and (
             "armor_stand_summon_with_skull_token" not in role):
            continue
        if not isinstance(node.get("position"),list) or len(node["position"])!=3:
            raise ValueError("original command node position not independently supported")
        origin=tuple(node["position"])
        # This function only handles commands with direct coordinate operands.
        # A nested execute has a *dynamic* execution origin: leave unresolved.
        if len(parts)<5 or parts[0] not in {"particle","summon"}:
            failures["unsupported_syntax_or_command_origin"]+=1
            continue
        point=resolve_xyz(parts[2:5],origin)
        if point is None:
            failures["non_resolvable_author_target"]+=1
            continue
        if "smoke_hint_candidate" in role:smoke.append(point)
        if "armor_stand_summon_with_skull_token" in role:heads.append(point)
    histogram=Counter()
    if not heads and smoke:
        histogram["smoke_without_saved_head_spawn_target_candidates"]=len(smoke)
    for origin in smoke:
        d2=min((sum((a-b)**2 for a,b in zip(origin,target))
                for target in heads),default=None)
        if d2 is None:continue
        histogram["same_coordinate" if d2==0 else
                  "within_3_blocks" if d2<=9 else
                  "within_16_blocks" if d2<=256 else
                  "more_than_16_blocks"]+=1
    return {
        "source_smoke_particle_effect_targets_resolved":len(smoke),
        "source_skull_armorstand_spawn_targets_resolved":len(heads),
        "source_effect_to_spawn_nearest_distance_bands":
             dict(sorted(histogram.items())),
        "source_target_coordinate_parse_failures":
             dict(sorted(failures.items())),
        "geometry_proof":"COMMAND_AUTHORED_EFFECT_COORDINATES_ONLY",
        "shared_scene_or_control_flow":"NOT_ESTABLISHED_BY_SPATIAL_OVERLAP",
        "particle_emission_and_spawn":"NOT_OBSERVED",
    }


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
        alt_armor=item.get("ArmorItems") or []
        if alt_armor:
            result["saved_armor_stands_with_alternate_armoritems"]+=1
        if not equipment and alt_armor:
            equipment=alt_armor
        if not isinstance(equipment,(list,tuple)) and type(equipment).__name__ not in {"List","ListTag"}:
            continue
        if len(equipment)>0:
            result["saved_armor_stands_with_equipment_entries"]+=1
        zero=False
        head=False
        if item.get("HandItems"):
            result["saved_armor_stands_with_handitems_field"]+=1
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
    selector_detail=Counter()
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
            if selector: selector_detail["named_presence_gate_commands"]+=1
            if any(DR_CUE.search(name) for name,_ in selector):
                selector_detail["named_dr_h_presence_gate_commands"]+=1
        if "entity_kill" in cc:
            selectors_by_role["kill"].update(selector)
            if selector:selector_detail["named_kill_commands"]+=1
            if any(DR_CUE.search(name) for name,_ in selector):
                selector_detail["named_dr_h_kill_commands"]+=1
        for sig in selector:
            actors[sig].add(cid)
        if "dr_h_author_text_cue" in cc: scenes["dr_h_cue_commands"]+=1
        if "chess_author_text_cue" in cc:scenes["chess_cue_commands"]+=1
    common=selectors_by_role["presence_gate"] & selectors_by_role["kill"]
    exact=source_exact_join_audit(graph,verified,classes)
    # Existing independently qualified strict sensor wiring supplies an
    # evidence class independent of author prose / component co-presence.
    routes,reference=typed_routes(graph)
    strict_scene_inputs=Counter()
    categories={
        "entity_presence_gate","entity_kill","smoke_hint_candidate",
        "skull_token_in_action","summon_armorstand","chess_author_text_cue",
        "dr_h_author_text_cue","dialogue","particle_feedback"
    }
    for sensor,cid,kind in routes:
        for role in classes[cid] & categories:
            strict_scene_inputs["typed_sensor_to_"+role]+=1
    if len(routes)!=reference["accepted_path_count"]:
        raise ValueError("strict source sensor witness count mismatch")
    # Source SNBT parser is supplied only from already approved original
    # custody; source-free CI invokes the pure classification with an injected parser.
    original_skull_shapes=Counter()
    try:
        from nbtlib import parse_nbt
    except ImportError:
        parse_nbt=None
    for cid,(node,raw,parts) in verified.items():
        if "armor_stand_summon_with_skull_token" not in classes[cid]:
            continue
        if parse_nbt is None:
            original_skull_shapes["source_snbt_parser_unavailable"]+=1
            continue
        original_skull_shapes.update(armorstand_summon_item_shapes(raw,parse_nbt))
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
        "entity_selector_source_detail_counts":dict(sorted(selector_detail.items())),
        "qualified_sensor_to_scene_command_path_counts":dict(sorted(strict_scene_inputs.items())),
        "qualified_sensor_to_command_route_count":len(routes),
        "distinct_strict_sensor_shared_scene_role_counts":summarize_shared_strict_input_roots(routes,classes),
        "shared_dr_h_typed_sensor_action_classes":shared_dr_h_sensor_effects(routes,classes,verified),
        "same_sensor_original_actor_type_compatibility":same_sensor_actor_type_compatibility(routes,classes,verified),
        "chess_source_effect_target_geometry":chess_source_effect_geometry(verified,classes),
        "armorstand_original_summon_snbt_shape_counts":dict(sorted(original_skull_shapes.items())),
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
            "Missing Count in source SNBT is not proof of an observed zero-count item or original-version engine default.",
            "Modern-parser compatibility-normalized success is not proof the unmodified original command parsed in Java 1.8.8.",
            "Shared source sensor and compatible entity types cannot establish same runtime actor instance or execution order.",
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
        "dr_h_actor_type_join":result["same_sensor_original_actor_type_compatibility"],
        "armorstand_snbt_shape":result["armorstand_original_summon_snbt_shape_counts"],
        "chess_effect_target_geometry":result["chess_source_effect_target_geometry"],
        "native":"NOT_RUN",
    },sort_keys=True))


if __name__=="__main__":
    main()
