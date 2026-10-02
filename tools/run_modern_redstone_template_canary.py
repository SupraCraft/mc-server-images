#!/usr/bin/env python3
"""Run exact modern redstone mechanism-template fixtures."""

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
    digest_bytes,
    fail_early,
    wait_for_log_marker,
    wait_for_marker,
)

REPEATER_COMMAND="setblock 6 100 0 minecraft:redstone_block"
REPEATER_SOURCE_COMMAND="setblock 0 100 0 minecraft:redstone_block"
NOT_INPUT_HIGH_COMMAND="setblock -1 100 0 minecraft:redstone_block"
NOT_INPUT_LOW_COMMAND="setblock -1 100 0 minecraft:air"


def evidence_java_major(evidence: dict) -> int:
    return int(
        (evidence.get("artifact_version_json") or {}).get(
            "java_version",evidence.get("java_major",0)
        )
    )


def launch_command(args,server,trace_path,gate_path):
    cmd=["java","-Xms512M","-Xmx3G"]
    if args.java_agent:
        adapter=args.adapter_id or f"modern-{args.expected_version}-java25"
        cmd.append(
            f"-javaagent:{args.java_agent.resolve()}="
            f"adapter={adapter},out={trace_path.resolve()},"
            f"gate={gate_path.resolve()},sensors=core+redstone"
        )
    cmd.extend(["-jar",str(server),"nogui"])
    return cmd


def common_setup(root,version):
    (root/"eula.txt").write_text("eula=true\n")
    props={
        "online-mode":"false",
        "server-port":"25580",
        "view-distance":"3",
        "simulation-distance":"3",
        "spawn-protection":"0",
        "max-players":"1",
        "enable-command-block":"true",
        "allow-flight":"true",
        "gamemode":"creative",
        "difficulty":"peaceful",
        "level-name":"world",
        "level-seed":"263265",
        "motd":f"SupraCraft redstone template {version}",
    }
    (root/"server.properties").write_text(
        "\n".join(f"{k}={v}" for k,v in props.items())+"\n"
    )


def setup_barrier(p,log_path,output_dir,marker):
    checked_command(p,f"say {marker}","setup_barrier",log_path,output_dir)
    return wait_for_log_marker(
        p,log_path,output_dir,marker,"setup_barrier",timeout_seconds=5.0
    )


