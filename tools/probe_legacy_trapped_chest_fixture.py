#!/usr/bin/env python3
"""Exact Minecraft 1.8.8 paired trapped-chest opening causal fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path

from analyze_legacy_causal_machinery import chunk_level, iter_chunks, plain
from probe_legacy_reference_mechanisms import delta, scoped_execution_receipt, snapshot
from run_legacy_reference_server import download, resolve_version, send, wait_ready

CHEST=(0,65,0)
WIRE=(1,65,0)
COMMAND=(2,65,0)
TARGET=(4,65,0)
PLAYER_STAND=(0.5,65,2.5)
NEUTRAL_SPAWN=(0,65,8)
FIXTURE_COMMAND="setblock 4 65 0 minecraft:redstone_block"
FIXTURE_COMMAND_SHA256=hashlib.sha256(FIXTURE_COMMAND.encode("utf-8")).hexdigest()


def tile_inventory_fingerprint(world: Path, pos):
    wanted=tuple(int(v) for v in pos)
    for region in sorted((world/"region").glob("r.*.*.mca")):
        for root in iter_chunks(region):
            level=chunk_level(root)
            if int(plain(level.get("xPos",0))) != wanted[0]//16:
                continue
            if int(plain(level.get("zPos",0))) != wanted[2]//16:
                continue
            for te in level.get("TileEntities",[]):
                try:
                    te_pos=(
                        int(plain(te["x"])),
                        int(plain(te["y"])),
                        int(plain(te["z"])),
                    )
                except Exception:
                    continue
                if te_pos != wanted:
                    continue
                items=te.get("Items",[])
                unpacked=items.unpack() if hasattr(items,"unpack") else items
                payload=json.dumps(
                    unpacked,
                    sort_keys=True,
                    separators=(",",":"),
                    default=str,
                ).encode("utf-8")
                return {
                    "present":True,
                    "item_entry_count":len(items),
                    "sha256":hashlib.sha256(payload).hexdigest(),
                }
    return {"present":False,"item_entry_count":None,"sha256":None}


def live_testforblock(proc, log_path: Path, pos, block: str, expected_meta: int):
    x,y,z=(int(v) for v in pos)
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
        "position":[x,y,z],
        "expected_legacy_metadata":int(expected_meta),
        "matched":success in segment,
        "response_sha256":hashlib.sha256(segment.encode("utf-8")).hexdigest(),
    }


def read_json_retry(path: Path, timeout=2.0):
    deadline=time.monotonic()+timeout
    last=None
    while time.monotonic()<deadline:
        try:
            if path.exists():
                return json.loads(path.read_text())
        except (json.JSONDecodeError,OSError) as exc:
            last=exc
        time.sleep(0.025)
    if last is not None:
        raise RuntimeError(f"could not read compact actor observation: {type(last).__name__}")
    return None


def start_actor(script: Path, trial_dir: Path, activate: bool):
    ready_path=trial_dir/"player-actor-ready.json"
    observation_path=trial_dir/"trapped-chest-observation.json"
    log_path=trial_dir/"player-actor.log"
    log=log_path.open("w",encoding="utf-8")
    proc=subprocess.Popen(
        [
            "node",str(script),
            "--host","127.0.0.1",
            "--port","25579",
            "--username","SupraChestBot",
            "--ready",str(ready_path),
            "--observation",str(observation_path),
            "--activate","true" if activate else "false",
            "--target-x",str(CHEST[0]),
            "--target-y",str(CHEST[1]),
            "--target-z",str(CHEST[2]),
        ],
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
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
            f"trapped-chest player actor failed to become ready: receipt={receipt} rc={proc.poll()}"
        )
    actor={
        "schema":receipt.get("schema"),
        "status":receipt.get("status"),
        "minecraft_version":receipt.get("minecraft_version"),
        "protocol_version":receipt.get("protocol_version"),
        "mineflayer_version":receipt.get("mineflayer_version"),
    }
    return proc,log,actor,observation_path


def prime_fixture_chunk(proc):
    send(
        proc,
        f"setworldspawn {NEUTRAL_SPAWN[0]} {NEUTRAL_SPAWN[1]} {NEUTRAL_SPAWN[2]}",
    )
    time.sleep(0.5)


def configure_fixture(proc):
    commands=[
        "gamerule commandBlockOutput false",
        "fill -2 63 -3 6 70 3 minecraft:air",
        "setblock 0 64 0 minecraft:stone 0 replace",
        "setblock 1 64 0 minecraft:stone 0 replace",
        "setblock 0 64 2 minecraft:stone 0 replace",
        "setblock 0 65 0 minecraft:trapped_chest 3 replace",
        "setblock 1 65 0 minecraft:redstone_wire 0 replace",
        (
            'setblock 2 65 0 minecraft:command_block 0 replace '
            '{Command:"setblock 4 65 0 minecraft:redstone_block",TrackOutput:1b}'
        ),
        "setblock 4 65 0 minecraft:air 0 replace",
        "setblock 0 64 8 minecraft:barrier 0 replace",
    ]
    for command in commands:
        send(proc,command)
        time.sleep(0.08)


def verify_fixture_setup(proc, log_path: Path):
    checks={
        "trapped_chest":live_testforblock(
            proc,log_path,CHEST,"minecraft:trapped_chest",3
        ),
        "wire_unpowered":live_testforblock(
            proc,log_path,WIRE,"minecraft:redstone_wire",0
        ),
        "command_block":live_testforblock(
            proc,log_path,COMMAND,"minecraft:command_block",0
        ),
        "target_air":live_testforblock(
            proc,log_path,TARGET,"minecraft:air",0
        ),
    }
    return {
        "all_matched":all(row["matched"] for row in checks.values()),
        "checks":checks,
    }


def run_trial(server_jar: Path, trial_dir: Path, actor_script: Path, activate: bool):
    (trial_dir/"eula.txt").write_text("eula=true\n")
    (trial_dir/"server.properties").write_text("\n".join([
        "online-mode=false",
        "server-port=25579",
        "level-name=world",
        "level-type=FLAT",
        "level-seed=188",
        "generate-structures=false",
        "enable-command-block=true",
        "spawn-protection=0",
        "spawn-radius=0",
        "max-players=1",
        "view-distance=6",
        "difficulty=1",
        "gamemode=2",
        "motd=SupraCraft exact 1.8.8 trapped chest fixture",
    ])+"\n")
    log_path=trial_dir/"server.log"
    with log_path.open("w",encoding="utf-8") as log:
        server=subprocess.Popen(
            ["java","-Xms512M","-Xmx2G","-jar",str(server_jar),"nogui"],
            cwd=trial_dir,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        ready=wait_ready(server,log_path,180)
        # A fresh 1.8.8 world does not guarantee that the synthetic target
        # chunk is resident before any player joins. Prime the login spawn,
        # let the exact-version actor load that chunk, then materialize and
        # verify the fixture before attempting interaction.
        prime_fixture_chunk(server)
        actor_proc,actor_log,actor,observation_path=start_actor(
            actor_script,trial_dir,activate
        )
        time.sleep(0.75)
        configure_fixture(server)
        send(server,"save-all")
        time.sleep(1)
        setup_verification=verify_fixture_setup(server,log_path)
        send(
            server,
            f"tp SupraChestBot {NEUTRAL_SPAWN[0] + 0.5} {NEUTRAL_SPAWN[1]} {NEUTRAL_SPAWN[2] + 0.5}",
        )
        time.sleep(0.5)

        control_observation=read_json_retry(observation_path)
        if activate:
            send(
                server,
                f"tp SupraChestBot {PLAYER_STAND[0]} {PLAYER_STAND[1]} {PLAYER_STAND[2]}",
            )
            deadline=time.monotonic()+6
            activated_observation=None
            while time.monotonic()<deadline:
                activated_observation=read_json_retry(observation_path,0.25)
                if activated_observation and activated_observation.get("open_observed"):
                    break
                if activated_observation and activated_observation.get("open_call_status")=="blocked":
                    break
                time.sleep(0.05)
            observation=activated_observation
            power_query=live_testforblock(
                server,log_path,WIRE,"minecraft:redstone_wire",1
            )
            time.sleep(0.5)
        else:
            observation=control_observation
            power_query=live_testforblock(
                server,log_path,WIRE,"minecraft:redstone_wire",0
            )
            time.sleep(0.5)

        send(server,"save-all")
        time.sleep(1)
        snap=snapshot(
            trial_dir/"world",
            CHEST,
            sensor_node_id="0,65,0",
            target_command_ids={"2,65,0"},
            radius=16,
        )
        inventory=tile_inventory_fingerprint(trial_dir/"world",CHEST)

        if actor_proc.poll() is None:
            actor_proc.terminate()
            try:
                actor_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                actor_proc.kill()
                actor_proc.wait(timeout=5)
        actor_log.close()

        send(server,"stop")
        rc=server.wait(timeout=60)

    server_text=log_path.read_text("utf-8",errors="replace")
    if rc!=0 or "Exception in server tick loop" in server_text:
        raise RuntimeError(f"trapped-chest fixture trial failed activate={activate} rc={rc}")
    return {
        "ready_seconds":round(ready,3),
        "player_actor":actor,
        "sensor_observation":observation,
        "opening_power_witness":power_query,
        "inventory_fingerprint":inventory,
        "fixture_setup_verification":setup_verification,
        "snapshot":snap,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--version",default="1.8.8")
    ap.add_argument("--player-client-script",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    entry,meta,server_meta=resolve_version(args.version)
    with tempfile.TemporaryDirectory(prefix="trapped-chest-1-8-8-") as td:
        root=Path(td)
        server_jar=root/"server.jar"
        download(server_meta,server_jar)
        control_dir=root/"control"
        active_dir=root/"activated"
        control_dir.mkdir()
        active_dir.mkdir()
        actor_script=args.player_client_script.resolve()

        control=run_trial(server_jar,control_dir,actor_script,False)
        active=run_trial(server_jar,active_dir,actor_script,True)

        diff=delta(control["snapshot"],active["snapshot"])
        cscope=control["snapshot"].get("world_target_source_scope",[])
        ascope=active["snapshot"].get("world_target_source_scope",[])
        if cscope != ascope:
            raise RuntimeError(
                f"world-target source scope changed across paired trials: control={cscope} activated={ascope}"
            )
        receipt=scoped_execution_receipt(
            control["snapshot"],active["snapshot"],cscope,diff
        )

    inventory_unchanged=(
        control["inventory_fingerprint"]==active["inventory_fingerprint"]
    )
    open_observed=bool(
        (active.get("sensor_observation") or {}).get("open_observed")
    )
    result={
        "schema":"supracraft-paired-legacy-trapped-chest-opening/1",
        "minecraft_version":args.version,
        "paired_control_design":True,
        "fixture":{
            "trapped_chest_position":list(CHEST),
            "opening_power_witness_position":list(WIRE),
            "command_node_id":"2,65,0",
            "world_target_position":list(TARGET),
            "command_verb":"setblock",
            "command_sha256":FIXTURE_COMMAND_SHA256,
            "comparator_present":False,
            "inventory_fixture":"empty_and_unchanged",
        },
        "activation_method":"paired_exact_1.8.8_player_open",
        "fixture_setup_verification":{
            "control":control["fixture_setup_verification"],
            "activated":active["fixture_setup_verification"],
        },
        "player_actor":{
            "control":control["player_actor"],
            "activated":active["player_actor"],
        },
        "sensor_observation":{
            "control":control["sensor_observation"],
            "activated":active["sensor_observation"],
        },
        "opening_power_witness":{
            "control":control["opening_power_witness"],
            "activated":active["opening_power_witness"],
        },
        "inventory_fingerprint":{
            "control":control["inventory_fingerprint"],
            "activated":active["inventory_fingerprint"],
            "unchanged":inventory_unchanged,
        },
        "world_target_source_scope":cscope,
        "execution_receipt":receipt,
        "delta":diff,
        "evidence":{
            "player_open_count_observed":open_observed,
            "opening_power_witness_observed":bool(
                active["opening_power_witness"].get("matched")
            ),
            "inventory_unchanged":inventory_unchanged,
            "command_block_change_count":len(diff["command_block_changes"]),
            "scoreboard_change_count":len(diff["scoreboard_changes"]),
            "world_target_change_count":len(diff["world_target_changes"]),
            "world_target_actuation_observed":bool(diff["world_target_changes"]),
            "outcome_class":receipt["outcome_class"],
            "runtime_effect_observed":bool(
                diff["command_block_changes"]
                or diff["scoreboard_changes"]
                or diff["world_target_changes"]
            ),
        },
        "channel_boundary":{
            "qualified":"player_open_count_to_redstone_power",
            "held_separate":"inventory_fullness_to_comparator_signal",
            "comparator_behavior_exercised":False,
        },
        "limitations":[
            "This is a synthetic exact-1.8.8 causal fixture, not evidence that a trapped-chest opening path exists in the frozen CORE artifact.",
            "The paired arms differ only by the real exact-version player opening the fixture chest; both start from fresh flat worlds with the same seed and identical fixture materialization.",
            "The trapped-chest inventory is empty in both arms and is compared by compact hash/count; comparator inventory/fullness behavior is intentionally not exercised.",
            "The opening sensor is observed through the exact chest-lid/open-count client event and a direct adjacent redstone-wire metadata witness.",
            "The compact execution receipt retains command verb/hash/state and scoped target block state only; it does not retain raw command or raw feedback/message text.",
            "Successful mechanism execution is structural/runtime evidence, not player comprehension or a qualitative score.",
        ],
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
