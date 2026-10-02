#!/usr/bin/env python3
"""Correlate standard redstone netlist motifs with exact runtime contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def motifs(doc,name):
    return [x for x in doc.get("motif_candidates",[]) if x.get("template")==name]


def component_map(doc):
    return {c["component_id"]:c for c in doc.get("components",[])}


def validate_repeater(doc,delay):
    rows=motifs(doc,"repeater_delay_line")
    assert rows,(delay,"missing repeater_delay_line")
    matches=[
        r for r in rows
        if str(r.get("configured_delay"))==str(delay)
    ]
    assert matches,(delay,rows)
    row=matches[0]
    assert len(row["net_ids"])==2
    assert row["net_ids"][0]!=row["net_ids"][1]
    return {
        "configured_delay":delay,
        "motif_count":len(rows),
        "matched_component_ids":row["component_ids"],
        "net_ids":row["net_ids"],
        "functional_netlist_sha256":doc["signatures"]["functional_netlist_sha256"],
        "horizontal_d4_topology_sha256":doc["signatures"]["horizontal_d4_topology_sha256"],
    }


def validate_not(doc):
    rows=motifs(doc,"not_gate")
    assert rows,"missing not_gate"
    resolved=[r for r in rows if r.get("input_support_resolved") is True]
    assert resolved,rows
    row=resolved[0]
    cmap=component_map(doc)
    source_ids=row.get("input_source_component_ids") or []
    assert source_ids,row
    assert any(
        cmap[source_id]["primitive"] in {
            "constant_power_source","manual_state_input","pulse_input","input_sensor"
        }
        for source_id in source_ids
        if source_id in cmap
    ),(source_ids,cmap)
    return {
        "motif_count":len(rows),
        "matched_component_ids":row["component_ids"],
        "input_source_component_ids":source_ids,
        "output_net_ids":row["net_ids"],
        "functional_netlist_sha256":doc["signatures"]["functional_netlist_sha256"],
        "horizontal_d4_topology_sha256":doc["signatures"]["horizontal_d4_topology_sha256"],
    }


def validate_or(doc):
    rows=motifs(doc,"or_gate")
    assert rows,"missing or_gate"
    qualified=[
        r for r in rows
        if len(set(r.get("input_source_component_ids") or []))>=2
        and len(set(r.get("output_sink_component_ids") or []))>=1
    ]
    assert qualified,rows
    row=qualified[0]
    cmap=component_map(doc)
    source_ids=sorted(set(row["input_source_component_ids"]))
    sink_ids=sorted(set(row["output_sink_component_ids"]))
    assert all(
        source_id in cmap and cmap[source_id]["primitive"] in {
            "constant_power_source","manual_state_input","pulse_input","input_sensor"
        }
        for source_id in source_ids
    ),(source_ids,cmap)
    return {
        "motif_count":len(rows),
        "matched_component_ids":row["component_ids"],
        "input_source_component_ids":source_ids,
        "output_sink_component_ids":sink_ids,
        "net_ids":row["net_ids"],
        "functional_netlist_sha256":doc["signatures"]["functional_netlist_sha256"],
        "horizontal_d4_topology_sha256":doc["signatures"]["horizontal_d4_topology_sha256"],
    }


def validate_nor(doc):
    rows=motifs(doc,"nor_gate")
    assert rows,"missing nor_gate"
    qualified=[
        r for r in rows
        if len(set(r.get("input_source_component_ids") or []))>=2
        and r.get("input_net_id")
        and r.get("inverter_component_id")
        and len(set(r.get("output_sink_component_ids") or []))>=1
    ]
    assert qualified,rows
    row=qualified[0]
    cmap=component_map(doc)
    source_ids=sorted(set(row["input_source_component_ids"]))
    inverter_id=row["inverter_component_id"]
    sink_ids=sorted(set(row["output_sink_component_ids"]))
    assert all(
        source_id in cmap and cmap[source_id]["primitive"] in {
            "constant_power_source","manual_state_input","pulse_input","input_sensor"
        }
        for source_id in source_ids
    ),(source_ids,cmap)
    assert inverter_id in cmap and cmap[inverter_id]["primitive"]=="inverter"
    return {
        "motif_count":len(rows),
        "matched_component_ids":row["component_ids"],
        "input_source_component_ids":source_ids,
        "input_net_id":row["input_net_id"],
        "inverter_component_id":inverter_id,
        "output_net_ids":row["output_net_ids"],
        "output_sink_component_ids":sink_ids,
        "functional_netlist_sha256":doc["signatures"]["functional_netlist_sha256"],
        "horizontal_d4_topology_sha256":doc["signatures"]["horizontal_d4_topology_sha256"],
    }


def validate_and(doc):
    rows=motifs(doc,"and_gate")
    assert rows,"missing and_gate"
    qualified=[
        r for r in rows
        if len(set(r.get("input_source_component_ids") or []))==2
        and len(set(r.get("input_inverter_component_ids") or []))==2
        and r.get("final_inverter_component_id")
        and len(set(r.get("output_sink_component_ids") or []))>=1
    ]
    assert qualified,rows
    row=qualified[0]
    cmap=component_map(doc)
    source_ids=sorted(set(row["input_source_component_ids"]))
    inverter_ids=sorted(set(row["input_inverter_component_ids"]))
    final_id=row["final_inverter_component_id"]
    sink_ids=sorted(set(row["output_sink_component_ids"]))
    assert all(
        source_id in cmap and cmap[source_id]["primitive"] in {
            "constant_power_source","manual_state_input","pulse_input","input_sensor"
        }
        for source_id in source_ids
    ),(source_ids,cmap)
    assert all(
        inverter_id in cmap and cmap[inverter_id]["primitive"]=="inverter"
        for inverter_id in inverter_ids+[final_id]
    ),(inverter_ids,final_id,cmap)
    return {
        "motif_count":len(rows),
        "matched_component_ids":row["component_ids"],
        "input_source_component_ids":source_ids,
        "input_inverter_component_ids":inverter_ids,
        "intermediate_net_id":row["intermediate_net_id"],
        "final_inverter_component_id":final_id,
        "output_sink_component_ids":sink_ids,
        "net_ids":row["net_ids"],
        "functional_netlist_sha256":doc["signatures"]["functional_netlist_sha256"],
        "horizontal_d4_topology_sha256":doc["signatures"]["horizontal_d4_topology_sha256"],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime-report",type=Path,required=True)
    ap.add_argument("--repeater-d1-netlist",type=Path,required=True)
    ap.add_argument("--repeater-d4-netlist",type=Path,required=True)
    ap.add_argument("--not-netlist",type=Path,required=True)
    ap.add_argument("--or-netlist",type=Path,required=True)
    ap.add_argument("--nor-netlist",type=Path,required=True)
    ap.add_argument("--and-netlist",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    runtime=load(args.runtime_report)
    d1=validate_repeater(load(args.repeater_d1_netlist),1)
    d4=validate_repeater(load(args.repeater_d4_netlist),4)
    inv=validate_not(load(args.not_netlist))
    disj=validate_or(load(args.or_netlist))
    nor=validate_nor(load(args.nor_netlist))
    conj=validate_and(load(args.and_netlist))

    rt_repeater=runtime["repeater_delay_line"]
    assert rt_repeater["ordering_pass"] is True
    assert (
        rt_repeater["delay_4"]["server_tick_delta"]
        > rt_repeater["delay_1"]["server_tick_delta"]
    )
    assert runtime["not_gate"]["truth_table_pass"] is True
    assert runtime["or_gate"]["truth_table_pass"] is True
    assert runtime["nor_gate"]["truth_table_pass"] is True
    assert runtime["and_gate"]["truth_table_pass"] is True

    report={
        "schema":"supracraft-redstone-netlist-runtime-correlation/1",
        "minecraft_version":runtime["minecraft_version"],
        "repeater_delay_line":{
            "static_delay_1":d1,
            "static_delay_4":d4,
            "runtime_delay_1_server_tick_delta":
                rt_repeater["delay_1"]["server_tick_delta"],
            "runtime_delay_4_server_tick_delta":
                rt_repeater["delay_4"]["server_tick_delta"],
            "correlation_class":
                "repeater_delay_template_supported_by_runtime_temporal_contract",
        },
        "not_gate":{
            "static":inv,
            "runtime_truth_table":runtime["not_gate"]["truth_table_sequence"],
            "correlation_class":
                "not_gate_template_supported_by_runtime_truth_table",
        },
        "or_gate":{
            "static":disj,
            "runtime_truth_table":runtime["or_gate"]["truth_table_sequence"],
            "correlation_class":
                "or_gate_template_supported_by_runtime_truth_table",
        },
        "nor_gate":{
            "static":nor,
            "runtime_truth_table":runtime["nor_gate"]["truth_table_sequence"],
            "correlation_class":
                "nor_gate_template_supported_by_runtime_truth_table",
        },
        "and_gate":{
            "static":conj,
            "runtime_truth_table":runtime["and_gate"]["truth_table_sequence"],
            "correlation_class":
                "and_gate_template_supported_by_runtime_truth_table",
        },
        "boundary":"template identification is exact-fixture/version evidence; broader motif recognition still requires independent examples and hard negatives",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
