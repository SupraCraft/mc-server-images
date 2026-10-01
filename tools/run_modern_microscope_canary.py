#!/usr/bin/env python3
"""Run an exact Minecraft 26.3 server-only causal-microscope canary."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from generate_vanilla_worldgen_bootstrap import command, download_server, wait_ready

CANARY_COMMAND="setblock 4 100 0 minecraft:redstone_block"


def digest_bytes(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def bounded_diagnostics(server_log: str) -> list[str]:
    markers=(
        "ERROR","Exception","Caused by:","\tat ","SupraCraft causal microscope",
        "Stopping server","Crash","FAILED","Failed","failed",
    )
    rows=[
        line[:800]
        for line in server_log.splitlines()
        if any(marker in line for marker in markers)
    ]
    return rows[-120:]


def fail_early(stage: str, process: subprocess.Popen[str],
               log_path: Path, output_dir: Path, exc: Exception | None=None) -> None:
    try:
        rc=process.poll()
        if rc is None:
            rc=process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        rc=process.poll()
    server_log=log_path.read_text("utf-8",errors="replace") if log_path.exists() else ""
    receipt={
        "schema":"supracraft-modern-microscope-early-exit/1",
        "stage":stage,
        "exit_code":rc,
        "exception_type":type(exc).__name__ if exc is not None else None,
        "server_log_sha256":hashlib.sha256(
            server_log.encode("utf-8",errors="replace")
        ).hexdigest(),
        "diagnostic_lines":bounded_diagnostics(server_log),
        "boundary":"diagnostic receipt contains bounded error/stack evidence only; raw console commands and authored payloads are not retained",
    }
    (output_dir/"diagnostic.json").write_text(
        json.dumps(receipt,indent=2,sort_keys=True)+"\n"
    )
    print("CANARY_EARLY_EXIT_DIAGNOSTIC")
    print(json.dumps(receipt,indent=2,sort_keys=True))
    raise SystemExit(
        f"modern microscope server exited during {stage}; rc={rc}"
    )


def checked_command(process: subprocess.Popen[str], line: str, stage: str,
                    log_path: Path, output_dir: Path) -> None:
    if process.poll() is not None:
        fail_early(stage,process,log_path,output_dir)
    try:
        command(process,line)
    except (BrokenPipeError,OSError) as exc:
        fail_early(stage,process,log_path,output_dir,exc)


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",type=Path,required=True)
    ap.add_argument("--server-jar",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--java-agent",type=Path)
    args=ap.parse_args()

    evidence=json.loads(args.evidence.read_text())
    if evidence["minecraft_version"]!="26.3":
        raise SystemExit("exact 26.3 evidence required")
    if int(evidence["artifact_version_json"]["java_version"])!=25:
        raise SystemExit("exact 26.3 Java 25 runtime required")

    args.output_dir.mkdir(parents=True,exist_ok=True)
    args.server_jar.parent.mkdir(parents=True,exist_ok=True)
    if not args.server_jar.exists():
        download_server(evidence,args.server_jar)

    with tempfile.TemporaryDirectory(prefix="modern-microscope-canary-") as td:
        root=Path(td)
        server=root/"server.jar"
        shutil.copy2(args.server_jar,server)
        (root/"eula.txt").write_text("eula=true\n")
        props={
            "online-mode":"false",
            "server-port":"25578",
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
            "motd":"SupraCraft causal microscope 26.3 canary",
        }
        (root/"server.properties").write_text(
            "\n".join(f"{k}={v}" for k,v in props.items())+"\n"
        )
        log_path=root/"server.log"
        trace_path=args.output_dir/"trace.jsonl"
        gate_path=root/"capture.gate"
        cmd=["java","-Xms512M","-Xmx3G"]
        if args.java_agent:
            cmd.append(
                f"-javaagent:{args.java_agent.resolve()}="
                f"adapter=modern-26.3-java25,out={trace_path.resolve()},"
                f"gate={gate_path.resolve()}"
            )
        cmd.extend(["-jar",str(server),"nogui"])

        started=time.monotonic()
        with log_path.open("w",encoding="utf-8") as log:
            p=subprocess.Popen(
                cmd,cwd=root,stdin=subprocess.PIPE,stdout=log,
                stderr=subprocess.STDOUT,text=True,
            )
            ready_seconds=wait_ready(p,log_path,180)

            checked_command(
                p,"forceload add -16 -16 16 16","forceload",
                log_path,args.output_dir,
            )
            time.sleep(1)
            checked_command(
                p,"fill -2 99 -2 6 102 2 minecraft:air","clear_workspace",
                log_path,args.output_dir,
            )
            checked_command(
                p,"fill -2 99 -2 6 99 2 minecraft:stone","build_floor",
                log_path,args.output_dir,
            )
            checked_command(
                p,
                'setblock 0 100 0 minecraft:command_block[facing=east]'
                '{Command:"setblock 4 100 0 minecraft:redstone_block"}',
                "place_command_block",log_path,args.output_dir,
            )
            time.sleep(0.15)
            if args.java_agent:
                gate_path.write_text("capture\n")
                time.sleep(0.15)
            else:
                time.sleep(0.15)
            checked_command(
                p,"setblock 0 99 0 minecraft:redstone_block","activate_canary",
                log_path,args.output_dir,
            )
            time.sleep(2)
            checked_command(
                p,
                "execute if block 4 100 0 minecraft:redstone_block "
                "run say SUPRACRAFT_MICROSCOPE_CANARY_PASS",
                "verify_target",log_path,args.output_dir,
            )
            checked_command(
                p,"save-all flush","save_flush",log_path,args.output_dir
            )
            time.sleep(1)
            checked_command(p,"stop","stop",log_path,args.output_dir)
            rc=p.wait(timeout=60)
        elapsed=time.monotonic()-started

        server_log=log_path.read_text("utf-8",errors="replace")
        diagnostics=[
            line for line in server_log.splitlines()
            if any(marker in line for marker in (
                "Incorrect argument","Unknown or incomplete command",
                "That position is not loaded","[Server thread/ERROR]",
                "SupraCraft causal microscope fail-closed binding",
            ))
        ]
        canary_pass="SUPRACRAFT_MICROSCOPE_CANARY_PASS" in server_log
        if rc!=0 or diagnostics or not canary_pass:
            print("CANARY_DIAGNOSTICS_BEGIN")
            for line in diagnostics[-80:]:
                print(line)
            print("CANARY_DIAGNOSTICS_END")
            raise SystemExit(
                f"modern microscope canary failed rc={rc} "
                f"diagnostics={len(diagnostics)} pass={canary_pass}"
            )

        result={
            "schema":"supracraft-modern-microscope-canary/1",
            "minecraft_version":"26.3",
            "java_major":25,
            "instrumented":bool(args.java_agent),
            "canary_pass":True,
            "target_position":[4,100,0],
            "command_block_position":[0,100,0],
            "command_sha256":digest_bytes(CANARY_COMMAND),
            "ready_seconds":round(ready_seconds,6),
            "elapsed_seconds":round(elapsed,6),
            "trace_present":trace_path.is_file(),
            "boundary":"world-target equality is observer-effect evidence; trace ordering remains separate causal evidence",
        }
        (args.output_dir/"result.json").write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n"
        )
        print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
