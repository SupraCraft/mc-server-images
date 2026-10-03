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
NOR_A_HIGH_COMMAND=OR_A_HIGH_COMMAND
NOR_A_LOW_COMMAND=OR_A_LOW_COMMAND
NOR_B_HIGH_COMMAND=OR_B_HIGH_COMMAND
NOR_B_LOW_COMMAND=OR_B_LOW_COMMAND
XOR_A_HIGH_COMMAND="setblock 0 100 -2 minecraft:redstone_block"
XOR_A_LOW_COMMAND="setblock 0 100 -2 minecraft:air"
XOR_B_HIGH_COMMAND="setblock 0 100 2 minecraft:redstone_block"
XOR_B_LOW_COMMAND="setblock 0 100 2 minecraft:air"
EDGE_INPUT_HIGH_COMMAND="setblock 0 100 0 minecraft:redstone_block"
EDGE_INPUT_LOW_COMMAND="setblock 0 100 0 minecraft:air"


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


def diagnose_nor_state(process,log_path,output_dir,phase):
    """Emit bounded exact block-state probes without changing NOR state."""
    checks=[]

    def add(label,value,condition):
        token=(
            f"P{value:02d}" if isinstance(value,int)
            else str(value).replace("-","NEG").replace(".","_").upper()
        )
        marker=f"SUPRACRAFT_NOR_DIAG_{label.upper()}_{token}"
        checks.append((label,value,marker,condition))

    for label,x,y,z in (
        ("source_a",-1,100,-1),
        ("source_b",-1,100,1),
    ):
        add(label,"air",f"execute if block {x} {y} {z} minecraft:air")
        add(
            label,"redstone_block",
            f"execute if block {x} {y} {z} minecraft:redstone_block",
        )

    for label,x,y,z in (
        ("input_a",0,100,-1),
        ("join_a",1,100,-1),
        ("input_b",0,100,1),
        ("join_b",1,100,1),
        ("junction",1,100,0),
        ("support_feed",2,100,0),
        ("output_wire",4,101,0),
    ):
        for power in range(16):
            add(
                label,power,
                f"execute if block {x} {y} {z} minecraft:redstone_wire[power={power}]",
            )

    for lit in (False,True):
        state="true" if lit else "false"
        label="lit" if lit else "unlit"
        add(
            "inverter",label,
            f"execute if block 3 101 0 minecraft:redstone_torch[lit={state}]",
        )
        add(
            "output_lamp",label,
            f"execute if block 5 101 0 minecraft:redstone_lamp[lit={state}]",
        )

    for label,value,marker,condition in checks:
        checked_command(
            process,f"{condition} run say {marker}",
            f"nor_diagnostic_{phase}_{label}",log_path,output_dir,
        )
    time.sleep(0.75)
    text=log_path.read_text("utf-8",errors="replace")
    observed={}
    for label,value,marker,_ in checks:
        if marker in text:
            observed.setdefault(label,[]).append(value)
    compact={
        label:(values[0] if len(values)==1 else values)
        for label,values in sorted(observed.items())
    }
    expected_by_phase={
        "baseline_00_timeout":{
            "source_a":"air",
            "source_b":"air",
            "input_a":0,
            "join_a":0,
            "input_b":0,
            "join_b":0,
            "junction":0,
            "support_feed":0,
            "inverter":"lit",
            "output_wire":15,
        },
        "10_timeout":{
            "source_a":"redstone_block",
            "source_b":"air",
            "inverter":"unlit",
            "output_wire":0,
        },
    }
    expected=expected_by_phase.get(phase,{})
    receipt={
        "schema":"supracraft-modern-nor-fixture-diagnostic/1",
        "phase":phase,
        "expected":expected,
        "observed":compact,
        "mismatched":{
            key:{"expected":value,"observed":compact.get(key)}
            for key,value in expected.items()
            if compact.get(key)!=value
        },
        "nonsemantic_observations":{
            "output_lamp":compact.get("output_lamp"),
        },
        "boundary":"diagnostic receipt records bounded block-state values; NOR semantics are exact inverter plus output-dust state, while the adjacent lamp is diagnostic only",
    }
    (output_dir/"diagnostic.json").write_text(
        json.dumps(receipt,indent=2,sort_keys=True)+"\n"
    )
    print("NOR_FIXTURE_DIAGNOSTIC")
    print(json.dumps(receipt,indent=2,sort_keys=True))
    return receipt


def nor_probe(a_high,b_high,torch_lit,output_power):
    a_block="minecraft:redstone_block" if a_high else "minecraft:air"
    b_block="minecraft:redstone_block" if b_high else "minecraft:air"
    torch="true" if torch_lit else "false"
    return (
        f"execute if block -1 100 -1 {a_block} "
        f"if block -1 100 1 {b_block} "
        f"if block 3 101 0 minecraft:redstone_torch[lit={torch}] "
        f"if block 4 101 0 minecraft:redstone_wire[power={output_power}]"
    )


