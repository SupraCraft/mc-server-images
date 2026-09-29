#!/usr/bin/env python3
"""Extract causal/semantic machinery from current palette-based Minecraft worlds."""

from __future__ import annotations

import argparse, gzip, hashlib, io, json, math, struct, tempfile, zipfile, zlib
from collections import Counter, defaultdict, deque
from pathlib import Path
import nbtlib

from analyze_legacy_causal_machinery import (
    COMMAND_ROLE, command_targets, normalize_command, read_scoreboard, scoreboard_refs
)

DIR={
  "north":(0,0,-1),"east":(1,0,0),"south":(0,0,1),"west":(-1,0,0),
  "up":(0,1,0),"down":(0,-1,0)
}
MACHINERY_ROLES={
  "minecraft:redstone_wire":["signal_transport"],
  "minecraft:repeater":["signal_transport","timer_clock"],
  "minecraft:comparator":["signal_transport","condition_query"],
  "minecraft:redstone_torch":["signal_transport","logic_gate"],
  "minecraft:redstone_wall_torch":["signal_transport","logic_gate"],
  "minecraft:redstone_lamp":["presentation_feedback"],
  "minecraft:lever":["sensor_input","state_memory"],
  "minecraft:stone_button":["sensor_input"],
  "minecraft:oak_button":["sensor_input"],
  "minecraft:stone_pressure_plate":["sensor_input"],
  "minecraft:light_weighted_pressure_plate":["sensor_input"],
  "minecraft:heavy_weighted_pressure_plate":["sensor_input"],
  "minecraft:tripwire":["sensor_input"],
  "minecraft:tripwire_hook":["sensor_input"],
  "minecraft:observer":["sensor_input","signal_transport"],
  "minecraft:sculk_sensor":["sensor_input"],
  "minecraft:calibrated_sculk_sensor":["sensor_input","condition_query"],
  "minecraft:target":["sensor_input"],
  "minecraft:daylight_detector":["sensor_input"],
  "minecraft:command_block":["condition_query","actuator","orchestrator"],
  "minecraft:repeating_command_block":["condition_query","actuator","orchestrator","timer_clock"],
  "minecraft:chain_command_block":["condition_query","actuator","orchestrator"],
  "minecraft:chest":["state_memory"],
  "minecraft:trapped_chest":["sensor_input","state_memory"],
  "minecraft:barrel":["state_memory"],
  "minecraft:hopper":["state_memory","actuator"],
  "minecraft:dispenser":["actuator"],
  "minecraft:dropper":["actuator"],
  "minecraft:crafter":["state_memory","actuator"],
  "minecraft:piston":["actuator"],
  "minecraft:sticky_piston":["actuator"],
  "minecraft:note_block":["presentation_feedback"],
  "minecraft:iron_door":["actuator"],
  "minecraft:oak_door":["actuator"],
  "minecraft:iron_trapdoor":["actuator"],
  "minecraft:oak_trapdoor":["actuator"],
}
ENTITY_ROLES={
  "minecraft:interaction":["sensor_input","interaction_surface"],
  "minecraft:text_display":["presentation_feedback"],
  "minecraft:block_display":["presentation_feedback"],
  "minecraft:item_display":["presentation_feedback"],
  "minecraft:marker":["semantic_anchor"],
  "minecraft:armor_stand":["presentation_feedback","semantic_anchor"],
}

def plain(v):
    if hasattr(v,"unpack"):
        try:return v.unpack()
        except Exception:pass
    return v

def decompress(payload,kind):
    if kind==1:return gzip.decompress(payload)
    if kind==2:return zlib.decompress(payload)
    if kind==3:return payload
    raise ValueError(kind)

def iter_region(path):
    blob=path.read_bytes()
    if len(blob)<8192:return
    for slot in range(1024):
        off=slot*4
        sector=int.from_bytes(blob[off:off+3],"big")
        count=blob[off+3]
        if not sector or not count:continue
        pos=sector*4096
        if pos+5>len(blob):continue
        length=struct.unpack(">I",blob[pos:pos+4])[0]
        end=pos+4+length
        if length<1 or end>len(blob):continue
        yield nbtlib.File.parse(io.BytesIO(decompress(blob[pos+5:end],blob[pos+4])))