def run_repeater(args,evidence,server_jar,output_dir):
    if args.delay not in {1,2,3,4}:
        raise SystemExit("--delay must be 1..4 for repeater fixture")
    version=evidence["minecraft_version"]
    with tempfile.TemporaryDirectory(prefix="modern-redstone-repeater-") as td:
        root=Path(td); server=root/"server.jar"
        shutil.copy2(server_jar,server)
        common_setup(root,version)
        log_path=root/"server.log"
        trace_path=output_dir/"trace.jsonl"
        gate_path=root/"capture.gate"
        started=time.monotonic()
        with log_path.open("w",encoding="utf-8") as log:
            p=subprocess.Popen(
                launch_command(args,server,trace_path,gate_path),
                cwd=root,stdin=subprocess.PIPE,stdout=log,
                stderr=subprocess.STDOUT,text=True,
            )
            ready=wait_ready(p,log_path,180)
            checked_command(p,"forceload add -16 -16 16 16","forceload",log_path,output_dir)
            time.sleep(1)
            checked_command(p,"fill -2 99 -2 8 102 2 minecraft:air","clear",log_path,output_dir)
            checked_command(p,"fill -2 99 -2 8 99 2 minecraft:stone","floor",log_path,output_dir)
            checked_command(p,"setblock 1 100 0 minecraft:redstone_wire","input_wire",log_path,output_dir)
            checked_command(
                p,
                f"setblock 2 100 0 minecraft:repeater[facing=west,delay={args.delay},locked=false,powered=false]",
                "repeater",log_path,output_dir,
            )
            checked_command(p,"setblock 3 100 0 minecraft:redstone_wire","output_wire",log_path,output_dir)
            checked_command(
                p,
                'setblock 4 100 0 minecraft:command_block[facing=east]'
                '{Command:"setblock 6 100 0 minecraft:redstone_block"}',
                "command_block",log_path,output_dir,
            )
            barrier=setup_barrier(
                p,log_path,output_dir,
                f"SUPRACRAFT_REPEATER_DELAY_{args.delay}_SETUP_READY",
            )
            if args.java_agent:
                gate_path.write_text("capture\n")
                time.sleep(0.15)
            checked_command(
                p,REPEATER_SOURCE_COMMAND,"activate_source",log_path,output_dir
            )
            attempts,wait_seconds=wait_for_marker(
                p,log_path,output_dir,
                f"SUPRACRAFT_REPEATER_DELAY_{args.delay}_PASS",
                "execute if block 6 100 0 minecraft:redstone_block",
                "verify_target",
                timeout_seconds=8.0,
            )
            checked_command(p,"save-all flush","save",log_path,output_dir)
            time.sleep(1)
            checked_command(p,"stop","stop",log_path,output_dir)
            rc=p.wait(timeout=60)
        elapsed=time.monotonic()-started
        zip_world(root/"world",output_dir/"world.zip")
        text=log_path.read_text("utf-8",errors="replace")
        diagnostics=[
            line for line in text.splitlines()
            if any(x in line for x in (
                "Incorrect argument","Unknown or incomplete command",
                "[Server thread/ERROR]",
                "SupraCraft causal microscope fail-closed binding",
            ))
        ]
        if rc!=0 or diagnostics:
            for line in diagnostics[-80:]:
                print(line)
            raise SystemExit(
                f"repeater template failed rc={rc} diagnostics={len(diagnostics)}"
            )
        result={
            "schema":"supracraft-modern-redstone-template-canary/1",
            "template":"repeater_delay_line",
            "minecraft_version":version,
            "java_major":evidence_java_major(evidence),
            "instrumented":bool(args.java_agent),
            "configured_delay":args.delay,
            "source_position":[0,100,0],
            "input_wire_position":[1,100,0],
            "repeater_position":[2,100,0],
            "output_wire_position":[3,100,0],
            "command_block_position":[4,100,0],
            "target_position":[6,100,0],
            "source_command_sha256":digest_bytes(REPEATER_SOURCE_COMMAND),
            "command_sha256":digest_bytes(REPEATER_COMMAND),
            "actual_actuation":True,
            "ready_seconds":round(ready,6),
            "setup_barrier_seconds":round(barrier,6),
            "verification_attempts":attempts,
            "target_wait_seconds":round(wait_seconds,6),
            "elapsed_seconds":round(elapsed,6),
            "trace_present":trace_path.is_file(),
            "world_sha256":hashlib.sha256(
                (output_dir/"world.zip").read_bytes()
            ).hexdigest(),
            "boundary":"configured repeater topology plus runtime tick delta is template evidence; exact delay semantics require qualified timing comparison",
        }
        (output_dir/"result.json").write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n"
        )
        print(json.dumps(result,indent=2,sort_keys=True))


def not_probe(input_wire_power,torch_lit,output_wire_power):
    lit="true" if torch_lit else "false"
    return (
        f"execute if block 0 100 0 minecraft:redstone_wire[power={input_wire_power}] "
        f"if block 1 101 0 minecraft:redstone_torch[lit={lit}] "
        f"if block 2 101 0 minecraft:redstone_wire[power={output_wire_power}]"
    )


