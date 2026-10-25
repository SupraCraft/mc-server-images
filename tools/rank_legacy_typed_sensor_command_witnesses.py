#!/usr/bin/env python3
"""Strict typed-port sensor->command original Java 1.8.8 witness ranking.

Independent of loose component adjacency and of historical native command
attribution. No source coordinates, raw commands, node identifiers, hashes,
inventories or saved world bytes in the public derived artifact.
These are source-static candidate paths, NEVER observed gameplay effects.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path

from tools.classify_legacy_gameplay_motifs import SOURCE_SCHEMA
from tools.rank_legacy_electromechanical_witnesses import _position

SCHEMA="supracraft-legacy-typed-sensor-command-candidates/1"
SENSORS={"lever","stone_button","wooden_button","stone_pressure_plate",
         "wooden_pressure_plate","light_weighted_pressure_plate",
         "heavy_weighted_pressure_plate"}
PLATES={"stone_pressure_plate","wooden_pressure_plate",
        "light_weighted_pressure_plate","heavy_weighted_pressure_plate"}
BUTTONS={"stone_button","wooden_button"}
COMMANDS={"command_block"}
HORIZONTAL={(1,0,0),(-1,0,0),(0,0,1),(0,0,-1)}
FACES=HORIZONTAL|{(0,1,0),(0,-1,0)}
MAX_WIRES_PER_PATH=96
ALIASES={
    "legacy_sensor_direct_dust_power":"sensor_wire",
    "legacy_dust_horizontal_connection":"wire_wire",
    "legacy_dust_downward_command_power":"wire_command",
    "legacy_dust_direct_component_power":"wire_command",
    "legacy_button_attached_support_power":"button_command_support",
    "legacy_pressure_plate_support_power":"plate_command_support",
}


def _face(a,b):
    pa,pb=_position(a),_position(b)
    if pa is None or pb is None:
        return None
    return tuple(pb[i]-pa[i] for i in range(3))


def _support(sensor,d):
    sem=sensor.get("metadata_semantics") or {}
    v=sem.get("support_vector")
    return (isinstance(v,list) and len(v)==3 and
            all(type(x) is int for x in v) and
            tuple(v)==d and d in FACES)


def _is_typed(src,dst,edge):
    sf,df=src["family"],dst["family"]
    et=edge.get("edge_type")
    d=_face(src,dst)
    if d is None or d not in FACES:
        return None
    if et=="legacy_sensor_direct_dust_power":
        return "sensor_wire" if sf in SENSORS and df=="redstone_wire" else None
    if et=="legacy_dust_horizontal_connection":
        return "wire_wire" if sf==df=="redstone_wire" and d in HORIZONTAL else None
    if et=="legacy_dust_downward_command_power":
        return "wire_command" if sf=="redstone_wire" and df in COMMANDS and d==(0,-1,0) else None
    if et=="legacy_dust_direct_component_power":
        return "wire_command" if sf=="redstone_wire" and df in COMMANDS and d in HORIZONTAL else None
    if et=="legacy_button_attached_support_power":
        return "button_command_support" if sf in BUTTONS and df in COMMANDS and _support(src,d) else None
    if et=="legacy_pressure_plate_support_power":
        return "plate_command_support" if sf in PLATES and df in COMMANDS and _support(src,d) else None
    return None


def rank(graph):
    if not isinstance(graph,dict) or graph.get("schema")!=SOURCE_SCHEMA:
        raise ValueError("unaccepted source graph")
    nodes,edges=graph.get("nodes"),graph.get("edges")
    if not isinstance(nodes,list) or not isinstance(edges,dict):
        raise ValueError("missing original graph")
    byid={}
    for node in nodes:
        if not isinstance(node,dict) or not isinstance(node.get("node_id"),str) or not isinstance(node.get("family"),str):
            raise ValueError("malformed graph node")
        ident=node["node_id"]
        if ident in byid:
            raise ValueError("duplicate original node identity")
        if _position(node) is None:
            raise ValueError("unverifiable original source position")
        byid[ident]=node
    rows=edges.get("direct_redstone_edges")
    if not isinstance(rows,list):
        raise ValueError("original typed direct-redstone collection missing")
    by_kind=defaultdict(list)
    rejected=Counter()
    for e in rows:
        if not isinstance(e,dict):
            raise ValueError("malformed original named edge")
        a,b=e.get("source"),e.get("target")
        et=e.get("edge_type")
        if et not in ALIASES:
            continue
        if a not in byid or b not in byid:
            rejected["unverified_typed_edge_endpoint"]+=1
            continue
        kind=_is_typed(byid[a],byid[b],e)
        if kind is None:
            rejected["invalid_typed_port_or_orientation"]+=1
            continue
        by_kind[kind].append((a,b))
    # Count only particular directed witnesses, never all connected-component members.
    signal=defaultdict(set)
    for a,b in by_kind["wire_wire"]:
        signal[a].add(b)
    sink=defaultdict(set)
    for a,b in by_kind["wire_command"]:
        sink[a].add(b)
    paths=Counter()
    root_coverage=Counter()
    unique_sources=set()
    matched_sinks=set()
    accepted_routes=set()  # Ephemeral identity-based unique (sensor,command,modality)
    bounded=0
    duplicate_routes=0
    # One directed walk per sensor, not per sensor-wire starting edge. This
    # prevents fan-in/fan-out wiring from fabricating extra "mechanisms".
    starts=defaultdict(set)
    for a,b in by_kind["sensor_wire"]:
        starts[a].add(b)
    for a,roots in starts.items():
        sensor=byid[a]
        distances={root:0 for root in roots}
        q=deque(sorted(roots))
        while q:
            now=q.popleft()
            depth=distances[now]
            for cmd in sink[now]:
                category="wire_path_"+sensor["family"]
                key=(a,cmd,"wire_path")
                if key in accepted_routes:
                    duplicate_routes+=1
                    continue
                accepted_routes.add(key)
                paths[category]+=1
                unique_sources.add(a)
                matched_sinks.add(cmd)
                root_coverage[sensor["family"]]+=1
            if depth>=MAX_WIRES_PER_PATH:
                bounded+=len(signal[now])
                continue
            for nxt in signal[now]:
                if nxt not in distances:
                    distances[nxt]=depth+1
                    q.append(nxt)
    for kind in ("button_command_support","plate_command_support"):
        for a,b in by_kind[kind]:
            key=(a,b,kind)
            if key in accepted_routes:
                duplicate_routes+=1
                continue
            accepted_routes.add(key)
            family=byid[a]["family"]
            paths["direct_support_"+family]+=1
            unique_sources.add(a)
            matched_sinks.add(b)
            root_coverage[family]+=1
    return {
        "schema":SCHEMA,
        "analysis":"original_1_8_8_source_static_directional_sensor_command_paths",
        "typed_edge_counts":dict(sorted((k,len(v)) for k,v in by_kind.items())),
        "rejected_typed_edge_counts":dict(sorted(rejected.items())),
        "accepted_sensor_command_path_counts":dict(sorted(paths.items())),
        "accepted_path_count":sum(paths.values()),
        "source_sensor_count":len(unique_sources),
        "target_command_count":len(matched_sinks),
        "sensor_family_path_counts":dict(sorted(root_coverage.items())),
        "bounded_wire_walk_events":bounded,
        "duplicate_route_projections_discarded":duplicate_routes,
        "runtime_native_sensor_activation":"NOT_RUN",
        "exclusive_command_causality":"NOT_PROVEN",
        "runtime_target_effect":"NOT_OBSERVED",
        "modern_26_3_parity":"NOT_RUN",
        "gameplay_promoted":False,
        "limitations":[
            "Only exact typed directed source graph paths; no generic proximity shortcuts.",
            "Repeated sensor-to-command wiring routes are deduplicated by source, destination and modality.",
            "An accepted sensor-to-command path is not observed powered state or command execution.",
            "Source sensor actuation, author intent, runtime feedback and world-state changes are not proven.",
            "Indirect opaque-solid conduction and dynamic command chains are incomplete.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--graph",type=Path,required=True)
    p.add_argument("--expected-graph-sha256",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        raise SystemExit("refuse overwrite")
    data=a.graph.read_bytes()
    actual=hashlib.sha256(data).hexdigest()
    if actual!=a.expected_graph_sha256:
        raise SystemExit("frozen original causal graph SHA mismatch")
    result=rank(json.loads(data))
    result["source_graph_sha256"]=actual
    text=json.dumps(result,sort_keys=True,indent=2)+"\n"
    for forbidden in ('"node_id"','"position"','"command"','"raw"','original-world.zip'):
        if forbidden in text:
            raise SystemExit("raw source/privacy leakage")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(text,encoding="utf-8")
    print(json.dumps({
        "accepted_path_count":result["accepted_path_count"],
        "source_sensors":result["source_sensor_count"],
        "target_commands":result["target_command_count"],
        "accepted_path_types":result["accepted_sensor_command_path_counts"],
        "rejected":result["rejected_typed_edge_counts"],
        "native":"NOT_RUN",
    },sort_keys=True))


if __name__=="__main__":
    main()
