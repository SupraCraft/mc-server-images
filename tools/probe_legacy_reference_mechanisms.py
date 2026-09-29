#!/usr/bin/env python3
"""Paired control/activated runtime probes for legacy Minecraft mechanisms."""

from __future__ import annotations

import argparse, copy, json, shutil, subprocess, tempfile, time, urllib.request, zipfile
from pathlib import Path

import nbtlib

from analyze_legacy_causal_machinery import analyze as analyze_machinery
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
    score=d.get("semantic_state",{})
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
        for k in ("success_count","condition_met","powered","last_execution"):
            if c.get(k)!=a.get(k):
                fields[k]={"control":c.get(k),"activated":a.get(k)}
        if fields:
            changed.append({"node_id":nid,"changes":fields})

    score_changes=[]
    cs=control["scoreboard_scores"];as_=active["scoreboard_scores"]
    for key in sorted(set(cs)|set(as_)):
        if cs.get(key)!=as_.get(key):
            score_changes.append({"score":key,"control":cs.get(key),"activated":as_.get(key)})
    return {"command_block_changes":changed,"scoreboard_changes":score_changes}

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
                "runtime_effect_observed":bool(diff["command_block_changes"] or diff["scoreboard_changes"])
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
        "Only lever/button sensors are included in this phase.",
        "A missing observed delta does not prove no mechanism effect; block/entity effects outside captured state may be missed.",
        "Every control and activated trial starts from a fresh copy of the exact source artifact."
      ]
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