def run_not_gate(args,evidence,server_jar,output_dir):
    version=evidence["minecraft_version"]
    with tempfile.TemporaryDirectory(prefix="modern-redstone-not-") as td:
        root=Path(td); server=root/"server.jar"
        shutil.copy2(server_jar,server)
        common_setup(root,version)
        log_path=root/"server.log"
        trace_path=output_dir/"trace.jsonl"
        gate_path=root/"capture.gate"
        started=time.monotonic()
        with log_path.open("w",encoding="utf-8") as log:
            p=subprocess.Popen(
                launch_command(args,server,trace_path,gate_path),
                cwd=root,stdin=subprocess.PIPE,stdout=log,
                stderr=subprocess.STDOUT,text=True,
            )
            ready=wait_ready(p,log_path,180)
            checked_command(p,"forceload add -16 -16 16 16","forceload",log_path,output_dir)
            time.sleep(1)
            checked_command(p,"fill -2 99 -2 5 103 2 minecraft:air","clear",log_path,output_dir)
            checked_command(p,"fill -2 99 -2 5 99 2 minecraft:stone","floor",log_path,output_dir)
            checked_command(p,"setblock 1 100 0 minecraft:stone","torch_support",log_path,output_dir)
            checked_command(p,"setblock 2 100 0 minecraft:stone","wire_support",log_path,output_dir)
            checked_command(p,NOT_INPUT_LOW_COMMAND,"input_low_setup",log_path,output_dir)
            checked_command(p,"setblock 0 100 0 minecraft:redstone_wire","input_wire",log_path,output_dir)
            checked_command(p,"setblock 1 101 0 minecraft:redstone_torch","torch",log_path,output_dir)
            checked_command(p,"setblock 2 101 0 minecraft:redstone_wire","output_wire",log_path,output_dir)
            checked_command(p,"setblock 3 101 0 minecraft:redstone_lamp","lamp",log_path,output_dir)

            baseline_attempts,baseline_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_NOT_BASELINE_PASS",
                not_probe(0,True,15),
                "not_baseline",
                timeout_seconds=8.0,
            )
            barrier=setup_barrier(
                p,log_path,output_dir,"SUPRACRAFT_NOT_SETUP_READY"
            )
            if args.java_agent:
                gate_path.write_text("capture\n")
                time.sleep(0.15)

            checked_command(
                p,NOT_INPUT_HIGH_COMMAND,"not_input_high",log_path,output_dir
            )
            high_attempts,high_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_NOT_HIGH_LOW_PASS",
                not_probe(15,False,0),
                "not_high_low",
                timeout_seconds=8.0,
            )

            checked_command(
                p,NOT_INPUT_LOW_COMMAND,"not_input_low_reset",log_path,output_dir
            )
            reset_attempts,reset_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_NOT_RESET_PASS",
                not_probe(0,True,15),
                "not_reset",
                timeout_seconds=8.0,
            )

            # Materialize a source-present high state for static netlist
            # recovery after the low/high/low truth table has already passed.
            # The controller drives the logical input by source injection;
            # no player-operated lever semantics are claimed by this rep.
            checked_command(
                p,NOT_INPUT_HIGH_COMMAND,
                "not_static_materialization_high",
                log_path,output_dir,
            )
            static_attempts,static_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_NOT_STATIC_HIGH_PASS",
                not_probe(15,False,0),
                "not_static_high",
                timeout_seconds=8.0,
            )

            checked_command(p,"save-all flush","save",log_path,output_dir)
            time.sleep(1)
            checked_command(p,"stop","stop",log_path,output_dir)
            rc=p.wait(timeout=60)
        elapsed=time.monotonic()-started
        zip_world(root/"world",output_dir/"world.zip")
        text=log_path.read_text("utf-8",errors="replace")
        diagnostics=[
            line for line in text.splitlines()
            if any(x in line for x in (
                "Incorrect argument","Unknown or incomplete command",
                "[Server thread/ERROR]",
                "SupraCraft causal microscope fail-closed binding",
            ))
        ]
        if rc!=0 or diagnostics:
            for line in diagnostics[-80:]:
                print(line)
            raise SystemExit(
                f"not-gate template failed rc={rc} diagnostics={len(diagnostics)}"
            )
        result={
            "schema":"supracraft-modern-redstone-template-canary/1",
            "template":"not_gate",
            "minecraft_version":version,
            "java_major":evidence_java_major(evidence),
            "instrumented":bool(args.java_agent),
            "input_component_position":[-1,100,0],
            "input_wire_position":[0,100,0],
            "input_control":"fixture_controller_source_injection_via_dust",
            "input_low_block":"minecraft:air",
            "input_high_block":"minecraft:redstone_block",
            "support_position":[1,100,0],
            "inverter_position":[1,101,0],
            "output_wire_position":[2,101,0],
            "output_lamp_position":[3,101,0],
            "input_high_command_sha256":digest_bytes(NOT_INPUT_HIGH_COMMAND),
            "input_low_command_sha256":digest_bytes(NOT_INPUT_LOW_COMMAND),
            "truth_table_sequence":[
                {
                    "phase":"baseline",
                    "input_powered":False,
                    "input_wire_power":0,
                    "torch_lit":True,
                    "output_wire_power":15,
                    "verified":True,
                },
                {
                    "phase":"assert_input",
                    "input_powered":True,
                    "input_wire_power":15,
                    "torch_lit":False,
                    "output_wire_power":0,
                    "verified":True,
                },
                {
                    "phase":"reset_input",
                    "input_powered":False,
                    "input_wire_power":0,
                    "torch_lit":True,
                    "output_wire_power":15,
                    "verified":True,
                },
            ],
            "ready_seconds":round(ready,6),
            "setup_barrier_seconds":round(barrier,6),
            "baseline_attempts":baseline_attempts,
            "baseline_wait_seconds":round(baseline_wait,6),
            "high_attempts":high_attempts,
            "high_wait_seconds":round(high_wait,6),
            "reset_attempts":reset_attempts,
            "reset_wait_seconds":round(reset_wait,6),
            "static_materialization_attempts":static_attempts,
            "static_materialization_wait_seconds":round(static_wait,6),
            "saved_input_state":"high",
            "elapsed_seconds":round(elapsed,6),
            "trace_present":trace_path.is_file(),
            "world_sha256":hashlib.sha256(
                (output_dir/"world.zip").read_bytes()
            ).hexdigest(),
            "boundary":"truth-table sequence qualifies this exact torch inverter under fixture-controller source injection through an explicit input dust net; saved high-state topology supports static source/net/support recovery, but no player-operated input-device semantics are claimed",
        }
        (output_dir/"result.json").write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n"
        )
        print(json.dumps(result,indent=2,sort_keys=True))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--evidence",type=Path,required=True)
    ap.add_argument("--server-jar",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--fixture",choices=("repeater_delay","not_gate"),required=True)
    ap.add_argument("--delay",type=int)
    ap.add_argument("--java-agent",type=Path)
    ap.add_argument("--adapter-id")
    ap.add_argument("--expected-version")
    args=ap.parse_args()

    evidence=json.loads(args.evidence.read_text())
    version=evidence["minecraft_version"]
    if args.expected_version and version!=args.expected_version:
        raise SystemExit(
            f"exact version mismatch expected={args.expected_version} observed={version}"
        )
    if evidence_java_major(evidence)!=25:
        raise SystemExit(
            f"exact modern Java 25 runtime required; observed={evidence_java_major(evidence)}"
        )
    args.output_dir.mkdir(parents=True,exist_ok=True)
    args.server_jar.parent.mkdir(parents=True,exist_ok=True)
    if not args.server_jar.exists():
        if "server_artifact" not in evidence:
            raise SystemExit(
                "server jar must already exist when using a discovery receipt"
            )
        download_server(evidence,args.server_jar)

    if args.fixture=="repeater_delay":
        run_repeater(args,evidence,args.server_jar,args.output_dir)
    else:
        run_not_gate(args,evidence,args.server_jar,args.output_dir)


if __name__=="__main__":
    main()
