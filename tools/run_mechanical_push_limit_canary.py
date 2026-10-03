#!/usr/bin/env python3
"""Exact Java 26.3 piston push-limit falsification.

Electrical power is fixture stimulus only. The semantic claim is mechanical:
12 movable blocks are within the bounded push set; 13 are not.
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, tempfile, time
from pathlib import Path
from generate_vanilla_worldgen_bootstrap import download_server, wait_ready
from run_modern_microscope_canary import checked_command, wait_for_state_marker

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",type=Path,required=True)
    ap.add_argument("--server-jar",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    args=ap.parse_args()
    ev=json.loads(args.evidence.read_text())
    if ev["minecraft_version"]!="26.3" or int(ev["artifact_version_json"]["java_version"])!=25:
        raise SystemExit("exact Java 26.3 / Java 25 required")
    args.output_dir.mkdir(parents=True,exist_ok=True)
    args.server_jar.parent.mkdir(parents=True,exist_ok=True)
    if not args.server_jar.exists():
        download_server(ev,args.server_jar)

    with tempfile.TemporaryDirectory(prefix="mechanical-push-limit-") as td:
        root=Path(td)
        server=root/"server.jar"; shutil.copy2(args.server_jar,server)
        (root/"eula.txt").write_text("eula=true\n")
        (root/"server.properties").write_text("\n".join([
            "online-mode=false","server-port=25581","view-distance=3",
            "simulation-distance=3","spawn-protection=0","max-players=1",
            "allow-flight=true","gamemode=creative","difficulty=peaceful",
            "level-name=world","level-seed=263266",
            "motd=SupraCraft mechanical push limit",
        ])+"\n")
        log_path=root/"server.log"
        with log_path.open("w",encoding="utf-8") as log:
            p=subprocess.Popen(["java","-Xms512M","-Xmx2G","-jar",str(server),"nogui"],
                cwd=root,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True)
            ready=wait_ready(p,log_path,180)
            checked_command(p,"forceload add -8 -8 24 8","forceload",log_path,args.output_dir)
            time.sleep(0.5)

            checked_command(p,"fill -3 99 -2 20 102 2 minecraft:air","clear12",log_path,args.output_dir)
            checked_command(p,"fill -3 99 -2 20 99 2 minecraft:stone","floor12",log_path,args.output_dir)
            checked_command(p,"setblock 0 100 0 minecraft:piston[facing=east]","piston12",log_path,args.output_dir)
            checked_command(p,"fill 1 100 0 12 100 0 minecraft:stone","payload12",log_path,args.output_dir)
            checked_command(p,"setblock -1 100 0 minecraft:redstone_block","stim12",log_path,args.output_dir)
            a12,s12=wait_for_state_marker(
                p,log_path,args.output_dir,"SUPRACRAFT_PUSH12_PASS",
                "execute if block 0 100 0 minecraft:piston[facing=east,extended=true] if block 13 100 0 minecraft:stone",
                "verify12",timeout_seconds=8.0)

            checked_command(p,"fill -3 100 -2 20 102 2 minecraft:air","clear13",log_path,args.output_dir)
            checked_command(p,"setblock 0 100 0 minecraft:piston[facing=east]","piston13",log_path,args.output_dir)
            checked_command(p,"fill 1 100 0 13 100 0 minecraft:stone","payload13",log_path,args.output_dir)
            checked_command(p,"setblock -1 100 0 minecraft:redstone_block","stim13",log_path,args.output_dir)
            time.sleep(1.0)
            a13,s13=wait_for_state_marker(
                p,log_path,args.output_dir,"SUPRACRAFT_PUSH13_BLOCKED_PASS",
                "execute if block 0 100 0 minecraft:piston[facing=east,extended=false] if block 1 100 0 minecraft:stone if block 13 100 0 minecraft:stone",
                "verify13",timeout_seconds=4.0)

            checked_command(p,"stop","stop",log_path,args.output_dir)
            rc=p.wait(timeout=60)

        text=log_path.read_text("utf-8",errors="replace")
        diags=[x for x in text.splitlines() if any(m in x for m in ("Incorrect argument","Unknown or incomplete command","[Server thread/ERROR]","Exception","Crash"))]
        markers=["SUPRACRAFT_PUSH12_PASS","SUPRACRAFT_PUSH13_BLOCKED_PASS"]
        if rc!=0 or diags or not all(m in text for m in markers):
            raise SystemExit(f"push limit canary failed rc={rc} diagnostics={len(diags)} markers={[m in text for m in markers]}")
        out={
            "schema":"supracraft-mechanical-push-limit/1",
            "edition":"java","minecraft_version":"26.3","domain":"mechanical",
            "canary_pass":True,
            "push_12":{"pass":True,"attempts":a12,"seconds":round(s12,6)},
            "push_13_blocked":{"pass":True,"attempts":a13,"seconds":round(s13,6)},
            "ready_seconds":round(ready,6),
            "boundary":"Redstone power is fixture stimulus only; this receipt qualifies no electrical-to-mechanical interaction."
        }
        (args.output_dir/"push-limit.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
        print(json.dumps(out,indent=2,sort_keys=True))
if __name__=="__main__": main()
