#!/usr/bin/env python3
"""Run an exact modern cross-coupled RS-NOR latch fixture."""

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
    checked_command,
    digest_bytes,
    wait_for_log_marker,
    wait_for_marker,
)

R_HIGH="setblock -2 100 0 minecraft:redstone_block"
R_LOW="setblock -2 100 0 minecraft:air"
S_HIGH="setblock 6 100 2 minecraft:redstone_block"
S_LOW="setblock 6 100 2 minecraft:air"


def evidence_java_major(evidence:dict)->int:
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


def common_setup(root:Path,version:str):
    (root/"eula.txt").write_text("eula=true\n")
    props={
        "online-mode":"false",
        "server-port":"25581",
        "view-distance":"3",
        "simulation-distance":"3",
        "spawn-protection":"0",
        "max-players":"1",
        "enable-command-block":"true",
        "allow-flight":"true",
        "gamemode":"creative",
        "difficulty":"peaceful",
        "level-name":"world",
        "level-seed":"263266",
        "motd":f"SupraCraft RS latch template {version}",
    }
    (root/"server.properties").write_text(
        "\n".join(f"{k}={v}" for k,v in props.items())+"\n"
    )


def setup_barrier(p,log_path,output_dir,marker):
    checked_command(p,f"say {marker}","setup_barrier",log_path,output_dir)
    return wait_for_log_marker(
        p,log_path,output_dir,marker,"setup_barrier",timeout_seconds=5.0
    )


def state_probe(q:int,q_lit:bool,qb:int,qb_lit:bool)->str:
    qlit="true" if q_lit else "false"
    qblit="true" if qb_lit else "false"
    qlamp="true" if q>0 else "false"
    qblamp="true" if qb>0 else "false"
    return (
        f"execute if block 1 100 0 minecraft:redstone_wall_torch[facing=east,lit={qlit}] "
        f"if block 2 100 0 minecraft:redstone_wire[power={q}] "
        f"if block 3 100 2 minecraft:redstone_wall_torch[facing=west,lit={qblit}] "
        f"if block 2 100 2 minecraft:redstone_wire[power={qb}] "
        f"if block 3 100 -1 minecraft:redstone_lamp[lit={qlamp}] "
        f"if block 1 100 3 minecraft:redstone_lamp[lit={qblamp}]"
    )


def wait_state(p,log_path,output_dir,phase,q,q_lit,qb,qb_lit):
    return wait_for_marker(
        p,log_path,output_dir,
        f"SUPRACRAFT_RS_{phase}_PASS",
        state_probe(q,q_lit,qb,qb_lit),
        f"rs_{phase.lower()}",
        timeout_seconds=8.0,
    )


