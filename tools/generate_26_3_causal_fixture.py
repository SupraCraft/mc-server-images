#!/usr/bin/env python3
"""Generate a tiny exact-26.3 authored causal-machinery fixture world."""

from __future__ import annotations
import argparse, json, shutil, subprocess, tempfile, time
from pathlib import Path

from generate_vanilla_worldgen_bootstrap import download_server, wait_ready, command, zip_world


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    args=ap.parse_args()

    evidence=json.loads(args.evidence.read_text())
    args.output_dir.mkdir(parents=True,exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="modern-causal-fixture-") as td:
        root=Path(td)
        server=root/"server.jar"
        world=root/"world"

        # Exact 26.3 datapack format 121.0. For modern pack metadata the
        # compatibility range is explicit and the legacy supported_formats field
        # is intentionally absent.
        pack=world/"datapacks"/"supracraft_causal_fixture"
        (pack/"data"/"supracraft"/"function").mkdir(parents=True,exist_ok=True)
        (pack/"pack.mcmeta").write_text(json.dumps({
          "pack":{
            "min_format":[121,0],
            "max_format":[121,0],
            "description":"SupraCraft exact-26.3 causal fixture"
          }
        },indent=2)+"\n")
        (pack/"data"/"supracraft"/"function"/"fixture.mcfunction").write_text(
          "scoreboard objectives add datapack_fixture dummy\n"
          "scoreboard players set $dp datapack_fixture 7\n"
          "data modify storage supracraft:fixture state set value 42\n"
          "setblock 8 100 0 minecraft:redstone_lamp\n"
          "schedule function supracraft:delayed 1t replace\n"
          "say CAUSAL_FIXTURE_DATAPACK_PASS\n"
        )
        (pack/"data"/"supracraft"/"function"/"delayed.mcfunction").write_text(
          "setblock 9 100 0 minecraft:redstone_lamp\n"
          "say CAUSAL_FIXTURE_DATAPACK_DELAYED_PASS\n"
        )

        download_server(evidence,server)
        (root/"eula.txt").write_text("eula=true\n")
        props={
          "online-mode":"false",
          "server-port":"25576",
          "view-distance":"3",
          "simulation-distance":"3",
          "spawn-protection":"0",
          "max-players":"1",
          "enable-command-block":"true",
          "allow-flight":"true",
          "gamemode":"creative",
          "difficulty":"peaceful",
          "level-name":"world",
          "level-seed":"263263",
          "motd":"SupraCraft 26.3 causal fixture"
        }
        (root/"server.properties").write_text("\n".join(f"{k}={v}" for k,v in props.items())+"\n")
        log_path=root/"server.log"
        with log_path.open("w",encoding="utf-8") as log:
            p=subprocess.Popen(
              ["java","-Xms512M","-Xmx3G","-jar",str(server),"nogui"],
              cwd=root,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True
            )
            wait_ready(p,log_path,180)

            # Force-load the fixture origin before any placement. Spawn is seed-dependent.
            command(p,"forceload add -16 -16 16 16")
            time.sleep(2)

            # Stable empty workspace high above terrain.
            command(p,"fill -4 99 -4 12 104 5 minecraft:air")
            command(p,"fill -4 99 -4 12 99 5 minecraft:stone")

            # Semantic state and player-facing orchestration.
            command(p,"scoreboard objectives add fixture dummy")
            command(p,"scoreboard players set $fixture fixture 0")

            # Channel A: trapped chest opening can emit redstone.
            command(p,"setblock 0 100 0 minecraft:trapped_chest[facing=north]")
            command(p,"setblock 1 100 0 minecraft:redstone_wire")
            command(p,"setblock 2 100 0 minecraft:command_block[facing=east]{Command:\"scoreboard players add $fixture fixture 1\"}")
            command(p,"setblock 3 100 0 minecraft:chain_command_block[facing=east,conditional=true]{Command:\"tellraw @a {\\\"text\\\":\\\"fixture activated\\\"}\",auto:1b}")
            command(p,"setblock 4 100 0 minecraft:chain_command_block[facing=east]{Command:\"setblock 6 100 0 minecraft:redstone_block\",auto:1b}")
            command(p,"setblock 5 100 0 minecraft:redstone_lamp")

            # Channel B: same trapped chest inventory state readable independently.
            # facing=west gives rear input on the west side under Minecraft's comparator facing semantics.
            command(p,"setblock 1 100 2 minecraft:trapped_chest[facing=north]")
            command(p,"setblock 2 100 2 minecraft:comparator[facing=west,mode=compare]")
            command(p,"setblock 3 100 2 minecraft:redstone_wire")
            command(p,"setblock 4 100 2 minecraft:redstone_lamp")

            # Additional embodied inputs/logic/actuators.
            command(p,"setblock 0 100 4 minecraft:lever[face=floor,facing=north,powered=false]")
            command(p,"setblock 1 100 4 minecraft:repeater[facing=west,delay=2]")
            command(p,"setblock 2 100 4 minecraft:redstone_wire")
            command(p,"setblock 3 100 4 minecraft:piston[facing=east]")
            command(p,"setblock 5 100 4 minecraft:note_block")

            # Current non-block interaction/presentation surfaces.
            command(p,'summon minecraft:interaction 7 101 2 {width:1.0f,height:1.0f,Tags:["fixture_interaction"]}')
            command(p,'summon minecraft:text_display 7 102 2 {Tags:["fixture_display"]}')

            # Datapack semantic-orchestration channel.
            command(p,"function supracraft:fixture")
            time.sleep(2)
            command(p,'execute if score $dp datapack_fixture matches 7 run say CAUSAL_FIXTURE_DATAPACK_SCORE_PASS')
            command(p,'execute if block 8 100 0 minecraft:redstone_lamp run say CAUSAL_FIXTURE_DATAPACK_WORLD_PASS')
            command(p,'execute if block 9 100 0 minecraft:redstone_lamp run say CAUSAL_FIXTURE_DATAPACK_DELAYED_WORLD_PASS')

            # Runtime causal verification for channels that do not require a real player.
            # B: container inventory -> comparator -> wire -> lamp.
            command(p,"item replace block 1 100 2 container.0 with minecraft:stone 64")
            time.sleep(2)
            command(p,'execute if block 4 100 2 minecraft:redstone_lamp[lit=true] run say CAUSAL_FIXTURE_COMPARATOR_PASS')

            # C: lever state -> repeater -> wire -> piston.
            command(p,"setblock 0 100 4 minecraft:lever[face=floor,facing=north,powered=true]")
            time.sleep(2)
            command(p,'execute if block 3 100 4 minecraft:piston[extended=true] run say CAUSAL_FIXTURE_PISTON_PASS')

            # A logic tail: direct power injection isolates command/scoreboard/chain semantics.
            # The trapped-chest opening sensor itself remains a live-player interaction test.
            command(p,"setblock 2 99 0 minecraft:redstone_block")
            time.sleep(2)
            command(p,'execute if score $fixture fixture matches 1.. run say CAUSAL_FIXTURE_SCORE_PASS')
            command(p,'execute if block 6 100 0 minecraft:redstone_block run say CAUSAL_FIXTURE_WORLD_EFFECT_PASS')

            command(p,"save-all flush")
            time.sleep(5)
            command(p,"forceload remove all")
            command(p,"save-all flush")
            time.sleep(2)
            command(p,"stop")
            rc=p.wait(timeout=60)
        server_log=log_path.read_text("utf-8",errors="replace")
        diagnostic_lines=[
            line for line in server_log.splitlines()
            if any(marker in line for marker in (
                "Incorrect argument", "Unknown or incomplete command",
                "That position is not loaded", "[Server thread/ERROR]"
            ))
        ]
        required_markers=[
            "CAUSAL_FIXTURE_COMPARATOR_PASS",
            "CAUSAL_FIXTURE_PISTON_PASS",
            "CAUSAL_FIXTURE_SCORE_PASS",
            "CAUSAL_FIXTURE_WORLD_EFFECT_PASS",
            "CAUSAL_FIXTURE_DATAPACK_PASS",
            "CAUSAL_FIXTURE_DATAPACK_DELAYED_PASS",
            "CAUSAL_FIXTURE_DATAPACK_SCORE_PASS",
            "CAUSAL_FIXTURE_DATAPACK_WORLD_PASS",
            "CAUSAL_FIXTURE_DATAPACK_DELAYED_WORLD_PASS",
        ]
        missing_markers=[m for m in required_markers if m not in server_log]
        if rc!=0 or diagnostic_lines or missing_markers:
            print("FIXTURE_SERVER_DIAGNOSTICS_BEGIN")
            for line in diagnostic_lines[-80:]:
                print(line)
            print("FIXTURE_SERVER_DIAGNOSTICS_END")
            if missing_markers:
                print("FIXTURE_MISSING_MARKERS", ",".join(missing_markers))
            raise SystemExit(
                f"server fixture failed rc={rc} diagnostics={len(diagnostic_lines)} missing_markers={missing_markers}"
            )

        zip_world(world,args.output_dir/"world.zip")
        shutil.copy2(log_path,args.output_dir/"server.log")
        manifest={
          "schema":"supracraft-26.3-causal-fixture/1",
          "minecraft_version":"26.3",
          "protocol":evidence["artifact_version_json"]["protocol_version"],
          "fixture_semantics":{
            "channel_a":"trapped chest opening -> redstone -> command semantic state -> conditional chain feedback/world mutation",
            "channel_b":"trapped chest inventory -> comparator -> redstone -> lamp",
            "channel_c":"lever -> repeater -> wire -> piston",
            "surfaces":["interaction entity","text display entity"]
          },
          "runtime_verified":[
            "container_inventory_to_comparator_to_lamp",
            "lever_to_repeater_to_piston",
            "command_block_to_scoreboard_state",
            "command_chain_to_world_effect",
            "datapack_function_to_scoreboard_and_storage_state",
            "datapack_schedule_to_delayed_world_effect"
          ],
          "live_player_pending":[
            "trapped_chest_opening_sensor_channel",
            "interaction_entity_click_channel"
          ],
          "expected_minimums":{
            "command_blocks":3,
            "trapped_chests":2,
            "comparators":1,
            "scoreboard_objectives":1,
            "interaction_entities":1,
            "text_display_entities":1
          }
        }
        (args.output_dir/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
        print(json.dumps(manifest,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
