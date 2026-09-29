#!/usr/bin/env python3
"""Paired control/activated runtime probes for legacy Minecraft mechanisms."""

from __future__ import annotations

import argparse, copy, json, shutil, subprocess, tempfile, time, urllib.request, zipfile
from pathlib import Path

import nbtlib

from analyze_legacy_causal_machinery import (
    analyze as analyze_machinery,
    byte_values,
    chunk_level,
    iter_chunks,
    nibble_at,
)
from run_legacy_reference_server import (
    download, materialize_world, resolve_version, send, wait_ready
)

ACTIVATABLE = {"lever","stone_button","wooden_button"}

def set_spawn(world: Path, pos):
    path=world/"level.dat"
    level=nbtlib.load(path)
    data=level.get("Data",level)
    data["SpawnX"]=nbtlib.Int(int(pos[0]))
    data["SpawnY"]=nbtlib.Int(int(pos[1]))
    data["SpawnZ"]=nbtlib.Int(int(pos[2]))
    level.save(path)

def legacy_block_states_at(world: Path, positions):
    """Read exact legacy block id/metadata at a bounded set of world positions."""
    wanted={tuple(int(v) for v in pos) for pos in positions}
    by_chunk={}
    for pos in wanted:
        by_chunk.setdefault((pos[0]//16,pos[2]//16),[]).append(pos)

    found={}
    for region in sorted((world/"region").glob("r.*.*.mca")):
        for root in iter_chunks(region):
            level=chunk_level(root)
            cx=int(level.get("xPos",0))
            cz=int(level.get("zPos",0))
            targets=by_chunk.get((cx,cz))
            if not targets:
                continue
            sections={}
            for sec in level.get("Sections",[]):
                blocks=sec.get("Blocks")
                if blocks is None:
                    continue
                sy=int(sec.get("Y",0))
                sections[sy]=(
                    byte_values(blocks),
                    sec.get("Add"),
                    sec.get("Data"),
                )
            for pos in targets:
                x,y,z=pos
                sec=sections.get(y//16)
                key=f"{x},{y},{z}"
                if sec is None:
                    found[key]={
                        "position":[x,y,z],
                        "observed":True,
                        "legacy_block_id":0,
                        "legacy_metadata":0,
                        "basis":"missing section implies air in legacy Anvil",
                    }
                    continue
                base,add,data=sec
                lx=x & 15
                lz=z & 15
                ly=y & 15
                i=(ly<<8)|(lz<<4)|lx
                bid=base[i]
                if add is not None:
                    bid |= nibble_at(add,i)<<8
                meta=nibble_at(data,i) if data is not None else 0
                found[key]={
                    "position":[x,y,z],
                    "observed":True,
                    "legacy_block_id":bid,
                    "legacy_metadata":meta,
                }

    for pos in wanted:
        key=f"{pos[0]},{pos[1]},{pos[2]}"
        found.setdefault(key,{
            "position":list(pos),
            "observed":False,
            "legacy_block_id":None,
            "legacy_metadata":None,
        })
    return found


def snapshot(world: Path, center, radius=96):
    d=analyze_machinery(world)
    cx,cy,cz=center
    nodes=[]
    for n in d["nodes"]:
        p=n.get("position")
        if not p:continue
        if abs(p[0]-cx)<=radius and abs(p[1]-cy)<=radius and abs(p[2]-cz)<=radius:
            if "command_block" in str(n.get("family","")):
                nodes.append({
                  "node_id":n["node_id"],
                  "family":n.get("family"),
                  "position":p,
                  "command":n.get("command"),
                })
    local_command_ids={n["node_id"] for n in nodes}
    target_specs=[]
    target_positions=[]
    for edge in d.get("edges",{}).get("command_world_targets",[]):
        if edge.get("source") not in local_command_ids:
            continue
        pos=edge.get("target_position")
        if not isinstance(pos,list) or len(pos)!=3:
            continue
        try:
            vals=[float(v) for v in pos]
        except (TypeError,ValueError):
            continue
        if not all(v.is_integer() for v in vals):
            continue
        target=[int(v) for v in vals]
        target_positions.append(target)
        target_specs.append({
            "source":edge.get("source"),
            "target_position":target,
            "target_kind":edge.get("target_kind"),
            "verb":edge.get("verb"),
            "coordinate_mode":edge.get("coordinate_mode"),
        })
    target_states=legacy_block_states_at(world,target_positions)
    world_targets=[]
    for spec in target_specs:
        key=",".join(str(v) for v in spec["target_position"])
        world_targets.append({**spec,"state":target_states[key]})

    objective_scores={}
    # The machinery result currently reports objective metadata but not score rows;
    # load raw scoreboard via helper-compatible output in a compact form.
    from analyze_legacy_causal_machinery import read_scoreboard
    sb=read_scoreboard(world)
    for row in sb.get("scores",[]):
        key=f"{row.get('name')}::{row.get('objective')}"
        objective_scores[key]=row.get("score")
    return {
      "command_blocks":nodes,
      "scoreboard_scores":objective_scores,
      "world_targets":world_targets,
      "machinery_node_count":d["node_count"],
    }

def delta(control,active):
    ccmd={x["node_id"]:x for x in control["command_blocks"]}
    acmd={x["node_id"]:x for x in active["command_blocks"]}
    changed=[]
    for nid in sorted(set(ccmd)|set(acmd)):
        c=(ccmd.get(nid) or {}).get("command") or {}
        a=(acmd.get(nid) or {}).get("command") or {}
        fields={}
        for k in ("success_count","condition_met","powered","last_execution","last_output_sha256"):
            if c.get(k)!=a.get(k):
                fields[k]={"control":c.get(k),"activated":a.get(k)}
        if fields:
            changed.append({"node_id":nid,"changes":fields})

    score_changes=[]
    cs=control["scoreboard_scores"];as_=active["scoreboard_scores"]
    for key in sorted(set(cs)|set(as_)):
        if cs.get(key)!=as_.get(key):
            score_changes.append({"score":key,"control":cs.get(key),"activated":as_.get(key)})

    def target_key(row):
        return (
            row.get("source"),
            tuple(row.get("target_position") or []),
            row.get("target_kind"),
        )
    ct={target_key(x):x for x in control.get("world_targets",[])}
    at={target_key(x):x for x in active.get("world_targets",[])}
    target_changes=[]
    for key in sorted(set(ct)|set(at),key=str):
        c=(ct.get(key) or {}).get("state")
        a=(at.get(key) or {}).get("state")
        if c!=a:
            source,pos,kind=key
            target_changes.append({
                "source":source,
                "target_position":list(pos),
                "target_kind":kind,
                "control":c,
                "activated":a,
            })
    return {
        "command_block_changes":changed,
        "scoreboard_changes":score_changes,
        "world_target_changes":target_changes,
    }

def run_trial(server_jar, source_zip, probe, trial_dir, activate):
    world=trial_dir/"world"
    materialize_world(source_zip,world)
    set_spawn(world,probe["position"])
    (trial_dir/"eula.txt").write_text("eula=true\n")
    (trial_dir/"server.properties").write_text("\n".join([
      "online-mode=false","server-port=25579","level-name=world",
      "enable-command-block=true","spawn-protection=0","max-players=1",
      "view-distance=6","difficulty=1","gamemode=2",
      "motd=SupraCraft paired legacy mechanism probe"
    ])+"\n")
    log_path=trial_dir/"server.log"
    with log_path.open("w",encoding="utf-8") as log:
        p=subprocess.Popen(
          ["java","-Xms512M","-Xmx2G","-jar",str(server_jar),"nogui"],
          cwd=trial_dir,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True
        )
        ready=wait_ready(p,log_path,180)
        time.sleep(3)
        if activate:
            family=probe["family"]
            if family not in ACTIVATABLE:
                raise RuntimeError(f"probe family not activatable: {family}")
            meta=int(probe.get("legacy_metadata") or 0)
            powered=meta|0x8
            block={
              "lever":"minecraft:lever",
              "stone_button":"minecraft:stone_button",
              "wooden_button":"minecraft:wooden_button",
            }[family]
            x,y,z=probe["position"]
            send(p,f"setblock {x} {y} {z} {block} {powered} replace")
            time.sleep(4)
        else:
            time.sleep(4)
        send(p,"save-all")
        time.sleep(2)
        send(p,"stop")
        rc=p.wait(timeout=60)
    text=log_path.read_text("utf-8",errors="replace")
    if rc!=0 or "Exception in server tick loop" in text:
        raise RuntimeError(f"trial failed activate={activate} rc={rc}")
    snap=snapshot(world,probe["position"])
    return {"ready_seconds":round(ready,3),"snapshot":snap}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--version",default="1.8.8")
    ap.add_argument("--world-zip",type=Path,required=True)
    ap.add_argument("--selection",type=Path,required=True)
    ap.add_argument("--limit",type=int,default=3)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    selection=json.loads(args.selection.read_text())
    probes=[p for p in selection["selected"] if p["family"] in ACTIVATABLE][:args.limit]
    if not probes:raise RuntimeError("selection contains no automatable lever/button probes")

    entry,meta,server_meta=resolve_version(args.version)
    with tempfile.TemporaryDirectory(prefix="paired-legacy-probes-") as td:
        root=Path(td); server=root/"server.jar"
        download(server_meta,server)
        results=[]
        for i,probe in enumerate(probes):
            control_dir=root/f"probe-{i}-control";active_dir=root/f"probe-{i}-active"
            control_dir.mkdir();active_dir.mkdir()
            control=run_trial(server,args.world_zip,probe,control_dir,False)
            active=run_trial(server,args.world_zip,probe,active_dir,True)
            diff=delta(control["snapshot"],active["snapshot"])
            results.append({
              "probe":probe,
              "control_ready_seconds":control["ready_seconds"],
              "activated_ready_seconds":active["ready_seconds"],
              "delta":diff,
              "evidence":{
                "command_block_change_count":len(diff["command_block_changes"]),
                "scoreboard_change_count":len(diff["scoreboard_changes"]),
                "world_target_change_count":len(diff["world_target_changes"]),
                "world_target_actuation_observed":bool(diff["world_target_changes"]),
                "runtime_effect_observed":bool(
                    diff["command_block_changes"] or
                    diff["scoreboard_changes"] or
                    diff["world_target_changes"]
                )
              }
            })

    result={
      "schema":"supracraft-paired-legacy-runtime-probes/1",
      "minecraft_version":args.version,
      "probe_count":len(results),
      "paired_control_design":True,
      "results":results,
      "limitations":[
        "Activation uses server-side block-state mutation as an actuator surrogate, not a real player's click packet.",
        "Hashed LastOutput changes can prove command execution/failure without retaining map text, but do not identify the message semantics.",
        "Resolved integer command world-target positions are sampled as legacy block id/metadata so paired target-state deltas can prove observable world-state actuation without retaining command text.",
        "Only lever/button sensors are included in this phase.",
        "A missing observed delta does not prove no mechanism effect; entity effects, unresolved/dynamic command targets, and world changes outside captured target positions may be missed.",
        "Every control and activated trial starts from a fresh copy of the exact source artifact."
      ]
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
