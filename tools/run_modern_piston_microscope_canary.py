#!/usr/bin/env python3
"""Run a bounded normal-piston stock/instrumented causal fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from generate_vanilla_worldgen_bootstrap import download_server, wait_ready, zip_world
from run_modern_redstone_microscope_canary import (
    bounded_diagnostics,
    checked_command,
    fail_early,
    wait_for_log_marker,
    wait_for_marker,
)

PISTON_POSITION=[0,100,0]
FRONT_POSITION=[1,100,0]
DESTINATION_POSITION=[2,100,0]
POWER_POSITION=[0,100,-1]


def evidence_java_major(evidence: dict) -> int:
    return int(
        (evidence.get("artifact_version_json") or {}).get(
            "java_version",evidence.get("java_major",0)
        )
    )


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",type=Path,required=True)
    ap.add_argument("--server-jar",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--java-agent",type=Path)
    ap.add_argument("--adapter-id")
    ap.add_argument("--expected-version")
    args=ap.parse_args()

    evidence=json.loads(args.evidence.read_text())
    version=evidence["minecraft_version"]
    java_major=evidence_java_major(evidence)
    if args.expected_version and version!=args.expected_version:
        raise SystemExit(
            f"exact version mismatch expected={args.expected_version} observed={version}"
        )
    if java_major!=25:
        raise SystemExit(f"exact modern Java 25 runtime required; observed={java_major}")

    args.output_dir.mkdir(parents=True,exist_ok=True)
    args.server_jar.parent.mkdir(parents=True,exist_ok=True)
    if not args.server_jar.exists():
        if "server_artifact" not in evidence:
            raise SystemExit("server jar absent and evidence has no server artifact")
        download_server(evidence,args.server_jar)

    with tempfile.TemporaryDirectory(prefix="modern-piston-microscope-") as td:
        root=Path(td)
        server=root/"server.jar"
        shutil.copy2(args.server_jar,server)
        (root/"eula.txt").write_text("eula=true\n")
        props={
            "online-mode":"false",
            "server-port":"25583",
            "view-distance":"3",
            "simulation-distance":"3",
            "spawn-protection":"0",
            "max-players":"1",
            "allow-flight":"true",
            "gamemode":"creative",
            "difficulty":"peaceful",
            "level-name":"world",
            "level-seed":"263267",
            "motd":f"SupraCraft piston microscope {version}",
        }
        (root/"server.properties").write_text(
            "\n".join(f"{k}={v}" for k,v in props.items())+"\n"
        )
        log_path=root/"server.log"
        trace_path=args.output_dir/"trace.jsonl"
        gate_path=root/"capture.gate"
        cmd=["java","-Xms512M","-Xmx3G"]
        if args.java_agent:
            adapter=args.adapter_id or f"modern-{version}-java25"
            cmd.append(
                f"-javaagent:{args.java_agent.resolve()}="
                f"adapter={adapter},out={trace_path.resolve()},"
                f"gate={gate_path.resolve()},sensors=core+piston"
            )
        cmd.extend(["-jar",str(server),"nogui"])

        started=time.monotonic()
        with log_path.open("w",encoding="utf-8") as log:
            p=subprocess.Popen(
                cmd,cwd=root,stdin=subprocess.PIPE,stdout=log,
                stderr=subprocess.STDOUT,text=True,
            )
            ready=wait_ready(p,log_path,180)
            checked_command(
                p,"forceload add -16 -16 16 16","forceload",
                log_path,args.output_dir,
            )
            time.sleep(1)
            checked_command(
                p,"fill -3 99 -3 5 103 3 minecraft:air","clear",
                log_path,args.output_dir,
            )
            checked_command(
                p,"fill -3 99 -3 5 99 3 minecraft:stone","floor",
                log_path,args.output_dir,
            )
            checked_command(
                p,
                "setblock 0 100 0 minecraft:piston[facing=east,extended=false]",
                "place_piston",log_path,args.output_dir,
            )
            checked_command(
                p,"setblock 1 100 0 minecraft:stone",
                "place_payload",log_path,args.output_dir,
            )
            checked_command(
                p,"setblock 2 100 0 minecraft:air",
                "clear_destination",log_path,args.output_dir,
            )
            checked_command(
                p,"setblock 0 100 -1 minecraft:air",
                "clear_power",log_path,args.output_dir,
            )
            marker="SUPRACRAFT_PISTON_SETUP_READY"
            checked_command(p,f"say {marker}","setup_barrier",log_path,args.output_dir)
            barrier=wait_for_log_marker(
                p,log_path,args.output_dir,marker,"setup_barrier"
            )
            if args.java_agent:
                gate_path.write_text("capture\n")
                time.sleep(0.15)

            checked_command(
                p,"setblock 0 100 -1 minecraft:redstone_block",
                "power_on",log_path,args.output_dir,
            )
            ext_attempts,ext_seconds=wait_for_marker(
                p,log_path,args.output_dir,
                "SUPRACRAFT_PISTON_EXTEND_PASS",
                "execute if block 0 100 0 minecraft:piston[facing=east,extended=true] "
                "if block 1 100 0 minecraft:piston_head[facing=east,type=normal] "
                "if block 2 100 0 minecraft:stone",
                "verify_extension",
                timeout_seconds=8.0,
            )

            checked_command(
                p,"setblock 0 100 -1 minecraft:air",
                "power_off",log_path,args.output_dir,
            )
            ret_attempts,ret_seconds=wait_for_marker(
                p,log_path,args.output_dir,
                "SUPRACRAFT_PISTON_RETRACT_PASS",
                "execute if block 0 100 0 minecraft:piston[facing=east,extended=false] "
                "if block 1 100 0 minecraft:air "
                "if block 2 100 0 minecraft:stone",
                "verify_retraction",
                timeout_seconds=8.0,
            )

            checked_command(p,"save-all flush","save",log_path,args.output_dir)
            time.sleep(0.5)
            checked_command(p,"stop","stop",log_path,args.output_dir)
            rc=p.wait(timeout=60)

        elapsed=time.monotonic()-started
        zip_world(root/"world",args.output_dir/"world.zip")
        server_log=log_path.read_text("utf-8",errors="replace")
        diagnostics=[
            line for line in server_log.splitlines()
            if any(marker in line for marker in (
                "Incorrect argument","Unknown or incomplete command",
                "That position is not loaded","[Server thread/ERROR]",
                "SupraCraft causal microscope fail-closed binding",
            ))
        ]
        extension_pass="SUPRACRAFT_PISTON_EXTEND_PASS" in server_log
        retraction_pass="SUPRACRAFT_PISTON_RETRACT_PASS" in server_log
        if rc!=0 or diagnostics or not extension_pass or not retraction_pass:
            receipt={
                "schema":"supracraft-modern-piston-microscope-failure/1",
                "exit_code":rc,
                "extension_pass":extension_pass,
                "retraction_pass":retraction_pass,
                "diagnostic_lines":bounded_diagnostics(server_log),
            }
            (args.output_dir/"diagnostic.json").write_text(
                json.dumps(receipt,indent=2,sort_keys=True)+"\n"
            )
            print(json.dumps(receipt,indent=2,sort_keys=True))
            raise SystemExit("bounded normal-piston fixture failed")

        result={
            "schema":"supracraft-modern-piston-microscope-canary/1",
            "minecraft_version":version,
            "java_major":java_major,
            "instrumented":bool(args.java_agent),
            "piston_kind":"normal",
            "piston_position":PISTON_POSITION,
            "front_position":FRONT_POSITION,
            "destination_position":DESTINATION_POSITION,
            "power_position":POWER_POSITION,
            "extension_pass":True,
            "retraction_pass":True,
            "terminal_contract":{
                "piston_extended":False,
                "front_block":"minecraft:air",
                "destination_block":"minecraft:stone",
                "payload_pulled_on_retraction":False,
            },
            "extension_attempts":ext_attempts,
            "extension_seconds":round(ext_seconds,6),
            "retraction_attempts":ret_attempts,
            "retraction_seconds":round(ret_seconds,6),
            "setup_barrier_seconds":round(barrier,6),
            "ready_seconds":round(ready,6),
            "elapsed_seconds":round(elapsed,6),
            "trace_present":trace_path.is_file(),
            "world_sha256":hashlib.sha256(
                (args.output_dir/"world.zip").read_bytes()
            ).hexdigest(),
            "boundary":"one normal piston pushing one ordinary block; no sticky, slime/honey, push-limit, quasi-connectivity, or multi-block semantic claim",
        }
        (args.output_dir/"result.json").write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n"
        )
        print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
