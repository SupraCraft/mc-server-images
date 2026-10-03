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
        "truth table: exercise input low and high; qualified output must be high for low input and low for high input, including reset back to high",
    "or_gate":
        "truth table: exercise 00, 10, 01, and 11; qualified output must be low only for 00 and high for every state with at least one asserted input",
    "nor_gate":
        "truth table: exercise 00, 10, 01, and 11; qualified output must be high only for 00 and low for every state with at least one asserted input",
    "and_gate":
        "truth table: exercise 00, 10, 01, and 11; qualified output must be high only for 11 and low for all other input states",
    "xor_gate":
        "truth table: exercise 00, 10, 01, and 11; qualified output must be high exactly when one of the two inputs is asserted",
    "rising_edge_detector":
        "temporal contract: a low-to-high source edge must produce one bounded positive output pulse that returns low while the source remains high; high-to-low must not produce a positive pulse; a second low-to-high edge after settling must retrigger",
    "repeater_ring_oscillator":
        "temporal contract: after a bounded seed pulse is removed, a closed four-stage delay-4 repeater ring must autonomously produce repeated rise/fall transitions with bounded period and jitter; opening the loop must quench transitions after settling; reclosing plus a new seed must restart repeated transitions",
    "rs_latch":
        "set/reset/hold sequence must demonstrate complementary outputs and retained state after stimulus removal; simultaneous set+reset is measured as an invalid-state boundary and post-invalid resolution is observed, not assumed",
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
                # Torch support/input is a separate conduction boundary, not
                # a port on whichever output dust net happens to be adjacent.
                if desc["kind"]=="input_support":
                    continue
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
    resolve_torch_support_peers(components,nodes,wire_pos_to_net,nets)
    return components,nets


def resolve_torch_support_peers(components,nodes,wire_pos_to_net,nets):
    by_pos={pos(n):nid for nid,n in nodes.items() if pos(n) is not None}
    comp_by_id={c["component_id"]:c for c in components}
    net_by_id={n["net_id"]:n for n in nets}
    for c in components:
        if c["primitive"]!="inverter":
            continue
        p=tuple(c["position"]) if c.get("position") else None
        if p is None:
            continue
        block=c["block"]
        props=c.get("properties") or {}
        support=None
        if block=="minecraft:redstone_torch":
            support=(p[0],p[1]-1,p[2])
        elif block=="minecraft:redstone_wall_torch":
            facing=props.get("facing")
            if facing in HORIZONTAL:
                fv=HORIZONTAL[facing]
                support=(p[0]-fv[0],p[1]-fv[1],p[2]-fv[2])
        if support is None:
            continue
        peers=[]
        support_nets=[]
        for d in DIR6.values():
            q=add(support,d)
            net_id=wire_pos_to_net.get(q)
            if net_id is not None:
                support_nets.append(net_id)
            nid=by_pos.get(q)
            if nid is None or nid==c["component_id"] or nid not in comp_by_id:
                continue
            peer=comp_by_id[nid]
            if peer["primitive"] in SOURCE_PRIMITIVES:
                peers.append(nid)
        support_nets=sorted(set(support_nets))
        for net_id in support_nets:
            net=net_by_id[net_id]
            for p in net.get("ports",[]):
                peer_id=p.get("component_id")
                if peer_id in comp_by_id and p.get("kind")=="output":
                    if comp_by_id[peer_id]["primitive"] in SOURCE_PRIMITIVES:
                        peers.append(peer_id)
        for port in c["ports"]:
            if port["kind"]=="input_support":
                port["support_position"]=list(support)
                port["support_net_ids"]=support_nets
                port["peer_component_ids"]=sorted(set(peers))
                if support_nets:
                    port["basis"]="topology_support_wire_net_candidate"
                    port["certainty"]="topology_candidate"
                elif peers:
                    port["basis"]="topology_support_source_candidate"
                    port["certainty"]="topology_candidate"


