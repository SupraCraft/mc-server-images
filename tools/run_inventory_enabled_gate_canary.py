#!/usr/bin/env python3
"""Exact Java 26.3 hopper enabled-state falsification.

The enabled block state is set directly by fixture control. The semantic claim
is inventory-local: enabled permits transfer; disabled blocks transfer.
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

    with tempfile.TemporaryDirectory(prefix="inventory-enabled-") as td:
        root=Path(td)
        server=root/"server.jar"; shutil.copy2(args.server_jar,server)
        (root/"eula.txt").write_text("eula=true\n")
        (root/"server.properties").write_text("\n".join([
            "online-mode=false","server-port=25582","view-distance=3",
            "simulation-distance=3","spawn-protection=0","max-players=1",
            "allow-flight=true","gamemode=creative","difficulty=peaceful",
            "level-name=world","level-seed=263267",
            "motd=SupraCraft inventory enabled gate",
        ])+"\n")
        log_path=root/"server.log"
        with log_path.open("w",encoding="utf-8") as log:
            p=subprocess.Popen(["java","-Xms512M","-Xmx2G","-jar",str(server),"nogui"],
                cwd=root,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True)
            ready=wait_ready(p,log_path,180)
            checked_command(p,"forceload add -8 -8 8 8","forceload",log_path,args.output_dir)
            time.sleep(0.5)

            checked_command(p,"fill -2 98 -2 2 102 2 minecraft:air","clear_enabled",log_path,args.output_dir)
            checked_command(p,"setblock 0 99 0 minecraft:chest","chest_enabled",log_path,args.output_dir)
            checked_command(p,"setblock 0 100 0 minecraft:hopper[facing=down,enabled=true]","hopper_enabled",log_path,args.output_dir)
            checked_command(p,"item replace block 0 100 0 container.0 with minecraft:stone 1","seed_enabled",log_path,args.output_dir)
            ae,se=wait_for_state_marker(
                p,log_path,args.output_dir,"SUPRACRAFT_HOPPER_ENABLED_PASS",
                "execute if items block 0 99 0 container.0 minecraft:stone",
                "verify_enabled",timeout_seconds=10.0)

            checked_command(p,"fill -2 99 -2 2 102 2 minecraft:air","clear_disabled",log_path,args.output_dir)
            checked_command(p,"setblock 0 99 0 minecraft:chest","chest_disabled",log_path,args.output_dir)
            checked_command(p,"setblock 0 100 0 minecraft:hopper[facing=down,enabled=false]","hopper_disabled",log_path,args.output_dir)
            checked_command(p,"item replace block 0 100 0 container.0 with minecraft:dirt 1","seed_disabled",log_path,args.output_dir)
            time.sleep(1.5)
            ad,sd=wait_for_state_marker(
                p,log_path,args.output_dir,"SUPRACRAFT_HOPPER_DISABLED_PASS",
                "execute if items block 0 100 0 container.0 minecraft:dirt unless items block 0 99 0 container.* minecraft:dirt",
                "verify_disabled",timeout_seconds=4.0)

            checked_command(p,"stop","stop",log_path,args.output_dir)
            rc=p.wait(timeout=60)

        text=log_path.read_text("utf-8",errors="replace")
        diags=[x for x in text.splitlines() if any(m in x for m in ("Incorrect argument","Unknown or incomplete command","[Server thread/ERROR]","Exception","Crash"))]
        markers=["SUPRACRAFT_HOPPER_ENABLED_PASS","SUPRACRAFT_HOPPER_DISABLED_PASS"]
        if rc!=0 or diags or not all(m in text for m in markers):
            raise SystemExit(f"hopper enabled canary failed rc={rc} diagnostics={len(diags)} markers={[m in text for m in markers]}")
        out={
            "schema":"supracraft-inventory-enabled-gate/1",
            "edition":"java","minecraft_version":"26.3","domain":"inventory",
            "canary_pass":True,
            "enabled_transfer":{"pass":True,"attempts":ae,"seconds":round(se,6)},
            "disabled_retention":{"pass":True,"attempts":ad,"seconds":round(sd,6)},
            "ready_seconds":round(ready,6),
            "boundary":"The hopper enabled state is set directly by fixture control; this receipt qualifies no electrical-to-inventory interaction."
        }
        (args.output_dir/"enabled-gate.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
        print(json.dumps(out,indent=2,sort_keys=True))
if __name__=="__main__": main()
