#!/usr/bin/env python3
"""Pinned original 1.8.8 clone source-material audit, static only.

Maps only source-derived clone destination overlaps with selected mechanical
wire contacts back to source block samples. Never exports source/dest positions,
commands, world bytes or claim of command execution.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from tools.audit_legacy_piston_authored_inputs import _exact_integer_position
from tools.inspect_legacy_piston_snapshot_inputs import (
    select_component_wires, DIRECTIONS, read_target_blocks,
)

SCHEMA="supracraft-legacy-piston-clone-source-material/1"
COMMAND_FAMILIES={"command_block","chain_command_block","repeating_command_block"}
GROUPED_CLASSES={
    0:"air", 55:"redstone_wire", 152:"redstone_block",
    75:"unlit_redstone_torch", 76:"lit_redstone_torch",
    93:"unpowered_repeater",94:"powered_repeater",
    29:"sticky_piston",33:"piston",
    69:"lever",77:"stone_button",143:"wooden_button",
    70:"stone_plate",72:"wooden_plate",
    137:"command_block",
}

def map_clone_material_source_positions(graph:dict, signature:str) -> list[tuple[str, tuple]]:
    """Private ephemeral pairs (command ID, source block) for candidate contacts.

    Destination is a lower-corner origin; source blocks are indexed from the
    normalized source bounding-box minimum. No command payload/fill/execute.
    """
    components=select_component_wires(graph,signature)
    contacts={tuple(pos[i]+step[i] for i in range(3))
              for wires in components for pos in wires for step in DIRECTIONS}
    byid={n["node_id"]:n for n in graph["nodes"]}
    if len(byid)!=len(graph["nodes"]):
        raise ValueError("duplicate node identity")
    targets={}
    for row in graph["edges"].get("command_world_targets",[]):
        if not isinstance(row,dict):
            raise ValueError("malformed target")
        if row.get("target_kind") in {"source_start","source_end","destination"}:
            targets.setdefault(row.get("source"),[]).append(row)
    mapping=[]
    for cid,n in byid.items():
        if n.get("family") not in COMMAND_FAMILIES or (n.get("command") or {}).get("verb")!="clone":
            continue
        rows=targets.get(cid,[])
        if len(rows)!=3:
            continue
        data={r["target_kind"]:_exact_integer_position(r.get("target_position")) for r in rows}
        if set(data)!={"source_start","source_end","destination"} or any(v is None for v in data.values()):
            continue
        a,b,dest=data["source_start"],data["source_end"],data["destination"]
        src_min=tuple(min(a[i],b[i]) for i in range(3))
        ext=tuple(abs(a[i]-b[i]) for i in range(3))
        for pos in contacts:
            if all(dest[i]<=pos[i]<=dest[i]+ext[i] for i in range(3)):
                src=tuple(src_min[i]+pos[i]-dest[i] for i in range(3))
                mapping.append((cid,src))
    return mapping


def classify_materials(pairs:list, blocks:dict) -> dict:
    byclass=Counter()
    missing=0
    for _,src in pairs:
        if src not in blocks:
            missing+=1
        else:
            byclass[GROUPED_CLASSES.get(blocks[src],"other_saved_block_id")]+=1
    return {
        "candidate_clone_source_cell_samples":len(pairs),
        "resolved_source_cell_samples":len(pairs)-missing,
        "unresolved_source_cell_samples":missing,
        "saved_source_material_class_counts":dict(sorted(byclass.items())),
        "clone_could_place_power_source_static_only":(
            "SAVED_REDSTONE_BLOCK_SOURCE_CANDIDATE"
            if byclass["redstone_block"] else "NO_SAVED_REDSTONE_BLOCK_IN_MAPPED_CLONE_CELLS"
        ),
        "clone_command_execution":"NOT_OBSERVED",
        "clone_mask_replace_filter_modes":"UNVERIFIED",
        "original_piston_motion":"NOT_OBSERVED",
        "minecraft_26_3_equivalence":"NOT_RUN",
        "gameplay_promoted":False,
    }


def inspect(graph:dict,signature:str,blocks:dict) -> dict:
    pairs=map_clone_material_source_positions(graph,signature)
    return {
        "schema":SCHEMA,
        "analysis":"saved_original_clone_cells_source_only",
        "signature_sha256":signature,
        **classify_materials(pairs,blocks),
        "limitations":[
            "Source cells are saved-state material, not proof command executes.",
            "Clone masked/filtered/move and command selection may alter actual result.",
            "No proof of piston extension, direct power, causality or player gameplay.",
            "Only six-face contacts around selected dust nodes were sampled.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--graph",type=Path,required=True)
    p.add_argument("--source-zip",type=Path,required=True)
    p.add_argument("--expected-graph-sha256",required=True)
    p.add_argument("--expected-source-sha256",required=True)
    p.add_argument("--signature",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        raise SystemExit("refuse overwrite")
    raw=a.graph.read_bytes()
    gh=hashlib.sha256(raw).hexdigest()
    if gh!=a.expected_graph_sha256:
        raise SystemExit("frozen causal graph mismatch")
    archive=a.source_zip.read_bytes()
    zh=hashlib.sha256(archive).hexdigest()
    if zh!=a.expected_source_sha256:
        raise SystemExit("frozen CORE original source mismatch")
    graph=json.loads(raw)
    pairs=map_clone_material_source_positions(graph,a.signature)
    blocks=read_target_blocks(a.source_zip,{src for _,src in pairs})
    result=inspect(graph,a.signature,blocks)
    result["source_graph_sha256"]=gh
    result["source_world_sha256"]=zh
    serialized=json.dumps(result,sort_keys=True,indent=2)+"\n"
    for forbidden in ('"node_id"','"position"','"command"','"raw"','"target_position"','original-world.zip'):
        if forbidden in serialized:
            raise SystemExit("source leak into derived-only result")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(serialized,encoding="utf-8")
    print(json.dumps({
        "candidate_samples":result["candidate_clone_source_cell_samples"],
        "material_classes":result["saved_source_material_class_counts"],
        "unresolved":result["unresolved_source_cell_samples"],
        "interpretation":result["clone_could_place_power_source_static_only"]
    },sort_keys=True))


if __name__=="__main__":
    main()
