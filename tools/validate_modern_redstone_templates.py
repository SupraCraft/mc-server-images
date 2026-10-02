#!/usr/bin/env python3
"""Validate exact modern redstone standard-template runtime evidence."""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def load_result(root:Path,name:str,arm:str):
    return json.loads((root/f"{name}-{arm}"/"result.json").read_text())


def load_trace(root:Path,name:str):
    return [
        json.loads(x)
        for x in (root/f"{name}-instrumented"/"trace.jsonl").read_text().splitlines()
        if x.strip()
    ]


def position(row):
    d=row.get("data") or {}
    return [d.get("x"),d.get("y"),d.get("z")]


def trace_contract(rows):
    assert rows
    assert [r["seq"] for r in rows]==list(range(1,len(rows)+1))
    assert rows[0]["event_type"]=="trace_start"
    assert rows[-1]["event_type"]=="trace_end"
    assert rows[-1]["data"]["dropped_events"]==0
    counts=collections.Counter(r["event_type"] for r in rows)
    return counts


def dispatch_after(rows,sha,min_seq=0):
    found=[
        r for r in rows
        if r["seq"]>min_seq
        and r["event_type"]=="command_dispatch"
        and r["data"].get("command_sha256")==sha
    ]
    assert found,("dispatch",sha,min_seq)
    return found[0]


def validate_repeater(root:Path,name:str):
    stock=load_result(root,name,"stock")
    inst=load_result(root,name,"instrumented")
    for k in (
        "template","minecraft_version","java_major","configured_delay",
        "source_position","input_wire_position","repeater_position",
        "output_wire_position","command_block_position","target_position",
        "source_command_sha256","command_sha256","actual_actuation",
    ):
        assert stock[k]==inst[k],(name,k,stock[k],inst[k])
    assert stock["instrumented"] is False
    assert inst["instrumented"] is True
    assert stock["actual_actuation"] is True
    assert inst["actual_actuation"] is True
    assert inst["trace_present"] is True

    rows=load_trace(root,name)
    counts=trace_contract(rows)
    for required in (
        "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
        "redstone_power_query","redstone_power_result",
        "command_trigger_start","command_trigger_end","command_dispatch",
    ):
        assert counts[required]>0,(name,required,counts)

    source_dispatch=dispatch_after(rows,inst["source_command_sha256"])
    source_writes=[
        r for r in rows
        if r["seq"]>source_dispatch["seq"]
        and r["event_type"]=="block_state_write"
        and position(r)==inst["source_position"]
    ]
    assert source_writes
    source=source_writes[0]

    triggers=[
        r for r in rows
        if r["seq"]>source["seq"]
        and r["event_type"]=="command_trigger_start"
        and r["data"].get("command_sha256")==inst["command_sha256"]
        and position(r)==inst["command_block_position"]
    ]
    assert triggers
    trigger=triggers[0]
    tick_delta=trigger["tick"]-source["tick"]
    assert tick_delta>0,(name,source["tick"],trigger["tick"])

    wire_positions={tuple(inst["input_wire_position"]),tuple(inst["output_wire_position"])}
    wire_events=[
        r for r in rows
        if source["seq"]<r["seq"]<trigger["seq"]
        and r["event_type"] in {
            "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
            "redstone_power_query","redstone_power_result",
        }
        and tuple(position(r)) in wire_positions
    ]
    assert wire_events,(name,"wire events before trigger")
    observed_positions={tuple(position(r)) for r in wire_events}
    assert tuple(inst["input_wire_position"]) in observed_positions
    assert tuple(inst["output_wire_position"]) in observed_positions

    return {
        "configured_delay":inst["configured_delay"],
        "source_dispatch_seq":source_dispatch["seq"],
        "source_write_seq":source["seq"],
        "source_tick":source["tick"],
        "command_trigger_seq":trigger["seq"],
        "command_trigger_tick":trigger["tick"],
        "server_tick_delta":tick_delta,
        "wire_event_count_before_trigger":len(wire_events),
        "event_counts":dict(sorted(counts.items())),
        "dropped_events":0,
        "semantic_divergence":False,
        "stock_elapsed_seconds":stock["elapsed_seconds"],
        "instrumented_elapsed_seconds":inst["elapsed_seconds"],
    }


