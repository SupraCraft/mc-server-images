#!/usr/bin/env python3
"""Validate exact-version stock/instrumented RS-latch runtime behavior."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def load(path:Path):
    return json.loads(path.read_text())


def position(row):
    return [
        row.get("data",{}).get("x"),
        row.get("data",{}).get("y"),
        row.get("data",{}).get("z"),
    ]


def trace_contract(rows):
    assert rows
    assert [r["seq"] for r in rows]==list(range(1,len(rows)+1))
    assert rows[0]["event_type"]=="trace_start"
    assert rows[-1]["event_type"]=="trace_end"
    assert rows[-1]["data"]["dropped_events"]==0
    return collections.Counter(r["event_type"] for r in rows)


def dispatches(rows,sha):
    return [
        r for r in rows
        if r["event_type"]=="command_dispatch"
        and r.get("data",{}).get("command_sha256")==sha
    ]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--stock",type=Path,required=True)
    ap.add_argument("--instrumented",type=Path,required=True)
    ap.add_argument("--trace",type=Path,required=True)
    ap.add_argument("--version",required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    stock=load(args.stock)
    inst=load(args.instrumented)
    assert stock["template"]==inst["template"]=="rs_latch"
    assert stock["minecraft_version"]==inst["minecraft_version"]==args.version
    for key in (
        "java_major","input_control",
        "reset_source_position","reset_input_wire_position",
        "set_source_position","set_input_wire_position",
        "inverter_a_position","inverter_b_position",
        "q_wire_position","qbar_wire_position",
        "q_lamp_position","qbar_lamp_position",
        "feedback_a_wire_positions","feedback_b_wire_positions",
        "reset_high_command_sha256","reset_low_command_sha256",
        "set_high_command_sha256","set_low_command_sha256",
        "state_sequence","retention_contract_pass",
        "invalid_boundary_observed","saved_state",
    ):
        assert stock[key]==inst[key],(key,stock[key],inst[key])
    assert stock["instrumented"] is False
    assert inst["instrumented"] is True
    assert inst["trace_present"] is True
    assert stock["retention_contract_pass"] is True
    assert inst["retention_contract_pass"] is True
    assert stock["invalid_boundary_observed"] is True
    assert inst["invalid_boundary_observed"] is True

    expected=[
        ("reset_asserted",0,15,"R"),
        ("reset_hold_1",0,15,"none"),
        ("reset_hold_2",0,15,"none"),
        ("set_asserted",15,0,"S"),
        ("set_hold_1",15,0,"none"),
        ("set_hold_2",15,0,"none"),
        ("reset2_asserted",0,15,"R"),
        ("reset2_hold",0,15,"none"),
        ("invalid_asserted",0,0,"S+R"),
        ("final_reset_hold",0,15,"none"),
    ]
    observed=[
        (r["phase"],r["q"],r["qbar"],r["stimulus"])
        for r in inst["state_sequence"]
    ]
    assert observed==expected,observed

    # The invalid-state release is deliberately not a semantic equality gate.
    # It must merely be observed and bounded; either stable latch state is
    # acceptable because the post-invalid resolution is not a qualified
    # contract.
    for row in (stock["post_invalid_resolution"],inst["post_invalid_resolution"]):
        assert row["observed"] is True
        assert (row["q_wire_power"],row["qbar_wire_power"]) in {
            (0,0),(15,0),(0,15),(15,15)
        }

    rows=[
        json.loads(x)
        for x in args.trace.read_text().splitlines()
        if x.strip()
    ]
    counts=trace_contract(rows)
    for required in (
        "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
        "redstone_power_query","redstone_power_result",
        "block_state_write","command_dispatch",
    ):
        assert counts[required]>0,(required,counts)

    hashes={
        "r_high":inst["reset_high_command_sha256"],
        "r_low":inst["reset_low_command_sha256"],
        "s_high":inst["set_high_command_sha256"],
        "s_low":inst["set_low_command_sha256"],
    }
    ds={name:dispatches(rows,sha) for name,sha in hashes.items()}
    assert len(ds["r_high"])>=4,len(ds["r_high"])
    assert len(ds["r_low"])>=4,len(ds["r_low"])
    assert len(ds["s_high"])>=2,len(ds["s_high"])
    assert len(ds["s_low"])>=2,len(ds["s_low"])

    source_writes={
        "reset":[
            r["seq"] for r in rows
            if r["event_type"]=="block_state_write"
            and position(r)==inst["reset_source_position"]
        ],
        "set":[
            r["seq"] for r in rows
            if r["event_type"]=="block_state_write"
            and position(r)==inst["set_source_position"]
        ],
    }
    assert len(source_writes["reset"])>=8,source_writes["reset"]
    assert len(source_writes["set"])>=4,source_writes["set"]

    a_positions={tuple(p) for p in inst["feedback_a_wire_positions"]}
    b_positions={tuple(p) for p in inst["feedback_b_wire_positions"]}
    wire_events=[
        r for r in rows
        if r["event_type"] in {
            "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
            "redstone_power_query","redstone_power_result","block_state_write",
        }
        and tuple(position(r)) in (a_positions|b_positions)
    ]
    assert wire_events
    assert any(tuple(position(r)) in a_positions for r in wire_events)
    assert any(tuple(position(r)) in b_positions for r in wire_events)

    inverter_writes={
        "a":[
            r["seq"] for r in rows
            if r["event_type"]=="block_state_write"
            and position(r)==inst["inverter_a_position"]
        ],
        "b":[
            r["seq"] for r in rows
            if r["event_type"]=="block_state_write"
            and position(r)==inst["inverter_b_position"]
        ],
    }
    assert inverter_writes["a"],inverter_writes
    assert inverter_writes["b"],inverter_writes

    report={
        "schema":"supracraft-rs-latch-runtime-qualification/1",
        "minecraft_version":args.version,
        "template":"rs_latch",
        "semantic_divergence":False,
        "retention_contract_pass":True,
        "state_sequence":inst["state_sequence"],
        "invalid_boundary":{
            "asserted_state":{"q":0,"qbar":0},
            "stock_post_release":stock["post_invalid_resolution"],
            "instrumented_post_release":inst["post_invalid_resolution"],
            "post_release_is_not_qualified_semantic_contract":True,
        },
        "dispatch_counts":{k:len(v) for k,v in ds.items()},
        "source_write_counts":{k:len(v) for k,v in source_writes.items()},
        "inverter_write_counts":{k:len(v) for k,v in inverter_writes.items()},
        "feedback_wire_event_count":len(wire_events),
        "event_counts":dict(sorted(counts.items())),
        "dropped_events":0,
        "stock_elapsed_seconds":stock["elapsed_seconds"],
        "instrumented_elapsed_seconds":inst["elapsed_seconds"],
        "boundary":"valid set/reset/hold states are observer-effect equality gates; post-invalid release resolution is recorded but intentionally not normalized into a stable latch contract",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