def run_nor_gate(args,evidence,server_jar,output_dir):
    version=evidence["minecraft_version"]
    with tempfile.TemporaryDirectory(prefix="modern-redstone-nor-") as td:
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
            checked_command(p,"fill -3 99 -3 6 103 3 minecraft:air","clear",log_path,output_dir)
            checked_command(p,"fill -3 99 -3 6 99 3 minecraft:stone","floor",log_path,output_dir)
            checked_command(p,NOR_A_LOW_COMMAND,"nor_a_low_setup",log_path,output_dir)
            checked_command(p,NOR_B_LOW_COMMAND,"nor_b_low_setup",log_path,output_dir)
            for x,z,name in (
                (0,-1,"a_input_wire"),(1,-1,"a_join_wire"),
                (0,1,"b_input_wire"),(1,1,"b_join_wire"),
                (1,0,"junction_wire"),(2,0,"support_feed_wire"),
            ):
                checked_command(
                    p,f"setblock {x} 100 {z} minecraft:redstone_wire",
                    name,log_path,output_dir,
                )
            checked_command(p,"setblock 3 100 0 minecraft:stone","inverter_support",log_path,output_dir)
            checked_command(p,"setblock 4 100 0 minecraft:stone","output_wire_support",log_path,output_dir)
            checked_command(p,"setblock 3 101 0 minecraft:redstone_torch","inverter",log_path,output_dir)
            checked_command(p,"setblock 4 101 0 minecraft:redstone_wire","output_wire",log_path,output_dir)
            checked_command(p,"setblock 5 101 0 minecraft:redstone_lamp","output_lamp",log_path,output_dir)

            try:
                baseline_attempts,baseline_wait=wait_for_marker(
                    p,log_path,output_dir,
                    "SUPRACRAFT_NOR_00_PASS",
                    nor_probe(False,False,True,15),
                    "nor_00",timeout_seconds=8.0,
                )
            except SystemExit as exc:
                receipt=diagnose_nor_state(
                    p,log_path,output_dir,"baseline_00_timeout"
                )
                checked_command(
                    p,"save-all flush","nor_diagnostic_save",
                    log_path,output_dir,
                )
                time.sleep(0.5)
                checked_command(
                    p,"stop","nor_diagnostic_stop",
                    log_path,output_dir,
                )
                rc=p.wait(timeout=60)
                zip_world(root/"world",output_dir/"world.zip")
                receipt["original_failure"]=str(exc)
                receipt["server_exit_code"]=rc
                receipt["world_sha256"]=hashlib.sha256(
                    (output_dir/"world.zip").read_bytes()
                ).hexdigest()
                (output_dir/"diagnostic.json").write_text(
                    json.dumps(receipt,indent=2,sort_keys=True)+"\n"
                )
                print(json.dumps(receipt,indent=2,sort_keys=True))
                raise
            barrier=setup_barrier(
                p,log_path,output_dir,"SUPRACRAFT_NOR_SETUP_READY"
            )
            if args.java_agent:
                gate_path.write_text("capture\n")
                time.sleep(0.15)

            checked_command(p,NOR_A_HIGH_COMMAND,"nor_a_high",log_path,output_dir)
            try:
                a_attempts,a_wait=wait_for_marker(
                    p,log_path,output_dir,
                    "SUPRACRAFT_NOR_10_PASS",
                    nor_probe(True,False,False,0),
                    "nor_10",timeout_seconds=8.0,
                )
            except SystemExit as exc:
                receipt=diagnose_nor_state(
                    p,log_path,output_dir,"10_timeout"
                )
                checked_command(
                    p,"save-all flush","nor_10_diagnostic_save",
                    log_path,output_dir,
                )
                time.sleep(0.5)
                checked_command(
                    p,"stop","nor_10_diagnostic_stop",
                    log_path,output_dir,
                )
                rc=p.wait(timeout=60)
                zip_world(root/"world",output_dir/"world.zip")
                receipt["original_failure"]=str(exc)
                receipt["server_exit_code"]=rc
                receipt["world_sha256"]=hashlib.sha256(
                    (output_dir/"world.zip").read_bytes()
                ).hexdigest()
                (output_dir/"diagnostic.json").write_text(
                    json.dumps(receipt,indent=2,sort_keys=True)+"\n"
                )
                print(json.dumps(receipt,indent=2,sort_keys=True))
                raise

            checked_command(p,NOR_A_LOW_COMMAND,"nor_a_low_reset",log_path,output_dir)
            reset_attempts,reset_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_NOR_00_RESET_PASS",
                nor_probe(False,False,True,15),
                "nor_00_reset",timeout_seconds=8.0,
            )

            checked_command(p,NOR_B_HIGH_COMMAND,"nor_b_high",log_path,output_dir)
            b_attempts,b_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_NOR_01_PASS",
                nor_probe(False,True,False,0),
                "nor_01",timeout_seconds=8.0,
            )

            checked_command(p,NOR_A_HIGH_COMMAND,"nor_both_high",log_path,output_dir)
            both_attempts,both_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_NOR_11_PASS",
                nor_probe(True,True,False,0),
                "nor_11",timeout_seconds=8.0,
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
                f"nor-gate template failed rc={rc} diagnostics={len(diagnostics)}"
            )
        result={
            "schema":"supracraft-modern-redstone-template-canary/1",
            "template":"nor_gate",
            "minecraft_version":version,
            "java_major":evidence_java_major(evidence),
            "instrumented":bool(args.java_agent),
            "input_control":"fixture_controller_two_source_injection",
            "input_a_position":[-1,100,-1],
            "input_b_position":[-1,100,1],
            "input_a_wire_position":[0,100,-1],
            "input_b_wire_position":[0,100,1],
            "junction_wire_position":[1,100,0],
            "input_net_wire_positions":[
                [0,100,-1],[1,100,-1],[0,100,1],[1,100,1],
                [1,100,0],[2,100,0]
            ],
            "inverter_support_position":[3,100,0],
            "inverter_position":[3,101,0],
            "output_wire_position":[4,101,0],
            "output_lamp_position":[5,101,0],
            "input_a_high_command_sha256":digest_bytes(NOR_A_HIGH_COMMAND),
            "input_a_low_command_sha256":digest_bytes(NOR_A_LOW_COMMAND),
            "input_b_high_command_sha256":digest_bytes(NOR_B_HIGH_COMMAND),
            "input_b_low_command_sha256":digest_bytes(NOR_B_LOW_COMMAND),
            "truth_table_sequence":[
                {"phase":"00","a":False,"b":False,"torch_lit":True,
                 "output_wire_power":15,"verified":True},
                {"phase":"10","a":True,"b":False,"torch_lit":False,
                 "output_wire_power":0,"verified":True},
                {"phase":"00_reset","a":False,"b":False,"torch_lit":True,
                 "output_wire_power":15,"verified":True},
                {"phase":"01","a":False,"b":True,"torch_lit":False,
                 "output_wire_power":0,"verified":True},
                {"phase":"11","a":True,"b":True,"torch_lit":False,
                 "output_wire_power":0,"verified":True},
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
            "output_lamp_semantic_authority":False,
            "boundary":"complete NOR truth table is qualified by exact inverter state plus output-dust power through an explicit merged-net support-feed segment; the adjacent lamp remains structural/diagnostic only and does not define NOR semantics",
        }
        (output_dir/"result.json").write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n"
        )
        print(json.dumps(result,indent=2,sort_keys=True))


