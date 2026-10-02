#!/usr/bin/env python3
"""Correlate inferred redstone topology/mechanism candidates with runtime A/B evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def node_id_for_position(doc: dict, position: list[int]) -> str | None:
    for comp in doc.get("components",[]):
        for node in comp.get("nodes",[]):
            if node.get("position")==position:
                return node.get("node_id")
    return None


def component_for_node(doc: dict, node_id: str | None) -> dict | None:
    if node_id is None:
        return None
    for comp in doc.get("components",[]):
        if any(n.get("node_id")==node_id for n in comp.get("nodes",[])):
            return comp
    return None


def candidate_names(comp: dict | None) -> set[str]:
    if not comp:
        return set()
    return {x.get("mechanism") for x in comp.get("mechanism_candidates",[])}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--positive-mechanism",type=Path,required=True)
    ap.add_argument("--gap-mechanism",type=Path,required=True)
    ap.add_argument("--runtime-report",type=Path,required=True)
    ap.add_argument("--positive-result",type=Path,required=True)
    ap.add_argument("--gap-result",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()

    positive=json.loads(args.positive_mechanism.read_text())
    gap=json.loads(args.gap_mechanism.read_text())
    runtime=json.loads(args.runtime_report.read_text())
    positive_result=json.loads(args.positive_result.read_text())
    gap_result=json.loads(args.gap_result.read_text())

    source_pos=positive_result["source_position"]
    command_pos=positive_result["command_block_position"]

    p_source=node_id_for_position(positive,source_pos)
    p_command=node_id_for_position(positive,command_pos)
    g_source=node_id_for_position(gap,gap_result["source_position"])
    g_command=node_id_for_position(gap,gap_result["command_block_position"])

    assert p_source and p_command,(p_source,p_command)
    assert g_source and g_command,(g_source,g_command)

    p_source_comp=component_for_node(positive,p_source)
    p_command_comp=component_for_node(positive,p_command)
    g_source_comp=component_for_node(gap,g_source)
    g_command_comp=component_for_node(gap,g_command)

    positive_same=(
        p_source_comp is not None and p_command_comp is not None
        and p_source_comp["component_id"]==p_command_comp["component_id"]
    )
    gap_same=(
        g_source_comp is not None and g_command_comp is not None
        and g_source_comp["component_id"]==g_command_comp["component_id"]
    )

    p_candidates=candidate_names(p_source_comp)
    assert positive_same
    assert "command_actuation_chain" in p_candidates
    assert "transmission_path" in p_candidates
    assert not gap_same

    observed_positive=runtime["fixtures"]["positive"]["actual_actuation"]
    observed_gap=runtime["fixtures"]["gap"]["actual_actuation"]
    assert observed_positive is True
    assert observed_gap is False

    report={
        "schema":"supracraft-redstone-mechanism-runtime-correlation/1",
        "minecraft_version":runtime["minecraft_version"],
        "positive":{
            "topology_prediction":"connected_command_actuation_candidate",
            "source_component":p_source_comp["component_id"],
            "source_component_topology_sha256":p_source_comp["topology_sha256"],
            "mechanism_candidates":sorted(p_candidates),
            "observed_actuation":True,
            "correlation_class":"structural_candidate_supported_by_runtime_fixture",
        },
        "gap_hard_negative":{
            "topology_prediction":"source_command_disconnected_by_air_gap",
            "source_component":g_source_comp["component_id"],
            "command_component":g_command_comp["component_id"],
            "source_component_topology_sha256":g_source_comp["topology_sha256"],
            "command_component_topology_sha256":g_command_comp["topology_sha256"],
            "observed_actuation":False,
            "correlation_class":"structural_disconnection_supported_by_runtime_hard_negative",
        },
        "boundary":"this correlation supports the exact fixture topology and observed behavior; it does not prove that all topologically similar redstone mechanisms share the same semantics across versions or update modes",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
