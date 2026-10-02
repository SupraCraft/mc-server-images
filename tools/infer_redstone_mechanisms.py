#!/usr/bin/env python3
"""Infer a conservative redstone mechanism/netlist from a causal-machinery graph.

This tool separates:
1. physical/layout topology;
2. source-derived directed causal links;
3. functional mechanism *candidates*;
4. runtime validation state supplied separately.

It never treats a familiar-looking topology as proven behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict, deque
from pathlib import Path

SCHEMA="supracraft-redstone-mechanism-inference/1"

PRIMITIVE_BY_BLOCK={
    "minecraft:redstone_wire":"wire",
    "minecraft:repeater":"buffer_delay",
    "minecraft:comparator":"analog_comparator",
    "minecraft:redstone_torch":"inverter",
    "minecraft:redstone_wall_torch":"inverter",
    "minecraft:redstone_block":"constant_power_source",
    "minecraft:lever":"manual_state_input",
    "minecraft:stone_button":"pulse_input",
    "minecraft:oak_button":"pulse_input",
    "minecraft:stone_pressure_plate":"occupancy_input",
    "minecraft:light_weighted_pressure_plate":"weighted_occupancy_input",
    "minecraft:heavy_weighted_pressure_plate":"weighted_occupancy_input",
    "minecraft:tripwire":"contact_input",
    "minecraft:tripwire_hook":"contact_input",
    "minecraft:observer":"change_detector",
    "minecraft:target":"impact_input",
    "minecraft:piston":"linear_actuator",
    "minecraft:sticky_piston":"linear_actuator",
    "minecraft:redstone_lamp":"visual_output",
    "minecraft:note_block":"audio_output",
    "minecraft:dispenser":"item_actuator",
    "minecraft:dropper":"item_actuator",
    "minecraft:hopper":"item_storage_transport",
    "minecraft:chest":"storage",
    "minecraft:trapped_chest":"storage_sensor",
    "minecraft:barrel":"storage",
    "minecraft:command_block":"programmable_processor",
    "minecraft:chain_command_block":"programmable_processor",
    "minecraft:repeating_command_block":"programmable_processor",
}

CAUSAL_EDGE_TYPES={
    "dust_connection",
    "oriented_rear_input",
    "oriented_front_output",
    "container_inventory_signal_read",
    "open_emits_redstone_power_candidate",
    "chain_facing_successor",
    "conditional_predecessor_success_dependency",
    "command_world_target",
    "command_function_call",
    "command_function_schedule",
    "scoreboard_read",
    "scoreboard_write",
}

STANDARD_MECHANISM_VOCABULARY=[
    {
        "family":"transmission",
        "members":["wire_path","buffered_delay_line","diode_like_path"],
        "recognition_status":"partially_implemented",
    },
    {
        "family":"combinational_logic",
        "members":["not","and","or","xor","nand","nor","xnor","multiplexer"],
        "recognition_status":"vocabulary_only_pending_templates",
    },
    {
        "family":"pulse",
        "members":["edge_detector","monostable","pulse_limiter","pulse_extender"],
        "recognition_status":"vocabulary_only_pending_templates",
    },
    {
        "family":"memory",
        "members":["rs_latch","t_flip_flop","d_latch","counter"],
        "recognition_status":"vocabulary_only_pending_templates",
    },
    {
        "family":"clock",
        "members":["oscillator","repeater_clock","comparator_clock","hopper_clock"],
        "recognition_status":"cycle_candidate_only",
    },
    {
        "family":"mechanical",
        "members":["piston_sequence","door","elevator","item_transport","sorter"],
        "recognition_status":"vocabulary_only_pending_templates",
    },
    {
        "family":"programmable",
        "members":["command_actuation_chain","command_state_machine"],
        "recognition_status":"partially_implemented",
    },
]


def pos_tuple(node: dict):
    p=node.get("position")
    if not isinstance(p,list) or len(p)!=3:
        return None
    if not all(isinstance(x,(int,float)) for x in p):
        return None
    return tuple(int(x) for x in p)


def short_block(block: str) -> str:
    return block.split(":",1)[-1] if block else "unknown"


def primitive(node: dict) -> str:
    block=node.get("block")
    if block in PRIMITIVE_BY_BLOCK:
        return PRIMITIVE_BY_BLOCK[block]
    roles=set(node.get("roles") or [])
    if "sensor_input" in roles:
        return "input_sensor"
    if "actuator" in roles:
        return "actuator"
    if "presentation_feedback" in roles:
        return "presentation_output"
    if "state_memory" in roles:
        return "state_storage"
    if "signal_transport" in roles:
        return "signal_transport"
    return "other"


def adjacency_links(nodes: dict[str,dict]) -> list[dict]:
    by_pos={pos_tuple(n):nid for nid,n in nodes.items() if pos_tuple(n) is not None}
    links=[]
    for p,nid in sorted(by_pos.items()):
        x,y,z=p
        for q in ((x+1,y,z),(x,y+1,z),(x,y,z+1)):
            other=by_pos.get(q)
            if other:
                links.append({"a":nid,"b":other,"relation":"face_adjacent"})
    return links


def causal_links(graph: dict, block_ids: set[str]) -> list[dict]:
    out=[]
    for edge in graph.get("edges",[]):
        s=edge.get("source")
        t=edge.get("target")
        if s not in block_ids or t not in block_ids:
            continue
        out.append({
            "source":s,
            "target":t,
            "edge_type":edge.get("edge_type"),
            "certainty":edge.get("certainty","unknown"),
        })
    return out


def components(nodes: dict[str,dict], layout: list[dict]) -> list[list[str]]:
    und=defaultdict(set)
    for link in layout:
        a,b=link["a"],link["b"]
        und[a].add(b); und[b].add(a)
    seen=set()
    result=[]
    for start in sorted(nodes):
        if start in seen:
            continue
        q=deque([start]); seen.add(start); members=[]
        while q:
            cur=q.popleft()
            members.append(cur)
            for nxt in sorted(und.get(cur,())):
                if nxt not in seen:
                    seen.add(nxt); q.append(nxt)
        result.append(sorted(members))
    return result


def directed_cycle(nodes: set[str], links: list[dict]) -> bool:
    adj=defaultdict(list)
    for e in links:
        if e["source"] in nodes and e["target"] in nodes:
            adj[e["source"]].append(e["target"])
    color={n:0 for n in nodes}
    def dfs(n):
        color[n]=1
        for q in adj.get(n,()):
            if color.get(q,0)==1:
                return True
            if color.get(q,0)==0 and dfs(q):
                return True
        color[n]=2
        return False
    return any(color[n]==0 and dfs(n) for n in sorted(nodes))


def path_exists(starts:set[str], goals:set[str], links:list[dict], allowed:set[str]):
    adj=defaultdict(list)
    for e in links:
        if e["source"] in allowed and e["target"] in allowed:
            adj[e["source"]].append(e["target"])
    q=deque(sorted(starts & allowed))
    seen=set(q)
    while q:
        n=q.popleft()
        if n in goals:
            return True
        for nxt in adj.get(n,()):
            if nxt not in seen:
                seen.add(nxt); q.append(nxt)
    return False


def infer_component(index:int, members:list[str], nodes:dict[str,dict], links:list[dict]):
    member_set=set(members)
    block_counts=Counter(nodes[n].get("block","unknown") for n in members)
    primitive_counts=Counter(primitive(nodes[n]) for n in members)
    positions=[pos_tuple(nodes[n]) for n in members if pos_tuple(nodes[n]) is not None]
    roles={n:set(nodes[n].get("roles") or []) for n in members}
    inputs={n for n in members if "sensor_input" in roles[n] or primitive(nodes[n]) in {
        "constant_power_source","manual_state_input","pulse_input","occupancy_input",
        "weighted_occupancy_input","contact_input","change_detector","impact_input"
    }}
    outputs={n for n in members if (
        "actuator" in roles[n] or "presentation_feedback" in roles[n]
        or primitive(nodes[n]) in {
            "linear_actuator","visual_output","audio_output","item_actuator",
            "programmable_processor"
        }
    )}
    repeaters={n for n in members if nodes[n].get("block")=="minecraft:repeater"}
    command_nodes={n for n in members if "command_block" in nodes[n].get("block","")}

    candidates=[]
    if path_exists(inputs,outputs,links,member_set):
        candidates.append({
            "mechanism":"transmission_path",
            "confidence":"structural_candidate",
            "evidence":["directed_input_to_output_path"],
        })
    if repeaters and path_exists(inputs,outputs,links,member_set):
        candidates.append({
            "mechanism":"buffered_delay_line",
            "confidence":"structural_candidate",
            "evidence":["repeater_present","directed_input_to_output_path"],
        })
    if command_nodes and path_exists(inputs,command_nodes,links,member_set):
        candidates.append({
            "mechanism":"command_actuation_chain",
            "confidence":"structural_candidate",
            "evidence":["directed_input_to_command_path"],
        })
    if directed_cycle(member_set,links):
        candidates.append({
            "mechanism":"oscillator_or_state_loop",
            "confidence":"structural_candidate_only",
            "evidence":["directed_cycle"],
            "boundary":"cycle alone does not establish oscillation, memory, period, or stability",
        })

    if positions:
        bounds={
            "min":[min(p[i] for p in positions) for i in range(3)],
            "max":[max(p[i] for p in positions) for i in range(3)],
        }
    else:
        bounds=None

    signature_rows=[]
    for n in sorted(members):
        node=nodes[n]
        signature_rows.append({
            "node_id":n,
            "block":node.get("block"),
            "properties":node.get("properties") or {},
            "primitive":primitive(node),
        })
    for e in sorted(
        (x for x in links if x["source"] in member_set and x["target"] in member_set),
        key=lambda x:(x["source"],x["target"],str(x["edge_type"])),
    ):
        signature_rows.append({"edge":e})
    topology_sha256=hashlib.sha256(
        json.dumps(signature_rows,sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()

    return {
        "component_id":f"mechanism::{index}",
        "node_count":len(members),
        "bounds":bounds,
        "topology_sha256":topology_sha256,
        "block_counts":dict(sorted(block_counts.items())),
        "primitive_counts":dict(sorted(primitive_counts.items())),
        "input_nodes":sorted(inputs),
        "output_nodes":sorted(outputs),
        "nodes":[
            {
                "node_id":n,
                "position":nodes[n].get("position"),
                "block":nodes[n].get("block"),
                "properties":nodes[n].get("properties") or {},
                "primitive":primitive(nodes[n]),
                "roles":sorted(nodes[n].get("roles") or []),
            }
            for n in members
        ],
        "causal_links":[
            e for e in links if e["source"] in member_set and e["target"] in member_set
        ],
        "mechanism_candidates":candidates,
        "runtime_validation":{
            "status":"not_yet_correlated",
            "boundary":"static topology/mechanism inference is not runtime causal proof",
        },
    }


def dot_escape(text:str)->str:
    return text.replace("\\","\\\\").replace('"','\\"')


def emit_dot(doc:dict)->str:
    rows=[
        "digraph redstone_mechanism {",
        "  rankdir=LR;",
        '  graph [label="SupraCraft inferred redstone schematic", labelloc=t];',
        '  node [shape=box];',
    ]
    for comp in doc["components"]:
        rows.append(f'  subgraph "cluster_{dot_escape(comp["component_id"])}" {{')
        label=", ".join(x["mechanism"] for x in comp["mechanism_candidates"]) or "unclassified topology"
        rows.append(f'    label="{dot_escape(label)}";')
        for n in comp["nodes"]:
            p=n.get("position")
            pos=",".join(str(x) for x in p) if p else "?"
            text=f'{short_block(n.get("block",""))}\\n{n["primitive"]}\\n{pos}'
            rows.append(f'    "{dot_escape(n["node_id"])}" [label="{dot_escape(text)}"];')
        for e in comp["causal_links"]:
            lbl=f'{e.get("edge_type")} / {e.get("certainty")}'
            rows.append(
                f'    "{dot_escape(e["source"])}" -> "{dot_escape(e["target"])}" '
                f'[label="{dot_escape(lbl)}"];'
            )
        rows.append("  }")
    rows.append("}")
    return "\n".join(rows)+"\n"


def infer(graph:dict)->dict:
    block_nodes={
        n["node_id"]:n
        for n in graph.get("nodes",[])
        if isinstance(n,dict) and n.get("block") and n.get("node_id")
    }
    layout=adjacency_links(block_nodes)
    links=causal_links(graph,set(block_nodes))
    comps=components(block_nodes,layout)
    result=[
        infer_component(i,members,block_nodes,links)
        for i,members in enumerate(sorted(comps,key=lambda x:(-len(x),x)),1)
    ]
    return {
        "schema":SCHEMA,
        "source_schema":graph.get("schema"),
        "analysis_kind":"static_topology_to_functional_mechanism_candidates",
        "block_node_count":len(block_nodes),
        "layout_link_count":len(layout),
        "causal_link_count":len(links),
        "component_count":len(result),
        "standard_mechanism_vocabulary":STANDARD_MECHANISM_VOCABULARY,
        "components":result,
        "limitations":[
            "physical resemblance does not prove functional identity",
            "runtime timing, signal strength, update ordering, quasi-connectivity, and observer effects require runtime evidence",
            "named mechanisms remain candidates until their template preconditions and behavioral truth table or temporal contract are validated",
            "version-specific behavior must be qualified independently",
        ],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--dot-output",type=Path)
    args=ap.parse_args()
    graph=json.loads(args.graph.read_text())
    doc=infer(graph)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n")
    if args.dot_output:
        args.dot_output.parent.mkdir(parents=True,exist_ok=True)
        args.dot_output.write_text(emit_dot(doc))
    print(json.dumps({
        "schema":doc["schema"],
        "block_node_count":doc["block_node_count"],
        "component_count":doc["component_count"],
        "candidate_count":sum(
            len(c["mechanism_candidates"]) for c in doc["components"]
        ),
    },sort_keys=True))


if __name__=="__main__":
    main()