def diagnose_and_state(process,log_path,output_dir,phase):
    """Emit bounded marker probes for the AND fixture without changing state."""
    checks=[]

    def add(label,value,condition):
        token=(f"P{value:02d}" if isinstance(value,int) else str(value).replace("-","NEG").replace(".","_").upper())
        marker=f"SUPRACRAFT_AND_DIAG_{label.upper()}_{token}"
        checks.append((label,value,marker,condition))

    for label,x,y,z in (
        ("source_a",-1,100,-1),
        ("source_b",-1,100,1),
    ):
        add(label,"air",f"execute if block {x} {y} {z} minecraft:air")
        add(label,"redstone_block",f"execute if block {x} {y} {z} minecraft:redstone_block")

    for label,x,y,z in (
        ("input_a_wire",0,100,-1),
        ("input_b_wire",0,100,1),
        ("intermediate_a",2,101,-1),
        ("intermediate_junction",2,101,0),
        ("intermediate_b",2,101,1),
        ("intermediate_stub",3,101,0),
        ("output_wire",5,102,0),
    ):
        for power in range(16):
            add(
                label,power,
                f"execute if block {x} {y} {z} minecraft:redstone_wire[power={power}]",
            )

    for label,x,y,z in (
        ("input_a_inverter",1,101,-1),
        ("input_b_inverter",1,101,1),
        ("final_inverter",4,102,0),
    ):
        for lit in (False,True):
            value="lit" if lit else "unlit"
            state="true" if lit else "false"
            add(
                label,value,
                f"execute if block {x} {y} {z} minecraft:redstone_torch[lit={state}]",
            )

    for lit in (False,True):
        value="lit" if lit else "unlit"
        state="true" if lit else "false"
        add(
            "output_lamp",value,
            f"execute if block 6 102 0 minecraft:redstone_lamp[lit={state}]",
        )

    for label,value,marker,condition in checks:
        checked_command(
            process,f"{condition} run say {marker}",
            f"and_diagnostic_{phase}_{label}",log_path,output_dir,
        )
    time.sleep(0.75)
    text=log_path.read_text("utf-8",errors="replace")
    observed={}
    for label,value,marker,_ in checks:
        if marker in text:
            observed.setdefault(label,[]).append(value)
    compact={
        label:(values[0] if len(values)==1 else values)
        for label,values in sorted(observed.items())
    }
    expected={
        "source_a":"air",
        "source_b":"air",
        "input_a_wire":0,
        "input_b_wire":0,
        "input_a_inverter":"lit",
        "input_b_inverter":"lit",
        "final_inverter":"unlit",
        "output_wire":0,
        "output_lamp":"unlit",
    }
    receipt={
        "schema":"supracraft-modern-and-fixture-diagnostic/1",
        "phase":phase,
        "expected":expected,
        "observed":compact,
        "mismatched":{
            key:{"expected":value,"observed":compact.get(key)}
            for key,value in expected.items()
            if compact.get(key)!=value
        },
        "intermediate_wire_powers":{
            key:compact.get(key)
            for key in (
                "intermediate_a","intermediate_junction","intermediate_b","intermediate_stub"
            )
        },
        "boundary":"diagnostic receipt records only bounded block-state values; it does not change the AND truth-table contract or promote semantics",
    }
    (output_dir/"diagnostic.json").write_text(
        json.dumps(receipt,indent=2,sort_keys=True)+"\n"
    )
    print("AND_FIXTURE_DIAGNOSTIC")
    print(json.dumps(receipt,indent=2,sort_keys=True))
    return receipt


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
        f"if block 4 102 0 minecraft:redstone_torch[lit={final_torch}] "
        f"if block 5 102 0 minecraft:redstone_wire[power={output_power}] "
        f"if block 6 102 0 minecraft:redstone_lamp[lit={lamp}]"
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
                (3,100,0,"intermediate_stub_support"),
                (4,101,0,"final_torch_support"),
                (5,101,0,"output_wire_support"),
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
                (3,0,"intermediate_wire_stub"),
            ):
                checked_command(
                    p,f"setblock {x} 101 {z} minecraft:redstone_wire",
                    name,log_path,output_dir,
                )
            checked_command(p,"setblock 4 102 0 minecraft:redstone_torch","final_inverter",log_path,output_dir)
            checked_command(p,"setblock 5 102 0 minecraft:redstone_wire","output_wire",log_path,output_dir)
            checked_command(p,"setblock 6 102 0 minecraft:redstone_lamp","output_lamp",log_path,output_dir)

            try:
                baseline_attempts,baseline_wait=wait_for_marker(
                    p,log_path,output_dir,
                    "SUPRACRAFT_AND_00_PASS",
                    and_probe(False,False,0,False),
                    "and_00",timeout_seconds=8.0,
                )
            except SystemExit:
                diagnose_and_state(
                    p,log_path,output_dir,"baseline_00_timeout"
                )
                raise
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
            "intermediate_wire_positions":[[2,101,-1],[2,101,0],[2,101,1],[3,101,0]],
            "final_inverter_position":[4,102,0],
            "output_wire_position":[5,102,0],
            "output_lamp_position":[6,102,0],
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




def diagnose_xor_state(process,log_path,output_dir,phase):
    """Record bounded exact XOR block state without changing the fixture."""
    checks=[]

    def add(label,value,condition):
        token=(
            f"P{value:02d}" if isinstance(value,int)
            else str(value).replace("-","NEG").replace(".","_").upper()
        )
        marker=f"SUPRACRAFT_XOR_DIAG_{label.upper()}_{token}"
        checks.append((label,value,marker,condition))

    for label,x,y,z in (
        ("source_a",0,100,-2),
        ("source_b",0,100,2),
    ):
        add(label,"air",f"execute if block {x} {y} {z} minecraft:air")
        add(
            label,"redstone_block",
            f"execute if block {x} {y} {z} minecraft:redstone_block",
        )

    for label,x,y,z in (
        ("or_a_input",1,100,-2),
        ("or_junction",2,100,0),
        ("or_route_end",6,102,-3),
        ("not_a_input",-1,100,-2),
        ("not_b_input",-1,100,2),
        ("nand_junction",-4,101,0),
        ("nand_route_end",3,101,4),
        ("intermediate_join",9,103,0),
        ("intermediate_feed",10,103,0),
        ("output_wire",12,104,0),
    ):
        for power in range(16):
            add(
                label,power,
                f"execute if block {x} {y} {z} minecraft:redstone_wire[power={power}]",
            )

    for label,x,y,z in (
        ("not_a_inverter",-2,101,-2),
        ("not_b_inverter",-2,101,2),
        ("or_stage_inverter",7,103,-3),
        ("nand_stage_inverter",4,102,4),
        ("final_inverter",11,104,0),
    ):
        for lit in (False,True):
            value="lit" if lit else "unlit"
            state="true" if lit else "false"
            add(
                label,value,
                f"execute if block {x} {y} {z} minecraft:redstone_torch[lit={state}]",
            )

    for lit in (False,True):
        value="lit" if lit else "unlit"
        state="true" if lit else "false"
        add(
            "output_lamp",value,
            f"execute if block 13 104 0 minecraft:redstone_lamp[lit={state}]",
        )

    for label,value,marker,condition in checks:
        checked_command(
            process,f"{condition} run say {marker}",
            f"xor_diagnostic_{phase}_{label}",log_path,output_dir,
        )
    time.sleep(0.75)
    text=log_path.read_text("utf-8",errors="replace")
    observed={}
    for label,value,marker,_ in checks:
        if marker in text:
            observed.setdefault(label,[]).append(value)
    compact={
        label:(values[0] if len(values)==1 else values)
        for label,values in sorted(observed.items())
    }
    receipt={
        "schema":"supracraft-modern-xor-fixture-diagnostic/1",
        "phase":phase,
        "expected_logic":{
            "10_timeout":{
                "source_a":"redstone_block",
                "source_b":"air",
                "or_branch":"powered",
                "not_a_inverter":"unlit",
                "not_b_inverter":"lit",
                "nand_branch":"powered",
                "or_stage_inverter":"unlit",
                "nand_stage_inverter":"unlit",
                "intermediate_branch":"unpowered",
                "final_inverter":"lit",
                "output_wire":"powered",
            },
            "00_reset_timeout":{
                "source_a":"air",
                "source_b":"air",
                "or_branch":"unpowered",
                "not_a_inverter":"lit",
                "not_b_inverter":"lit",
                "nand_branch":"powered",
                "or_stage_inverter":"lit",
                "nand_stage_inverter":"unlit",
                "intermediate_branch":"powered",
                "final_inverter":"unlit",
                "output_wire":"unpowered",
            },
            "01_timeout":{
                "source_a":"air",
                "source_b":"redstone_block",
                "or_branch":"powered",
                "not_a_inverter":"lit",
                "not_b_inverter":"unlit",
                "nand_branch":"powered",
                "or_stage_inverter":"unlit",
                "nand_stage_inverter":"unlit",
                "intermediate_branch":"unpowered",
                "final_inverter":"lit",
                "output_wire":"powered",
            },
        }.get(phase,{}),
        "observed":compact,
        "nonsemantic_observations":{
            "output_lamp":compact.get("output_lamp"),
        },
        "boundary":"diagnostic receipt records exact bounded block states only; XOR semantics remain the complete 00/10/01/11 truth table and presentation-lamp state is non-authoritative",
    }
    (output_dir/"diagnostic.json").write_text(
        json.dumps(receipt,indent=2,sort_keys=True)+"\n"
    )
    print("XOR_FIXTURE_DIAGNOSTIC")
    print(json.dumps(receipt,indent=2,sort_keys=True))
    return receipt


