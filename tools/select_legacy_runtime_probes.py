#!/usr/bin/env python3
"""Select bounded legacy runtime probes from a static causal graph.

Selection is structural and feedback-blind. It favors automatable player-like
sensors (lever/button/pressure plate) in components that also contain command,
state, actuator and feedback roles, while preserving diversity and explicit
selection reasons.
"""

from __future__ import annotations

import argparse, json
from collections import defaultdict, deque
from pathlib import Path

STABLE_SENSOR_FAMILIES = {
    "lever",
    "stone_button",
    "wooden_button",
}

PRESSURE_PLATE_SENSOR_FAMILIES = {
    "stone_pressure_plate",
    "wooden_pressure_plate",
    "light_weighted_pressure_plate",
    "heavy_weighted_pressure_plate",
}

TRAPPED_CHEST_SENSOR_FAMILIES = {"trapped_chest"}

SENSOR_MODES = {
    "stable": STABLE_SENSOR_FAMILIES,
    "pressure_plates": PRESSURE_PLATE_SENSOR_FAMILIES,
    "trapped_chest": TRAPPED_CHEST_SENSOR_FAMILIES,
}

def iter_edges(doc):
    raw=doc.get("edges",{})
    if isinstance(raw,list):
        yield from raw
        return
    for key,val in raw.items():
        if key.endswith("_count") or not isinstance(val,list):
            continue
        yield from val

def candidate_graph(doc):
    nodes={n["node_id"]:n for n in doc.get("nodes",[]) if n.get("node_id")}
    graph=defaultdict(set)
    for e in iter_edges(doc):
        if e.get("a") and e.get("b"):
            a,b=e["a"],e["b"]
            if a in nodes and b in nodes:
                graph[a].add(b); graph[b].add(a)
            continue
        a,b=e.get("source"),e.get("target")
        if a in nodes and b in nodes:
            graph[a].add(b)
    return nodes,graph

def component(graph,start):
    seen={start}; q=deque([start])
    while q:
        cur=q.popleft()
        for nxt in graph.get(cur,()):
            if nxt not in seen:
                seen.add(nxt); q.append(nxt)
    return seen

def role_set(node):
    return set(node.get("roles",[]))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",type=Path,required=True)
    ap.add_argument("--limit",type=int,default=5)
    ap.add_argument("--sensor-mode",choices=sorted(SENSOR_MODES),default="stable")
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    doc=json.loads(args.graph.read_text())
    nodes,graph=candidate_graph(doc)
    selected_families=SENSOR_MODES[args.sensor_mode]

    candidates=[]
    for nid,node in nodes.items():
        family=node.get("family")
        if family not in selected_families:
            continue
        members=component(graph,nid)
        member_nodes=[nodes[x] for x in members if x in nodes]
        roles=set().union(*(role_set(x) for x in member_nodes)) if member_nodes else set()
        families={x.get("family") for x in member_nodes}
        command_nodes=[
            {
              "node_id":x["node_id"],
              "position":x.get("position"),
              "family":x.get("family"),
              "verb":(x.get("command") or {}).get("verb"),
              "command_sha256":(x.get("command") or {}).get("sha256"),
            }
            for x in member_nodes if "command_block" in str(x.get("family",""))
        ]
        commands=len(command_nodes)
        feedback=sum(1 for x in member_nodes if "presentation_feedback" in role_set(x))
        actuators=sum(1 for x in member_nodes if "actuator" in role_set(x))
        state=sum(1 for x in member_nodes if role_set(x)&{"semantic_state","state_memory"})
        score=0
        score += 12 if commands else 0
        score += min(commands,10)
        score += 8 if feedback else 0
        score += min(feedback,5)
        score += 6 if actuators else 0
        score += min(actuators,5)
        score += 5 if state else 0
        score += min(state,5)
        score += min(len(members)//10,10)
        candidates.append({
          "node_id":nid,
          "position":node.get("position"),
          "family":family,
          "legacy_metadata":node.get("legacy_metadata"),
          "metadata_semantics":node.get("metadata_semantics",{}),
          "candidate_component_node_count":len(members),
          "candidate_component_command_blocks":commands,
          "candidate_component_commands":sorted(command_nodes,key=lambda x:x["node_id"])[:25],
          "candidate_component_feedback_nodes":feedback,
          "candidate_component_actuators":actuators,
          "candidate_component_state_nodes":state,
          "candidate_component_families":sorted(x for x in families if x),
          "selection_score":score,
          "selection_basis":"feedback-blind structural candidate graph"
        })

    candidates.sort(key=lambda x:(-x["selection_score"],x["family"],x["node_id"]))

    # Preserve mechanism diversity before filling remaining slots by score.
    selected=[]; used_families=set()
    for c in candidates:
        if c["family"] in used_families:
            continue
        if c["candidate_component_command_blocks"]==0:
            continue
        selected.append(c); used_families.add(c["family"])
        if len(selected)>=args.limit:break
    if len(selected)<args.limit:
        used={x["node_id"] for x in selected}
        for c in candidates:
            if c["node_id"] in used or c["candidate_component_command_blocks"]==0:
                continue
            selected.append(c);used.add(c["node_id"])
            if len(selected)>=args.limit:break

    deferred=set().union(*SENSOR_MODES.values())-set(selected_families)
    mode_constraints={
      "stable":"Stable block-state activation sensors (lever/buttons) only.",
      "pressure_plates":"Pressure plates only; activation must use live entity occupancy, not metadata mutation.",
      "trapped_chest":"Trapped chests only; opening-power qualification must remain separate from comparator inventory/fullness state.",
    }
    result={
      "schema":"supracraft-legacy-runtime-probe-selection/1",
      "source_graph_schema":doc.get("schema"),
      "selection_kind":"feedback_blind_structural",
      "sensor_mode":args.sensor_mode,
      "candidate_count":len(candidates),
      "selected_count":len(selected),
      "selected":selected,
      "deferred_sensor_families":sorted(deferred),
      "constraints":[
        mode_constraints[args.sensor_mode],
        "Selection uses structural causal evidence only and does not read human feedback.",
        "Only candidates whose structural component contains command blocks are selected.",
        "Each runtime probe must start from a fresh copy of the exact original world.",
        "Probe outcome is mechanism evidence, not a qualitative judgment."
      ]
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
