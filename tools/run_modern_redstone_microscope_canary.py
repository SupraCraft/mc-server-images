#!/usr/bin/env python3
"""Run a bounded modern redstone causal-microscope stock/instrumented fixture."""

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

CANARY_COMMAND="setblock 6 100 0 minecraft:redstone_block"
SOURCE_POSITION=[0,100,0]
COMMAND_BLOCK_POSITION=[4,100,0]
TARGET_POSITION=[6,100,0]
POSITIVE_WIRES=[[1,100,0],[2,100,0],[3,100,0]]
GAP_WIRES=[[1,100,0],[3,100,0]]


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
        "schema":"supracraft-modern-redstone-microscope-early-exit/1",
        "stage":stage,
        "exit_code":rc,
        "exception_type":type(exc).__name__ if exc is not None else None,
        "server_log_sha256":hashlib.sha256(
            server_log.encode("utf-8",errors="replace")
        ).hexdigest(),
        "diagnostic_lines":bounded_diagnostics(server_log),
        "boundary":"bounded diagnostics exclude authored command payloads from the receipt",
    }
    (output_dir/"diagnostic.json").write_text(
        json.dumps(receipt,indent=2,sort_keys=True)+"\n"
    )
    print(json.dumps(receipt,indent=2,sort_keys=True))
    raise SystemExit(f"modern redstone microscope exited during {stage}; rc={rc}")


def checked_command(process: subprocess.Popen[str], line: str, stage: str,
                    log_path: Path, output_dir: Path) -> None:
    if process.poll() is not None:
        fail_early(stage,process,log_path,output_dir)
    try:
        command(process,line)
    except (BrokenPipeError,OSError) as exc:
        fail_early(stage,process,log_path,output_dir,exc)


def wait_for_marker(
    process: subprocess.Popen[str],
    log_path: Path,
    output_dir: Path,
    marker: str,
    probe_command: str,
    stage: str,
    timeout_seconds: float=8.0,
    poll_seconds: float=0.20,
) -> tuple[int,float]:
    started=time.monotonic()
    deadline=started+timeout_seconds
    attempts=0
    while time.monotonic()<deadline:
        if process.poll() is not None:
            fail_early(stage,process,log_path,output_dir)
        checked_command(
            process,f"{probe_command} run say {marker}",
            stage,log_path,output_dir,
        )
        attempts+=1
        window=min(deadline,time.monotonic()+poll_seconds)
        while time.monotonic()<window:
            if process.poll() is not None:
                fail_early(stage,process,log_path,output_dir)
            if log_path.exists() and marker in log_path.read_text(
                "utf-8",errors="replace"
            ):
                return attempts,time.monotonic()-started
            time.sleep(0.05)
    raise SystemExit(
        f"modern redstone state condition timed out during {stage}; "
        f"attempts={attempts}"
    )