def xor_probe(a_high,b_high,final_torch_lit,output_power):
    a_block="minecraft:redstone_block" if a_high else "minecraft:air"
    b_block="minecraft:redstone_block" if b_high else "minecraft:air"
    final_torch="true" if final_torch_lit else "false"
    return (
        f"execute if block 0 100 -2 {a_block} "
        f"if block 0 100 2 {b_block} "
        f"if block 11 104 0 minecraft:redstone_torch[lit={final_torch}] "
        f"if block 12 104 0 minecraft:redstone_wire[power={output_power}]"
    )


def run_xor_gate(args,evidence,server_jar,output_dir):
    """Qualify one bounded XOR composition: (A OR B) AND (NOT A OR NOT B)."""
    version=evidence["minecraft_version"]
    with tempfile.TemporaryDirectory(prefix="modern-redstone-xor-") as td:
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
            checked_command(p,"fill -6 99 -5 14 106 5 minecraft:air","clear",log_path,output_dir)
            checked_command(p,"fill -6 99 -5 14 99 5 minecraft:stone","floor",log_path,output_dir)
            checked_command(p,XOR_A_LOW_COMMAND,"xor_a_low_setup",log_path,output_dir)
            checked_command(p,XOR_B_LOW_COMMAND,"xor_b_low_setup",log_path,output_dir)

            # One physical fixture source per logical input fans out into two
            # isolated branches: east into the direct OR net, west into that
            # input's inverter.  This avoids duplicate logical input sources.
            for x,z,name in (
                (1,-2,"or_a_input"),(2,-2,"or_a_join"),
                (1,2,"or_b_input"),(2,2,"or_b_join"),
                (2,-1,"or_a_turn"),(2,0,"or_junction"),(2,1,"or_b_turn"),
                (3,0,"or_rise_feed"),
                (-1,-2,"not_a_input"),(-1,2,"not_b_input"),
            ):
                checked_command(
                    p,f"setblock {x} 100 {z} minecraft:redstone_wire",
                    name,log_path,output_dir,
                )

            # Per-input NOT branches.
            for x,y,z,name in (
                (-2,100,-2,"not_a_support"),
                (-2,100,2,"not_b_support"),
                (-3,100,-2,"not_a_output_support"),
                (-3,100,2,"not_b_output_support"),
            ):
                checked_command(
                    p,f"setblock {x} {y} {z} minecraft:stone",
                    name,log_path,output_dir,
                )
            checked_command(p,"setblock -2 101 -2 minecraft:redstone_torch","not_a",log_path,output_dir)
            checked_command(p,"setblock -2 101 2 minecraft:redstone_torch","not_b",log_path,output_dir)

            # Merge NOT A and NOT B into the NAND-equivalent branch at y=101.
            nand_wire_positions=[
                (-3,-2),(-4,-2),(-4,-1),(-4,0),(-4,1),(-4,2),(-3,2),(-4,3),(-4,4),
                (-3,4),(-2,4),(-1,4),(0,4),(1,4),(2,4),(3,4),
            ]
            for x,z in nand_wire_positions:
                if not (x==-3 and z in {-2,2}):
                    checked_command(
                        p,f"setblock {x} 100 {z} minecraft:stone",
                        f"nand_support_{x}_{z}",log_path,output_dir,
                    )
                checked_command(
                    p,f"setblock {x} 101 {z} minecraft:redstone_wire",
                    f"nand_wire_{x}_{z}",log_path,output_dir,
                )

            # Raise the direct OR branch twice so its final-stage input remains
            # physically separated from the NAND-equivalent branch.
            for x,y,z,name in (
                (4,100,0,"or_rise_1_support"),
                (5,101,0,"or_rise_2_support"),
                (5,101,-1,"or_route_support_1"),
                (5,101,-2,"or_route_support_2"),
                (5,101,-3,"or_route_support_3"),
                (6,101,-3,"or_route_support_4"),
                (4,101,4,"xor_nand_stage_support"),
                (5,101,4,"xor_nand_output_support_1"),
                (6,101,4,"xor_nand_output_support_2"),
            ):
                checked_command(
                    p,f"setblock {x} {y} {z} minecraft:stone",
                    name,log_path,output_dir,
                )
            for x,y,z,name in (
                (4,101,0,"or_rise_1"),
                (5,102,0,"or_rise_2"),
                (5,102,-1,"or_route_1"),
                (5,102,-2,"or_route_2"),
                (5,102,-3,"or_route_3"),
                (6,102,-3,"or_route_4"),
                (5,102,4,"xor_nand_stage_output_1"),
                (6,102,4,"xor_nand_stage_output_2"),
            ):
                checked_command(
                    p,f"setblock {x} {y} {z} minecraft:redstone_wire",
                    name,log_path,output_dir,
                )

            # Final AND stage: invert the OR and NAND-equivalent branches,
            # merge those inverter outputs, then invert once more.
            for x,y,z,name in (
                (7,102,-3,"xor_or_input_support"),
                (7,102,4,"xor_nand_output_rise_support"),
                (8,102,-3,"xor_mid_a_support"),
                (9,102,-3,"xor_mid_a2_support"),
                (9,102,-2,"xor_mid_a3_support"),
                (9,102,-1,"xor_mid_a4_support"),
                (9,102,0,"xor_mid_join_support"),
                (9,102,1,"xor_mid_b5_support"),
                (9,102,2,"xor_mid_b4_support"),
                (9,102,3,"xor_mid_b3_support"),
                (9,102,4,"xor_mid_b2_support"),
                (8,102,4,"xor_mid_b_support"),
                (10,102,0,"xor_mid_feed_support"),
                (11,103,0,"xor_final_support"),
                (12,103,0,"xor_output_support"),
            ):
                checked_command(
                    p,f"setblock {x} {y} {z} minecraft:stone",
                    name,log_path,output_dir,
                )
            checked_command(p,"setblock 7 103 -3 minecraft:redstone_torch","xor_or_input_inverter",log_path,output_dir)
            checked_command(p,"setblock 4 102 4 minecraft:redstone_torch","xor_nand_input_inverter",log_path,output_dir)
            for x,z,name in (
                (8,-3,"xor_mid_a"),(9,-3,"xor_mid_a2"),(9,-2,"xor_mid_a3"),
                (9,-1,"xor_mid_a4"),(9,0,"xor_mid_join"),
                (9,1,"xor_mid_b5"),(9,2,"xor_mid_b4"),(9,3,"xor_mid_b3"),
                (9,4,"xor_mid_b2"),(8,4,"xor_mid_b"),(7,4,"xor_mid_b_rise"),
                (10,0,"xor_mid_feed"),
            ):
                checked_command(
                    p,f"setblock {x} 103 {z} minecraft:redstone_wire",
                    name,log_path,output_dir,
                )
            checked_command(p,"setblock 11 104 0 minecraft:redstone_torch","xor_final_inverter",log_path,output_dir)
            checked_command(p,"setblock 12 104 0 minecraft:redstone_wire","xor_output_wire",log_path,output_dir)
            checked_command(p,"setblock 13 104 0 minecraft:redstone_lamp","xor_output_lamp",log_path,output_dir)

            baseline_attempts,baseline_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_XOR_00_PASS",
                xor_probe(False,False,False,0),
                "xor_00",timeout_seconds=10.0,
            )
            barrier=setup_barrier(
                p,log_path,output_dir,"SUPRACRAFT_XOR_SETUP_READY"
            )
            if args.java_agent:
                gate_path.write_text("capture\n")
                time.sleep(0.15)

            checked_command(p,XOR_A_HIGH_COMMAND,"xor_a_high",log_path,output_dir)
            try:
                a_attempts,a_wait=wait_for_marker(
                    p,log_path,output_dir,
                    "SUPRACRAFT_XOR_10_PASS",
                    xor_probe(True,False,True,15),
                    "xor_10",timeout_seconds=10.0,
                )
            except SystemExit as exc:
                receipt=diagnose_xor_state(
                    p,log_path,output_dir,"10_timeout"
                )
                checked_command(
                    p,"save-all flush","xor_10_diagnostic_save",
                    log_path,output_dir,
                )
                time.sleep(0.5)
                checked_command(
                    p,"stop","xor_10_diagnostic_stop",
                    log_path,output_dir,
                )
                rc=p.wait(timeout=60)
                zip_world(root/"world",output_dir/"world.zip")
                receipt["original_failure"]=str(exc)
                receipt["server_exit_code"]=rc
                receipt["world_sha256"]=hashlib.sha256(
                    (output_dir/"world.zip").read_bytes()
                ).hexdigest()
                (output_dir/"diagnostic.json").write_text(
                    json.dumps(receipt,indent=2,sort_keys=True)+"\n"
                )
                print(json.dumps(receipt,indent=2,sort_keys=True))
                raise

            checked_command(p,XOR_A_LOW_COMMAND,"xor_a_low_reset",log_path,output_dir)
            try:
                reset_attempts,reset_wait=wait_for_marker(
                    p,log_path,output_dir,
                    "SUPRACRAFT_XOR_00_RESET_PASS",
                    xor_probe(False,False,False,0),
                    "xor_00_reset",timeout_seconds=10.0,
                )
            except SystemExit as exc:
                receipt=diagnose_xor_state(
                    p,log_path,output_dir,"00_reset_timeout"
                )
                checked_command(
                    p,"save-all flush","xor_00_reset_diagnostic_save",
                    log_path,output_dir,
                )
                time.sleep(0.5)
                checked_command(
                    p,"stop","xor_00_reset_diagnostic_stop",
                    log_path,output_dir,
                )
                rc=p.wait(timeout=60)
                zip_world(root/"world",output_dir/"world.zip")
                receipt["original_failure"]=str(exc)
                receipt["server_exit_code"]=rc
                receipt["world_sha256"]=hashlib.sha256(
                    (output_dir/"world.zip").read_bytes()
                ).hexdigest()
                (output_dir/"diagnostic.json").write_text(
                    json.dumps(receipt,indent=2,sort_keys=True)+"\n"
                )
                print(json.dumps(receipt,indent=2,sort_keys=True))
                raise

            checked_command(p,XOR_B_HIGH_COMMAND,"xor_b_high",log_path,output_dir)
            try:
                b_attempts,b_wait=wait_for_marker(
                    p,log_path,output_dir,
                    "SUPRACRAFT_XOR_01_PASS",
                    xor_probe(False,True,True,15),
                    "xor_01",timeout_seconds=10.0,
                )
            except SystemExit as exc:
                receipt=diagnose_xor_state(
                    p,log_path,output_dir,"01_timeout"
                )
                checked_command(
                    p,"save-all flush","xor_01_diagnostic_save",
                    log_path,output_dir,
                )
                time.sleep(0.5)
                checked_command(
                    p,"stop","xor_01_diagnostic_stop",
                    log_path,output_dir,
                )
                rc=p.wait(timeout=60)
                zip_world(root/"world",output_dir/"world.zip")
                receipt["original_failure"]=str(exc)
                receipt["server_exit_code"]=rc
                receipt["world_sha256"]=hashlib.sha256(
                    (output_dir/"world.zip").read_bytes()
                ).hexdigest()
                (output_dir/"diagnostic.json").write_text(
                    json.dumps(receipt,indent=2,sort_keys=True)+"\n"
                )
                print(json.dumps(receipt,indent=2,sort_keys=True))
                raise

            checked_command(p,XOR_A_HIGH_COMMAND,"xor_both_high",log_path,output_dir)
            both_attempts,both_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_XOR_11_PASS",
                xor_probe(True,True,False,0),
                "xor_11",timeout_seconds=10.0,
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
                f"xor-gate template failed rc={rc} diagnostics={len(diagnostics)}"
            )
        result={
            "schema":"supracraft-modern-redstone-template-canary/1",
            "template":"xor_gate",
            "minecraft_version":version,
            "java_major":evidence_java_major(evidence),
            "instrumented":bool(args.java_agent),
            "input_control":"fixture_controller_two_source_single_component_fanout",
            "input_a_position":[0,100,-2],
            "input_b_position":[0,100,2],
            "input_a_high_command_sha256":digest_bytes(XOR_A_HIGH_COMMAND),
            "input_a_low_command_sha256":digest_bytes(XOR_A_LOW_COMMAND),
            "input_b_high_command_sha256":digest_bytes(XOR_B_HIGH_COMMAND),
            "input_b_low_command_sha256":digest_bytes(XOR_B_LOW_COMMAND),
            "input_inverter_positions":[[-2,101,-2],[-2,101,2]],
            "stage_inverter_positions":[[7,103,-3],[4,102,4]],
            "final_inverter_position":[11,104,0],
            "output_wire_position":[12,104,0],
            "output_lamp_position":[13,104,0],
            "branch_wire_positions":[
                [1,100,-2],[2,100,-2],[2,100,-1],[2,100,0],
                [2,100,1],[2,100,2],[1,100,2],[3,100,0],
                [-1,100,-2],[-1,100,2],
                [-3,101,-2],[-4,101,-2],[-4,101,-1],[-4,101,0],
                [-4,101,1],[-4,101,2],[-3,101,2],[-4,101,3],[-4,101,4],
                [-3,101,4],[-2,101,4],[-1,101,4],[0,101,4],
                [1,101,4],[2,101,4],[3,101,4],
                [4,101,0],[5,102,0],[5,102,-1],[5,102,-2],
                [5,102,-3],[6,102,-3],[5,102,4],[6,102,4],
                [8,103,-3],[9,103,-3],[9,103,-2],[9,103,-1],
                [9,103,0],[9,103,1],[9,103,2],[9,103,3],[9,103,4],
                [8,103,4],[7,103,4],[10,103,0],
            ],
            "truth_table_sequence":[
                {"phase":"00","a":False,"b":False,"final_inverter_lit":False,
                 "output_wire_power":0,"verified":True},
                {"phase":"10","a":True,"b":False,"final_inverter_lit":True,
                 "output_wire_power":15,"verified":True},
                {"phase":"00_reset","a":False,"b":False,"final_inverter_lit":False,
                 "output_wire_power":0,"verified":True},
                {"phase":"01","a":False,"b":True,"final_inverter_lit":True,
                 "output_wire_power":15,"verified":True},
                {"phase":"11","a":True,"b":True,"final_inverter_lit":False,
                 "output_wire_power":0,"verified":True},
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
            "output_lamp_semantic_authority":False,
            "boolean_composition":"(A OR B) AND (NOT A OR NOT B)",
            "boundary":"complete XOR truth table qualifies only this generated two-source composed topology; semantic authority is the final inverter plus output dust, while the presentation lamp remains diagnostic only",
        }
        (output_dir/"result.json").write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n"
        )
        print(json.dumps(result,indent=2,sort_keys=True))



