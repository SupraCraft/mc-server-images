#!/usr/bin/env python3
"""Exact Minecraft 1.8.8 trapped-chest inventory -> comparator fixture."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

from analyze_legacy_causal_machinery import chunk_level, iter_chunks, plain
from probe_legacy_reference_mechanisms import legacy_block_states_at
from probe_legacy_trapped_chest_fixture import (
    CHEST,
    NEUTRAL_SPAWN,
    live_testforblock,
    prime_fixture_chunk,
    read_json_retry,
    start_actor,
    tile_inventory_fingerprint,
)
from run_legacy_reference_server import download, resolve_version, send, wait_ready

COMPARATOR=(1,65,0)
EXPECTED_CONTROL_SIGNAL=0
EXPECTED_ACTIVATED_SIGNAL=1


def comparator_output_fingerprint(world: Path, pos):
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
                output=te.get("OutputSignal")
                return {
                    "present":True,
                    "output_signal":int(plain(output)) if output is not None else None,
                }
    return {"present":False,"output_signal":None}


def configure_fixture(proc):
    commands=[
        "gamerule commandBlockOutput false",
        "fill -2 63 -3 4 70 3 minecraft:air",
        "setblock 0 64 0 minecraft:stone 0 replace",
        "setblock 1 64 0 minecraft:stone 0 replace",
        "setblock 0 65 0 minecraft:trapped_chest 3 replace",
        # WEST has horizontal index 1 in exact 1.8.8. The comparator at
        # x=1 therefore samples the trapped chest immediately west at x=0.
        "setblock 1 65 0 minecraft:unpowered_comparator 1 replace",
    ]
    for command in commands:
        send(proc,command)
        time.sleep(0.08)


def verify_setup(proc, log_path: Path):
    checks={
        "trapped_chest":live_testforblock(
            proc,log_path,CHEST,"minecraft:trapped_chest",3
        ),
        "comparator_empty_input_state":live_testforblock(
            proc,log_path,COMPARATOR,"minecraft:unpowered_comparator",1
        ),
    }
    return {
        "all_matched":all(row["matched"] for row in checks.values()),
        "checks":checks,
    }


def run_trial(server_jar: Path, trial_dir: Path, actor_script: Path, activate_inventory: bool):
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
        "motd=SupraCraft exact 1.8.8 trapped chest comparator fixture",
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

        prime_fixture_chunk(server)
        actor_proc,actor_log,actor,observation_path=start_actor(
            actor_script,trial_dir,False
        )
        time.sleep(0.75)

        configure_fixture(server)
        time.sleep(0.5)
        setup=verify_setup(server,log_path)

        send(
            server,
            f"tp SupraChestBot {NEUTRAL_SPAWN[0] + 0.5} {NEUTRAL_SPAWN[1]} {NEUTRAL_SPAWN[2] + 0.5}",
        )
        time.sleep(0.25)

        if activate_inventory:
            send(
                server,
                "replaceitem block 0 65 0 slot.container.0 minecraft:stone 1 0",
            )
            # markDirty() notifies comparator outputs; allow update scheduling
            # and the comparator's two-tick delay to settle.
            time.sleep(1.0)
        else:
            time.sleep(1.0)

        actor_observation=read_json_retry(observation_path)
        if actor_proc.poll() is None:
            actor_proc.terminate()
            try:
                actor_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                actor_proc.kill()
                actor_proc.wait(timeout=5)
        actor_log.close()

        send(server,"save-all")
        time.sleep(1)
        send(server,"stop")
        rc=server.wait(timeout=60)

    server_text=log_path.read_text("utf-8",errors="replace")
    if rc!=0 or "Exception in server tick loop" in server_text:
        raise RuntimeError(
            f"trapped-chest comparator fixture failed activate_inventory={activate_inventory} rc={rc}"
        )

    world=trial_dir/"world"
    inventory=tile_inventory_fingerprint(world,CHEST)
    comparator=comparator_output_fingerprint(world,COMPARATOR)
    comparator_block=legacy_block_states_at(world,[COMPARATOR])["1,65,0"]

    return {
        "ready_seconds":round(ready,3),
        "player_actor":actor,
        "player_observation":actor_observation,
        "fixture_setup_verification":setup,
        "inventory_fingerprint":inventory,
        "comparator_output":comparator,
        "comparator_block_state":comparator_block,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--version",default="1.8.8")
    ap.add_argument("--player-client-script",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    entry,meta,server_meta=resolve_version(args.version)
    with tempfile.TemporaryDirectory(prefix="trapped-chest-comparator-1-8-8-") as td:
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

    result={
        "schema":"supracraft-paired-legacy-trapped-chest-comparator/1",
        "minecraft_version":args.version,
        "paired_control_design":True,
        "activation_method":"paired_inventory_fullness_replaceitem",
        "fixture":{
            "trapped_chest_position":list(CHEST),
            "comparator_position":list(COMPARATOR),
            "comparator_facing":"west",
            "control_inventory":"empty",
            "activated_inventory":"one stone in slot.container.0",
        },
        "player_actor":{
            "control":control["player_actor"],
            "activated":active["player_actor"],
        },
        "player_observation":{
            "control":control["player_observation"],
            "activated":active["player_observation"],
        },
        "fixture_setup_verification":{
            "control":control["fixture_setup_verification"],
            "activated":active["fixture_setup_verification"],
        },
        "inventory_fingerprint":{
            "control":control["inventory_fingerprint"],
            "activated":active["inventory_fingerprint"],
        },
        "comparator_output":{
            "control":control["comparator_output"],
            "activated":active["comparator_output"],
            "expected_control":EXPECTED_CONTROL_SIGNAL,
            "expected_activated":EXPECTED_ACTIVATED_SIGNAL,
        },
        "comparator_block_state":{
            "control":control["comparator_block_state"],
            "activated":active["comparator_block_state"],
        },
        "evidence":{
            "inventory_transition_observed":(
                control["inventory_fingerprint"].get("item_entry_count")==0
                and active["inventory_fingerprint"].get("item_entry_count")==1
            ),
            "comparator_signal_transition_observed":(
                control["comparator_output"].get("output_signal")==EXPECTED_CONTROL_SIGNAL
                and active["comparator_output"].get("output_signal")==EXPECTED_ACTIVATED_SIGNAL
            ),
            "chest_opening_observed":bool(
                (control.get("player_observation") or {}).get("open_observed")
                or (active.get("player_observation") or {}).get("open_observed")
            ),
        },
        "channel_boundary":{
            "qualified":"inventory_fullness_to_comparator_signal",
            "held_separate":"player_open_count_to_redstone_power",
            "player_open_behavior_exercised":False,
        },
        "limitations":[
            "This exact-1.8.8 paired runtime fixture exercises only the empty-to-one-item comparator transition; the exact source formula, not this bounded runtime rep, grounds the full 0..15 range.",
            "The neutral exact-version player actor exists only to load the synthetic fixture chunk and does not open the chest in either arm.",
            "Comparator OutputSignal is sampled from the durable exact-version comparator tile entity after clean shutdown.",
            "Inventory evidence retains compact item-entry count and hash only; no user-authored content is involved.",
            "Comparator execution is structural/runtime evidence, not player perception, comprehension, legibility, or qualitative value.",
        ],
    }

    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
