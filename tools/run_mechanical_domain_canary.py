#!/usr/bin/env python3
"""Bounded Java 26.3 piston runtime canary.

The redstone block is fixture stimulus only. This canary qualifies no
Redstone->mechanical transducer semantics; it observes only mechanical geometry
after the piston boundary is crossed.
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
    java_major=int(evidence["artifact_version_json"]["java_version"])
    if java_major!=25:
        raise SystemExit(f"Java 25 required; observed {java_major}")

    args.output_dir.mkdir(parents=True,exist_ok=True)
    args.server_jar.parent.mkdir(parents=True,exist_ok=True)
    if not args.server_jar.exists():
        download_server(evidence,args.server_jar)

    with tempfile.TemporaryDirectory(prefix="mechanical-domain-") as td:
        root=Path(td)
        server=root/"server.jar"; shutil.copy2(args.server_jar,server)
        (root/"eula.txt").write_text("eula=true\n")
        (root/"server.properties").write_text("\n".join([
            "online-mode=false","server-port=25579","view-distance=3",
            "simulation-distance=3","spawn-protection=0","max-players=1",
            "allow-flight=true","gamemode=creative","difficulty=peaceful",
            "level-name=world","level-seed=263264",
            "motd=SupraCraft mechanical domain canary",
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

            # Positive: one normal piston pushes one stone, then retracts.
            checked_command(p,"fill -3 99 -2 4 102 2 minecraft:air","clear_positive",log_path,args.output_dir)
            checked_command(p,"fill -3 99 -2 4 99 2 minecraft:stone","floor_positive",log_path,args.output_dir)
            checked_command(p,"setblock 0 100 0 minecraft:piston[facing=east]","piston_positive",log_path,args.output_dir)
            checked_command(p,"setblock 1 100 0 minecraft:stone","payload_positive",log_path,args.output_dir)
            checked_command(p,"setblock -1 100 0 minecraft:redstone_block","fixture_stimulus_on",log_path,args.output_dir)
            extend_attempts,extend_seconds=wait_for_state_marker(
                p,log_path,args.output_dir,
                "SUPRACRAFT_MECHANICAL_EXTEND_PASS",
                "execute if block 0 100 0 minecraft:piston[facing=east,extended=true] if block 2 100 0 minecraft:stone",
                "verify_extension",timeout_seconds=8.0,
            )
            checked_command(p,"setblock -1 100 0 minecraft:air","fixture_stimulus_off",log_path,args.output_dir)
            retract_attempts,retract_seconds=wait_for_state_marker(
                p,log_path,args.output_dir,
                "SUPRACRAFT_MECHANICAL_RETRACT_PASS",
                "execute if block 0 100 0 minecraft:piston[facing=east,extended=false] if block 1 100 0 minecraft:air if block 2 100 0 minecraft:stone",
                "verify_retraction",timeout_seconds=8.0,
            )

            # Hard negative: obsidian must not be displaced by the bounded piston fixture.
            checked_command(p,"fill -3 100 -1 4 101 1 minecraft:air","clear_negative",log_path,args.output_dir)
            checked_command(p,"setblock 0 100 0 minecraft:piston[facing=east]","piston_negative",log_path,args.output_dir)
            checked_command(p,"setblock 1 100 0 minecraft:obsidian","payload_negative",log_path,args.output_dir)
            checked_command(p,"setblock -1 100 0 minecraft:redstone_block","fixture_negative_stimulus",log_path,args.output_dir)
            time.sleep(1.0)
            negative_attempts,negative_seconds=wait_for_state_marker(
                p,log_path,args.output_dir,
                "SUPRACRAFT_MECHANICAL_IMMOVABLE_PASS",
                "execute if block 0 100 0 minecraft:piston[facing=east,extended=false] if block 1 100 0 minecraft:obsidian",
                "verify_immovable",timeout_seconds=4.0,
            )

            checked_command(p,"stop","stop",log_path,args.output_dir)
            rc=p.wait(timeout=60)

        text=log_path.read_text("utf-8",errors="replace")
        markers=[
            "SUPRACRAFT_MECHANICAL_EXTEND_PASS",
            "SUPRACRAFT_MECHANICAL_RETRACT_PASS",
            "SUPRACRAFT_MECHANICAL_IMMOVABLE_PASS",
        ]
        diagnostics=[line for line in text.splitlines() if any(x in line for x in (
            "Incorrect argument","Unknown or incomplete command",
            "[Server thread/ERROR]","Exception","Crash",
        ))]
        if rc!=0 or diagnostics or not all(m in text for m in markers):
            for line in diagnostics[-80:]: print(line)
            raise SystemExit(
                f"mechanical runtime canary failed rc={rc} diagnostics={len(diagnostics)} "
                f"markers={[m in text for m in markers]}"
            )

        result={
            "schema":"supracraft-mechanical-domain-runtime/1",
            "edition":"java","minecraft_version":"26.3","domain":"mechanical",
            "canary_pass":True,
            "positive":{
                "fixture":"normal piston + one stone",
                "extension_geometry_pass":True,
                "retraction_geometry_pass":True,
                "extend_attempts":extend_attempts,
                "extend_seconds":round(extend_seconds,6),
                "retract_attempts":retract_attempts,
                "retract_seconds":round(retract_seconds,6),
            },
            "hard_negative":{
                "fixture":"normal piston + obsidian",
                "immovable_geometry_pass":True,
                "attempts":negative_attempts,
                "seconds":round(negative_seconds,6),
            },
            "ready_seconds":round(ready_seconds,6),
            "boundary":"redstone block is external fixture stimulus only; this receipt starts at piston mechanical behavior and does not qualify an electrical-to-mechanical transducer",
        }
        (args.output_dir/"mechanical-runtime.json").write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n")
        print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__": main()