def diagnose_rising_edge_state(process,log_path,output_dir,phase):
    """Record exact bounded edge-detector block state without changing topology."""
    checks=[]

    def add(label,value,condition):
        token=(
            f"P{value:02d}" if isinstance(value,int)
            else str(value).replace("-","NEG").replace(".","_").upper()
        )
        marker=f"SUPRACRAFT_EDGE_DIAG_{label.upper()}_{token}"
        checks.append((label,value,marker,condition))

    add("source","air","execute if block 0 100 0 minecraft:air")
    add(
        "source","redstone_block",
        "execute if block 0 100 0 minecraft:redstone_block",
    )

    for label,x,y,z in (
        ("input_main",1,100,0),
        ("input_branch_1",1,100,-1),
        ("input_branch_2",1,100,-2),
        ("direct_support_feed",2,100,-2),
        ("delay_output",3,100,0),
        ("direct_output",4,101,-2),
        ("direct_turn",4,101,-1),
        ("intermediate",4,101,0),
        ("support_feed",5,101,0),
        ("output_wire",7,102,0),
    ):
        for power in range(16):
            add(
                label,power,
                f"execute if block {x} {y} {z} minecraft:redstone_wire[power={power}]",
            )

    for powered in (False,True):
        state="true" if powered else "false"
        add(
            "delay_repeater","powered" if powered else "unpowered",
            f"execute if block 2 100 0 minecraft:repeater[powered={state}]",
        )

    for label,x,y,z in (
        ("direct_inverter",3,101,-2),
        ("final_inverter",6,102,0),
    ):
        for lit in (False,True):
            state="true" if lit else "false"
            add(
                label,"lit" if lit else "unlit",
                f"execute if block {x} {y} {z} minecraft:redstone_torch[lit={state}]",
            )

    for lit in (False,True):
        state="true" if lit else "false"
        add(
            "output_lamp","lit" if lit else "unlit",
            f"execute if block 8 102 0 minecraft:redstone_lamp[lit={state}]",
        )

    for label,value,marker,condition in checks:
        checked_command(
            process,f"{condition} run say {marker}",
            f"rising_edge_diagnostic_{phase}_{label}",
            log_path,output_dir,
        )
    time.sleep(0.75)
    text=log_path.read_text("utf-8",errors="replace")
    observed={}
    for label,value,marker,_ in checks:
        if marker in text:
            observed.setdefault(label,[]).append(value)
    compact={
        label:(values[0] if len(values)==1 else values)
        for label,values in sorted(observed.items())
    }
    receipt={
        "schema":"supracraft-modern-rising-edge-fixture-diagnostic/1",
        "phase":phase,
        "expected_logic":(
            {
                "source":"air",
                "input_net":"unpowered",
                "delay_repeater":"unpowered",
                "direct_inverter":"lit",
                "intermediate":"powered",
                "final_inverter":"unlit",
                "output_wire":"unpowered",
            } if phase=="baseline_timeout" else
            {
                "source":"redstone_block",
                "input_net":"powered",
                "direct_inverter":"unlit",
                "delay_repeater":"transition_pending_or_powered",
                "final_inverter":"lit_during_positive_pulse",
                "output_wire":"powered_during_positive_pulse",
            } if phase=="pulse_1_high_timeout" else {}
        ),
        "observed":compact,
        "nonsemantic_observations":{
            "output_lamp":compact.get("output_lamp"),
        },
        "boundary":"diagnostic receipt records bounded exact block states only; it does not alter the rising-edge temporal contract or topology",
    }
    (output_dir/"diagnostic.json").write_text(
        json.dumps(receipt,indent=2,sort_keys=True)+"\n"
    )
    print("RISING_EDGE_FIXTURE_DIAGNOSTIC")
    print(json.dumps(receipt,indent=2,sort_keys=True))
    return receipt


