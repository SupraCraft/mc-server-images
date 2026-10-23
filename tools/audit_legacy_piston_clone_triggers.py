#!/usr/bin/env python3
"""Read-only original Java 1.8.8 Redstone trigger candidates for CORE clones.

Never asserts command execution. Only exact-source graph typed edges and
original coordinate/metadata-consistent ports are counted. No identifiers,
source command strings or positions in derived result.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from tools.inspect_legacy_piston_clone_payloads import map_clone_material_source_positions
from tools.classify_legacy_gameplay_motifs import SENSORS
from tools.rank_legacy_electromechanical_witnesses import _position

SCHEMA="supracraft-legacy-clone-trigger-static/1"
INCOMING_TYPES={
    "legacy_dust_direct_component_power",
    "legacy_dust_downward_command_power",
    "legacy_button_attached_support_power",
    "legacy_pressure_plate_support_power",
    "oriented_front_output_candidate",
    "legacy_setblock_redstone_block_direct_command_power",
}
WIRE_CONNECT="legacy_dust_horizontal_connection"
SENSOR_CONNECT="legacy_sensor_direct_dust_power"
WIRE={"redstone_wire"}
REPEATERS={"repeater_off","repeater_on"}
COMMAND={"command_block","chain_command_block","repeating_command_block"}


def _is_direct(source: dict, target: dict, et: str) -> bool:
    a,b=_position(source),_position(target)
    if a is None or b is None:
        return False
    d=tuple(b[i]-a[i] for i in range(3))
    af=source.get("family")
    if et=="legacy_dust_downward_command_power":
        return af in WIRE and d==(0,-1,0)
    if et=="legacy_dust_direct_component_power":
        return af in WIRE and d[1]==0 and abs(d[0])+abs(d[2])==1
    if et in {"legacy_button_attached_support_power",
              "legacy_pressure_plate_support_power"}:
        return (af in SENSORS and d==tuple(
            (source.get("metadata_semantics") or {}).get("support_vector", ())
        ))
    if et=="oriented_front_output_candidate":
        facing=(source.get("metadata_semantics") or {}).get("facing_vector")
        return (af in REPEATERS and isinstance(facing,list)
                and len(facing)==3 and all(type(v) is int for v in facing)
                and d==tuple(-v for v in facing))
    if et=="legacy_setblock_redstone_block_direct_command_power":
        return sum(abs(x) for x in d) >= 1  # dynamic authored target, separately unverified
    return False


def audit(graph:dict,signature:str) -> dict:
    pairs=map_clone_material_source_positions(graph,signature)
    clones={cid for cid,_ in pairs}
    byid={n["node_id"]:n for n in graph["nodes"]}
    if len(byid)!=len(graph["nodes"]):
        raise ValueError("duplicate original node")
    if any(byid.get(c,{}).get("family") not in COMMAND for c in clones):
        raise ValueError("source clone identity not command block")
    incoming=Counter()
    perclone=Counter()
    roots=set()
    rejected=0
    wire_incoming=defaultdict(set)
    sensor_link=defaultdict(set)
    direct_rows=graph["edges"].get("direct_redstone_edges",[])
    for row in direct_rows:
        if not isinstance(row,dict):
            raise ValueError("bad typed edge")
        src,dst,et=row.get("source"),row.get("target"),row.get("edge_type")
        if src not in byid or dst not in byid:
            continue
        a,b=byid[src],byid[dst]
        if et==WIRE_CONNECT and a.get("family") in WIRE and b.get("family") in WIRE:
            pa,pb=_position(a),_position(b)
            if pa is not None and pb is not None and pa[1]==pb[1] and abs(pa[0]-pb[0])+abs(pa[2]-pb[2])==1:
                wire_incoming[dst].add(src)
        if et==SENSOR_CONNECT and a.get("family") in SENSORS and b.get("family") in WIRE:
            pa,pb=_position(a),_position(b)
            if pa is not None and pb is not None and sum(abs(pa[i]-pb[i]) for i in range(3))==1:
                sensor_link[dst].add(src)
    for group,types in [
        ("direct_redstone_edges",INCOMING_TYPES),
        ("oriented_signal_candidates",INCOMING_TYPES),
        ("command_authored_redstone_edges",INCOMING_TYPES),
    ]:
        rows=graph["edges"].get(group,[])
        if not isinstance(rows,list):
            raise ValueError("invalid original edge collection")
        for row in rows:
            if not isinstance(row,dict):
                raise ValueError("bad incoming edge")
            src,dst,et=row.get("source"),row.get("target"),row.get("edge_type")
            if dst not in clones or src not in byid:
                continue
            if et not in types or not _is_direct(byid[src],byid[dst],et):
                rejected+=1
                continue
            incoming[et]+=1
            perclone[dst]+=1
            if byid[src].get("family") in WIRE:
                roots.add(src)
    sensors=set()
    q=list(roots)
    reached=set(q)
    while q:
        u=q.pop()
        for sensor in sensor_link.get(u,()):
            sensors.add(sensor)
        for v in wire_incoming.get(u,()):
            if v not in reached:
                reached.add(v)
                q.append(v)
    if sensors:
        label="NAMED_LOCAL_SENSOR_TO_CLONE_STATIC_CANDIDATE"
    elif incoming:
        label="NAMED_DIRECT_CLONE_POWER_STATIC_CANDIDATE"
    else:
        label="NO_SUPPORTED_TYPED_CLONE_ACTIVATION_INPUT"
    return {
        "schema":SCHEMA,
        "analysis":"source_graph_typed_clone_activation_candidates_only",
        "source_signature_sha256":signature,
        "candidate_clone_count":len(clones),
        "clones_with_typed_incoming":len(perclone),
        "named_typed_incoming_edge_counts":dict(sorted(incoming.items())),
        "named_reachable_upstream_wire_count":len(reached),
        "named_reachable_sensor_count":len(sensors),
        "rejected_or_unrecognized_incoming_rows":rejected,
        "source_trigger_classification":label,
        "runtime_clone_command_execution":"NOT_OBSERVED",
        "runtime_wire_power":"NOT_OBSERVED",
        "runtime_piston_motion":"NOT_OBSERVED",
        "modern_26_3_equivalence":"NOT_RUN",
        "gameplay_promoted":False,
        "limits":[
            "Only named source-graph input edges; opaque solid conduction is incomplete.",
            "Dynamic command chains, player activation and scheduled block updates remain unknown.",
            "Static sensor links do not establish actual powered state or command execution.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--graph",type=Path,required=True)
    p.add_argument("--expected-graph-sha256",required=True)
    p.add_argument("--signature",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        raise SystemExit("refuse overwrite")
    raw=a.graph.read_bytes()
    h=hashlib.sha256(raw).hexdigest()
    if h!=a.expected_graph_sha256:
        raise SystemExit("immutable original graph mismatch")
    result=audit(json.loads(raw),a.signature)
    result["source_graph_sha256"]=h
    serial=json.dumps(result,indent=2,sort_keys=True)+"\n"
    for token in ('"node_id"','"position"','"target_position"','"command"','"raw"'):
        if token in serial:
            raise SystemExit("source input egress rejected")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(serial,encoding="utf-8")
    print(json.dumps({
        "clones":result["candidate_clone_count"],
        "incoming":result["named_typed_incoming_edge_counts"],
        "named_upstream_sensors":result["named_reachable_sensor_count"],
        "classification":result["source_trigger_classification"],
        "native":"NOT_RUN",
    },sort_keys=True))


if __name__=="__main__":
    main()