def motifs(components,nets):
    by_id={c["component_id"]:c for c in components}
    net_by_id={n["net_id"]:n for n in nets}
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

        source_ids=sorted({p["component_id"] for p in sources})
        sink_ids=sorted({p["component_id"] for p in sinks})
        if len(source_ids)>=2 and sink_ids:
            out.append({
                "template":"or_gate",
                "confidence":"structural_candidate_only",
                "component_ids":source_ids+sink_ids,
                "net_ids":[net["net_id"]],
                "input_source_component_ids":source_ids,
                "output_sink_component_ids":sink_ids,
                "evidence":["multiple_independent_sources_share_output_net"],
                "required_runtime_contract":RUNTIME_CONTRACTS["or_gate"],
            })


    # NOR composition: at least two independent source outputs share one
    # collapsed input net, that net drives exactly one inverter support, and
    # the inverter reaches a distinct output net/sink. Structural recognition
    # remains candidate-only until the complete truth table passes at runtime.
    for final in components:
        if final["primitive"]!="inverter":
            continue
        supports=[p for p in final["ports"] if p["kind"]=="input_support"]
        outputs=[p for p in final["ports"] if p["kind"]=="output" and p.get("net_id")]
        if not supports or not outputs:
            continue
        for support in supports:
            for input_net_id in sorted(set(support.get("support_net_ids",[]))):
                input_net=net_by_id.get(input_net_id)
                if input_net is None:
                    continue
                source_ids=sorted({
                    p["component_id"]
                    for p in input_net.get("ports",[])
                    if p.get("kind")=="output"
                    and p.get("component_id") in by_id
                    and by_id[p["component_id"]]["primitive"] in SOURCE_PRIMITIVES
                })
                if len(source_ids)<2:
                    continue
                output_net_ids=sorted({
                    p["net_id"] for p in outputs
                    if p.get("net_id") and p["net_id"]!=input_net_id
                })
                if not output_net_ids:
                    continue
                sink_ids=set()
                for output_net_id in output_net_ids:
                    net=net_by_id.get(output_net_id) or {}
                    for port in net.get("ports",[]):
                        cid=port.get("component_id")
                        if (
                            port.get("kind")=="input"
                            and cid in by_id
                            and by_id[cid]["primitive"] in SINK_PRIMITIVES
                        ):
                            sink_ids.add(cid)
                if not sink_ids:
                    continue
                out.append({
                    "template":"nor_gate",
                    "confidence":"structural_candidate_only",
                    "component_ids":sorted(
                        set(source_ids+[final["component_id"]]+list(sink_ids))
                    ),
                    "net_ids":[input_net_id]+output_net_ids,
                    "input_source_component_ids":source_ids,
                    "input_net_id":input_net_id,
                    "inverter_component_id":final["component_id"],
                    "output_net_ids":output_net_ids,
                    "output_sink_component_ids":sorted(sink_ids),
                    "evidence":[
                        "multiple_independent_sources_share_input_net",
                        "shared_input_net_drives_inverter_support",
                        "inverter_output_reaches_distinct_sink_net",
                    ],
                    "required_runtime_contract":RUNTIME_CONTRACTS["nor_gate"],
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


    # Repeater-ring oscillator candidate: exactly four delay-4 repeaters
    # form a closed directed ring through four distinct dust nets. Structure
    # alone is never oscillator authority: runtime must prove autonomous
    # repeated transitions after seed removal plus bounded stop/restart.
    ring_repeaters=[]
    for comp in components:
        if (
            comp["primitive"]!="buffer_delay"
            or str((comp.get("properties") or {}).get("delay"))!="4"
        ):
            continue
        inputs=sorted({
            p["net_id"] for p in comp.get("ports",[])
            if p.get("kind")=="input" and p.get("net_id")
        })
        outputs=sorted({
            p["net_id"] for p in comp.get("ports",[])
            if p.get("kind")=="output" and p.get("net_id")
        })
        if len(inputs)==1 and len(outputs)==1 and inputs[0]!=outputs[0]:
            ring_repeaters.append({
                "component_id":comp["component_id"],
                "input_net_id":inputs[0],
                "output_net_id":outputs[0],
            })

    ring_by_id={r["component_id"]:r for r in ring_repeaters}
    ring_edges=defaultdict(list)
    for a in ring_repeaters:
        for b in ring_repeaters:
            if (
                a["component_id"]!=b["component_id"]
                and a["output_net_id"]==b["input_net_id"]
            ):
                ring_edges[a["component_id"]].append(b["component_id"])

    seen_rings=set()
    for start in sorted(ring_by_id):
        stack=[(start,[start])]
        while stack:
            current,path=stack.pop()
            if len(path)>4:
                continue
            for nxt in sorted(ring_edges.get(current,[])):
                if nxt==start and len(path)==4:
                    rotations=[
                        tuple(path[i:]+path[:i]) for i in range(len(path))
                    ]
                    canonical=min(rotations)
                    key=frozenset(canonical)
                    if key in seen_rings:
                        continue
                    seen_rings.add(key)
                    ordered=list(canonical)
                    interconnect_nets=[
                        ring_by_id[cid]["output_net_id"] for cid in ordered
                    ]
                    if len(set(interconnect_nets))!=4:
                        continue
                    out.append({
                        "template":"repeater_ring_oscillator",
                        "confidence":"structural_candidate_only",
                        "component_ids":sorted(ordered),
                        "net_ids":sorted(interconnect_nets),
                        "repeater_component_ids":ordered,
                        "configured_delays":[4,4,4,4],
                        "loop_net_ids":interconnect_nets,
                        "evidence":[
                            "four_delay4_repeaters_form_closed_directed_ring",
                            "four_distinct_interconnect_nets_preserve_stage_boundaries",
                        ],
                        "required_runtime_contract":
                            RUNTIME_CONTRACTS["repeater_ring_oscillator"],
                    })
                    continue
                if nxt in path or len(path)>=4:
                    continue
                stack.append((nxt,path+[nxt]))

    # Rising-edge detector: one source/input net fans out to a direct
    # inverter and an exact three-stage delay-4 repeater chain. The third
    # repeater output and direct-inverter output merge on one intermediate
    # net that drives a final inverter. One- and two-stage delay-4 shapes are
    # explicit hard negatives for this qualified cross-frontier reference:
    # one stage had no causal pulse window; two stages produced an
    # instrumented-only pulse while stock failed.
    for delay_a in components:
        if (
            delay_a["primitive"]!="buffer_delay"
            or str((delay_a.get("properties") or {}).get("delay"))!="4"
        ):
            continue
        for ain in [
            p for p in delay_a["ports"]
            if p["kind"]=="input" and p.get("net_id")
        ]:
            input_net_id=ain["net_id"]
            input_net=net_by_id.get(input_net_id) or {}
            source_ids=sorted({
                p["component_id"]
                for p in input_net.get("ports",[])
                if p.get("kind")=="output"
                and p.get("component_id") in by_id
                and by_id[p["component_id"]]["primitive"] in SOURCE_PRIMITIVES
            })
            if len(source_ids)!=1:
                continue
            for aout in [
                p for p in delay_a["ports"]
                if p["kind"]=="output" and p.get("net_id")
            ]:
                interstage_a=aout["net_id"]
                if not interstage_a or interstage_a==input_net_id:
                    continue
                for delay_b in components:
                    if (
                        delay_b["component_id"]==delay_a["component_id"]
                        or delay_b["primitive"]!="buffer_delay"
                        or str((delay_b.get("properties") or {}).get("delay"))!="4"
                    ):
                        continue
                    b_inputs={
                        p["net_id"] for p in delay_b["ports"]
                        if p["kind"]=="input" and p.get("net_id")
                    }
                    if interstage_a not in b_inputs:
                        continue
                    for bout in [
                        p for p in delay_b["ports"]
                        if p["kind"]=="output" and p.get("net_id")
                    ]:
                        interstage_b=bout["net_id"]
                        if (
                            not interstage_b
                            or interstage_b in {input_net_id,interstage_a}
                        ):
                            continue
                        for delay_c in components:
                            if (
                                delay_c["component_id"] in {
                                    delay_a["component_id"],
                                    delay_b["component_id"],
                                }
                                or delay_c["primitive"]!="buffer_delay"
                                or str(
                                    (delay_c.get("properties") or {}).get("delay")
                                )!="4"
                            ):
                                continue
                            c_inputs={
                                p["net_id"] for p in delay_c["ports"]
                                if p["kind"]=="input" and p.get("net_id")
                            }
                            if interstage_b not in c_inputs:
                                continue
                            for cout in [
                                p for p in delay_c["ports"]
                                if p["kind"]=="output" and p.get("net_id")
                            ]:
                                intermediate_id=cout["net_id"]
                                if (
                                    not intermediate_id
                                    or intermediate_id in {
                                        input_net_id,interstage_a,interstage_b
                                    }
                                ):
                                    continue
                                direct_inverters=[]
                                for inv in components:
                                    if inv["primitive"]!="inverter":
                                        continue
                                    support_ids={
                                        nid
                                        for p in inv["ports"]
                                        if p.get("kind")=="input_support"
                                        for nid in p.get("support_net_ids",[])
                                    }
                                    output_ids={
                                        p["net_id"] for p in inv["ports"]
                                        if p.get("kind")=="output"
                                        and p.get("net_id")
                                    }
                                    if (
                                        input_net_id in support_ids
                                        and intermediate_id in output_ids
                                    ):
                                        direct_inverters.append(inv)
                                for direct_inv in direct_inverters:
                                    for final in components:
                                        if (
                                            final["primitive"]!="inverter"
                                            or final["component_id"]==
                                                direct_inv["component_id"]
                                        ):
                                            continue
                                        final_support_ids={
                                            nid
                                            for p in final["ports"]
                                            if p.get("kind")=="input_support"
                                            for nid in p.get("support_net_ids",[])
                                        }
                                        if intermediate_id not in final_support_ids:
                                            continue
                                        output_net_ids=sorted({
                                            p["net_id"] for p in final["ports"]
                                            if p.get("kind")=="output"
                                            and p.get("net_id")
                                            and p["net_id"]!=intermediate_id
                                        })
                                        if not output_net_ids:
                                            continue
                                        sink_ids=set()
                                        for output_net_id in output_net_ids:
                                            out_net=net_by_id.get(output_net_id) or {}
                                            for port in out_net.get("ports",[]):
                                                cid=port.get("component_id")
                                                if (
                                                    port.get("kind")=="input"
                                                    and cid in by_id
                                                    and by_id[cid]["primitive"]
                                                        in SINK_PRIMITIVES
                                                ):
                                                    sink_ids.add(cid)
                                        if not sink_ids:
                                            continue
                                        delay_ids=[
                                            delay_a["component_id"],
                                            delay_b["component_id"],
                                            delay_c["component_id"],
                                        ]
                                        out.append({
                                            "template":"rising_edge_detector",
                                            "confidence":"structural_candidate_only",
                                            "component_ids":sorted(set(
                                                source_ids+delay_ids+
                                                [direct_inv["component_id"],
                                                 final["component_id"]]+
                                                list(sink_ids)
                                            )),
                                            "net_ids":sorted(set(
                                                [input_net_id,interstage_a,
                                                 interstage_b,intermediate_id]+
                                                output_net_ids
                                            )),
                                            "input_source_component_id":
                                                source_ids[0],
                                            "input_net_id":input_net_id,
                                            "delay_component_ids":delay_ids,
                                            "configured_delays":[4,4,4],
                                            "delay_interstage_net_ids":[
                                                interstage_a,interstage_b
                                            ],
                                            "direct_inverter_component_id":
                                                direct_inv["component_id"],
                                            "intermediate_net_id":intermediate_id,
                                            "final_inverter_component_id":
                                                final["component_id"],
                                            "output_net_ids":output_net_ids,
                                            "output_sink_component_ids":
                                                sorted(sink_ids),
                                            "evidence":[
                                                "single_source_fans_out_to_direct_inverter_and_three_stage_delay4_chain",
                                                "serial_three_stage_delay4_path_reaches_intermediate_net",
                                                "direct_inverter_and_third_delay_output_share_intermediate_net",
                                                "intermediate_net_drives_final_inverter",
                                                "final_inverter_output_reaches_distinct_sink_net",
                                            ],
                                            "required_runtime_contract":
                                                RUNTIME_CONTRACTS[
                                                    "rising_edge_detector"
                                                ],
                                        })

    # AND via De Morgan: two independently sourced inverter outputs feed a
    # shared intermediate net that drives a third inverter. Structural shape
    # alone remains candidate-only until the complete four-row truth table is
    # observed at runtime.
    net_by_id={n["net_id"]:n for n in nets}
    for final in components:
        if final["primitive"]!="inverter":
            continue
        final_support=[p for p in final["ports"] if p["kind"]=="input_support"]
        final_outputs=[p for p in final["ports"] if p["kind"]=="output" and p["net_id"]]
        if not final_support or not final_outputs:
            continue
        for support in final_support:
            intermediate_ids=sorted(set(support.get("support_net_ids",[])))
            for intermediate_id in intermediate_ids:
                intermediate=net_by_id.get(intermediate_id)
                if intermediate is None:
                    continue
                upstream_ids=sorted({
                    p["component_id"]
                    for p in intermediate.get("ports",[])
                    if p.get("kind")=="output"
                    and p.get("component_id") in by_id
                    and by_id[p["component_id"]]["primitive"]=="inverter"
                    and p["component_id"]!=final["component_id"]
                })
                if len(upstream_ids)!=2:
                    continue
                source_ids=set()
                input_net_ids=set()
                resolved=True
                for upstream_id in upstream_ids:
                    upstream=by_id[upstream_id]
                    supports=[
                        p for p in upstream["ports"]
                        if p["kind"]=="input_support"
                    ]
                    if not supports:
                        resolved=False
                        break
                    this_resolved=False
                    for pin in supports:
                        input_net_ids.update(pin.get("support_net_ids",[]))
                        source_ids.update(pin.get("peer_component_ids",[]))
                        if (
                            pin.get("support_net_ids")
                            or pin.get("peer_component_ids")
                        ):
                            this_resolved=True
                    if not this_resolved:
                        resolved=False
                        break
                source_ids=sorted(source_ids)
                if not resolved or len(set(source_ids))<2:
                    continue

                output_net_ids=sorted({
                    p["net_id"] for p in final_outputs if p.get("net_id")
                })
                sink_ids=set()
                for net_id in output_net_ids:
                    net=net_by_id.get(net_id) or {}
                    for port in net.get("ports",[]):
                        cid=port.get("component_id")
                        if (
                            port.get("kind")=="input"
                            and cid in by_id
                            and by_id[cid]["primitive"] in SINK_PRIMITIVES
                        ):
                            sink_ids.add(cid)
                if not sink_ids:
                    continue

                out.append({
                    "template":"and_gate",
                    "confidence":"structural_candidate_only",
                    "component_ids":sorted(
                        set(source_ids+upstream_ids+[final["component_id"]]+list(sink_ids))
                    ),
                    "net_ids":sorted(
                        set(input_net_ids)|{intermediate_id}|set(output_net_ids)
                    ),
                    "input_source_component_ids":source_ids,
                    "input_inverter_component_ids":upstream_ids,
                    "intermediate_net_id":intermediate_id,
                    "final_inverter_component_id":final["component_id"],
                    "output_sink_component_ids":sorted(sink_ids),
                    "evidence":[
                        "two_independent_sources_feed_two_inverters",
                        "upstream_inverter_outputs_share_intermediate_net",
                        "intermediate_net_drives_final_inverter",
                        "final_inverter_output_reaches_sink",
                    ],
                    "required_runtime_contract":RUNTIME_CONTRACTS["and_gate"],
                })



    # XOR composition: the same two physical sources fan out into a direct OR
    # net and into independent input inverters.  Those inverter outputs merge
    # into NOT A OR NOT B.  The direct-OR and NAND-equivalent nets feed the
    # two input inverters of a final De-Morgan AND stage.
    seen_xor=set()
    for direct_net in nets:
        primary_sources=sorted({
            p["component_id"]
            for p in direct_net.get("ports",[])
            if p.get("kind")=="output"
            and p.get("component_id") in by_id
            and by_id[p["component_id"]]["primitive"] in SOURCE_PRIMITIVES
        })
        if len(primary_sources)!=2:
            continue

        input_inverters=[]
        for inv in components:
            if inv["primitive"]!="inverter":
                continue
            support_sources=sorted({
                peer
                for p in inv.get("ports",[])
                if p.get("kind")=="input_support"
                for peer in p.get("peer_component_ids",[])
                if peer in primary_sources
            })
            if len(support_sources)!=1:
                continue
            output_nets=sorted({
                p["net_id"] for p in inv.get("ports",[])
                if p.get("kind")=="output" and p.get("net_id")
            })
            if output_nets:
                input_inverters.append((inv,support_sources[0],output_nets))

        by_source={}
        for inv,source_id,output_nets in input_inverters:
            by_source.setdefault(source_id,[]).append((inv,output_nets))
        if any(source_id not in by_source for source_id in primary_sources):
            continue

        for inv_a,nets_a in by_source[primary_sources[0]]:
            for inv_b,nets_b in by_source[primary_sources[1]]:
                if inv_a["component_id"]==inv_b["component_id"]:
                    continue
                for nand_id in sorted(set(nets_a)&set(nets_b)):
                    if nand_id==direct_net["net_id"]:
                        continue

                    stage_direct=[]
                    stage_nand=[]
                    for inv in components:
                        if inv["primitive"]!="inverter":
                            continue
                        if inv["component_id"] in {
                            inv_a["component_id"],inv_b["component_id"]
                        }:
                            continue
                        support_ids={
                            net_id
                            for p in inv.get("ports",[])
                            if p.get("kind")=="input_support"
                            for net_id in p.get("support_net_ids",[])
                        }
                        output_ids=sorted({
                            p["net_id"] for p in inv.get("ports",[])
                            if p.get("kind")=="output" and p.get("net_id")
                        })
                        if direct_net["net_id"] in support_ids and output_ids:
                            stage_direct.append((inv,output_ids))
                        if nand_id in support_ids and output_ids:
                            stage_nand.append((inv,output_ids))

                    for direct_inv,direct_outputs in stage_direct:
                        for nand_inv,nand_outputs in stage_nand:
                            if direct_inv["component_id"]==nand_inv["component_id"]:
                                continue
                            for mid_id in sorted(set(direct_outputs)&set(nand_outputs)):
                                for final in components:
                                    if final["primitive"]!="inverter":
                                        continue
                                    if final["component_id"] in {
                                        inv_a["component_id"],inv_b["component_id"],
                                        direct_inv["component_id"],nand_inv["component_id"],
                                    }:
                                        continue
                                    final_support_ids={
                                        net_id
                                        for p in final.get("ports",[])
                                        if p.get("kind")=="input_support"
                                        for net_id in p.get("support_net_ids",[])
                                    }
                                    if mid_id not in final_support_ids:
                                        continue
                                    output_net_ids=sorted({
                                        p["net_id"] for p in final.get("ports",[])
                                        if p.get("kind")=="output" and p.get("net_id")
                                    })
                                    sink_ids=set()
                                    for output_net_id in output_net_ids:
                                        net=net_by_id.get(output_net_id) or {}
                                        for port in net.get("ports",[]):
                                            cid=port.get("component_id")
                                            if (
                                                port.get("kind")=="input"
                                                and cid in by_id
                                                and by_id[cid]["primitive"] in SINK_PRIMITIVES
                                            ):
                                                sink_ids.add(cid)
                                    if not sink_ids:
                                        continue
                                    key=(
                                        tuple(primary_sources),
                                        tuple(sorted((inv_a["component_id"],inv_b["component_id"]))),
                                        tuple(sorted((direct_inv["component_id"],nand_inv["component_id"]))),
                                        final["component_id"],
                                    )
                                    if key in seen_xor:
                                        continue
                                    seen_xor.add(key)
                                    out.append({
                                        "template":"xor_gate",
                                        "confidence":"structural_candidate_only",
                                        "component_ids":sorted(set(
                                            primary_sources+
                                            [inv_a["component_id"],inv_b["component_id"],
                                             direct_inv["component_id"],nand_inv["component_id"],
                                             final["component_id"]]+list(sink_ids)
                                        )),
                                        "net_ids":sorted({
                                            direct_net["net_id"],nand_id,mid_id,*output_net_ids
                                        }),
                                        "input_source_component_ids":primary_sources,
                                        "direct_or_net_id":direct_net["net_id"],
                                        "input_inverter_component_ids":sorted(
                                            [inv_a["component_id"],inv_b["component_id"]]
                                        ),
                                        "nand_net_id":nand_id,
                                        "stage_inverter_component_ids":sorted(
                                            [direct_inv["component_id"],nand_inv["component_id"]]
                                        ),
                                        "intermediate_net_id":mid_id,
                                        "final_inverter_component_id":final["component_id"],
                                        "output_net_ids":output_net_ids,
                                        "output_sink_component_ids":sorted(sink_ids),
                                        "evidence":[
                                            "same_two_sources_feed_direct_or_net",
                                            "same_sources_feed_individual_input_inverters",
                                            "input_inverter_outputs_merge_as_nand_equivalent_net",
                                            "direct_or_and_nand_nets_feed_final_and_stage",
                                            "final_inverter_output_reaches_distinct_sink_net",
                                        ],
                                        "required_runtime_contract":RUNTIME_CONTRACTS["xor_gate"],
                                    })

    # RS latch candidate: exactly two cross-coupled inverter primitives.
    # Each inverter output net must appear in the other inverter's support-net
    # inputs. External S/R sources and sinks are optional observations; the
    # feedback topology is the minimum static requirement. Runtime set/reset/
    # hold evidence is mandatory before promotion.
    inverters=[x for x in components if x["primitive"]=="inverter"]
    seen_latches=set()
    for i,a in enumerate(inverters):
        a_outputs=sorted({
            p["net_id"] for p in a["ports"]
            if p["kind"]=="output" and p.get("net_id")
        })
        a_supports=sorted({
            net_id
            for p in a["ports"] if p["kind"]=="input_support"
            for net_id in p.get("support_net_ids",[])
        })
        if not a_outputs or not a_supports:
            continue
        for b in inverters[i+1:]:
            b_outputs=sorted({
                p["net_id"] for p in b["ports"]
                if p["kind"]=="output" and p.get("net_id")
            })
            b_supports=sorted({
                net_id
                for p in b["ports"] if p["kind"]=="input_support"
                for net_id in p.get("support_net_ids",[])
            })
            if not b_outputs or not b_supports:
                continue
            a_to_b=sorted(set(a_outputs)&set(b_supports))
            b_to_a=sorted(set(b_outputs)&set(a_supports))
            if not a_to_b or not b_to_a:
                continue
            key=tuple(sorted((a["component_id"],b["component_id"])))
            if key in seen_latches:
                continue
            seen_latches.add(key)

            source_by_inverter={}
            for inv in (a,b):
                source_by_inverter[inv["component_id"]]=sorted({
                    peer
                    for p in inv["ports"] if p["kind"]=="input_support"
                    for peer in p.get("peer_component_ids",[])
                })

            output_net_ids=sorted(set(a_outputs+b_outputs))
            sink_ids=set()
            for net_id in output_net_ids:
                net=net_by_id.get(net_id) or {}
                for port in net.get("ports",[]):
                    cid=port.get("component_id")
                    if (
                        port.get("kind")=="input"
                        and cid in by_id
                        and by_id[cid]["primitive"] in SINK_PRIMITIVES
                    ):
                        sink_ids.add(cid)

            out.append({
                "template":"rs_latch",
                "confidence":"structural_candidate_only",
                "component_ids":sorted(
                    {a["component_id"],b["component_id"]}|sink_ids
                ),
                "net_ids":output_net_ids,
                "inverter_component_ids":list(key),
                "feedback_a_to_b_net_ids":a_to_b,
                "feedback_b_to_a_net_ids":b_to_a,
                "input_source_component_ids_by_inverter":source_by_inverter,
                "output_sink_component_ids":sorted(sink_ids),
                "evidence":[
                    "two_inverter_primitives",
                    "first_inverter_output_drives_second_support_net",
                    "second_inverter_output_drives_first_support_net",
                    "closed_cross_coupled_feedback",
                ],
                "required_runtime_contract":RUNTIME_CONTRACTS["rs_latch"],
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
                "input_support_resolved":any(
                    p.get("net_id") or p.get("support_net_ids") or p.get("peer_component_ids")
                    for p in support
                ),
                "input_support_net_ids":sorted({
                    net_id
                    for p in support
                    for net_id in p.get("support_net_ids",[])
                }),
                "input_source_component_ids":sorted({
                    peer
                    for p in support
                    for peer in p.get("peer_component_ids",[])
                }),
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
                        "connected":(
                            p["net_id"] is not None
                            or bool(p.get("support_net_ids"))
                            or bool(p.get("peer_component_ids"))
                        ),
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
    for c in doc["components"]:
        for p in c["ports"]:
            if p["kind"]!="input_support":
                continue
            for net_id in p.get("support_net_ids",[]):
                rows.append(
                    f'  "{escape(net_id)}" -> "{escape(c["component_id"])}" '
                    f'[style=dashed,label="support-net input candidate"];'
                )
            for peer in p.get("peer_component_ids",[]):
                rows.append(
                    f'  "{escape(peer)}" -> "{escape(c["component_id"])}" '
                    f'[style=dashed,label="support input candidate"];'
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
