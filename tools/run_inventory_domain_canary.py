#!/usr/bin/env python3
"""Bounded Java 26.3 hopper runtime canary.

Console commands are fixture control only. This qualifies no programmable
semantics and no comparator/electrical interaction.
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

    evidence=json.loads(args.evidence.read_text())
    if evidence["minecraft_version"]!="26.3":
        raise SystemExit("exact Java 26.3 required")
    if int(evidence["artifact_version_json"]["java_version"])!=25:
        raise SystemExit("Java 25 required")

    args.output_dir.mkdir(parents=True,exist_ok=True)
    args.server_jar.parent.mkdir(parents=True,exist_ok=True)
    if not args.server_jar.exists():
        download_server(evidence,args.server_jar)

    with tempfile.TemporaryDirectory(prefix="inventory-domain-") as td:
        root=Path(td)
        server=root/"server.jar"; shutil.copy2(args.server_jar,server)
        (root/"eula.txt").write_text("eula=true\n")
        (root/"server.properties").write_text("\n".join([
            "online-mode=false","server-port=25580","view-distance=3",
            "simulation-distance=3","spawn-protection=0","max-players=1",
            "allow-flight=true","gamemode=creative","difficulty=peaceful",
            "level-name=world","level-seed=263265",
            "motd=SupraCraft inventory domain canary",
        ])+"\n")
        log_path=root/"server.log"
        with log_path.open("w",encoding="utf-8") as log:
            p=subprocess.Popen(
                ["java","-Xms512M","-Xmx2G","-jar",str(server),"nogui"],
                cwd=root,stdin=subprocess.PIPE,stdout=log,
                stderr=subprocess.STDOUT,text=True,
            )
            ready_seconds=wait_ready(p,log_path,180)
            checked_command(p,"forceload add -8 -8 8 8","forceload",log_path,args.output_dir)
            time.sleep(0.5)

            # Positive: one hopper transfers one stone into an empty chest below.
            checked_command(p,"fill -2 98 -2 2 102 2 minecraft:air","clear_positive",log_path,args.output_dir)
            checked_command(p,"fill -2 98 -2 2 98 2 minecraft:stone","floor_positive",log_path,args.output_dir)
            checked_command(p,"setblock 0 99 0 minecraft:chest","destination_positive",log_path,args.output_dir)
            checked_command(p,"setblock 0 100 0 minecraft:hopper[facing=down,enabled=true]","hopper_positive",log_path,args.output_dir)
            checked_command(p,"item replace block 0 100 0 container.0 with minecraft:stone 1","seed_positive",log_path,args.output_dir)
            pos_attempts,pos_seconds=wait_for_state_marker(
                p,log_path,args.output_dir,
                "SUPRACRAFT_INVENTORY_TRANSFER_PASS",
                "execute if items block 0 99 0 container.0 minecraft:stone",
                "verify_transfer",timeout_seconds=10.0,
            )

            # Hard negative: a full destination hopper must leave source item in place.
            checked_command(p,"fill -2 99 -2 2 102 2 minecraft:air","clear_negative",log_path,args.output_dir)
            checked_command(p,"setblock 0 99 0 minecraft:hopper[facing=down,enabled=true]","destination_negative",log_path,args.output_dir)
            checked_command(p,"setblock 0 100 0 minecraft:hopper[facing=down,enabled=true]","source_negative",log_path,args.output_dir)
            for slot in range(5):
                checked_command(
                    p,f"item replace block 0 99 0 container.{slot} with minecraft:stone 64",
                    f"fill_destination_{slot}",log_path,args.output_dir,
                )
            checked_command(p,"item replace block 0 100 0 container.0 with minecraft:dirt 1","seed_negative",log_path,args.output_dir)
            time.sleep(1.5)
            neg_attempts,neg_seconds=wait_for_state_marker(
                p,log_path,args.output_dir,
                "SUPRACRAFT_INVENTORY_FULL_DESTINATION_PASS",
                "execute if items block 0 100 0 container.0 minecraft:dirt",
                "verify_full_destination",timeout_seconds=4.0,
            )

            checked_command(p,"stop","stop",log_path,args.output_dir)
            rc=p.wait(timeout=60)

        text=log_path.read_text("utf-8",errors="replace")
        markers=[
            "SUPRACRAFT_INVENTORY_TRANSFER_PASS",
            "SUPRACRAFT_INVENTORY_FULL_DESTINATION_PASS",
        ]
        diagnostics=[line for line in text.splitlines() if any(x in line for x in (
            "Incorrect argument","Unknown or incomplete command",
            "[Server thread/ERROR]","Exception","Crash",
        ))]
        if rc!=0 or diagnostics or not all(m in text for m in markers):
            for line in diagnostics[-80:]: print(line)
            raise SystemExit(
                f"inventory runtime canary failed rc={rc} diagnostics={len(diagnostics)} "
                f"markers={[m in text for m in markers]}"
            )

        result={
            "schema":"supracraft-inventory-domain-runtime/1",
            "edition":"java","minecraft_version":"26.3","domain":"inventory",
            "canary_pass":True,
            "positive":{
                "fixture":"one hopper -> empty chest",
                "single_item_transfer_pass":True,
                "attempts":pos_attempts,
                "seconds":round(pos_seconds,6),
            },
            "hard_negative":{
                "fixture":"source hopper -> full destination hopper",
                "source_item_retained_pass":True,
                "attempts":neg_attempts,
                "seconds":round(neg_seconds,6),
            },
            "ready_seconds":round(ready_seconds,6),
            "boundary":"console commands are external fixture control only; this receipt qualifies no programmable, comparator, or electrical interaction semantics",
        }
        (args.output_dir/"inventory-runtime.json").write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n")
        print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__": main()
