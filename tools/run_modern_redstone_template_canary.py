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
OR_A_HIGH_COMMAND="setblock -1 100 -1 minecraft:redstone_block"
OR_A_LOW_COMMAND="setblock -1 100 -1 minecraft:air"
OR_B_HIGH_COMMAND="setblock -1 100 1 minecraft:redstone_block"
OR_B_LOW_COMMAND="setblock -1 100 1 minecraft:air"
AND_A_HIGH_COMMAND=OR_A_HIGH_COMMAND
AND_A_LOW_COMMAND=OR_A_LOW_COMMAND
AND_B_HIGH_COMMAND=OR_B_HIGH_COMMAND
AND_B_LOW_COMMAND=OR_B_LOW_COMMAND


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


def or_probe(a_high,b_high,output_power,lamp_lit):
    a_block="minecraft:redstone_block" if a_high else "minecraft:air"
    b_block="minecraft:redstone_block" if b_high else "minecraft:air"
    lamp="true" if lamp_lit else "false"
    return (
        f"execute if block -1 100 -1 {a_block} "
        f"if block -1 100 1 {b_block} "
        f"if block 2 100 0 minecraft:redstone_wire[power={output_power}] "
        f"if block 3 100 0 minecraft:redstone_lamp[lit={lamp}]"
    )


def run_or_gate(args,evidence,server_jar,output_dir):
    version=evidence["minecraft_version"]
    with tempfile.TemporaryDirectory(prefix="modern-redstone-or-") as td:
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
            checked_command(p,"fill -3 99 -3 5 102 3 minecraft:air","clear",log_path,output_dir)
            checked_command(p,"fill -3 99 -3 5 99 3 minecraft:stone","floor",log_path,output_dir)
            checked_command(p,OR_A_LOW_COMMAND,"or_a_low_setup",log_path,output_dir)
            checked_command(p,OR_B_LOW_COMMAND,"or_b_low_setup",log_path,output_dir)
            for x,z,name in (
                (0,-1,"a_input_wire"),(1,-1,"a_join_wire"),
                (0,1,"b_input_wire"),(1,1,"b_join_wire"),
                (1,0,"junction_wire"),(2,0,"output_wire"),
            ):
                checked_command(
                    p,f"setblock {x} 100 {z} minecraft:redstone_wire",
                    name,log_path,output_dir,
                )
            checked_command(
                p,"setblock 3 100 0 minecraft:redstone_lamp",
                "output_lamp",log_path,output_dir,
            )

            baseline_attempts,baseline_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_OR_00_PASS",
                or_probe(False,False,0,False),
                "or_00",
                timeout_seconds=8.0,
            )
            barrier=setup_barrier(
                p,log_path,output_dir,"SUPRACRAFT_OR_SETUP_READY"
            )
            if args.java_agent:
                gate_path.write_text("capture\n")
                time.sleep(0.15)

            checked_command(p,OR_A_HIGH_COMMAND,"or_a_high",log_path,output_dir)
            a_attempts,a_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_OR_10_PASS",
                or_probe(True,False,12,True),
                "or_10",
                timeout_seconds=8.0,
            )

            checked_command(p,OR_A_LOW_COMMAND,"or_a_low_reset",log_path,output_dir)
            reset_attempts,reset_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_OR_00_RESET_PASS",
                or_probe(False,False,0,False),
                "or_00_reset",
                timeout_seconds=8.0,
            )

            checked_command(p,OR_B_HIGH_COMMAND,"or_b_high",log_path,output_dir)
            b_attempts,b_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_OR_01_PASS",
                or_probe(False,True,12,True),
                "or_01",
                timeout_seconds=8.0,
            )

            checked_command(p,OR_A_HIGH_COMMAND,"or_both_high",log_path,output_dir)
            both_attempts,both_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_OR_11_PASS",
                or_probe(True,True,12,True),
                "or_11",
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
                f"or-gate template failed rc={rc} diagnostics={len(diagnostics)}"
            )
        result={
            "schema":"supracraft-modern-redstone-template-canary/1",
            "template":"or_gate",
            "minecraft_version":version,
            "java_major":evidence_java_major(evidence),
            "instrumented":bool(args.java_agent),
            "input_control":"fixture_controller_two_source_injection",
            "input_a_position":[-1,100,-1],
            "input_b_position":[-1,100,1],
            "input_a_wire_position":[0,100,-1],
            "input_b_wire_position":[0,100,1],
            "junction_wire_position":[1,100,0],
            "output_wire_position":[2,100,0],
            "output_lamp_position":[3,100,0],
            "input_a_high_command_sha256":digest_bytes(OR_A_HIGH_COMMAND),
            "input_a_low_command_sha256":digest_bytes(OR_A_LOW_COMMAND),
            "input_b_high_command_sha256":digest_bytes(OR_B_HIGH_COMMAND),
            "input_b_low_command_sha256":digest_bytes(OR_B_LOW_COMMAND),
            "truth_table_sequence":[
                {"phase":"00","a":False,"b":False,"output_wire_power":0,
                 "output_lamp_lit":False,"verified":True},
                {"phase":"10","a":True,"b":False,"output_wire_power":12,
                 "output_lamp_lit":True,"verified":True},
                {"phase":"00_reset","a":False,"b":False,"output_wire_power":0,
                 "output_lamp_lit":False,"verified":True},
                {"phase":"01","a":False,"b":True,"output_wire_power":12,
                 "output_lamp_lit":True,"verified":True},
                {"phase":"11","a":True,"b":True,"output_wire_power":12,
                 "output_lamp_lit":True,"verified":True},
            ],
            "ready_seconds":round(ready,6),
            "setup_barrier_seconds":round(barrier,6),
            "baseline_attempts":baseline_attempts,
            "baseline_wait_seconds":round(baseline_wait,6),
            "a_high_attempts":a_attempts,
            "a_high_wait_seconds":round(a_wait,6),
            "reset_attempts":reset_attempts,
            "reset_wait_seconds":round(reset_wait,6),
            "b_high_attempts":b_attempts,
            "b_high_wait_seconds":round(b_wait,6),
            "both_high_attempts":both_attempts,
            "both_high_wait_seconds":round(both_wait,6),
            "saved_input_state":"11",
            "elapsed_seconds":round(elapsed,6),
            "trace_present":trace_path.is_file(),
            "world_sha256":hashlib.sha256(
                (output_dir/"world.zip").read_bytes()
            ).hexdigest(),
            "boundary":"full two-input OR truth table qualifies this exact joined-dust topology under fixture-controller source injection; arbitrary multi-source buses remain structural candidates until independently validated",
        }
        (output_dir/"result.json").write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n"
        )
        print(json.dumps(result,indent=2,sort_keys=True))


