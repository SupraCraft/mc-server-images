#!/usr/bin/env python3
"""Pinned CORE Java 1.8.8 clone input-wire source audit, static-only.

Private original graph coordinates and stopped-world source blocks stay inside
existing ephemeral custody. Only aggregate named upstream wire saved power,
immediate neighbor classes, and compact authored writes leave the workcell.
Neither saved metadata nor source writes prove live power or clone execution.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from tools.audit_legacy_piston_clone_triggers import audit as trigger_audit
from tools.inspect_legacy_piston_clone_payloads import map_clone_material_source_positions
from tools.compare_legacy_piston_clone_saved_deltas import read_saved_states
from tools.rank_legacy_electromechanical_witnesses import _position
from tools.audit_legacy_piston_authored_inputs import spatial_mutator_contacts
from tools.inspect_legacy_piston_snapshot_inputs import DIRECTIONS, POWER_IDS

SCHEMA = "supracraft-legacy-clone-input-root-snapshot/1"
HORIZONTAL = ((1,0,0),(-1,0,0),(0,0,1),(0,0,-1))
SOURCE_FAMILIES = {"command_block","chain_command_block","repeating_command_block"}


def select_upstream_wire_positions(graph: dict, signature: str):
    """Only exact typed dust-above clone and horizontal dust-to-dust edges."""
    clone_ids = {cid for cid,_ in
                 map_clone_material_source_positions(graph,signature)}
    nodes=graph.get("nodes")
    if not isinstance(nodes,list):
        raise ValueError("invalid graph nodes")
    byid={n["node_id"]:n for n in nodes}
    if len(byid)!=len(nodes):
        raise ValueError("duplicate node ID")
    inputs=set()
    upstream=defaultdict(set)
    for row in graph["edges"].get("direct_redstone_edges",[]):
        a,b,etype=row.get("source"),row.get("target"),row.get("edge_type")
        if a not in byid or b not in byid:
            continue
        src,dst=byid[a],byid[b]
        sp,dp=_position(src),_position(dst)
        if sp is None or dp is None:
            continue
        d=tuple(dp[i]-sp[i] for i in range(3))
        if (etype=="legacy_dust_downward_command_power" and b in clone_ids
                and src.get("family")=="redstone_wire" and d==(0,-1,0)):
            inputs.add(a)
        if (etype=="legacy_dust_horizontal_connection"
                and src.get("family")==dst.get("family")=="redstone_wire"
                and d in HORIZONTAL):
            upstream[b].add(a)
    seen=set(inputs)
    q=list(inputs)
    while q:
        for prev in upstream.get(q.pop(),()):
            if prev not in seen:
                seen.add(prev)
                q.append(prev)
    witness=trigger_audit(graph,signature)
    if (len(seen)!=witness["named_reachable_upstream_wire_count"]
            or len(inputs)!=witness["named_typed_incoming_edge_counts"]
            .get("legacy_dust_downward_command_power",0)):
        raise ValueError("independent typed upstream wire parity mismatch")
    positions={_position(byid[n]) for n in seen}
    if None in positions or len(positions)!=len(seen):
        raise ValueError("duplicate or invalid upstream coordinate")
    return positions, len(inputs)


def collect_neighborhoods(wires):
    return {tuple(w[i]+d[i] for i in range(3))
            for w in wires for d in DIRECTIONS}


def classify_snapshot(wires, near, blocks):
    wire_state=Counter()
    neighbor_classes=Counter()
    missing_wires=0
    missing_neighbor=0
    for p in wires:
        state=blocks.get(p)
        if state is None:
            missing_wires+=1
        elif state[0]!=55:
            wire_state["saved_cell_not_redstone_wire"]+=1
        elif state[1]==0:
            wire_state["saved_wire_power_metadata_zero"]+=1
        else:
            wire_state["saved_wire_power_metadata_nonzero"]+=1
    for p in near:
        state=blocks.get(p)
        if state is None:
            missing_neighbor+=1
            continue
        block=state[0]
        label=POWER_IDS.get(block)
        if label is not None:
            neighbor_classes[label]+=1
        elif block==0:
            neighbor_classes["air"]+=1
        elif block==55:
            neighbor_classes["redstone_wire"]+=1
        elif block in (93,94):
            neighbor_classes["repeater_off" if block==93 else "repeater_on"]+=1
        else:
            neighbor_classes["other_saved_block_id"]+=1
    return {
        "upstream_wire_count":len(wires),
        "saved_upstream_wire_status_counts":dict(sorted(wire_state.items())),
        "unresolved_upstream_wire_states":missing_wires,
        "unique_six_face_neighbor_positions":len(near),
        "resolved_six_face_neighbor_positions":len(near)-missing_neighbor,
        "unresolved_six_face_neighbor_positions":missing_neighbor,
        "saved_neighbor_class_counts":dict(sorted(neighbor_classes.items())),
    }


def classify_authored_write_contacts(graph,wires,near):
    counts=Counter()
    total=0
    for node in graph["nodes"]:
        if node.get("family") not in SOURCE_FAMILIES:
            continue
        command=node.get("command") or {}
        writes=command.get("authored_world_state_writes") or []
        if not isinstance(writes,list):
            raise ValueError("untrusted compact writes")
        for w in writes:
            if w.get("write_kind")!="setblock":
                raise ValueError("untrusted write kind")
            if command.get("verb")!="setblock":
                raise ValueError("compact write bound to wrong verb")
            cls=w.get("state_class")
            if cls not in {"redstone_block","air"}:
                raise ValueError("unrecognized compact write class")
            pos=w.get("position")
            if (not isinstance(pos,list) or len(pos)!=3 or
                    any(type(v) is not int for v in pos)):
                raise ValueError("untrusted authored target")
            total+=1
            p=tuple(pos)
            if p in wires:
                counts[cls+"_on_upstream_wire_cell"]+=1
            elif p in near:
                counts[cls+"_adjacent_upstream_wire"]+=1
    return {
        "compact_authored_write_count_examined":total,
        "compact_writes_at_or_near_clone_input":dict(sorted(counts.items())),
    }


def audit(graph,signature,blocks):
    wires, direct=select_upstream_wire_positions(graph,signature)
    neighbors=collect_neighborhoods(wires)
    outcome=classify_snapshot(wires,neighbors,blocks)
    outcomes=classify_authored_write_contacts(graph,wires,neighbors)
    spatial=spatial_mutator_contacts(graph,wires|neighbors)
    return {
        "schema":SCHEMA,
        "analysis":"original_saved_six_wire_input_snapshot_and_compact_writes_only",
        "source_signature_sha256":signature,
        "clone_direct_typed_wire_ports":direct,
        **outcome,
        **outcomes,
        **spatial,
        "indirect_opaque_conduction":"UNQUALIFIED",
        "dynamic_noncompact_commands":"UNRESOLVED",
        "runtime_wire_power":"NOT_OBSERVED",
        "runtime_command_activation":"NOT_OBSERVED",
        "runtime_piston_motion":"NOT_OBSERVED",
        "minecraft_26_3_equivalence":"NOT_RUN",
        "gameplay_promoted":False,
        "limitations":[
            "Saved Redstone-wire metadata is stopped-world evidence, not live power.",
            "Other neighboring block IDs are not classified as proven conductors.",
            "Only exact named original typed wire paths and compact setblock writes are audited.",
            "Fill/clone static target footprints are geometry only; source material, execution and power remain unknown.",
            "Indirect solid conduction, dynamic fill/clone/execute, remote and scheduled writes remain unknown.",
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
    actual=hashlib.sha256(raw).hexdigest()
    if actual!=a.expected_graph_sha256:
        raise SystemExit("graph SHA mismatch")
    if hashlib.sha256(a.source_zip.read_bytes()).hexdigest()!=a.expected_source_sha256:
        raise SystemExit("original ZIP SHA mismatch")
    graph=json.loads(raw)
    wires,_=select_upstream_wire_positions(graph,a.signature)
    near=collect_neighborhoods(wires)
    saved=read_saved_states(a.source_zip,wires|near)
    result=audit(graph,a.signature,saved)
    result["source_graph_sha256"]=actual
    result["source_world_sha256"]=a.expected_source_sha256
    serialized=json.dumps(result,sort_keys=True,indent=2)+"\n"
    for private in ('"node_id"','"position"','"target_position"','"command"','original-world.zip'):
        if private in serialized:
            raise SystemExit("raw source leak")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(serialized,encoding="utf-8")
    print(json.dumps({
        "wires":result["upstream_wire_count"],
        "saved_wire_states":result["saved_upstream_wire_status_counts"],
        "neighbor_classes":result["saved_neighbor_class_counts"],
        "compact_contact_writes":result["compact_writes_at_or_near_clone_input"],
        "spatial_write_overlaps":result["spatial_write_footprint_candidate_overlaps"],
        "native":"NOT_RUN",
    },sort_keys=True))


if __name__=="__main__":
    main()