def validate_not(root:Path):
    name="not-gate"
    stock=load_result(root,name,"stock")
    inst=load_result(root,name,"instrumented")
    for k in (
        "template","minecraft_version","java_major",
        "input_component_position","input_wire_position","input_control",
        "support_position","inverter_position","output_wire_position","output_lamp_position",
        "input_high_command_sha256","input_low_command_sha256",
        "truth_table_sequence",
    ):
        assert stock[k]==inst[k],(k,stock[k],inst[k])
    assert stock["instrumented"] is False
    assert inst["instrumented"] is True
    assert inst["trace_present"] is True

    expected=[
        (False,0,True,15),
        (True,15,False,0),
        (False,0,True,15),
    ]
    observed=[
        (
            row["input_powered"],
            row["input_wire_power"],
            row["torch_lit"],
            row["output_wire_power"],
        )
        for row in inst["truth_table_sequence"]
    ]
    assert observed==expected,observed
    assert all(row["verified"] is True for row in inst["truth_table_sequence"])

    rows=load_trace(root,name)
    counts=trace_contract(rows)
    for required in (
        "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
        "redstone_power_query","redstone_power_result","command_dispatch",
    ):
        assert counts[required]>0,(required,counts)

    high=dispatch_after(rows,inst["input_high_command_sha256"])
    low=dispatch_after(rows,inst["input_low_command_sha256"],high["seq"])
    assert high["seq"]<low["seq"]

    in_pos=inst["input_wire_position"]
    out_pos=inst["output_wire_position"]
    between_phase=[
        r for r in rows
        if high["seq"]<r["seq"]<low["seq"]
        and r["event_type"] in {
            "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
            "redstone_power_query","redstone_power_result",
        }
    ]
    after_phase=[
        r for r in rows
        if r["seq"]>low["seq"]
        and r["event_type"] in {
            "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
            "redstone_power_query","redstone_power_result",
        }
    ]
    between_input=[r for r in between_phase if position(r)==in_pos]
    between_output=[r for r in between_phase if position(r)==out_pos]
    after_input=[r for r in after_phase if position(r)==in_pos]
    after_output=[r for r in after_phase if position(r)==out_pos]
    assert between_input,("high input dust recomputation",counts)
    assert between_output,("high->low output recomputation",counts)
    assert after_input,("reset input dust recomputation",counts)
    assert after_output,("low->high output recomputation",counts)

    return {
        "truth_table_sequence":inst["truth_table_sequence"],
        "input_high_dispatch_seq":high["seq"],
        "input_low_reset_dispatch_seq":low["seq"],
        "wire_events_high_to_low":len(between_phase),
        "wire_events_low_to_high":len(after_phase),
        "input_wire_events_high":len(between_input),
        "output_wire_events_high":len(between_output),
        "input_wire_events_reset":len(after_input),
        "output_wire_events_reset":len(after_output),
        "event_counts":dict(sorted(counts.items())),
        "dropped_events":0,
        "semantic_divergence":False,
        "stock_elapsed_seconds":stock["elapsed_seconds"],
        "instrumented_elapsed_seconds":inst["elapsed_seconds"],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--version",required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    d1=validate_repeater(args.root,"repeater-d1")
    d4=validate_repeater(args.root,"repeater-d4")
    assert d1["configured_delay"]==1
    assert d4["configured_delay"]==4
    assert d4["server_tick_delta"]>d1["server_tick_delta"],(
        d1["server_tick_delta"],d4["server_tick_delta"]
    )
    inv=validate_not(args.root)

    report={
        "schema":"supracraft-redstone-template-runtime-qualification/1",
        "minecraft_version":args.version,
        "sensor_pack":"core+redstone",
        "repeater_delay_line":{
            "delay_1":d1,
            "delay_4":d4,
            "ordering_contract":"delay_4_server_tick_delta_gt_delay_1_server_tick_delta",
            "ordering_pass":True,
        },
        "not_gate":{
            **inv,
            "truth_table_contract":"low->high, high->low, reset low->high",
            "truth_table_pass":True,
        },
        "boundary":"runtime qualification applies to these exact generated fixtures and versions; template generalization remains separately gated by static netlist matching",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
