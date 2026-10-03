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


def validate_or(root:Path):
    name="or-gate"
    stock=load_result(root,name,"stock")
    inst=load_result(root,name,"instrumented")
    for k in (
        "template","minecraft_version","java_major","input_control",
        "input_a_position","input_b_position",
        "input_a_wire_position","input_b_wire_position",
        "junction_wire_position","output_wire_position","output_lamp_position",
        "input_a_high_command_sha256","input_a_low_command_sha256",
        "input_b_high_command_sha256","input_b_low_command_sha256",
        "truth_table_sequence",
    ):
        assert stock[k]==inst[k],(k,stock[k],inst[k])
    assert stock["instrumented"] is False
    assert inst["instrumented"] is True
    assert inst["trace_present"] is True

    expected=[
        (False,False,0,False),
        (True,False,12,True),
        (False,False,0,False),
        (False,True,12,True),
        (True,True,12,True),
    ]
    observed=[
        (row["a"],row["b"],row["output_wire_power"],row["output_lamp_lit"])
        for row in inst["truth_table_sequence"]
    ]
    assert observed==expected,observed
    assert all(row["verified"] is True for row in inst["truth_table_sequence"])

    rows=load_trace(root,name)
    counts=trace_contract(rows)
    for required in (
        "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
        "redstone_power_query","redstone_power_result","command_dispatch",
        "block_state_write",
    ):
        assert counts[required]>0,(required,counts)

    a1=dispatch_after(rows,inst["input_a_high_command_sha256"])
    a0=dispatch_after(rows,inst["input_a_low_command_sha256"],a1["seq"])
    b1=dispatch_after(rows,inst["input_b_high_command_sha256"],a0["seq"])
    a2=dispatch_after(rows,inst["input_a_high_command_sha256"],b1["seq"])
    assert a1["seq"]<a0["seq"]<b1["seq"]<a2["seq"]

    source_writes={}
    for label,dispatch,pos in (
        ("a_high",a1,inst["input_a_position"]),
        ("a_low",a0,inst["input_a_position"]),
        ("b_high",b1,inst["input_b_position"]),
        ("both_high",a2,inst["input_a_position"]),
    ):
        found=[
            r for r in rows
            if r["seq"]>dispatch["seq"]
            and r["event_type"]=="block_state_write"
            and position(r)==pos
        ]
        assert found,(label,"source block write",counts)
        source_writes[label]=found[0]["seq"]

    output=inst["output_wire_position"]
    event_types={
        "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
        "redstone_power_query","redstone_power_result","block_state_write",
    }
    phases=[
        ("10",a1["seq"],a0["seq"],12),
        ("00_reset",a0["seq"],b1["seq"],0),
        ("01",b1["seq"],a2["seq"],12),
    ]
    phase_evidence={}
    for label,start,end,expected_power in phases:
        events=[
            r for r in rows
            if start<r["seq"]<end
            and r["event_type"] in event_types
            and position(r)==output
        ]
        assert events,(label,"output wire events",counts)
        writes=[r for r in events if r["event_type"]=="block_state_write"]
        assert writes,(label,"output block-state write",counts)
        neighbour_values=[
            r["data"].get("value")
            for r in events
            if r["event_type"]=="redstone_power_result"
        ]
        phase_evidence[label]={
            "event_count":len(events),
            "block_state_write_count":len(writes),
            "exact_state_probe_output_wire_power":expected_power,
            "incoming_neighbor_signal_result_values":neighbour_values,
        }

    after_both=[
        r for r in rows
        if r["seq"]>a2["seq"]
        and r["event_type"] in event_types
        and position(r) in (
            inst["input_a_wire_position"],
            inst["input_b_wire_position"],
            inst["junction_wire_position"],
            output,
        )
    ]

    return {
        "truth_table_sequence":inst["truth_table_sequence"],
        "input_dispatch_seq":{
            "a_high":a1["seq"],"a_low_reset":a0["seq"],
            "b_high":b1["seq"],"both_high":a2["seq"],
        },
        "source_write_seq":source_writes,
        "output_phase_evidence":phase_evidence,
        "post_11_wire_event_count":len(after_both),
        "event_counts":dict(sorted(counts.items())),
        "dropped_events":0,
        "semantic_divergence":False,
        "stock_elapsed_seconds":stock["elapsed_seconds"],
        "instrumented_elapsed_seconds":inst["elapsed_seconds"],
    }