def palette_entry(entry):
    if isinstance(entry,str): return str(entry),{}
    if hasattr(entry,"get"):
        name=entry.get("id",entry.get("Name",entry.get("name",entry.get(""))))
        props=entry.get("properties",entry.get("Properties",{}))
        return str(name), {str(k):str(plain(v)) for k,v in props.items()} if hasattr(props,"items") else {}
    return str(entry),{}

def decode(container,count=4096,min_bits=4):
    pal=container.get("palette")
    if pal is None:return []
    if len(pal)<=1:return [0]*count
    data=container.get("data")
    if data is None:raise ValueError("palette data missing")
    bits=max(min_bits,math.ceil(math.log2(len(pal))))
    per=64//bits
    mask=(1<<bits)-1
    longs=[int(x)&((1<<64)-1) for x in data]
    out=[]
    for i in range(count):
        idx=(longs[i//per]>>((i%per)*bits))&mask
        if idx>=len(pal):raise ValueError("palette index out of range")
        out.append(idx)
    return out

def nid(pos):return f"{pos[0]},{pos[1]},{pos[2]}"
def add(a,d):return (a[0]+d[0],a[1]+d[1],a[2]+d[2])
def opp(d):return (-d[0],-d[1],-d[2])

def analyze(world:Path):
    od=world/"dimensions"/"minecraft"/"overworld"
    region_dir=od/"region"; entity_dir=od/"entities"
    machinery={}
    block_entities={}

    for rp in sorted(region_dir.glob("r.*.*.mca")):
      for ch in iter_region(rp):
        cx=int(plain(ch.get("xPos",0))); cz=int(plain(ch.get("zPos",0)))
        for be in ch.get("block_entities",[]):
            try:p=(int(plain(be["x"])),int(plain(be["y"])),int(plain(be["z"])))
            except Exception:continue
            block_entities[p]=be
        for sec in ch.get("sections",[]):
            bs=sec.get("block_states")
            if not bs or bs.get("palette") is None:continue
            palette=[palette_entry(x) for x in bs["palette"]]
            if not any(name in MACHINERY_ROLES for name,_ in palette):continue
            idxs=decode(bs)
            sy=int(plain(sec.get("Y",0)))
            for i,pidx in enumerate(idxs):
                name,props=palette[pidx]
                if name not in MACHINERY_ROLES:continue
                lx=i&15;lz=(i>>4)&15;ly=(i>>8)&15
                pos=(cx*16+lx,sy*16+ly,cz*16+lz)
                machinery[pos]={
                  "node_id":nid(pos),"position":list(pos),"block":name,
                  "properties":props,"roles":MACHINERY_ROLES[name]
                }

    score=read_scoreboard(world)
    objectives={x["name"] for x in score["objectives"] if x["name"]}
    semantic_nodes={x:f"scoreboard_objective::{x}" for x in objectives}
    edges=[]; command_counts=Counter(); role_counts=Counter()
    for node in machinery.values():
        for r in node["roles"]:role_counts[r]+=1

    for pos,node in machinery.items():
        be=block_entities.get(pos)
        if be is None:continue
        ident=str(plain(be.get("id","")))
        node["block_entity"]={"id":ident}
        if "command_block" in node["block"]:
            command=str(plain(be.get("Command","")))
            verb,parts=normalize_command(command)
            command_counts[verb or "<empty>"]+=1
            command_roles=COMMAND_ROLE.get(verb,[])
            if command_roles:
                node["roles"]=sorted(set(node["roles"]) | set(command_roles))
                for role in command_roles:
                    role_counts[role]+=1
            node["block_entity"].update({
              "command_present":bool(command.strip()),"verb":verb or None,
              "command_sha256":hashlib.sha256(command.encode()).hexdigest(),
              "success_count":int(plain(be.get("SuccessCount",0))) if be.get("SuccessCount") is not None else None,
              "track_output":bool(plain(be.get("TrackOutput",1))) if be.get("TrackOutput") is not None else None,
              "auto":bool(plain(be.get("auto",0))) if be.get("auto") is not None else None,
              "powered":bool(plain(be.get("powered",0))) if be.get("powered") is not None else None,
              "condition_met":bool(plain(be.get("conditionMet",0))) if be.get("conditionMet") is not None else None,
            })
            for ref in scoreboard_refs(parts):
                objectives.add(ref["objective"])
                target=f"scoreboard_objective::{ref['objective']}"
                semantic_nodes[ref["objective"]]=target
                edges.append({"source":nid(pos),"target":target,"edge_type":f"scoreboard_{ref['access']}","certainty":"strong"})
            for t in command_targets(parts,pos):
                tp=t["position"]
                bp=tuple(int(v) for v in tp) if all(float(v).is_integer() for v in tp) else None
                edges.append({"source":nid(pos),"target":nid(bp) if bp in machinery else None,
                  "target_position":list(tp),"edge_type":"command_world_target","target_kind":t["kind"],
                  "certainty":"strong" if bp in machinery else "adequate","verb":verb})

    # Directed ports from explicit modern block-state properties.
    for pos,node in machinery.items():
        b=node["block"]; props=node["properties"]
        facing=props.get("facing")
        if b in {"minecraft:repeater","minecraft:comparator"} and facing in DIR:
            # Minecraft describes facing for these blocks from output side toward rear input.
            fv=DIR[facing]; rear=add(pos,fv); front=add(pos,opp(fv))
            if rear in machinery:edges.append({"source":nid(rear),"target":nid(pos),"edge_type":"oriented_rear_input","certainty":"strong"})
            if front in machinery:edges.append({"source":nid(pos),"target":nid(front),"edge_type":"oriented_front_output","certainty":"strong"})
            if b=="minecraft:comparator" and rear in machinery and machinery[rear]["block"] in {
                "minecraft:chest","minecraft:trapped_chest","minecraft:barrel","minecraft:hopper"
            }:
                edges.append({"source":nid(rear),"target":nid(pos),"edge_type":"container_inventory_signal_read","certainty":"strong"})
        if "command_block" in b and facing in DIR:
            fv=DIR[facing]; nxt=add(pos,fv); prev=add(pos,opp(fv))
            if b=="minecraft:chain_command_block" and nxt in machinery and "command_block" in machinery[nxt]["block"]:
                edges.append({"source":nid(pos),"target":nid(nxt),"edge_type":"chain_facing_successor","certainty":"strong"})
            if props.get("conditional")=="true" and prev in machinery and "command_block" in machinery[prev]["block"]:
                edges.append({"source":nid(prev),"target":nid(pos),"edge_type":"conditional_predecessor_success_dependency","certainty":"strong"})
        if b=="minecraft:redstone_wire":
            for name,delta in DIR.items():
                if name not in {"north","south","east","west"}:continue
                state=props.get(name)
                if state and state!="none":
                    q=add(pos,delta)
                    if state=="up":q=add(q,(0,1,0))
                    if q in machinery:edges.append({"source":nid(pos),"target":nid(q),"edge_type":"dust_connection","certainty":"strong","shape":state})
        if b=="minecraft:trapped_chest":
            for delta in DIR.values():
                q=add(pos,delta)
                if q in machinery and machinery[q]["block"] not in {"minecraft:chest","minecraft:trapped_chest"}:
                    edges.append({"source":nid(pos),"target":nid(q),"edge_type":"open_emits_redstone_power_candidate","certainty":"adequate","channel":"player_open_count_signal"})

    # Interaction and display entities are in separate entity region files in 26.3.
    entity_nodes=[]
    for rp in sorted(entity_dir.glob("r.*.*.mca")):
      for ch in iter_region(rp):
        for ent in ch.get("Entities",[]):
            ident=str(plain(ent.get("id","")))
            if ident not in ENTITY_ROLES:continue
            pos=[float(x) for x in ent.get("Pos",[0,0,0])]
            tag_values=[str(x) for x in ent.get("Tags",[])]
            tag_hash=hashlib.sha256("\n".join(sorted(tag_values)).encode()).hexdigest() if tag_values else None
            entity_nodes.append({
              "node_id":f"entity::{ident}::{len(entity_nodes)}","kind":"entity_surface","entity_type":ident,
              "position":pos,"roles":ENTITY_ROLES[ident],"tag_count":len(tag_values),"tag_set_sha256":tag_hash
            })
            for r in ENTITY_ROLES[ident]:role_counts[r]+=1

    # Physical adjacency components remain descriptive context.
    und=defaultdict(set); adj=0
    for pos in machinery:
      for delta in DIR.values():
        q=add(pos,delta)
        if q in machinery and pos<q:
            und[pos].add(q);und[q].add(pos);adj+=1
    seen=set();components=[]
    for start in machinery:
      if start in seen:continue
      dq=deque([start]);seen.add(start);members=[]
      while dq:
        p=dq.popleft();members.append(p)
        for q in und.get(p,()):
          if q not in seen:seen.add(q);dq.append(q)
      components.append({"node_count":len(members),
        "bounds":{"min":[min(p[i] for p in members) for i in range(3)],"max":[max(p[i] for p in members) for i in range(3)]}})

    edge_counts=Counter(e["edge_type"] for e in edges)
    family_counts=Counter(n["block"] for n in machinery.values())
    return {
      "schema":"supracraft-modern-causal-machinery/1",
      "analysis_kind":"static_structural_feedback_blind",
      "node_count":len(machinery)+len(entity_nodes)+len(semantic_nodes),
      "block_machinery_node_count":len(machinery),
      "entity_surface_node_count":len(entity_nodes),
      "semantic_state_node_count":len(semantic_nodes),
      "family_counts":dict(family_counts.most_common()),
      "role_counts":dict(sorted(role_counts.items())),
      "command_verb_counts":dict(command_counts.most_common()),
      "edge_counts":dict(sorted(edge_counts.items())),
      "physical_adjacency_candidate_count":adj,
      "component_count":len(components),
      "largest_components":sorted(components,key=lambda x:x["node_count"],reverse=True)[:30],
      "scoreboard":{"present":score["present"],"objective_count":len(objectives),"score_record_count":len(score["scores"])},
      "nodes":sorted(machinery.values(),key=lambda x:tuple(x["position"]))+entity_nodes+
        [{"node_id":v,"kind":"scoreboard_objective","objective":k} for k,v in sorted(semantic_nodes.items())],
      "edges":edges,
      "limitations":[
        "Wire edges use saved block-state connection shapes but do not model all solid-block conduction or quasi-connectivity.",
        "Trapped-chest opening power and comparator inventory reads are separate causal channels.",
        "Display/interaction entities are first-class surfaces but are not automatically linked to nearby blocks without stronger evidence.",
        "Static command and scoreboard references do not prove runtime execution or player understanding.",
        "No human-feedback labels are loaded by this analyzer."
      ]
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--world-zip",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="modern-causal-") as td:
      root=Path(td)
      with zipfile.ZipFile(args.world_zip) as zf:zf.extractall(root)
      result=analyze(root/"world")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
      "node_count":result["node_count"],"block_machinery_node_count":result["block_machinery_node_count"],
      "entity_surface_node_count":result["entity_surface_node_count"],"semantic_state_node_count":result["semantic_state_node_count"],
      "family_counts":result["family_counts"],"role_counts":result["role_counts"],
      "command_verb_counts":result["command_verb_counts"],"edge_counts":result["edge_counts"],
      "scoreboard":result["scoreboard"],"component_count":result["component_count"]
    },indent=2,sort_keys=True))

if __name__=="__main__":
    main()