def diagnose_reset_failure(p,log_path,output_dir):
    """Measure the failed forced-reset state without changing fixture semantics."""
    prefix=f"SUPRACRAFT_RS_DIAG_{time.time_ns()}"
    probes=[]

    def add_bool(name,command_true,command_false):
        probes.append((name,True,command_true,f"{prefix}_{name}_TRUE"))
        probes.append((name,False,command_false,f"{prefix}_{name}_FALSE"))

    add_bool(
        "reset_source_present",
        "execute if block -2 100 0 minecraft:redstone_block",
        "execute if block -2 100 0 minecraft:air",
    )
    add_bool(
        "set_source_present",
        "execute if block 6 100 2 minecraft:redstone_block",
        "execute if block 6 100 2 minecraft:air",
    )
    add_bool(
        "inverter_a_lit",
        "execute if block 1 100 0 minecraft:redstone_wall_torch[facing=east,lit=true]",
        "execute if block 1 100 0 minecraft:redstone_wall_torch[facing=east,lit=false]",
    )
    add_bool(
        "inverter_b_lit",
        "execute if block 3 100 2 minecraft:redstone_wall_torch[facing=west,lit=true]",
        "execute if block 3 100 2 minecraft:redstone_wall_torch[facing=west,lit=false]",
    )
    add_bool(
        "q_lamp_lit",
        "execute if block 3 100 -1 minecraft:redstone_lamp[lit=true]",
        "execute if block 3 100 -1 minecraft:redstone_lamp[lit=false]",
    )
    add_bool(
        "qbar_lamp_lit",
        "execute if block 1 100 3 minecraft:redstone_lamp[lit=true]",
        "execute if block 1 100 3 minecraft:redstone_lamp[lit=false]",
    )

    power_points={
        "reset_input_wire_power":(-1,100,0),
        "set_input_wire_power":(5,100,2),
        "q_wire_power":(2,100,0),
        "qbar_wire_power":(2,100,2),
        "feedback_a_endpoint_power":(4,100,1),
        "feedback_b_endpoint_power":(0,100,1),
    }
    power_markers={}
    for name,(x,y,z) in power_points.items():
        power_markers[name]=[]
        for value in range(16):
            marker=f"{prefix}_{name}_P{value:02d}"
            power_markers[name].append((value,marker))
            checked_command(
                p,
                f"execute if block {x} {y} {z} "
                f"minecraft:redstone_wire[power={value}] run say {marker}",
                "rs_reset_diagnostic",log_path,output_dir,
            )

    for _,_,probe,marker in probes:
        checked_command(
            p,f"{probe} run say {marker}",
            "rs_reset_diagnostic",log_path,output_dir,
        )
    end_marker=f"{prefix}_END"
    checked_command(
        p,f"say {end_marker}",
        "rs_reset_diagnostic",log_path,output_dir,
    )
    wait_for_log_marker(
        p,log_path,output_dir,end_marker,
        "rs_reset_diagnostic",timeout_seconds=5.0,
    )
    text=log_path.read_text("utf-8",errors="replace")

    values={}
    for name in (
        "reset_source_present","set_source_present",
        "inverter_a_lit","inverter_b_lit",
        "q_lamp_lit","qbar_lamp_lit",
    ):
        t=f"{prefix}_{name}_TRUE" in text
        f_=f"{prefix}_{name}_FALSE" in text
        values[name]=True if t and not f_ else False if f_ and not t else None

    for name,rows in power_markers.items():
        matched=[value for value,marker in rows if marker in text]
        values[name]=matched[0] if len(matched)==1 else None
        values[name+"_matched_values"]=matched

    return {
        "schema":"supracraft-rs-latch-reset-diagnostic/1",
        "stage":"rs_reset_asserted",
        "observed":values,
        "positions":{
            "reset_source":[-2,100,0],
            "reset_input_wire":[-1,100,0],
            "set_source":[6,100,2],
            "set_input_wire":[5,100,2],
            "inverter_a":[1,100,0],
            "inverter_b":[3,100,2],
            "q_wire":[2,100,0],
            "qbar_wire":[2,100,2],
            "feedback_a_endpoint":[4,100,1],
            "feedback_b_endpoint":[0,100,1],
            "q_lamp":[3,100,-1],
            "qbar_lamp":[1,100,3],
        },
        "expected_reset":{
            "reset_source_present":True,
            "reset_input_wire_power":15,
            "set_source_present":False,
            "set_input_wire_power":0,
            "inverter_a_lit":False,
            "inverter_b_lit":True,
            "q_wire_power":0,
            "qbar_wire_power":15,
            "q_lamp_lit":False,
            "qbar_lamp_lit":True,
        },
        "boundary":"diagnostic-only exact block-state receipt; no latch semantic promotion and no raw authored commands retained",
    }


