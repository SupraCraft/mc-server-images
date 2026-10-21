#!/usr/bin/env python3
"""Correlate an RS-latch static netlist candidate with exact runtime evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--runtime-report",type=Path,required=True)
    ap.add_argument("--netlist",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    runtime=load(args.runtime_report)
    netlist=load(args.netlist)
    rows=[
        x for x in netlist.get("motif_candidates",[])
        if x.get("template")=="rs_latch"
    ]
    assert rows,"missing rs_latch structural candidate"
    qualified=[
        r for r in rows
        if len(set(r.get("inverter_component_ids") or []))==2
        and r.get("feedback_a_to_b_net_ids")
        and r.get("feedback_b_to_a_net_ids")
    ]
    assert qualified,rows
    row=qualified[0]
    assert runtime["template"]=="rs_latch"
    assert runtime["retention_contract_pass"] is True
    assert runtime["semantic_divergence"] is False
    assert runtime["dropped_events"]==0

    report={
        "schema":"supracraft-rs-latch-netlist-runtime-correlation/1",
        "minecraft_version":runtime["minecraft_version"],
        "template":"rs_latch",
        "static":{
            "inverter_component_ids":row["inverter_component_ids"],
            "feedback_a_to_b_net_ids":row["feedback_a_to_b_net_ids"],
            "feedback_b_to_a_net_ids":row["feedback_b_to_a_net_ids"],
            "output_sink_component_ids":row.get("output_sink_component_ids",[]),
            "functional_netlist_sha256":
                netlist["signatures"]["functional_netlist_sha256"],
            "horizontal_d4_topology_sha256":
                netlist["signatures"]["horizontal_d4_topology_sha256"],
        },
        "runtime":{
            "state_sequence":runtime["state_sequence"],
            "retention_contract_pass":True,
            "invalid_boundary":runtime["invalid_boundary"],
            "dropped_events":0,
        },
        "correlation_class":
            "rs_latch_template_supported_by_runtime_set_reset_hold_contract",
        "boundary":"cross-coupled topology plus exact-version set/reset/hold persistence supports this RS latch template only; generic cycles and post-invalid resolution remain unpromoted",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
