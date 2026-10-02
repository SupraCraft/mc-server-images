#!/usr/bin/env python3
"""Build an EDA-style redstone netlist from a SupraCraft modern machinery graph.

The netlist is deliberately conservative:
- contiguous redstone dust is collapsed into named nets;
- non-dust machinery remains as explicit components;
- ports carry provenance/certainty;
- motif matches are hypotheses with required runtime contracts;
- exact block topology remains available upstream and is never replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path

SCHEMA="supracraft-redstone-netlist/1"

HORIZONTAL={
    "north":(0,0,-1),
    "east":(1,0,0),
    "south":(0,0,1),
    "west":(-1,0,0),
}
DIR6={**HORIZONTAL,"up":(0,1,0),"down":(0,-1,0)}

SOURCE_PRIMITIVES={
    "constant_power_source","manual_state_input","pulse_input",
    "occupancy_input","weighted_occupancy_input","contact_input",
    "change_detector","impact_input","input_sensor",
}
SINK_PRIMITIVES={
    "programmable_processor","linear_actuator","visual_output","audio_output",
    "item_actuator","actuator","presentation_output",
}

BLOCK_PRIMITIVE={
    "minecraft:redstone_block":"constant_power_source",
    "minecraft:redstone_wire":"wire",
    "minecraft:repeater":"buffer_delay",
    "minecraft:comparator":"analog_comparator",
    "minecraft:redstone_torch":"inverter",
    "minecraft:redstone_wall_torch":"inverter",
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
    "minecraft:command_block":"programmable_processor",
    "minecraft:chain_command_block":"programmable_processor",
    "minecraft:repeating_command_block":"programmable_processor",
    "minecraft:piston":"linear_actuator",
    "minecraft:sticky_piston":"linear_actuator",
    "minecraft:redstone_lamp":"visual_output",
    "minecraft:note_block":"audio_output",
    "minecraft:dispenser":"item_actuator",
    "minecraft:dropper":"item_actuator",
    "minecraft:crafter":"item_actuator",
    "minecraft:hopper":"item_storage_transport",
    "minecraft:chest":"storage",
    "minecraft:trapped_chest":"storage_sensor",
    "minecraft:barrel":"storage",
}

RUNTIME_CONTRACTS={
    "wire_transmission_path":
        "input transition must produce the predicted downstream transition with no active component between source and sink",
    "repeater_delay_line":
        "input transition must traverse repeater input/output ports and produce a downstream transition after a positive server-tick delay consistent with the configured delay setting",
    "not_gate":
        "exercise input low and high; qualified output must be high for low input and low for high input, including reset back to high",
}

D4=(
    (1,0,0,1),    # identity
    (0,-1,1,0),   # 90
    (-1,0,0,-1),  # 180
    (0,1,-1,0),   # 270
    (-1,0,0,1),   # reflect x
    (1,0,0,-1),   # reflect z
    (0,1,1,0),    # reflect diagonal
    (0,-1,-1,0),  # reflect anti-diagonal
)


def add(a,b):
    return tuple(a[i]+b[i] for i in range(3))


def pos(node):
    p=node.get("position")
    if not isinstance(p,list) or len(p)!=3:
        return None
    if not all(isinstance(x,(int,float)) for x in p):
        return None
    return tuple(int(x) for x in p)


def primitive(node):
    block=node.get("block")
    if block in BLOCK_PRIMITIVE:
        return BLOCK_PRIMITIVE[block]
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


def wire_components(nodes,edges):
    wire_ids={nid for nid,n in nodes.items() if n.get("block")=="minecraft:redstone_wire"}
    adj=defaultdict(set)
    for e in edges:
        if e.get("edge_type")!="dust_connection":
            continue
        s,t=e.get("source"),e.get("target")
        if s in wire_ids and t in wire_ids:
            adj[s].add(t); adj[t].add(s)
    seen=set(); groups=[]
    for start in sorted(wire_ids):
        if start in seen:
            continue
        q=deque([start]); seen.add(start); group=[]
        while q:
            cur=q.popleft(); group.append(cur)
            for nxt in sorted(adj.get(cur,())):
                if nxt not in seen:
                    seen.add(nxt); q.append(nxt)
        groups.append(sorted(group))
    return groups


def bounds_for(ids,nodes):
    ps=[pos(nodes[n]) for n in ids if pos(nodes[n]) is not None]
    if not ps:
        return None
    return {
        "min":[min(p[i] for p in ps) for i in range(3)],
        "max":[max(p[i] for p in ps) for i in range(3)],
    }


def component_port_role(node,net_wire_positions):
    """Return one or more bounded port descriptors attaching this component to a net."""
    p=pos(node)
    if p is None:
        return []
    block=node.get("block")
    props=node.get("properties") or {}
    prim=primitive(node)
    ports=[]

    def emit(kind,basis,direction=None):
        ports.append({
            "kind":kind,
            "basis":basis,
            "direction":direction,
            "certainty":"strong" if basis.startswith("explicit_") else "topology_candidate",
        })

    if block in {"minecraft:repeater","minecraft:comparator"}:
        facing=props.get("facing")
        if facing in HORIZONTAL:
            # Keep the same exact facing convention already used by
            # analyze_modern_causal_machinery.py: facing points toward rear input.
            rear=add(p,HORIZONTAL[facing])
            fv=HORIZONTAL[facing]
            front=(p[0]-fv[0],p[1]-fv[1],p[2]-fv[2])
            if rear in net_wire_positions:
                emit("input","explicit_oriented_rear",facing)
            if front in net_wire_positions:
                emit("output","explicit_oriented_front",opposite(facing))
            if block=="minecraft:comparator":
                left,right=side_directions(facing)
                if add(p,HORIZONTAL[left]) in net_wire_positions:
                    emit("side_input","explicit_comparator_side",left)
                if add(p,HORIZONTAL[right]) in net_wire_positions:
                    emit("side_input","explicit_comparator_side",right)
            return ports

    if block=="minecraft:redstone_torch":
        support=(p[0],p[1]-1,p[2])
        emit("input_support","explicit_floor_torch_support","down")
        if any(add(p,d) in net_wire_positions for d in DIR6.values()):
            emit("output","topology_adjacent_inverter_output")
        return ports

    if block=="minecraft:redstone_wall_torch":
        facing=props.get("facing")
        if facing in HORIZONTAL:
            emit("input_support","wall_torch_support_candidate",opposite(facing))
        if any(add(p,d) in net_wire_positions for d in DIR6.values()):
            emit("output","topology_adjacent_inverter_output")
        return ports

    adjacent=[
        name for name,d in DIR6.items()
        if add(p,d) in net_wire_positions
    ]
    if not adjacent:
        return []

    if prim in SOURCE_PRIMITIVES:
        for direction in adjacent:
            emit("output","topology_adjacent_source",direction)
    elif prim in SINK_PRIMITIVES:
        for direction in adjacent:
            emit("input","topology_adjacent_sink",direction)
    elif prim=="analog_comparator":
        for direction in adjacent:
            emit("bidirectional_candidate","topology_adjacent_component",direction)
    else:
        for direction in adjacent:
            emit("bidirectional_candidate","topology_adjacent_component",direction)
    return ports


def opposite(name):
    return {"north":"south","south":"north","east":"west","west":"east",
            "up":"down","down":"up"}.get(name)


def side_directions(facing):
    # left/right when looking from front/output toward rear/input is not used
    # as semantic direction; only the two perpendicular sides matter.
    if facing in {"east","west"}:
        return "north","south"
    return "east","west"


def attach_ports(nodes,groups):
    wire_pos_to_net={}
    nets=[]
    for i,ids in enumerate(groups,1):
        net_id=f"net::{i}"
        for nid in ids:
            p=pos(nodes[nid])
            if p is not None:
                wire_pos_to_net[p]=net_id
        rows=[
            {
                "node_id":nid,
                "position":nodes[nid].get("position"),
                "properties":nodes[nid].get("properties") or {},
            }
            for nid in ids
        ]
        nets.append({
            "net_id":net_id,
            "wire_node_count":len(ids),
            "wire_nodes":rows,
            "bounds":bounds_for(ids,nodes),
            "ports":[],
        })

    by_net={n["net_id"]:n for n in nets}
    components=[]
    for nid,node in sorted(nodes.items()):
        if node.get("block")=="minecraft:redstone_wire":
            continue
        p=pos(node)
        ports=[]
        for net in nets:
            net_positions={
                pos(nodes[row["node_id"]])
                for row in net["wire_nodes"]
            }
            for j,desc in enumerate(component_port_role(node,net_positions),1):
                port={
                    "port_id":f"{nid}::p{len(ports)+1}",
                    "component_id":nid,
                    "net_id":net["net_id"],
                    **desc,
                }
                ports.append(port)
                by_net[net["net_id"]]["ports"].append(port.copy())

        # Torches need an explicit input-support port even if no wire net is
        # attached on that side; it is intentionally unresolved until support
        # block/conduction evidence is recovered.
        if node.get("block") in {
            "minecraft:redstone_torch","minecraft:redstone_wall_torch"
        } and not any(p.get("kind")=="input_support" for p in ports):
            extra=component_port_role(node,set())
            for desc in extra:
                if desc["kind"]!="input_support":
                    continue
                ports.append({
                    "port_id":f"{nid}::p{len(ports)+1}",
                    "component_id":nid,
                    "net_id":None,
                    **desc,
                })

        components.append({
            "component_id":nid,
            "block":node.get("block"),
            "primitive":primitive(node),
            "position":node.get("position"),
            "properties":node.get("properties") or {},
            "roles":sorted(node.get("roles") or []),
            "ports":ports,
        })

    for net in nets:
        net["ports"].sort(key=lambda x:(x["component_id"],x["port_id"]))
        net["net_signature_sha256"]=hashlib.sha256(
            json.dumps(
                {
                    "wire_count":net["wire_node_count"],
                    "ports":[
                        {
                            "kind":p["kind"],
                            "component_primitive":next(
                                c["primitive"] for c in components
                                if c["component_id"]==p["component_id"]
                            ),
                            "certainty":p["certainty"],
                        }
                        for p in net["ports"]
                    ],
                },
                sort_keys=True,separators=(",",":")
            ).encode()
        ).hexdigest()
    return components,nets


def motifs(components,nets):
    by_id={c["component_id"]:c for c in components}
    out=[]

    for net in nets:
        sources=[
            p for p in net["ports"]
            if p["kind"]=="output" and by_id[p["component_id"]]["primitive"] in SOURCE_PRIMITIVES
        ]
        sinks=[
            p for p in net["ports"]
            if p["kind"]=="input" and by_id[p["component_id"]]["primitive"] in SINK_PRIMITIVES
        ]
        if sources and sinks:
            out.append({
                "template":"wire_transmission_path",
                "confidence":"structural_candidate",
                "component_ids":sorted({p["component_id"] for p in sources+sinks}),
                "net_ids":[net["net_id"]],
                "evidence":["source_output_and_sink_input_share_collapsed_dust_net"],
                "required_runtime_contract":RUNTIME_CONTRACTS["wire_transmission_path"],
            })

    # Repeater/delay: input net -> repeater -> output net.
    for c in components:
        if c["primitive"]!="buffer_delay":
            continue
        inputs=[p for p in c["ports"] if p["kind"]=="input" and p["net_id"]]
        outputs=[p for p in c["ports"] if p["kind"]=="output" and p["net_id"]]
        for pin in inputs:
            for pout in outputs:
                if pin["net_id"]==pout["net_id"]:
                    continue
                delay=(c.get("properties") or {}).get("delay")
                out.append({
                    "template":"repeater_delay_line",
                    "confidence":"structural_candidate",
                    "component_ids":[c["component_id"]],
                    "net_ids":[pin["net_id"],pout["net_id"]],
                    "configured_delay":delay,
                    "evidence":["explicit_repeater_rear_input","explicit_repeater_front_output"],
                    "required_runtime_contract":RUNTIME_CONTRACTS["repeater_delay_line"],
                })

    # A torch is an inverter primitive. Full NOT-gate acceptance requires
    # runtime truth-table evidence and an input-support relation; unresolved
    # support is retained explicitly rather than guessed.
    for c in components:
        if c["primitive"]!="inverter":
            continue
        outputs=[p for p in c["ports"] if p["kind"]=="output" and p["net_id"]]
        support=[p for p in c["ports"] if p["kind"]=="input_support"]
        if outputs and support:
            out.append({
                "template":"not_gate",
                "confidence":"structural_candidate_only",
                "component_ids":[c["component_id"]],
                "net_ids":sorted({p["net_id"] for p in outputs if p["net_id"]}),
                "input_support_resolved":any(p["net_id"] for p in support),
                "evidence":["redstone_torch_inverter_primitive","output_net_present"],
                "required_runtime_contract":RUNTIME_CONTRACTS["not_gate"],
            })

    return sorted(out,key=lambda x:(
        x["template"],tuple(x.get("component_ids",[])),tuple(x.get("net_ids",[]))
    ))


def transform_xz(x,z,m):
    a,b,c,d=m
    return a*x+b*z,c*x+d*z


def transform_facing(name,m):
    if name not in HORIZONTAL:
        return name
    x,_,z=HORIZONTAL[name]
    tx,tz=transform_xz(x,z,m)
    rev={(v[0],v[2]):k for k,v in HORIZONTAL.items()}
    return rev[(tx,tz)]


def transform_properties(props,m):
    out={}
    for k,v in props.items():
        if k=="facing" and v in HORIZONTAL:
            out[k]=transform_facing(v,m)
        elif k in HORIZONTAL:
            out[transform_facing(k,m)]=v
        else:
            out[k]=v
    return dict(sorted(out.items()))


def d4_signature(nodes):
    """Translation + horizontal D4 invariant block-layout signature."""
    rows=[]
    relevant=[
        n for n in nodes.values()
        if pos(n) is not None and n.get("block") in BLOCK_PRIMITIVE
    ]
    for m in D4:
        transformed=[]
        coords=[]
        for n in relevant:
            x,y,z=pos(n)
            tx,tz=transform_xz(x,z,m)
            coords.append((tx,y,tz))
            transformed.append((tx,y,tz,n))
        if not transformed:
            rows.append("[]"); continue
        minx=min(x for x,_,_,_ in transformed)
        miny=min(y for _,y,_,_ in transformed)
        minz=min(z for _,_,z,_ in transformed)
        canon=[
            {
                "relative_position":[x-minx,y-miny,z-minz],
                "block":n.get("block"),
                "primitive":primitive(n),
                "properties":transform_properties(n.get("properties") or {},m),
            }
            for x,y,z,n in transformed
        ]
        canon.sort(key=lambda r:(
            tuple(r["relative_position"]),r["block"],r["primitive"],
            json.dumps(r["properties"],sort_keys=True)
        ))
        rows.append(json.dumps(canon,sort_keys=True,separators=(",",":")))
    canonical=min(rows)
    return hashlib.sha256(canonical.encode()).hexdigest()


def functional_signature(components,nets):
    """Coordinate-free bipartite component/net signature for cross-layout comparison."""
    comp_rows=[
        {
            "primitive":c["primitive"],
            "block":c["block"],
            "properties":{
                k:v for k,v in sorted(c["properties"].items())
                if k not in {
                    "powered","lit","power","triggered",
                    "facing","north","east","south","west",
                }
            },
            "ports":sorted(
                [
                    {
                        "kind":p["kind"],
                        "certainty":p["certainty"],
                        "connected":p["net_id"] is not None,
                    }
                    for p in c["ports"]
                ],
                key=lambda x:(x["kind"],x["certainty"],x["connected"]),
            ),
        }
        for c in components
    ]
    comp_rows.sort(key=lambda x:(
        x["primitive"],x["block"],json.dumps(x["properties"],sort_keys=True),
        json.dumps(x["ports"],sort_keys=True)
    ))
    net_rows=[]
    by_id={c["component_id"]:c for c in components}
    for n in nets:
        attachments=sorted(
            (
                by_id[p["component_id"]]["primitive"],
                p["kind"],
                p["certainty"],
            )
            for p in n["ports"]
        )
        net_rows.append({
            "wire_count":n["wire_node_count"],
            "attachments":attachments,
        })
    net_rows.sort(key=lambda x:(x["wire_count"],json.dumps(x["attachments"])))
    return hashlib.sha256(
        json.dumps(
            {"components":comp_rows,"nets":net_rows},
            sort_keys=True,separators=(",",":")
        ).encode()
    ).hexdigest()


def render_dot(doc):
    rows=[
        "digraph redstone_netlist {",
        "  rankdir=LR;",
        '  graph [label="SupraCraft redstone functional netlist", labelloc=t];',
        '  node [fontname="monospace"];',
    ]
    for c in doc["components"]:
        label=f'{c["primitive"]}\\n{c["block"].split(":",1)[-1]}'
        rows.append(
            f'  "{escape(c["component_id"])}" '
            f'[shape=box,label="{escape(label)}"];'
        )
    for n in doc["nets"]:
        rows.append(
            f'  "{n["net_id"]}" [shape=ellipse,label="{n["net_id"]}\\n'
            f'{n["wire_node_count"]} dust"];'
        )
        for p in n["ports"]:
            if p["kind"] in {"output"}:
                rows.append(
                    f'  "{escape(p["component_id"])}" -> "{n["net_id"]}" '
                    f'[label="{p["kind"]}"];'
                )
            elif p["kind"] in {"input","side_input"}:
                rows.append(
                    f'  "{n["net_id"]}" -> "{escape(p["component_id"])}" '
                    f'[label="{p["kind"]}"];'
                )
            else:
                rows.append(
                    f'  "{escape(p["component_id"])}" -> "{n["net_id"]}" '
                    f'[dir=both,style=dashed,label="{p["kind"]}"];'
                )
    rows.append("}")
    return "\n".join(rows)+"\n"


def render_layers(nodes):
    by_y=defaultdict(list)
    for n in nodes.values():
        p=pos(n)
        if p is None or n.get("block") not in BLOCK_PRIMITIVE:
            continue
        by_y[p[1]].append((p,n))
    return {
        "schema":"supracraft-redstone-layered-schematic/1",
        "layers":[
            {
                "y":y,
                "cells":[
                    {
                        "position":list(p),
                        "block":n.get("block"),
                        "primitive":primitive(n),
                        "properties":n.get("properties") or {},
                    }
                    for p,n in sorted(by_y[y],key=lambda x:(x[0][2],x[0][0]))
                ],
            }
            for y in sorted(by_y)
        ],
        "boundary":"layered block schematic preserves exact layout; functional netlist is a separate abstraction",
    }


def escape(s):
    return str(s).replace("\\","\\\\").replace('"','\\"')


def build(graph):
    nodes={
        n["node_id"]:n
        for n in graph.get("nodes",[])
        if isinstance(n,dict) and n.get("node_id") and n.get("block")
    }
    groups=wire_components(nodes,graph.get("edges",[]))
    components,nets=attach_ports(nodes,groups)
    result={
        "schema":SCHEMA,
        "source_schema":graph.get("schema"),
        "analysis_kind":"eda_style_redstone_netlist_candidate",
        "component_count":len(components),
        "net_count":len(nets),
        "collapsed_wire_node_count":sum(n["wire_node_count"] for n in nets),
        "components":components,
        "nets":nets,
        "motif_candidates":motifs(components,nets),
        "signatures":{
            "horizontal_d4_topology_sha256":d4_signature(nodes),
            "functional_netlist_sha256":functional_signature(components,nets),
        },
        "limitations":[
            "dust collapse uses saved dust_connection evidence; solid-block conduction and quasi-connectivity are not invented",
            "topology-adjacent ports are candidates unless explicit oriented/source evidence exists",
            "torch input-support ports may remain unresolved until support/conduction context is recovered",
            "motif names are structural hypotheses until their runtime contracts pass",
            "runtime behavior and client presentation remain separate evidence layers",
        ],
    }
    return result,render_layers(nodes)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--dot-output",type=Path)
    ap.add_argument("--layers-output",type=Path)
    args=ap.parse_args()

    graph=json.loads(args.graph.read_text())
    doc,layers=build(graph)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n")
    if args.dot_output:
        args.dot_output.parent.mkdir(parents=True,exist_ok=True)
        args.dot_output.write_text(render_dot(doc))
    if args.layers_output:
        args.layers_output.parent.mkdir(parents=True,exist_ok=True)
        args.layers_output.write_text(json.dumps(layers,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
        "schema":doc["schema"],
        "component_count":doc["component_count"],
        "net_count":doc["net_count"],
        "motif_candidates":[m["template"] for m in doc["motif_candidates"]],
        "signatures":doc["signatures"],
    },sort_keys=True))


if __name__=="__main__":
    main()
