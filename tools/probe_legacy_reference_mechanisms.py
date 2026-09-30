#!/usr/bin/env python3
"""Paired control/activated runtime probes for legacy Minecraft mechanisms."""

from __future__ import annotations

import argparse, copy, hashlib, json, shutil, subprocess, tempfile, time, urllib.request, zipfile
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
from select_legacy_runtime_probes import candidate_graph, component

STABLE_ACTIVATABLE = {"lever","stone_button","wooden_button"}
PRESSURE_PLATE_ACTIVATABLE = {
    "stone_pressure_plate","wooden_pressure_plate",
    "light_weighted_pressure_plate","heavy_weighted_pressure_plate",
}
ACTIVATABLE = STABLE_ACTIVATABLE | PRESSURE_PLATE_ACTIVATABLE

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


def snapshot(world: Path, center, sensor_node_id=None, target_command_ids=None, radius=96):
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
    explicit_target_ids=set(target_command_ids or [])
    if explicit_target_ids:
        target_source_scope=local_command_ids & explicit_target_ids
    elif sensor_node_id:
        graph_nodes,graph=candidate_graph(d)
        members=component(graph,sensor_node_id)
        derived_command_ids={
            nid for nid in members
            if nid in graph_nodes and "command_block" in str(graph_nodes[nid].get("family",""))
        }
        target_source_scope=local_command_ids & derived_command_ids
    else:
        target_source_scope=set(local_command_ids)
    target_specs=[]
    target_positions=[]
    for edge in d.get("edges",{}).get("command_world_targets",[]):
        if edge.get("source") not in target_source_scope:
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
    sensor_states=legacy_block_states_at(world,[center])
    sensor_key=f"{int(center[0])},{int(center[1])},{int(center[2])}"
    return {
      "command_blocks":nodes,
      "scoreboard_scores":objective_scores,
      "world_targets":world_targets,
      "world_target_source_scope":sorted(target_source_scope),
      "sensor_state":sensor_states[sensor_key],
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

def scoped_execution_receipt(control, active, scope, diff):
    """Preserve compact paired outcome evidence without retaining command/message text."""
    scope=set(scope)
    ccmd={x["node_id"]:x for x in control.get("command_blocks",[])}
    acmd={x["node_id"]:x for x in active.get("command_blocks",[])}
    command_fields=(
        "verb","sha256","success_count","condition_met",
        "powered","last_execution","last_output_sha256",
    )
    commands=[]
    for nid in sorted(scope):
        c=(ccmd.get(nid) or {}).get("command") or {}
        a=(acmd.get(nid) or {}).get("command") or {}
        commands.append({
            "node_id":nid,
            "control":{k:c.get(k) for k in command_fields},
            "activated":{k:a.get(k) for k in command_fields},
        })

    def target_key(row):
        return (
            row.get("source"),
            tuple(row.get("target_position") or []),
            row.get("target_kind"),
        )
    ct={
        target_key(x):x
        for x in control.get("world_targets",[])
        if x.get("source") in scope
    }
    at={
        target_key(x):x
        for x in active.get("world_targets",[])
        if x.get("source") in scope
    }
    targets=[]
    for key in sorted(set(ct)|set(at),key=str):
        source,pos,kind=key
        c=(ct.get(key) or {}).get("state")
        a=(at.get(key) or {}).get("state")
        row=ct.get(key) or at.get(key) or {}
        targets.append({
            "source":source,
            "target_position":list(pos),
            "target_kind":kind,
            "verb":row.get("verb"),
            "control":c,
            "activated":a,
            "changed":c!=a,
        })

    changed_command_ids={
        row.get("node_id") for row in diff.get("command_block_changes",[])
        if row.get("node_id") in scope
    }
    if diff.get("world_target_changes"):
        outcome_class="observable_world_target_actuation"
    elif changed_command_ids:
        outcome_class="selected_command_state_change_without_observable_target_delta"
    elif diff.get("scoreboard_changes"):
        outcome_class="other_runtime_state_change_without_observable_target_delta"
    else:
        outcome_class="no_observed_runtime_effect"

    return {
        "schema":"supracraft-legacy-execution-receipt/1",
        "command_scope":sorted(scope),
        "changed_command_ids":sorted(changed_command_ids),
        "commands":commands,
        "targets":targets,
        "outcome_class":outcome_class,
        "interpretation_limit":"No target delta does not distinguish failure, no-op, same-state actuation, or an effect outside captured targets.",
    }

def live_testforblock(proc, log_path, probe, expected_meta):
    """Query exact live sensor block state without retaining raw console feedback."""
    family=probe["family"]
    block={
      "stone_pressure_plate":"minecraft:stone_pressure_plate",
      "wooden_pressure_plate":"minecraft:wooden_pressure_plate",
      "light_weighted_pressure_plate":"minecraft:light_weighted_pressure_plate",
      "heavy_weighted_pressure_plate":"minecraft:heavy_weighted_pressure_plate",
    }.get(family)
    if block is None:
        return None
    x,y,z=probe["position"]
    try:
        start=log_path.stat().st_size
    except FileNotFoundError:
        start=0
    send(proc,f"testforblock {x} {y} {z} {block} {int(expected_meta)}")
    deadline=time.monotonic()+2.0
    segment=""
    success=f"Successfully found the block at {x},{y},{z}."
    while time.monotonic()<deadline:
        time.sleep(0.05)
        with log_path.open("r",encoding="utf-8",errors="replace") as fh:
            fh.seek(start)
            segment=fh.read()
        if success in segment:
            break
        if "commands.testforblock" in segment or "The block at " in segment:
            break
    return {
      "query_kind":"exact_1.8.8_testforblock_metadata",
      "expected_legacy_metadata":int(expected_meta),
      "matched":success in segment,
      "response_sha256":hashlib.sha256(segment.encode("utf-8")).hexdigest(),
    }


def start_legacy_player_actor(script, trial_dir, port=25579):
    ready_path=trial_dir/"player-actor-ready.json"
    log_path=trial_dir/"player-actor.log"
    log=log_path.open("w",encoding="utf-8")
    proc=subprocess.Popen(
        [
            "node",str(script),
            "--host","127.0.0.1",
            "--port",str(port),
            "--username","SupraPlateBot",
            "--ready",str(ready_path),
        ],
        stdout=log,stderr=subprocess.STDOUT,text=True,
    )
    deadline=time.monotonic()+30
    receipt=None
    while time.monotonic()<deadline:
        if ready_path.exists():
            receipt=json.loads(ready_path.read_text())
            break
        if proc.poll() is not None:
            break
        time.sleep(0.1)
    if receipt is None or receipt.get("status")!="ready":
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=5)
        log.close()
        raise RuntimeError(
            f"legacy player actor failed to become ready: receipt={receipt} rc={proc.poll()}"
        )
    return proc,log,{
        "schema":receipt.get("schema"),
        "status":receipt.get("status"),
        "minecraft_version":receipt.get("minecraft_version"),
        "protocol_version":receipt.get("protocol_version"),
        "mineflayer_version":receipt.get("mineflayer_version"),
    }