def prove_non_actuation(
    process: subprocess.Popen[str],
    log_path: Path,
    output_dir: Path,
    timeout_seconds: float=4.0,
    poll_seconds: float=0.20,
) -> tuple[int,float]:
    """Continuously check that the gap fixture never materializes the target."""
    started=time.monotonic()
    deadline=started+timeout_seconds
    attempts=0
    violation="SUPRACRAFT_REDSTONE_GAP_VIOLATION"
    while time.monotonic()<deadline:
        if process.poll() is not None:
            fail_early("gap_non_actuation",process,log_path,output_dir)
        checked_command(
            process,
            "execute if block 6 100 0 minecraft:redstone_block "
            f"run say {violation}",
            "gap_non_actuation",log_path,output_dir,
        )
        attempts+=1
        time.sleep(poll_seconds)
        if violation in log_path.read_text("utf-8",errors="replace"):
            raise SystemExit("one-block-gap hard negative actuated unexpectedly")

    attempts2,elapsed2=wait_for_marker(
        process,log_path,output_dir,
        "SUPRACRAFT_REDSTONE_GAP_PASS",
        "execute if block 6 100 0 minecraft:air",
        "gap_final_air",
        timeout_seconds=2.0,
        poll_seconds=poll_seconds,
    )
    return attempts+attempts2,(time.monotonic()-started)+elapsed2*0.0


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",type=Path,required=True)
    ap.add_argument("--server-jar",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--fixture",choices=("positive","gap"),required=True)
    ap.add_argument("--java-agent",type=Path)
    ap.add_argument("--adapter-id")
    ap.add_argument("--expected-version")
    args=ap.parse_args()

    evidence=json.loads(args.evidence.read_text())
    version=evidence["minecraft_version"]
    java_major=int(
        (evidence.get("artifact_version_json") or {}).get(
            "java_version",evidence.get("java_major",0)
        )
    )
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
            raise SystemExit(
                "server jar must already exist when using a discovery receipt"
            )
        download_server(evidence,args.server_jar)

    wire_positions=POSITIVE_WIRES if args.fixture=="positive" else GAP_WIRES
    expected_actuation=args.fixture=="positive"

    with tempfile.TemporaryDirectory(prefix="modern-redstone-microscope-") as td:
        root=Path(td)
        server=root/"server.jar"
        shutil.copy2(args.server_jar,server)
        (root/"eula.txt").write_text("eula=true\n")
        props={
            "online-mode":"false",
            "server-port":"25579",
            "view-distance":"3",
            "simulation-distance":"3",
            "spawn-protection":"0",
            "max-players":"1",
            "enable-command-block":"true",
            "allow-flight":"true",
            "gamemode":"creative",
            "difficulty":"peaceful",
            "level-name":"world",
            "level-seed":"263264",
            "motd":f"SupraCraft redstone microscope {version} {args.fixture}",
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
                f"gate={gate_path.resolve()},sensors=core+redstone"
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
                p,"fill -2 99 -2 8 102 2 minecraft:air","clear_workspace",
                log_path,args.output_dir,
            )
            checked_command(
                p,"fill -2 99 -2 8 99 2 minecraft:stone","build_floor",
                log_path,args.output_dir,
            )
            checked_command(
                p,
                'setblock 4 100 0 minecraft:command_block[facing=east]'
                '{Command:"setblock 6 100 0 minecraft:redstone_block"}',
                "place_command_block",log_path,args.output_dir,
            )
            for x,_,_ in wire_positions:
                checked_command(
                    p,f"setblock {x} 100 0 minecraft:redstone_wire",
                    f"place_wire_{x}",log_path,args.output_dir,
                )
            if args.fixture=="gap":
                checked_command(
                    p,"setblock 2 100 0 minecraft:air","enforce_gap",
                    log_path,args.output_dir,
                )
            time.sleep(0.20)
            if args.java_agent:
                gate_path.write_text("capture\n")
                time.sleep(0.15)

            checked_command(
                p,"setblock 0 100 0 minecraft:redstone_block",
                "activate_source",log_path,args.output_dir,
            )
            if expected_actuation:
                verification_attempts,settle_seconds=wait_for_marker(
                    p,log_path,args.output_dir,
                    "SUPRACRAFT_REDSTONE_POSITIVE_PASS",
                    "execute if block 6 100 0 minecraft:redstone_block",
                    "positive_target",
                )
                actual_actuation=True
            else:
                verification_attempts,settle_seconds=prove_non_actuation(
                    p,log_path,args.output_dir
                )
                actual_actuation=False

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
        if rc!=0 or diagnostics:
            print("REDSTONE_CANARY_DIAGNOSTICS_BEGIN")
            for line in diagnostics[-80:]:
                print(line)
            print("REDSTONE_CANARY_DIAGNOSTICS_END")
            raise SystemExit(
                f"modern redstone microscope failed rc={rc} "
                f"diagnostics={len(diagnostics)}"
            )

        result={
            "schema":"supracraft-modern-redstone-microscope-canary/1",
            "minecraft_version":version,
            "java_major":java_major,
            "fixture":args.fixture,
            "instrumented":bool(args.java_agent),
            "expected_actuation":expected_actuation,
            "actual_actuation":actual_actuation,
            "source_position":SOURCE_POSITION,
            "wire_positions":wire_positions,
            "gap_position":[2,100,0] if args.fixture=="gap" else None,
            "command_block_position":COMMAND_BLOCK_POSITION,
            "target_position":TARGET_POSITION,
            "command_sha256":digest_bytes(CANARY_COMMAND),
            "ready_seconds":round(ready_seconds,6),
            "elapsed_seconds":round(elapsed,6),
            "verification_attempts":verification_attempts,
            "settle_seconds":round(settle_seconds,6),
            "trace_present":trace_path.is_file(),
            "boundary":"fixture outcome plus bounded wire-event ordering is causal evidence for this exact redstone shape only",
        }
        (args.output_dir/"result.json").write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n"
        )
        print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