def and_probe(a_high,b_high,output_power,lamp_lit):
    a_block="minecraft:redstone_block" if a_high else "minecraft:air"
    b_block="minecraft:redstone_block" if b_high else "minecraft:air"
    a_torch="false" if a_high else "true"
    b_torch="false" if b_high else "true"
    final_torch="true" if a_high and b_high else "false"
    lamp="true" if lamp_lit else "false"
    a_wire=15 if a_high else 0
    b_wire=15 if b_high else 0
    return (
        f"execute if block -1 100 -1 {a_block} "
        f"if block -1 100 1 {b_block} "
        f"if block 0 100 -1 minecraft:redstone_wire[power={a_wire}] "
        f"if block 0 100 1 minecraft:redstone_wire[power={b_wire}] "
        f"if block 1 101 -1 minecraft:redstone_torch[lit={a_torch}] "
        f"if block 1 101 1 minecraft:redstone_torch[lit={b_torch}] "
        f"if block 3 102 0 minecraft:redstone_torch[lit={final_torch}] "
        f"if block 4 102 0 minecraft:redstone_wire[power={output_power}] "
        f"if block 5 102 0 minecraft:redstone_lamp[lit={lamp}]"
    )


def run_and_gate(args,evidence,server_jar,output_dir):
    version=evidence["minecraft_version"]
    with tempfile.TemporaryDirectory(prefix="modern-redstone-and-") as td:
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
            checked_command(p,"fill -3 99 -3 7 104 3 minecraft:air","clear",log_path,output_dir)
            checked_command(p,"fill -3 99 -3 7 99 3 minecraft:stone","floor",log_path,output_dir)

            # Input inverter supports and intermediate wire supports.
            for x,y,z,name in (
                (1,100,-1,"a_torch_support"),
                (1,100,1,"b_torch_support"),
                (2,100,-1,"intermediate_support_a"),
                (2,100,0,"intermediate_support_junction"),
                (2,100,1,"intermediate_support_b"),
                (3,101,0,"final_torch_support"),
                (4,101,0,"output_wire_support"),
            ):
                checked_command(
                    p,f"setblock {x} {y} {z} minecraft:stone",
                    name,log_path,output_dir,
                )

            checked_command(p,AND_A_LOW_COMMAND,"and_a_low_setup",log_path,output_dir)
            checked_command(p,AND_B_LOW_COMMAND,"and_b_low_setup",log_path,output_dir)
            checked_command(p,"setblock 0 100 -1 minecraft:redstone_wire","a_input_wire",log_path,output_dir)
            checked_command(p,"setblock 0 100 1 minecraft:redstone_wire","b_input_wire",log_path,output_dir)
            checked_command(p,"setblock 1 101 -1 minecraft:redstone_torch","a_inverter",log_path,output_dir)
            checked_command(p,"setblock 1 101 1 minecraft:redstone_torch","b_inverter",log_path,output_dir)
            for x,z,name in (
                (2,-1,"intermediate_wire_a"),
                (2,0,"intermediate_wire_junction"),
                (2,1,"intermediate_wire_b"),
            ):
                checked_command(
                    p,f"setblock {x} 101 {z} minecraft:redstone_wire",
                    name,log_path,output_dir,
                )
            checked_command(p,"setblock 3 102 0 minecraft:redstone_torch","final_inverter",log_path,output_dir)
            checked_command(p,"setblock 4 102 0 minecraft:redstone_wire","output_wire",log_path,output_dir)
            checked_command(p,"setblock 5 102 0 minecraft:redstone_lamp","output_lamp",log_path,output_dir)

            baseline_attempts,baseline_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_AND_00_PASS",
                and_probe(False,False,0,False),
                "and_00",timeout_seconds=8.0,
            )
            barrier=setup_barrier(
                p,log_path,output_dir,"SUPRACRAFT_AND_SETUP_READY"
            )
            if args.java_agent:
                gate_path.write_text("capture\n")
                time.sleep(0.15)

            checked_command(p,AND_A_HIGH_COMMAND,"and_a_high",log_path,output_dir)
            a_attempts,a_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_AND_10_PASS",
                and_probe(True,False,0,False),
                "and_10",timeout_seconds=8.0,
            )

            checked_command(p,AND_A_LOW_COMMAND,"and_a_low_reset",log_path,output_dir)
            reset_attempts,reset_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_AND_00_RESET_PASS",
                and_probe(False,False,0,False),
                "and_00_reset",timeout_seconds=8.0,
            )

            checked_command(p,AND_B_HIGH_COMMAND,"and_b_high",log_path,output_dir)
            b_attempts,b_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_AND_01_PASS",
                and_probe(False,True,0,False),
                "and_01",timeout_seconds=8.0,
            )

            checked_command(p,AND_A_HIGH_COMMAND,"and_both_high",log_path,output_dir)
            both_attempts,both_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_AND_11_PASS",
                and_probe(True,True,15,True),
                "and_11",timeout_seconds=8.0,
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
                f"and-gate template failed rc={rc} diagnostics={len(diagnostics)}"
            )
        result={
            "schema":"supracraft-modern-redstone-template-canary/1",
            "template":"and_gate",
            "minecraft_version":version,
            "java_major":evidence_java_major(evidence),
            "instrumented":bool(args.java_agent),
            "input_control":"fixture_controller_two_source_injection",
            "input_a_position":[-1,100,-1],
            "input_b_position":[-1,100,1],
            "input_a_wire_position":[0,100,-1],
            "input_b_wire_position":[0,100,1],
            "input_a_inverter_position":[1,101,-1],
            "input_b_inverter_position":[1,101,1],
            "intermediate_wire_positions":[[2,101,-1],[2,101,0],[2,101,1]],
            "final_inverter_position":[3,102,0],
            "output_wire_position":[4,102,0],
            "output_lamp_position":[5,102,0],
            "input_a_high_command_sha256":digest_bytes(AND_A_HIGH_COMMAND),
            "input_a_low_command_sha256":digest_bytes(AND_A_LOW_COMMAND),
            "input_b_high_command_sha256":digest_bytes(AND_B_HIGH_COMMAND),
            "input_b_low_command_sha256":digest_bytes(AND_B_LOW_COMMAND),
            "truth_table_sequence":[
                {"phase":"00","a":False,"b":False,"output_wire_power":0,
                 "output_lamp_lit":False,"verified":True},
                {"phase":"10","a":True,"b":False,"output_wire_power":0,
                 "output_lamp_lit":False,"verified":True},
                {"phase":"00_reset","a":False,"b":False,"output_wire_power":0,
                 "output_lamp_lit":False,"verified":True},
                {"phase":"01","a":False,"b":True,"output_wire_power":0,
                 "output_lamp_lit":False,"verified":True},
                {"phase":"11","a":True,"b":True,"output_wire_power":15,
                 "output_lamp_lit":True,"verified":True},
            ],
            "ready_seconds":round(ready,6),
            "setup_barrier_seconds":round(barrier,6),
            "baseline_attempts":baseline_attempts,
            "baseline_wait_seconds":round(baseline_wait,6),
            "a_high_attempts":a_attempts,
            "a_high_wait_seconds":round(a_wait,6),
            "reset_attempts":reset_attempts,
            "reset_wait_seconds":round(reset_wait,6),
            "b_high_attempts":b_attempts,
            "b_high_wait_seconds":round(b_wait,6),
            "both_high_attempts":both_attempts,
            "both_high_wait_seconds":round(both_wait,6),
            "saved_input_state":"11",
            "elapsed_seconds":round(elapsed,6),
            "trace_present":trace_path.is_file(),
            "world_sha256":hashlib.sha256(
                (output_dir/"world.zip").read_bytes()
            ).hexdigest(),
            "boundary":"complete AND truth table plus explicit three-inverter De-Morgan topology qualifies only this generated fixture; arbitrary torch networks remain unqualified",
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
    ap.add_argument("--fixture",choices=("repeater_delay","not_gate","or_gate","and_gate"),required=True)
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
    elif args.fixture=="not_gate":
        run_not_gate(args,evidence,args.server_jar,args.output_dir)
    elif args.fixture=="or_gate":
        run_or_gate(args,evidence,args.server_jar,args.output_dir)
    else:
        run_and_gate(args,evidence,args.server_jar,args.output_dir)


if __name__=="__main__":
    main()