def validate_nor(root:Path):
    name="nor-gate"
    stock=load_result(root,name,"stock")
    inst=load_result(root,name,"instrumented")
    for k in (
        "template","minecraft_version","java_major","input_control",
        "input_a_position","input_b_position",
        "input_a_wire_position","input_b_wire_position",
        "junction_wire_position","input_net_wire_positions",
        "inverter_support_position","inverter_position",
        "output_wire_position","output_lamp_position",
        "input_a_high_command_sha256","input_a_low_command_sha256",
        "input_b_high_command_sha256","input_b_low_command_sha256",
        "truth_table_sequence","output_lamp_semantic_authority",
    ):
        assert stock[k]==inst[k],(k,stock[k],inst[k])
    assert stock["instrumented"] is False
    assert inst["instrumented"] is True
    assert inst["trace_present"] is True

    assert inst["output_lamp_semantic_authority"] is False
    expected=[
        (False,False,True,15),
        (True,False,False,0),
        (False,False,True,15),
        (False,True,False,0),
        (True,True,False,0),
    ]
    observed=[
        (
            row["a"],row["b"],row["torch_lit"],
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
        "redstone_power_query","redstone_power_result",
        "command_dispatch","block_state_write",
    ):
        assert counts[required]>0,(required,counts)

    a1=dispatch_after(rows,inst["input_a_high_command_sha256"])
    a0=dispatch_after(rows,inst["input_a_low_command_sha256"],a1["seq"])
    b1=dispatch_after(rows,inst["input_b_high_command_sha256"],a0["seq"])
    a2=dispatch_after(rows,inst["input_a_high_command_sha256"],b1["seq"])
    assert a1["seq"]<a0["seq"]<b1["seq"]<a2["seq"]

    source_writes={}
    for label,dispatch,pos in (
        ("a_high",a1,inst["input_a_position"]),
        ("a_low",a0,inst["input_a_position"]),
        ("b_high",b1,inst["input_b_position"]),
        ("both_high",a2,inst["input_a_position"]),
    ):
        found=[
            r for r in rows
            if r["seq"]>dispatch["seq"]
            and r["event_type"]=="block_state_write"
            and position(r)==pos
        ]
        assert found,(label,"source block write",counts)
        source_writes[label]=found[0]["seq"]

    event_types={
        "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
        "redstone_power_query","redstone_power_result","block_state_write",
    }
    input_positions={tuple(p) for p in inst["input_net_wire_positions"]}
    output=inst["output_wire_position"]
    phases=[
        ("10",a1["seq"],a0["seq"]),
        ("00_reset",a0["seq"],b1["seq"]),
        ("01",b1["seq"],a2["seq"]),
    ]
    phase_evidence={}
    for label,start,end in phases:
        input_events=[
            r for r in rows
            if start<r["seq"]<end
            and r["event_type"] in event_types
            and tuple(position(r)) in input_positions
        ]
        output_events=[
            r for r in rows
            if start<r["seq"]<end
            and r["event_type"] in event_types
            and position(r)==output
        ]
        assert input_events,(label,"input net activity",counts)
        assert output_events,(label,"output activity",counts)
        assert any(
            r["event_type"]=="block_state_write" for r in output_events
        ),(label,"output block-state write",counts)
        phase_evidence[label]={
            "input_event_count":len(input_events),
            "output_event_count":len(output_events),
        }

    after_11=[
        r for r in rows
        if r["seq"]>a2["seq"]
        and r["event_type"] in event_types
        and tuple(position(r)) in input_positions
    ]
    assert after_11,("11","input causal activity",counts)

    inverter_writes=[
        r for r in rows
        if r["event_type"]=="block_state_write"
        and position(r)==inst["inverter_position"]
    ]
    assert inverter_writes,("inverter state writes",counts)

    return {
        "truth_table_sequence":inst["truth_table_sequence"],
        "input_dispatch_seq":{
            "a_high":a1["seq"],"a_low_reset":a0["seq"],
            "b_high":b1["seq"],"both_high":a2["seq"],
        },
        "source_write_seq":source_writes,
        "phase_evidence":phase_evidence,
        "post_11_input_event_count":len(after_11),
        "inverter_write_count":len(inverter_writes),
        "event_counts":dict(sorted(counts.items())),
        "dropped_events":0,
        "semantic_divergence":False,
        "stock_elapsed_seconds":stock["elapsed_seconds"],
        "instrumented_elapsed_seconds":inst["elapsed_seconds"],
        "output_lamp_semantic_authority":False,
        "measurement_boundary":"NOR truth-table authority is exact inverter state plus output-dust power; adjacent lamp state is intentionally diagnostic only",
    }


def validate_and(root:Path):
    name="and-gate"
    stock=load_result(root,name,"stock")
    inst=load_result(root,name,"instrumented")
    for k in (
        "template","minecraft_version","java_major","input_control",
        "input_a_position","input_b_position",
        "input_a_wire_position","input_b_wire_position",
        "input_a_inverter_position","input_b_inverter_position",
        "intermediate_wire_positions","final_inverter_position",
        "output_wire_position","output_lamp_position",
        "input_a_high_command_sha256","input_a_low_command_sha256",
        "input_b_high_command_sha256","input_b_low_command_sha256",
        "truth_table_sequence",
    ):
        assert stock[k]==inst[k],(k,stock[k],inst[k])
    assert stock["instrumented"] is False
    assert inst["instrumented"] is True
    assert inst["trace_present"] is True

    expected=[
        (False,False,0,False),
        (True,False,0,False),
        (False,False,0,False),
        (False,True,0,False),
        (True,True,15,True),
    ]
    observed=[
        (row["a"],row["b"],row["output_wire_power"],row["output_lamp_lit"])
        for row in inst["truth_table_sequence"]
    ]
    assert observed==expected,observed
    assert all(row["verified"] is True for row in inst["truth_table_sequence"])

    rows=load_trace(root,name)
    counts=trace_contract(rows)
    for required in (
        "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
        "redstone_power_query","redstone_power_result","command_dispatch",
        "block_state_write",
    ):
        assert counts[required]>0,(required,counts)

    a1=dispatch_after(rows,inst["input_a_high_command_sha256"])
    a0=dispatch_after(rows,inst["input_a_low_command_sha256"],a1["seq"])
    b1=dispatch_after(rows,inst["input_b_high_command_sha256"],a0["seq"])
    a2=dispatch_after(rows,inst["input_a_high_command_sha256"],b1["seq"])
    assert a1["seq"]<a0["seq"]<b1["seq"]<a2["seq"]

    source_writes={}
    for label,dispatch,pos in (
        ("a_high",a1,inst["input_a_position"]),
        ("a_low",a0,inst["input_a_position"]),
        ("b_high",b1,inst["input_b_position"]),
        ("both_high",a2,inst["input_a_position"]),
    ):
        found=[
            r for r in rows
            if r["seq"]>dispatch["seq"]
            and r["event_type"]=="block_state_write"
            and position(r)==pos
        ]
        assert found,(label,"source block write",counts)
        source_writes[label]=found[0]["seq"]

    event_types={
        "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
        "redstone_power_query","redstone_power_result","block_state_write",
    }
    input_positions={
        tuple(inst["input_a_wire_position"]),
        tuple(inst["input_b_wire_position"]),
    }
    intermediate_positions={tuple(p) for p in inst["intermediate_wire_positions"]}
    output=inst["output_wire_position"]

    phases=[
        ("10",a1["seq"],a0["seq"]),
        ("00_reset",a0["seq"],b1["seq"]),
        ("01",b1["seq"],a2["seq"]),
    ]
    phase_activity={}
    for label,start,end in phases:
        events=[
            r for r in rows
            if start<r["seq"]<end
            and r["event_type"] in event_types
            and tuple(position(r)) in (input_positions|intermediate_positions)
        ]
        assert events,(label,"input/intermediate causal activity",counts)
        phase_activity[label]=len(events)

    after_11=[
        r for r in rows
        if r["seq"]>a2["seq"]
        and r["event_type"] in event_types
        and (
            tuple(position(r)) in (input_positions|intermediate_positions)
            or position(r)==output
        )
    ]
    assert after_11,("11","causal activity",counts)
    output_events=[
        r for r in after_11
        if position(r)==output
    ]
    assert output_events,("11","output wire activity",counts)
    output_writes=[
        r for r in output_events
        if r["event_type"]=="block_state_write"
    ]
    assert output_writes,("11","output block-state write",counts)

    final_inverter_writes=[
        r for r in rows
        if r["seq"]>a2["seq"]
        and r["event_type"]=="block_state_write"
        and position(r)==inst["final_inverter_position"]
    ]
    assert final_inverter_writes,("11","final inverter state write",counts)

    return {
        "truth_table_sequence":inst["truth_table_sequence"],
        "input_dispatch_seq":{
            "a_high":a1["seq"],"a_low_reset":a0["seq"],
            "b_high":b1["seq"],"both_high":a2["seq"],
        },
        "source_write_seq":source_writes,
        "non_output_transition_activity":phase_activity,
        "post_11_event_count":len(after_11),
        "post_11_output_wire_event_count":len(output_events),
        "post_11_output_block_state_write_count":len(output_writes),
        "post_11_final_inverter_write_count":len(final_inverter_writes),
        "event_counts":dict(sorted(counts.items())),
        "dropped_events":0,
        "semantic_divergence":False,
        "stock_elapsed_seconds":stock["elapsed_seconds"],
        "instrumented_elapsed_seconds":inst["elapsed_seconds"],
    }



def validate_xor(root:Path):
    name="xor-gate"
    stock=load_result(root,name,"stock")
    inst=load_result(root,name,"instrumented")
    for k in (
        "template","minecraft_version","java_major","input_control",
        "input_a_position","input_b_position",
        "input_a_high_command_sha256","input_a_low_command_sha256",
        "input_b_high_command_sha256","input_b_low_command_sha256",
        "input_inverter_positions","stage_inverter_positions",
        "final_inverter_position","output_wire_position","output_lamp_position",
        "branch_wire_positions","truth_table_sequence",
        "output_lamp_semantic_authority","boolean_composition",
    ):
        assert stock[k]==inst[k],(k,stock[k],inst[k])
    assert stock["instrumented"] is False
    assert inst["instrumented"] is True
    assert inst["trace_present"] is True
    assert inst["output_lamp_semantic_authority"] is False

    expected=[
        (False,False,False,0),
        (True,False,True,15),
        (False,False,False,0),
        (False,True,True,15),
        (True,True,False,0),
    ]
    observed=[
        (
            row["a"],row["b"],row["final_inverter_lit"],
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
        "redstone_power_query","redstone_power_result",
        "command_dispatch","block_state_write",
    ):
        assert counts[required]>0,(required,counts)

    a1=dispatch_after(rows,inst["input_a_high_command_sha256"])
    a0=dispatch_after(rows,inst["input_a_low_command_sha256"],a1["seq"])
    b1=dispatch_after(rows,inst["input_b_high_command_sha256"],a0["seq"])
    a2=dispatch_after(rows,inst["input_a_high_command_sha256"],b1["seq"])
    assert a1["seq"]<a0["seq"]<b1["seq"]<a2["seq"]

    branch_positions={tuple(p) for p in inst["branch_wire_positions"]}
    output=inst["output_wire_position"]
    event_types={
        "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
        "redstone_power_query","redstone_power_result","block_state_write",
    }
    phases=[
        ("10",a1["seq"],a0["seq"]),
        ("00_reset",a0["seq"],b1["seq"]),
        ("01",b1["seq"],a2["seq"]),
    ]
    phase_activity={}
    for label,start,end in phases:
        branch_events=[
            r for r in rows
            if start<r["seq"]<end
            and r["event_type"] in event_types
            and tuple(position(r)) in branch_positions
        ]
        output_events=[
            r for r in rows
            if start<r["seq"]<end
            and r["event_type"] in event_types
            and position(r)==output
        ]
        assert branch_events,(label,"branch causal activity",counts)
        assert output_events,(label,"output causal activity",counts)
        assert any(
            r["event_type"]=="block_state_write" for r in output_events
        ),(label,"output block-state write",counts)
        phase_activity[label]={
            "branch_event_count":len(branch_events),
            "output_event_count":len(output_events),
        }

    after_11=[
        r for r in rows
        if r["seq"]>a2["seq"]
        and r["event_type"] in event_types
        and (
            tuple(position(r)) in branch_positions
            or position(r)==output
        )
    ]
    assert after_11,("11","causal activity",counts)
    final_writes=[
        r for r in rows
        if r["event_type"]=="block_state_write"
        and position(r)==inst["final_inverter_position"]
    ]
    assert final_writes,("final inverter writes",counts)

    return {
        "truth_table_sequence":inst["truth_table_sequence"],
        "input_dispatch_seq":{
            "a_high":a1["seq"],"a_low_reset":a0["seq"],
            "b_high":b1["seq"],"both_high":a2["seq"],
        },
        "phase_activity":phase_activity,
        "post_11_event_count":len(after_11),
        "final_inverter_write_count":len(final_writes),
        "event_counts":dict(sorted(counts.items())),
        "dropped_events":0,
        "semantic_divergence":False,
        "stock_elapsed_seconds":stock["elapsed_seconds"],
        "instrumented_elapsed_seconds":inst["elapsed_seconds"],
        "output_lamp_semantic_authority":False,
        "measurement_boundary":"XOR authority is exact final-inverter state plus output-dust power; the presentation lamp is diagnostic only",
    }



def validate_rising_edge(root:Path):
    name="rising-edge"
    stock=load_result(root,name,"stock")
    inst=load_result(root,name,"instrumented")
    for k in (
        "template","minecraft_version","java_major","input_control",
        "configured_delays","delay_stage_count",
        "input_source_position","input_net_wire_positions",
        "delay_repeater_positions","delay_interstage_wire_position",
        "delay_output_wire_position",
        "direct_inverter_position","intermediate_wire_positions",
        "final_inverter_position","output_wire_position","output_lamp_position",
        "input_high_command_sha256","input_low_command_sha256",
        "temporal_sequence","output_lamp_semantic_authority",
        "boolean_temporal_composition",
    ):
        assert stock[k]==inst[k],(k,stock[k],inst[k])
    assert stock["instrumented"] is False
    assert inst["instrumented"] is True
    assert inst["trace_present"] is True
    assert inst["configured_delays"]==[4,4]
    assert inst["delay_stage_count"]==2
    assert inst["output_lamp_semantic_authority"] is False

    expected=[
        ("baseline_low",False,False),
        ("rising_1_pulse",True,True),
        ("rising_1_settled",True,False),
        ("falling_edge_guard",False,False),
        ("low_settled",False,False),
        ("rising_2_pulse",True,True),
        ("rising_2_settled",True,False),
    ]
    observed=[]
    for row in inst["temporal_sequence"]:
        if row["phase"]=="falling_edge_guard":
            observed.append((
                row["phase"],row["input_high"],
                bool(row["positive_pulse_observed"]),
            ))
        else:
            observed.append((row["phase"],row["input_high"],row["output_high"]))
        assert row["verified"] is True,row
    assert observed==expected,observed

    rows=load_trace(root,name)
    counts=trace_contract(rows)
    for required in (
        "wire_neighbor_changed","wire_recompute_start","wire_recompute_end",
        "redstone_power_query","redstone_power_result","command_dispatch",
        "block_state_write",
    ):
        assert counts[required]>0,(required,counts)

    high1=dispatch_after(rows,inst["input_high_command_sha256"])
    low=dispatch_after(rows,inst["input_low_command_sha256"],high1["seq"])
    high2=dispatch_after(rows,inst["input_high_command_sha256"],low["seq"])
    assert high1["seq"]<low["seq"]<high2["seq"]

    source_writes={}
    for label,dispatch in (("high1",high1),("low",low),("high2",high2)):
        found=[
            r for r in rows
            if r["seq"]>dispatch["seq"]
            and r["event_type"]=="block_state_write"
            and position(r)==inst["input_source_position"]
        ]
        assert found,(label,"source write",counts)
        source_writes[label]=found[0]["seq"]

    final_pos=inst["final_inverter_position"]
    first_pulse_writes=[
        r for r in rows
        if high1["seq"]<r["seq"]<low["seq"]
        and r["event_type"]=="block_state_write"
        and position(r)==final_pos
    ]
    assert len(first_pulse_writes)>=2,("first rising pulse transitions",first_pulse_writes)
    first_tick_width=first_pulse_writes[-1]["tick"]-first_pulse_writes[0]["tick"]
    assert first_tick_width>0,("first rising pulse tick width",first_tick_width)

    falling_final_writes=[
        r for r in rows
        if low["seq"]<r["seq"]<high2["seq"]
        and r["event_type"]=="block_state_write"
        and position(r)==final_pos
    ]
    assert not falling_final_writes,(
        "falling edge must not toggle final inverter",falling_final_writes
    )

    second_pulse_writes=[
        r for r in rows
        if r["seq"]>high2["seq"]
        and r["event_type"]=="block_state_write"
        and position(r)==final_pos
    ]
    assert len(second_pulse_writes)>=2,("second rising pulse transitions",second_pulse_writes)
    second_tick_width=second_pulse_writes[-1]["tick"]-second_pulse_writes[0]["tick"]
    assert second_tick_width>0,("second rising pulse tick width",second_tick_width)

    output_pos=inst["output_wire_position"]
    output_power_results=[
        r for r in rows
        if r["event_type"]=="redstone_power_result"
        and position(r)==output_pos
    ]
    assert output_power_results,("output power observations",counts)

    return {
        "temporal_sequence":inst["temporal_sequence"],
        "input_dispatch_seq":{
            "high1":high1["seq"],"low":low["seq"],"high2":high2["seq"],
        },
        "source_write_seq":source_writes,
        "first_rising_final_inverter_write_count":len(first_pulse_writes),
        "first_rising_pulse_tick_width":first_tick_width,
        "falling_final_inverter_write_count":0,
        "second_rising_final_inverter_write_count":len(second_pulse_writes),
        "second_rising_pulse_tick_width":second_tick_width,
        "output_power_observation_count":len(output_power_results),
        "event_counts":dict(sorted(counts.items())),
        "dropped_events":0,
        "semantic_divergence":False,
        "temporal_contract_pass":True,
        "stock_elapsed_seconds":stock["elapsed_seconds"],
        "instrumented_elapsed_seconds":inst["elapsed_seconds"],
        "output_lamp_semantic_authority":False,
        "measurement_boundary":"runtime probes define positive-pulse semantics; trace ordering independently proves positive-width final-inverter transitions on rising edges and no final-inverter transition during the falling-edge window",
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
    disj=validate_or(args.root)
    nor=validate_nor(args.root)
    conj=validate_and(args.root)
    xor=validate_xor(args.root)
    rising=validate_rising_edge(args.root)

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
        "or_gate":{
            **disj,
            "truth_table_contract":"00->0, 10->1, 01->1, 11->1",
            "truth_table_pass":True,
        },
        "nor_gate":{
            **nor,
            "truth_table_contract":"00->1, 10->0, 01->0, 11->0",
            "truth_table_pass":True,
        },
        "and_gate":{
            **conj,
            "truth_table_contract":"00->0, 10->0, 01->0, 11->1",
            "truth_table_pass":True,
        },
        "xor_gate":{
            **xor,
            "truth_table_contract":"00->0, 10->1, 01->1, 11->0",
            "truth_table_pass":True,
        },
        "rising_edge_detector":{
            **rising,
            "temporal_contract":"low->high emits one bounded positive pulse then settles low; high->low emits no positive pulse; second rise retriggers after low settling",
            "temporal_contract_pass":True,
        },
        "boundary":"runtime qualification applies to these exact generated fixtures and versions; template generalization remains separately gated by static netlist matching",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