def run_trial(server_jar, source_zip, probe, trial_dir, activate, player_client_script=None):
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
        family=probe["family"]
        if family not in ACTIVATABLE:
            raise RuntimeError(f"probe family not activatable: {family}")
        live_sensor_query=None
        player_proc=None
        player_log=None
        player_actor=None
        x,y,z=probe["position"]

        if family in PRESSURE_PLATE_ACTIVATABLE:
            if player_client_script is None:
                raise RuntimeError("pressure-plate probes require --player-client-script")
            player_proc,player_log,player_actor=start_legacy_player_actor(
                player_client_script,trial_dir
            )
            # Keep player presence and gamemode paired across both arms. The
            # neutral platform is far outside the local causal snapshot; only
            # the activated arm moves that same player onto the plate.
            nx,nz=x+128,z+128
            send(p,f"gamemode 3 SupraPlateBot")
            send(p,f"setblock {nx} 249 {nz} minecraft:barrier 0 replace")
            send(p,f"tp SupraPlateBot {nx + 0.5} 250 {nz + 0.5}")
            time.sleep(0.5)
            send(p,f"gamemode 2 SupraPlateBot")
            time.sleep(0.5)

        if activate:
            if family in STABLE_ACTIVATABLE:
                meta=int(probe.get("legacy_metadata") or 0)
                powered=meta|0x8
                block={
                  "lever":"minecraft:lever",
                  "stone_button":"minecraft:stone_button",
                  "wooden_button":"minecraft:wooden_button",
                }[family]
                send(p,f"setblock {x} {y} {z} {block} {powered} replace")
                time.sleep(4)
            elif family in PRESSURE_PLATE_ACTIVATABLE:
                send(p,f"tp SupraPlateBot {x + 0.5} {y} {z + 0.5}")
                time.sleep(0.25)
                live_sensor_query=live_testforblock(p,log_path,probe,1)
                time.sleep(3.5)
        else:
            if family in PRESSURE_PLATE_ACTIVATABLE:
                time.sleep(0.25)
                live_sensor_query=live_testforblock(
                    p,log_path,probe,int(probe.get("legacy_metadata") or 0)
                )
                time.sleep(3.5)
            else:
                time.sleep(4)
        send(p,"save-all")
        time.sleep(2)

        # Capture dynamic occupancy-backed block state while the world is still
        # live. Server shutdown can unload entities before the final on-disk
        # observation, which would collapse a valid pressure-plate activation
        # back to its unpowered state.
        target_command_ids={
            row.get("node_id")
            for row in probe.get("candidate_component_commands",[])
            if row.get("node_id")
        }
        snap=snapshot(
            world,
            probe["position"],
            sensor_node_id=probe.get("node_id"),
            target_command_ids=target_command_ids or None,
        )

        send(p,"stop")
        rc=p.wait(timeout=60)
        if player_proc is not None:
            if player_proc.poll() is None:
                player_proc.terminate()
                try:
                    player_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    player_proc.kill()
                    player_proc.wait(timeout=5)
            if player_log is not None:
                player_log.close()
    text=log_path.read_text("utf-8",errors="replace")
    if rc!=0 or "Exception in server tick loop" in text:
        raise RuntimeError(f"trial failed activate={activate} rc={rc}")
    return {
        "ready_seconds":round(ready,3),
        "snapshot":snap,
        "live_sensor_query":live_sensor_query,
        "player_actor":player_actor,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--version",default="1.8.8")
    ap.add_argument("--world-zip",type=Path,required=True)
    ap.add_argument("--selection",type=Path,required=True)
    ap.add_argument("--limit",type=int,default=3)
    ap.add_argument("--player-client-script",type=Path)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    selection=json.loads(args.selection.read_text())
    probes=[p for p in selection["selected"] if p["family"] in ACTIVATABLE][:args.limit]
    if not probes:raise RuntimeError("selection contains no supported runtime sensor probes")

    entry,meta,server_meta=resolve_version(args.version)
    with tempfile.TemporaryDirectory(prefix="paired-legacy-probes-") as td:
        root=Path(td); server=root/"server.jar"
        download(server_meta,server)
        results=[]
        for i,probe in enumerate(probes):
            control_dir=root/f"probe-{i}-control";active_dir=root/f"probe-{i}-active"
            control_dir.mkdir();active_dir.mkdir()
            player_script=(
                args.player_client_script.resolve()
                if args.player_client_script is not None else None
            )
            control=run_trial(
                server,args.world_zip,probe,control_dir,False,player_script
            )
            active=run_trial(
                server,args.world_zip,probe,active_dir,True,player_script
            )
            diff=delta(control["snapshot"],active["snapshot"])
            control_scope=control["snapshot"].get("world_target_source_scope",[])
            active_scope=active["snapshot"].get("world_target_source_scope",[])
            if control_scope != active_scope:
                raise RuntimeError(
                    f"world-target source scope changed across paired trials: "
                    f"control={control_scope} activated={active_scope}"
                )
            receipt=scoped_execution_receipt(
                control["snapshot"],
                active["snapshot"],
                control_scope,
                diff,
            )
            control_sensor=control["snapshot"].get("sensor_state")
            active_sensor=active["snapshot"].get("sensor_state")
            sensor_state_changed=control_sensor != active_sensor
            results.append({
              "probe":probe,
              "activation_method":(
                  "server_side_powered_block_state_surrogate"
                  if probe["family"] in STABLE_ACTIVATABLE
                  else "paired_exact_1.8.8_player_occupancy"
              ),
              "world_target_source_scope":control_scope,
              "execution_receipt":receipt,
              "control_ready_seconds":control["ready_seconds"],
              "activated_ready_seconds":active["ready_seconds"],
              "player_actor":{
                "control":control.get("player_actor"),
                "activated":active.get("player_actor"),
              },
              "live_sensor_query":{
                "control":control.get("live_sensor_query"),
                "activated":active.get("live_sensor_query"),
              },
              "sensor_state":{
                "control":control_sensor,
                "activated":active_sensor,
                "changed":sensor_state_changed,
              },
              "delta":diff,
              "evidence":{
                "sensor_state_change_observed":sensor_state_changed,
                "live_sensor_activation_observed":bool(
                    (active.get("live_sensor_query") or {}).get("matched")
                ),
                "command_block_change_count":len(diff["command_block_changes"]),
                "scoreboard_change_count":len(diff["scoreboard_changes"]),
                "world_target_change_count":len(diff["world_target_changes"]),
                "world_target_actuation_observed":bool(diff["world_target_changes"]),
                "outcome_class":receipt["outcome_class"],
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
        "World-target sampling is scoped to the feedback-blind command set in the selected probe component. Older selection artifacts without embedded command IDs are reconciled against the current static candidate graph; nearby command-state changes remain observable but cannot borrow attribution merely because they share a target coordinate.",
        "Stable lever/button activation remains a server-side powered-block-state surrogate; pressure-plate control and activated arms both use the same exact-1.8.8 offline player actor, with only the activated arm moving that player from an identical neutral platform onto the plate.",
        "Pressure-plate activation is checked immediately with exact 1.8.8 testforblock metadata and only a boolean plus response hash is retained; later saved metadata may legitimately return to zero after the trigger leaves.",
        "Compact execution receipts retain selected command hashes/verbs/state fields and scoped target block states for both trials, including unchanged values; raw command/message text is not retained.",
        "A missing observed target delta does not distinguish failure, no-op, same-state actuation, entity effects, unresolved/dynamic targets, or changes outside captured target positions.",
        "Every control and activated trial starts from a fresh copy of the exact source artifact."
      ]
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