def observe_post_invalid(p,log_path,output_dir):
    prefix=f"SUPRACRAFT_RS_INVALID_RESOLVE_{time.time_ns()}"
    combos=[
        (0,False,0,False),
        (15,True,0,False),
        (0,False,15,True),
        (15,True,15,True),
    ]
    for q,ql,qb,qbl in combos:
        marker=f"{prefix}_Q{q:02d}_QB{qb:02d}"
        checked_command(
            p,f"{state_probe(q,ql,qb,qbl)} run say {marker}",
            "rs_invalid_resolution_probe",log_path,output_dir,
        )
    started=time.monotonic()
    deadline=started+4.0
    while time.monotonic()<deadline:
        text=log_path.read_text("utf-8",errors="replace")
        for q,_,qb,_ in combos:
            marker=f"{prefix}_Q{q:02d}_QB{qb:02d}"
            if marker in text:
                return {
                    "q_wire_power":q,
                    "qbar_wire_power":qb,
                    "observed":True,
                    "wait_seconds":round(time.monotonic()-started,6),
                }
        time.sleep(0.05)
    raise SystemExit("RS latch post-invalid resolution was not one of bounded output states")


def main():
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
            raise SystemExit("server jar required for discovery receipt")
        download_server(evidence,args.server_jar)

    with tempfile.TemporaryDirectory(prefix="modern-redstone-rs-latch-") as td:
        root=Path(td)
        server=root/"server.jar"
        shutil.copy2(args.server_jar,server)
        common_setup(root,version)
        log_path=root/"server.log"
        trace_path=args.output_dir/"trace.jsonl"
        gate_path=root/"capture.gate"
        started=time.monotonic()

        waits={}
        with log_path.open("w",encoding="utf-8") as log:
            p=subprocess.Popen(
                launch_command(args,server,trace_path,gate_path),
                cwd=root,stdin=subprocess.PIPE,stdout=log,
                stderr=subprocess.STDOUT,text=True,
            )
            ready=wait_ready(p,log_path,180)
            checked_command(
                p,"forceload add -16 -16 16 16","forceload",
                log_path,args.output_dir,
            )
            time.sleep(1)
            checked_command(
                p,"fill -3 99 -3 7 103 5 minecraft:air","clear",
                log_path,args.output_dir,
            )
            checked_command(
                p,"fill -3 99 -3 7 99 5 minecraft:stone","floor",
                log_path,args.output_dir,
            )

            # Two wall-torch inverters with direct dust-net cross coupling.
            checked_command(p,"setblock 0 100 0 minecraft:stone","a_support",log_path,args.output_dir)
            checked_command(p,"setblock 4 100 2 minecraft:stone","b_support",log_path,args.output_dir)
            checked_command(
                p,"setblock 1 100 0 minecraft:redstone_wall_torch[facing=east]",
                "a_torch",log_path,args.output_dir,
            )
            checked_command(
                p,"setblock 3 100 2 minecraft:redstone_wall_torch[facing=west]",
                "b_torch",log_path,args.output_dir,
            )
            for x,z in ((2,0),(3,0),(4,0),(4,1),(2,2),(1,2),(0,2),(0,1)):
                checked_command(
                    p,f"setblock {x} 100 {z} minecraft:redstone_wire",
                    f"wire_{x}_{z}",log_path,args.output_dir,
                )
            checked_command(
                p,"setblock 3 100 -1 minecraft:redstone_lamp",
                "q_lamp",log_path,args.output_dir,
            )
            checked_command(
                p,"setblock 1 100 3 minecraft:redstone_lamp",
                "qbar_lamp",log_path,args.output_dir,
            )
            checked_command(p,R_LOW,"r_low_setup",log_path,args.output_dir)
            checked_command(p,S_LOW,"s_low_setup",log_path,args.output_dir)
            checked_command(
                p,"setblock -1 100 0 minecraft:redstone_wire",
                "reset_input_wire",log_path,args.output_dir,
            )
            checked_command(
                p,"setblock 5 100 2 minecraft:redstone_wire",
                "set_input_wire",log_path,args.output_dir,
            )

            barrier=setup_barrier(
                p,log_path,args.output_dir,"SUPRACRAFT_RS_SETUP_READY"
            )
            if args.java_agent:
                gate_path.write_text("capture\n")
                time.sleep(0.15)

            # Force reset then prove state retention after R stimulus removal.
            checked_command(p,R_HIGH,"r_assert_1",log_path,args.output_dir)
            try:
                waits["reset_asserted"]=wait_state(
                    p,log_path,args.output_dir,"RESET_ASSERTED",0,False,15,True
                )
            except SystemExit as exc:
                diagnostic=diagnose_reset_failure(
                    p,log_path,args.output_dir
                )
                checked_command(
                    p,"save-all flush","rs_reset_diagnostic_save",
                    log_path,args.output_dir,
                )
                time.sleep(1)
                checked_command(
                    p,"stop","rs_reset_diagnostic_stop",
                    log_path,args.output_dir,
                )
                diagnostic["server_exit_code"]=p.wait(timeout=60)
                zip_world(root/"world",args.output_dir/"world.zip")
                diagnostic["world_sha256"]=hashlib.sha256(
                    (args.output_dir/"world.zip").read_bytes()
                ).hexdigest()
                diagnostic["original_failure"]=str(exc)
                (args.output_dir/"diagnostic.json").write_text(
                    json.dumps(diagnostic,indent=2,sort_keys=True)+"\n"
                )
                print("RS_LATCH_RESET_DIAGNOSTIC")
                print(json.dumps(diagnostic,indent=2,sort_keys=True))
                raise SystemExit(
                    "RS latch forced-reset state failed; "
                    "bounded diagnostic receipt written"
                )
            checked_command(p,R_LOW,"r_release_1",log_path,args.output_dir)
            waits["reset_hold_1"]=wait_state(
                p,log_path,args.output_dir,"RESET_HOLD_1",0,False,15,True
            )
            time.sleep(0.75)
            waits["reset_hold_2"]=wait_state(
                p,log_path,args.output_dir,"RESET_HOLD_2",0,False,15,True
            )

            # Set, remove S, and prove retained Q state twice.
            checked_command(p,S_HIGH,"s_assert",log_path,args.output_dir)
            waits["set_asserted"]=wait_state(
                p,log_path,args.output_dir,"SET_ASSERTED",15,True,0,False
            )
            checked_command(p,S_LOW,"s_release",log_path,args.output_dir)
            waits["set_hold_1"]=wait_state(
                p,log_path,args.output_dir,"SET_HOLD_1",15,True,0,False
            )
            time.sleep(0.75)
            waits["set_hold_2"]=wait_state(
                p,log_path,args.output_dir,"SET_HOLD_2",15,True,0,False
            )

            # Reset again and prove retained reset state.
            checked_command(p,R_HIGH,"r_assert_2",log_path,args.output_dir)
            waits["reset2_asserted"]=wait_state(
                p,log_path,args.output_dir,"RESET2_ASSERTED",0,False,15,True
            )
            checked_command(p,R_LOW,"r_release_2",log_path,args.output_dir)
            waits["reset2_hold"]=wait_state(
                p,log_path,args.output_dir,"RESET2_HOLD",0,False,15,True
            )

            # Invalid RS-NOR condition: both inputs asserted. Measure rather
            # than normalize the post-release resolution.
            checked_command(p,S_HIGH,"invalid_s_assert",log_path,args.output_dir)
            checked_command(p,R_HIGH,"invalid_r_assert",log_path,args.output_dir)
            waits["invalid_asserted"]=wait_state(
                p,log_path,args.output_dir,"INVALID_ASSERTED",0,False,0,False
            )
            checked_command(p,S_LOW,"invalid_s_release",log_path,args.output_dir)
            checked_command(p,R_LOW,"invalid_r_release",log_path,args.output_dir)
            post_invalid=observe_post_invalid(
                p,log_path,args.output_dir
            )

            # Return to a known valid quiescent reset state for static recovery.
            checked_command(p,R_HIGH,"final_r_assert",log_path,args.output_dir)
            waits["final_reset_asserted"]=wait_state(
                p,log_path,args.output_dir,"FINAL_RESET_ASSERTED",0,False,15,True
            )
            checked_command(p,R_LOW,"final_r_release",log_path,args.output_dir)
            waits["final_reset_hold"]=wait_state(
                p,log_path,args.output_dir,"FINAL_RESET_HOLD",0,False,15,True
            )

            checked_command(p,"save-all flush","save",log_path,args.output_dir)
            time.sleep(1)
            checked_command(p,"stop","stop",log_path,args.output_dir)
            rc=p.wait(timeout=60)

        elapsed=time.monotonic()-started
        zip_world(root/"world",args.output_dir/"world.zip")
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
                f"RS latch template failed rc={rc} diagnostics={len(diagnostics)}"
            )

        result={
            "schema":"supracraft-modern-redstone-template-canary/1",
            "template":"rs_latch",
            "minecraft_version":version,
            "java_major":evidence_java_major(evidence),
            "instrumented":bool(args.java_agent),
            "input_control":"fixture_controller_set_reset_source_injection",
            "reset_source_position":[-2,100,0],
            "reset_input_wire_position":[-1,100,0],
            "set_source_position":[6,100,2],
            "set_input_wire_position":[5,100,2],
            "inverter_a_position":[1,100,0],
            "inverter_b_position":[3,100,2],
            "q_wire_position":[2,100,0],
            "qbar_wire_position":[2,100,2],
            "q_lamp_position":[3,100,-1],
            "qbar_lamp_position":[1,100,3],
            "feedback_a_wire_positions":[[2,100,0],[3,100,0],[4,100,0],[4,100,1]],
            "feedback_b_wire_positions":[[2,100,2],[1,100,2],[0,100,2],[0,100,1]],
            "reset_high_command_sha256":digest_bytes(R_HIGH),
            "reset_low_command_sha256":digest_bytes(R_LOW),
            "set_high_command_sha256":digest_bytes(S_HIGH),
            "set_low_command_sha256":digest_bytes(S_LOW),
            "state_sequence":[
                {"phase":"reset_asserted","q":0,"qbar":15,"stimulus":"R"},
                {"phase":"reset_hold_1","q":0,"qbar":15,"stimulus":"none"},
                {"phase":"reset_hold_2","q":0,"qbar":15,"stimulus":"none"},
                {"phase":"set_asserted","q":15,"qbar":0,"stimulus":"S"},
                {"phase":"set_hold_1","q":15,"qbar":0,"stimulus":"none"},
                {"phase":"set_hold_2","q":15,"qbar":0,"stimulus":"none"},
                {"phase":"reset2_asserted","q":0,"qbar":15,"stimulus":"R"},
                {"phase":"reset2_hold","q":0,"qbar":15,"stimulus":"none"},
                {"phase":"invalid_asserted","q":0,"qbar":0,"stimulus":"S+R"},
                {"phase":"final_reset_hold","q":0,"qbar":15,"stimulus":"none"},
            ],
            "post_invalid_resolution":post_invalid,
            "retention_contract_pass":True,
            "invalid_boundary_observed":True,
            "saved_state":"reset_hold",
            "ready_seconds":round(ready,6),
            "setup_barrier_seconds":round(barrier,6),
            "phase_waits":{
                k:{"attempts":v[0],"seconds":round(v[1],6)}
                for k,v in waits.items()
            },
            "elapsed_seconds":round(elapsed,6),
            "trace_present":trace_path.is_file(),
            "world_sha256":hashlib.sha256(
                (args.output_dir/"world.zip").read_bytes()
            ).hexdigest(),
            "boundary":"cross-coupled inverter topology plus explicit source-to-input-dust-to-support coupling and set/reset/hold persistence qualify only this generated RS latch; post-invalid resolution is observed but not treated as a stable contract",
        }
        (args.output_dir/"result.json").write_text(
            json.dumps(result,indent=2,sort_keys=True)+"\n"
        )
        print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