def edge_probe(source_high,final_lit,output_power):
    source="minecraft:redstone_block" if source_high else "minecraft:air"
    lit="true" if final_lit else "false"
    return (
        f"execute if block 0 100 0 {source} "
        f"if block 6 102 0 minecraft:redstone_torch[lit={lit}] "
        f"if block 7 102 0 minecraft:redstone_wire[power={output_power}]"
    )


def prove_no_edge_pulse(process,log_path,output_dir,duration_seconds=0.9):
    marker="SUPRACRAFT_RISING_EDGE_FALLING_VIOLATION"
    started=time.monotonic()
    attempts=0
    while time.monotonic()-started<duration_seconds:
        checked_command(
            process,
            "execute if block 6 102 0 minecraft:redstone_torch[lit=true] "
            f"run say {marker}",
            "rising_edge_falling_torch_guard",log_path,output_dir,
        )
        checked_command(
            process,
            "execute if block 7 102 0 minecraft:redstone_wire[power=15] "
            f"run say {marker}",
            "rising_edge_falling_wire_guard",log_path,output_dir,
        )
        attempts+=1
        time.sleep(0.05)
        if marker in log_path.read_text("utf-8",errors="replace"):
            raise SystemExit("rising-edge detector emitted a positive pulse on falling edge")
    return attempts,time.monotonic()-started


