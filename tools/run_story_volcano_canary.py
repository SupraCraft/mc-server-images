#!/usr/bin/env python3
"""Exact Java 26.3 runtime canary for the recurring resource volcano slice."""

from __future__ import annotations
import argparse, json, shutil, subprocess, tempfile, time
from pathlib import Path

from generate_vanilla_worldgen_bootstrap import download_server, wait_ready, command
from story_volcano_pack import PACK_NAME, write_volcano_pack

def wait_marker(log_path:Path,marker:str,process,timeout:float):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if process.poll() is not None:
            break
        text=log_path.read_text("utf-8",errors="replace") if log_path.exists() else ""
        if marker in text:
            return
        time.sleep(0.1)
    tail=log_path.read_text("utf-8",errors="replace")[-12000:] if log_path.exists() else ""
    raise RuntimeError(f"marker timeout {marker}: {tail}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    args=ap.parse_args()
    ev=json.loads(args.evidence.read_text())
    if ev["minecraft_version"]!="26.3":
        raise SystemExit("exact Java 26.3 required")
    data_major=int(ev["artifact_version_json"]["pack_version"]["data_major"])
    args.output_dir.mkdir(parents=True,exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="story-volcano-") as td:
        root=Path(td); world=root/"world"; world.mkdir()
        manifest=write_volcano_pack(
            world,data_major,cx=0,base_y=100,cz=0,
            underwater=True,water_surface_y=104,max_cycles=3,
            warning_ticks=2,eruption_ticks=2,cooling_ticks=2,dormant_ticks=2,
        )
        server=root/"server.jar"; download_server(ev,server)
        (root/"eula.txt").write_text("eula=true\n")
        (root/"server.properties").write_text("\n".join([
            "online-mode=false","server-port=25583","view-distance=3",
            "simulation-distance=3","spawn-protection=0","max-players=1",
            "allow-flight=true","gamemode=creative","difficulty=peaceful",
            "level-name=world","level-seed=263300",
            "level-type=minecraft:flat","generate-structures=false",
            "generator-settings={\"biome\":\"minecraft:ocean\",\"layers\":[{\"block\":\"minecraft:bedrock\",\"height\":1},{\"block\":\"minecraft:stone\",\"height\":2}]}",
            f"initial-enabled-packs=vanilla,file/{PACK_NAME}",
            "initial-disabled-packs=",
            "motd=SupraCraft recurring volcano canary",
        ])+"\n")
        log_path=root/"server.log"
        with log_path.open("w",encoding="utf-8") as log:
            p=subprocess.Popen(["java","-Xms512M","-Xmx2G","-jar",str(server),"nogui"],
                cwd=root,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True)
            ready=wait_ready(p,log_path,180)
            command(p,"forceload add -16 -16 16 16")
            command(p,"fill -8 99 -8 8 99 8 minecraft:stone")
            command(p,"fill -8 100 -8 8 104 8 minecraft:water")
            command(p,"function supracraft_volcano:start")
            wait_marker(log_path,"SUPRACRAFT_VOLCANO_COMPLETE",p,20)
            wait_marker(log_path,"SUPRACRAFT_VOLCANO_ISLAND_EMERGED",p,5)
            command(p,"execute if score #volcano scv_cycle matches 3 run say SUPRACRAFT_VOLCANO_CYCLE_PASS")
            command(p,"execute if block 0 105 0 minecraft:basalt run say SUPRACRAFT_VOLCANO_ISLAND_BLOCK_PASS")
            command(p,"execute if block 0 103 1 minecraft:gold_ore run say SUPRACRAFT_VOLCANO_RESOURCE_PASS")
            time.sleep(1)
            command(p,"save-all flush")
            command(p,"stop")
            rc=p.wait(timeout=60)

        text=log_path.read_text("utf-8",errors="replace")
        required=[
            "SUPRACRAFT_VOLCANO_START",
            "SUPRACRAFT_VOLCANO_WARNING",
            "SUPRACRAFT_VOLCANO_ERUPTION cycle=1",
            "SUPRACRAFT_VOLCANO_ERUPTION cycle=2",
            "SUPRACRAFT_VOLCANO_ERUPTION cycle=3",
            "SUPRACRAFT_VOLCANO_RESOURCES_READY cycle=3",
            "SUPRACRAFT_VOLCANO_ISLAND_EMERGED",
            "SUPRACRAFT_VOLCANO_COMPLETE",
            "SUPRACRAFT_VOLCANO_CYCLE_PASS",
            "SUPRACRAFT_VOLCANO_ISLAND_BLOCK_PASS",
            "SUPRACRAFT_VOLCANO_RESOURCE_PASS",
        ]
        diagnostics=[line for line in text.splitlines() if any(x in line for x in (
            "Unknown or incomplete command","Incorrect argument","[Server thread/ERROR]","Exception","Crash"
        ))]
        if rc!=0 or diagnostics or not all(x in text for x in required):
            raise SystemExit(json.dumps({
                "rc":rc,"diagnostics":diagnostics[-50:],
                "missing":[x for x in required if x not in text]
            },indent=2))
        receipt={
            "schema":"supracraft-volcano-runtime/1",
            "edition":"java","minecraft_version":"26.3",
            "story_id":"recurring_resource_volcano_v1",
            "implementation_mode":"command_orchestrated",
            "canary_pass":True,
            "cycles_completed":3,
            "resource_ready":True,
            "island_emerged":True,
            "ready_seconds":round(ready,6),
            "lowering_manifest":manifest,
        }
        (args.output_dir/"volcano-runtime.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
        (args.output_dir/"server.log").write_text(text,"utf-8")
        print(json.dumps(receipt,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
