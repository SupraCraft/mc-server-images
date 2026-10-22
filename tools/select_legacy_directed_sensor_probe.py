#!/usr/bin/env python3
"""Select one bounded, directed, originally-authored CORE gameplay test witness.

Reads the *private-to-runner* source graph, emits a private-to-runner selection
for the existing 1.8.8 paired world probe plus a derived, non-coordinate public
summary. The graph and selection MUST NOT be uploaded to public artifacts.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from tools.scout_legacy_gameplay_mechanisms import (
    COMMAND, SENSOR, WORLD_EFFECT_VERBS, scout,
)

ACTIVATABLE = {
    "lever", "stone_button", "wooden_button",
    "stone_pressure_plate", "wooden_pressure_plate",
    "light_weighted_pressure_plate", "heavy_weighted_pressure_plate",
}
PLAYER_PRESENCE = {
    "stone_pressure_plate", "wooden_pressure_plate",
    "light_weighted_pressure_plate", "heavy_weighted_pressure_plate",
}
DIRECT_COMMAND_TYPES = {
    "legacy_dust_direct_component_power", "legacy_dust_downward_command_power",
}


def choose(graph: dict) -> tuple[dict, dict]:
    scan = scout(graph, version="1.8.8")
    nodes = {n["node_id"]: n for n in graph["nodes"]}
    edges = graph["edges"]
    sensor_wires = defaultdict(set)
    wire_commands = defaultdict(set)
    effect_verbs = defaultdict(set)

    # Only typed directed source edges, never proximity adjacency.
    for e in edges.get("direct_redstone_edges", []):
        s, t, typ = e.get("source"), e.get("target"), e.get("edge_type")
        if s not in nodes or t not in nodes:
            continue
        if (typ == "legacy_sensor_direct_dust_power"
                and nodes[s].get("family") in ACTIVATABLE
                and nodes[t].get("family") == "redstone_wire"):
            sensor_wires[s].add(t)
        if (typ in DIRECT_COMMAND_TYPES
                and nodes[s].get("family") == "redstone_wire"
                and nodes[t].get("family") in COMMAND):
            wire_commands[s].add(t)

    for e in edges.get("command_world_targets", []):
        src, verb = e.get("source"), e.get("verb")
        if src in nodes and verb in WORLD_EFFECT_VERBS:
            effect_verbs[src].add(verb)

    options = []
    for sid, wires in sensor_wires.items():
        node = nodes[sid]
        if node.get("family") in PLAYER_PRESENCE and (node.get("legacy_metadata") or 0) != 0:
            continue  # require unpowered initial player-occupancy fixture
        commands = sorted({c for w in wires for c in wire_commands.get(w, ())})
        if not commands:
            continue
        with_effect = sorted(c for c in commands if effect_verbs.get(c))
        # Runtime candidate need not be an effect success; prioritize observable
        # suspected world mutation while retaining the hard negative option.
        options.append(((-int(bool(with_effect)), -int(node["family"] in PLAYER_PRESENCE),
                         -len(with_effect), -len(commands), sid),
                        sid, commands, with_effect))
    if not options:
        raise ValueError("NO_DIRECTED_SUPPORTED_ORIGIN_WORLD_SENSOR_WITNESS")
    options.sort()
    _, sid, commands, with_effect = options[0]
    sensor = nodes[sid]
    result = {
        "schema": "supracraft-legacy-runtime-probe-selection/1",
        "sensor_mode": ("pressure_plates" if sensor["family"] in PLAYER_PRESENCE else "stable"),
        "selected_count": 1,
        "selection_kind": "source_directed_sensor_wire_command_hypothesis",
        "selected": [{
            "node_id": sid,
            "position": sensor["position"],
            "family": sensor["family"],
            "legacy_metadata": sensor.get("legacy_metadata"),
            "candidate_component_commands": [
                {
                    "node_id": cid,
                    "position": nodes[cid].get("position"),
                    "family": nodes[cid].get("family"),
                    "verb": (nodes[cid].get("command") or {}).get("verb"),
                    "command_sha256": (nodes[cid].get("command") or {}).get("sha256"),
                }
                for cid in commands
            ],
        }],
    }
    public = {
        "schema": "supracraft-directed-legacy-runtime-witness/1",
        "source_version": "1.8.8",
        "source_graph_sha256": scan["source_graph_sha256"],
        "sensor_family": sensor["family"],
        "sensor_node_sha256": hashlib.sha256(sid.encode("utf-8")).hexdigest(),
        "direct_command_candidate_count": len(commands),
        "candidate_commands_with_direct_world_effect": len(with_effect),
        "player_occupancy_required": sensor["family"] in PLAYER_PRESENCE,
        "selection_kind": "STATIC_DIRECTED_CANDIDATE_ONLY",
        "native_runtime_qualified": False,
        "limitations": [
            "Physical sensor->dust may not be energized or oriented in the original world.",
            "World-effect verbs can be unreachable, unexecuted, denied or conditionally guarded.",
            "No actual player or native game execution occurs in selection.",
        ],
    }
    return result, public


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--graph", type=Path, required=True)
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--public-summary", type=Path, required=True)
    a = p.parse_args()
    if a.selection.exists() or a.public_summary.exists():
        raise SystemExit("refuse overwrite")
    sel, public = choose(json.loads(a.graph.read_text(encoding="utf-8")))
    a.selection.parent.mkdir(parents=True, exist_ok=True)
    a.public_summary.parent.mkdir(parents=True, exist_ok=True)
    a.selection.write_text(json.dumps(sel, sort_keys=True, indent=2)+"\n",encoding="utf-8")
    a.public_summary.write_text(json.dumps(public, sort_keys=True, indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "sensor_family": public["sensor_family"],
        "direct_command_candidates": public["direct_command_candidate_count"],
        "with_world_effect_verb": public["candidate_commands_with_direct_world_effect"],
        "selection_kind": public["selection_kind"],
    },sort_keys=True))


if __name__ == "__main__":
    main()