def run_rising_edge_detector(args,evidence,server_jar,output_dir):
    """Qualify direct input AND NOT(delay-4 input) as a rising-edge detector."""
    version=evidence["minecraft_version"]
    delay=4
    with tempfile.TemporaryDirectory(prefix="modern-redstone-rising-edge-") as td:
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
            checked_command(p,"fill -2 99 -4 8 104 2 minecraft:air","clear",log_path,output_dir)
            checked_command(p,"fill -2 99 -4 8 99 2 minecraft:stone","floor",log_path,output_dir)
            checked_command(p,EDGE_INPUT_LOW_COMMAND,"edge_input_low_setup",log_path,output_dir)

            # One source fans out across one collapsed input net to:
            #   (1) a direct inverter, and
            #   (2) a delay-4 repeater.
            for x,y,z,name in (
                (3,100,-2,"edge_direct_inverter_support"),
                (4,100,-2,"edge_direct_output_support"),
                (4,100,-1,"edge_direct_turn_support"),
                (4,100,0,"edge_delayed_rise_support"),
                (5,100,0,"edge_final_support_feed_support"),
                (6,101,0,"edge_final_inverter_support"),
                (7,101,0,"edge_output_support"),
            ):
                checked_command(
                    p,f"setblock {x} {y} {z} minecraft:stone",
                    name,log_path,output_dir,
                )

            for x,z,name in (
                (1,0,"edge_input_main"),
                (1,-1,"edge_input_branch_1"),
                (1,-2,"edge_input_branch_2"),
                (2,-2,"edge_direct_support_feed"),
            ):
                checked_command(
                    p,f"setblock {x} 100 {z} minecraft:redstone_wire",
                    name,log_path,output_dir,
                )

            checked_command(
                p,
                f"setblock 2 100 0 minecraft:repeater[facing=west,delay={delay},locked=false,powered=false]",
                "edge_delay_repeater",log_path,output_dir,
            )
            checked_command(
                p,"setblock 3 100 0 minecraft:redstone_wire",
                "edge_delay_output",log_path,output_dir,
            )
            checked_command(
                p,"setblock 3 101 -2 minecraft:redstone_torch",
                "edge_direct_inverter",log_path,output_dir,
            )
            for x,z,name in (
                (4,-2,"edge_direct_output"),
                (4,-1,"edge_direct_turn"),
                (4,0,"edge_intermediate_merge"),
                (5,0,"edge_final_support_feed"),
            ):
                checked_command(
                    p,f"setblock {x} 101 {z} minecraft:redstone_wire",
                    name,log_path,output_dir,
                )
            checked_command(
                p,"setblock 6 102 0 minecraft:redstone_torch",
                "edge_final_inverter",log_path,output_dir,
            )
            checked_command(
                p,"setblock 7 102 0 minecraft:redstone_wire",
                "edge_output_wire",log_path,output_dir,
            )
            checked_command(
                p,"setblock 8 102 0 minecraft:redstone_lamp",
                "edge_output_lamp",log_path,output_dir,
            )

            try:
                baseline_attempts,baseline_wait=wait_for_marker(
                    p,log_path,output_dir,
                    "SUPRACRAFT_RISING_EDGE_BASELINE_PASS",
                    edge_probe(False,False,0),
                    "rising_edge_baseline",timeout_seconds=10.0,
                )
            except SystemExit as exc:
                receipt=diagnose_rising_edge_state(
                    p,log_path,output_dir,"baseline_timeout"
                )
                checked_command(
                    p,"save-all flush","rising_edge_baseline_diagnostic_save",
                    log_path,output_dir,
                )
                time.sleep(0.5)
                checked_command(
                    p,"stop","rising_edge_baseline_diagnostic_stop",
                    log_path,output_dir,
                )
                rc=p.wait(timeout=60)
                zip_world(root/"world",output_dir/"world.zip")
                receipt["original_failure"]=str(exc)
                receipt["server_exit_code"]=rc
                receipt["world_sha256"]=hashlib.sha256(
                    (output_dir/"world.zip").read_bytes()
                ).hexdigest()
                (output_dir/"diagnostic.json").write_text(
                    json.dumps(receipt,indent=2,sort_keys=True)+"\n"
                )
                print(json.dumps(receipt,indent=2,sort_keys=True))
                raise
            barrier=setup_barrier(
                p,log_path,output_dir,"SUPRACRAFT_RISING_EDGE_SETUP_READY"
            )
            if args.java_agent:
                gate_path.write_text("capture\n")
                time.sleep(0.15)

            # Rising edge #1: output must pulse high then settle low while the
            # input remains high.
            checked_command(
                p,EDGE_INPUT_HIGH_COMMAND,"rising_edge_input_high_1",
                log_path,output_dir,
            )
            try:
                rise1_attempts,rise1_wait=wait_for_marker(
                    p,log_path,output_dir,
                    "SUPRACRAFT_RISING_EDGE_PULSE_1_HIGH",
                    edge_probe(True,True,15),
                    "rising_edge_pulse_1_high",timeout_seconds=5.0,
                    poll_seconds=0.05,
                )
            except SystemExit as exc:
                receipt=diagnose_rising_edge_state(
                    p,log_path,output_dir,"pulse_1_high_timeout"
                )
                checked_command(
                    p,"save-all flush","rising_edge_pulse_1_diagnostic_save",
                    log_path,output_dir,
                )
                time.sleep(0.5)
                checked_command(
                    p,"stop","rising_edge_pulse_1_diagnostic_stop",
                    log_path,output_dir,
                )
                rc=p.wait(timeout=60)
                zip_world(root/"world",output_dir/"world.zip")
                receipt["original_failure"]=str(exc)
                receipt["server_exit_code"]=rc
                receipt["world_sha256"]=hashlib.sha256(
                    (output_dir/"world.zip").read_bytes()
                ).hexdigest()
                (output_dir/"diagnostic.json").write_text(
                    json.dumps(receipt,indent=2,sort_keys=True)+"\n"
                )
                print(json.dumps(receipt,indent=2,sort_keys=True))
                raise
            settle1_attempts,settle1_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_RISING_EDGE_PULSE_1_LOW",
                edge_probe(True,False,0),
                "rising_edge_pulse_1_low",timeout_seconds=5.0,
                poll_seconds=0.05,
            )

            # Falling edge: detector must remain low throughout delayed reset.
            checked_command(
                p,EDGE_INPUT_LOW_COMMAND,"rising_edge_input_low",
                log_path,output_dir,
            )
            falling_attempts,falling_guard=prove_no_edge_pulse(
                p,log_path,output_dir,0.9
            )
            low_attempts,low_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_RISING_EDGE_LOW_SETTLED",
                edge_probe(False,False,0),
                "rising_edge_low_settled",timeout_seconds=5.0,
                poll_seconds=0.05,
            )

            # Rising edge #2 proves retriggerability after full low settling.
            checked_command(
                p,EDGE_INPUT_HIGH_COMMAND,"rising_edge_input_high_2",
                log_path,output_dir,
            )
            rise2_attempts,rise2_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_RISING_EDGE_PULSE_2_HIGH",
                edge_probe(True,True,15),
                "rising_edge_pulse_2_high",timeout_seconds=5.0,
                poll_seconds=0.05,
            )
            settle2_attempts,settle2_wait=wait_for_marker(
                p,log_path,output_dir,
                "SUPRACRAFT_RISING_EDGE_PULSE_2_LOW",
                edge_probe(True,False,0),
                "rising_edge_pulse_2_low",timeout_seconds=5.0,
                poll_seconds=0.05,
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
                f"rising-edge template failed rc={rc} diagnostics={len(diagnostics)}"
            )

        result={
            "schema":"supracraft-modern-redstone-template-canary/1",
            "template":"rising_edge_detector",
            "minecraft_version":version,
            "java_major":evidence_java_major(evidence),
            "instrumented":bool(args.java_agent),
            "input_control":"fixture_controller_single_source_fanout",
            "configured_delay":delay,
            "input_source_position":[0,100,0],
            "input_net_wire_positions":[
                [1,100,0],[1,100,-1],[1,100,-2],[2,100,-2]
            ],
            "delay_repeater_position":[2,100,0],
            "delay_output_wire_position":[3,100,0],
            "direct_inverter_position":[3,101,-2],
            "intermediate_wire_positions":[
                [4,101,-2],[4,101,-1],[4,101,0],[5,101,0]
            ],
            "final_inverter_position":[6,102,0],
            "output_wire_position":[7,102,0],
            "output_lamp_position":[8,102,0],
            "input_high_command_sha256":digest_bytes(EDGE_INPUT_HIGH_COMMAND),
            "input_low_command_sha256":digest_bytes(EDGE_INPUT_LOW_COMMAND),
            "temporal_sequence":[
                {"phase":"baseline_low","input_high":False,"output_high":False,"verified":True},
                {"phase":"rising_1_pulse","input_high":True,"output_high":True,"verified":True},
                {"phase":"rising_1_settled","input_high":True,"output_high":False,"verified":True},
                {"phase":"falling_edge_guard","input_high":False,"positive_pulse_observed":False,"verified":True},
                {"phase":"low_settled","input_high":False,"output_high":False,"verified":True},
                {"phase":"rising_2_pulse","input_high":True,"output_high":True,"verified":True},
                {"phase":"rising_2_settled","input_high":True,"output_high":False,"verified":True},
            ],
            "ready_seconds":round(ready,6),
            "setup_barrier_seconds":round(barrier,6),
            "baseline_attempts":baseline_attempts,
            "baseline_wait_seconds":round(baseline_wait,6),
            "rising_1_high_attempts":rise1_attempts,
            "rising_1_high_wait_seconds":round(rise1_wait,6),
            "rising_1_low_attempts":settle1_attempts,
            "rising_1_low_wait_seconds":round(settle1_wait,6),
            "falling_guard_attempts":falling_attempts,
            "falling_guard_seconds":round(falling_guard,6),
            "low_settled_attempts":low_attempts,
            "low_settled_wait_seconds":round(low_wait,6),
            "rising_2_high_attempts":rise2_attempts,
            "rising_2_high_wait_seconds":round(rise2_wait,6),
            "rising_2_low_attempts":settle2_attempts,
            "rising_2_low_wait_seconds":round(settle2_wait,6),
            "saved_input_state":"high_settled",
            "elapsed_seconds":round(elapsed,6),
            "trace_present":trace_path.is_file(),
            "world_sha256":hashlib.sha256(
                (output_dir/"world.zip").read_bytes()
            ).hexdigest(),
            "output_lamp_semantic_authority":False,
            "boolean_temporal_composition":"A AND NOT(delay4(A))",
            "boundary":"rising-edge qualification requires a bounded positive pulse only after low-to-high input transitions, no positive pulse on the falling edge, low output while high is settled, and retrigger after low settling; lamp state is diagnostic only",
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
    ap.add_argument("--fixture",choices=("repeater_delay","not_gate","or_gate","nor_gate","and_gate","xor_gate","rising_edge_detector"),required=True)
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
    elif args.fixture=="nor_gate":
        run_nor_gate(args,evidence,args.server_jar,args.output_dir)
    elif args.fixture=="and_gate":
        run_and_gate(args,evidence,args.server_jar,args.output_dir)
    elif args.fixture=="xor_gate":
        run_xor_gate(args,evidence,args.server_jar,args.output_dir)
    else:
        run_rising_edge_detector(args,evidence,args.server_jar,args.output_dir)


if __name__=="__main__":
    main()
