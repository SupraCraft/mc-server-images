#!/usr/bin/env python3
"""Rank candidate gameplay mechanisms from the existing legacy causal graph.

Discovery only. Neither proximity nor a source-backed possible power path
establishes actual gameplay behavior. Outputs contain aggregates, never raw
world coordinates, block/entity names, command strings, or world payloads.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

SCHEMA = "supracraft-legacy-causal-machinery/1"
RESULT = "supracraft-legacy-gameplay-scout/1"

# The first campaign is pinned to CORE's native 1.8.8 evidence.
SUPPORTED_VERSION = "1.8.8"

EDGE_BUCKETS = {
    "legacy_sensor_direct_dust_power": "sensor_to_electrical",
    "legacy_pressure_plate_support_power": "sensor_to_electrical",
    "legacy_button_attached_support_power": "sensor_to_electrical",
    "legacy_dust_horizontal_connection": "electrical_transport",
    "legacy_dust_direct_component_power": "electrical_to_component",
    "legacy_dust_downward_command_power": "electrical_to_programmable",
    "legacy_repeater_through_command_block_to_dust_power": "electrical_transport",
    "authored_redstone_block_direct_power": "programmable_to_electrical",
    "legacy_setblock_redstone_direct_power": "programmable_to_electrical",
    "command_world_target": "programmable_world_target",
    "container_inventory_signal_read": "inventory_to_electrical",
    "open_emits_redstone_power_candidate": "inventory_to_electrical",
    "chain_facing_successor_candidate": "programmable_chain",
    "conditional_predecessor_success_dependency": "programmable_chain",
}
EDGE_GROUPS = {
    "direct_redstone_edges",
    "repeater_command_block_conduction_edges",
    "command_authored_redstone_edges",
    "command_world_targets",
    "container_comparator_reads",
    "trapped_chest_open_power_candidates",
    "command_chain_candidates",
}
SENSOR = {"lever", "stone_button", "wooden_button",
          "stone_pressure_plate", "wooden_pressure_plate",
          "light_weighted_pressure_plate", "heavy_weighted_pressure_plate",
          "daylight_detector", "inverted_daylight_detector", "tripwire_hook"}
COMMAND = {"command_block", "repeating_command_block", "chain_command_block"}
ACTUATOR = {"piston", "sticky_piston", "iron_door", "wooden_door",
            "iron_trapdoor", "trapdoor", "fence_gate",
            "dispenser", "dropper", "redstone_lamp_on", "redstone_lamp_off",
            "note_block", "hopper"}


def _safe_edges(graph, ids):
    edges = graph.get("edges")
    if not isinstance(edges, dict):
        raise ValueError("missing edges dictionary")
    out = []
    for key in sorted(EDGE_GROUPS):
        values = edges.get(key, [])
        if not isinstance(values, list):
            raise ValueError("invalid edge collection: " + key)
        for edge in values:
            if not isinstance(edge, dict):
                raise ValueError("invalid edge record: " + key)
            src = edge.get("source")
            if not isinstance(src, str) or src not in ids:
                raise ValueError("unresolved source in " + key)
            dst = edge.get("target")
            # Command world targets can address positions outside the machinery
            # census; don't transform such coordinates into confirmed nodes.
            if key != "command_world_targets" and (
                not isinstance(dst, str) or dst not in ids
            ):
                raise ValueError("unresolved target in " + key)
            if key == "command_world_targets" and dst is not None and dst not in ids:
                raise ValueError("unresolved command target node")
            out.append((key, edge))
    return out


def scout(graph, *, version):
    if version != SUPPORTED_VERSION:
        raise ValueError("unqualified version: " + str(version))
    if not isinstance(graph, dict) or graph.get("schema") != SCHEMA:
        raise ValueError("wrong legacy analyzer schema")
    if graph.get("world_format") != "legacy_anvil_pre_palette":
        raise ValueError("world format mismatch")
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("missing node inventory")
    node_map = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("node_id"), str):
            raise ValueError("malformed node")
        node_id = node["node_id"]
        if node_id in node_map:
            raise ValueError("duplicate node")
        node_map[node_id] = node
    selected = _safe_edges(graph, node_map)

    counts = Counter()
    ignored = Counter()
    sensor_to_wire = defaultdict(set)
    wire_to_command = defaultdict(set)
    wire_to_actuator = defaultdict(set)
    command_targets = set()
    command_mutates_known_node = set()

    for collection, edge in selected:
        src, dst = edge["source"], edge.get("target")
        kind = edge.get("edge_type")
        bucket = EDGE_BUCKETS.get(kind)
        # Do not infer a wire/sensor connection from geometric adjacency.
        if not bucket:
            ignored[str(kind)] += 1
            continue
        if collection == "command_world_targets" and kind != "command_world_target":
            ignored[str(kind)] += 1
            continue
        counts[bucket] += 1
        sf = node_map[src].get("family")
        df = node_map[dst].get("family") if dst is not None else None
        if collection == "direct_redstone_edges":
            if sf in SENSOR and df == "redstone_wire" and kind == "legacy_sensor_direct_dust_power":
                sensor_to_wire[dst].add(src)
            if sf == "redstone_wire" and df in COMMAND and kind in {
                "legacy_dust_direct_component_power", "legacy_dust_downward_command_power"
            }:
                wire_to_command[src].add(dst)
            if sf == "redstone_wire" and df in ACTUATOR and kind == "legacy_dust_direct_component_power":
                wire_to_actuator[src].add(dst)
        if collection == "command_world_targets":
            command_targets.add(src)
            if dst is not None:
                command_mutates_known_node.add(src)

    sensor_programmable = sum(
        len(sensor_to_wire[wire]) * len(cmds)
        for wire, cmds in wire_to_command.items()
        if wire in sensor_to_wire
    )
    sensor_actuator = sum(
        len(sensor_to_wire[wire]) * len(acts)
        for wire, acts in wire_to_actuator.items()
        if wire in sensor_to_wire
    )
    electrical_command_target = sum(
        len(cmds & command_targets) for cmds in wire_to_command.values()
    )

    candidates = [
        ("sensor_wire_command", sensor_programmable,
         "sensor -> adjacent dust -> command; orientation/timing unproved"),
        ("sensor_wire_actuator", sensor_actuator,
         "sensor -> adjacent dust -> actuator; actuation unproved"),
        ("wire_command_world_target", electrical_command_target,
         "wire -> command -> syntactic world target; execution unproved"),
    ]
    hypotheses = [
        {"family": family, "structural_path_count": count,
         "status": "STRUCTURAL_CANDIDATE_ONLY",
         "runtime_qualified": False, "limitation": limitation}
        for family, count, limitation in candidates
    ]
    # This fingerprint binds the exact graph but conveys no world coordinates.
    digest = hashlib.sha256(json.dumps(graph, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "schema": RESULT,
        "source_schema": SCHEMA,
        "source_graph_sha256": digest,
        "source_version": version,
        "analysis_level": "STATIC_CANDIDATE_ONLY",
        "native_execution": "NOT_RUN",
        "independent_acceptance": "NOT_RUN",
        "node_count": len(node_map),
        "edge_family_counts": dict(sorted(counts.items())),
        "unrecognized_edge_type_counts": dict(sorted(ignored.items())),
        "unresolved_command_world_target_count":
            len(command_targets - command_mutates_known_node),
        "hypotheses": hypotheses,
        "next_oracle": "exact-original-version stimulated world readback before semantics or 26.3 uplift",
        "privacy": "aggregate_only_no_world_source_coordinates_commands_or_actor_identifiers",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--graph", type=Path, required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    graph = json.loads(a.graph.read_text(encoding="utf-8"))
    result = scout(graph, version=a.version)
    if a.output.exists():
        raise SystemExit("output exists; refusing overwrite")
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({"hypotheses": result["hypotheses"],
                      "source_version": result["source_version"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
