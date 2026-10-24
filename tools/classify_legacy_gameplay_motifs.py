#!/usr/bin/env python3
"""Discover, but never promote, gameplay mechanism candidates in recovered 1.8.x worlds.

Consumes the *existing* supracraft-legacy-causal-machinery/1 graph. Uses only
source graph structure; results are NOT runtime mechanics or semantic evidence.
Output is derived aggregate metadata: no raw world blocks, coordinates,
commands, signs, UUIDs or inventories.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from hashlib import sha256
import json
from pathlib import Path


SCHEMA = "supracraft-legacy-gameplay-motif-candidates/1"
SOURCE_SCHEMA = "supracraft-legacy-causal-machinery/1"
ELECTRICAL = {"redstone_wire", "redstone_torch_off", "redstone_torch_on",
              "repeater_off", "repeater_on", "comparator_off", "comparator_on",
              "daylight_detector", "inverted_daylight_detector"}
MECHANICAL = {"piston", "sticky_piston", "wooden_door", "iron_door",
              "trapdoor", "iron_trapdoor", "fence_gate"}
INVENTORY = {"hopper", "chest", "trapped_chest", "dispenser", "dropper",
             "furnace", "lit_furnace"}
PROGRAMMABLE = {"command_block", "repeating_command_block", "chain_command_block"}
SENSORS = {"lever", "stone_button", "wooden_button", "stone_pressure_plate",
           "wooden_pressure_plate", "light_weighted_pressure_plate",
           "heavy_weighted_pressure_plate", "tripwire", "tripwire_hook"}
OBSERVATION = {"note_block", "redstone_lamp_off", "redstone_lamp_on",
               "standing_sign", "wall_sign"}
# The existing extractor's named edge collections are *candidate* evidence,
# including those it calls 'strong'. No cross-domain runtime promotion here.
EDGE_KEYS = {
    "direct_redstone_edges", "command_authored_redstone_edges",
    "repeater_command_block_conduction_edges", "command_world_targets",
    "command_chain_candidates", "container_comparator_reads",
    "trapped_chest_open_power_candidates", "oriented_signal_candidates",
    "scoreboard_state_edges",
}


def domain(family: str) -> str:
    if family in ELECTRICAL:
        return "electrical"
    if family in MECHANICAL:
        return "mechanical"
    if family in INVENTORY:
        return "inventory"
    if family in PROGRAMMABLE:
        return "programmable"
    if family in SENSORS:
        return "sensor"
    if family in OBSERVATION:
        return "observation"
    return "unknown"


def inventory(graph: dict) -> dict:
    """Aggregate candidate signatures, never infer causality from proximity."""
    if graph.get("schema") != SOURCE_SCHEMA:
        raise ValueError("unaccepted source graph schema")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, dict):
        raise ValueError("missing full node/edge graph; top-50 summaries are insufficient")
    by_id = {}
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("node_id"), str) or not isinstance(node.get("family"), str):
            raise ValueError("invalid node")
        identifier = node["node_id"]
        if identifier in by_id:
            raise ValueError("duplicate node id")
        by_id[identifier] = node
    # A connection is a physical *candidate*, not a signal path or transducer.
    graph_edges = edges.get("physical_adjacency_candidates")
    if not isinstance(graph_edges, list):
        raise ValueError("full adjacency not provided")
    adj = defaultdict(set)
    for edge in graph_edges:
        if not isinstance(edge, dict):
            raise ValueError("invalid adjacency edge")
        a, b = edge.get("a"), edge.get("b")
        if a not in by_id or b not in by_id or a == b:
            raise ValueError("adjacency endpoint unknown or self-edge")
        adj[a].add(b)
        adj[b].add(a)
    # Record named candidate edges without treating them as proven transfers.
    candidate_edges = []
    for kind in sorted(EDGE_KEYS):
        values = edges.get(kind, [])
        if not isinstance(values, list):
            raise ValueError("invalid candidate edge collection: " + kind)
        for edge in values:
            if not isinstance(edge, dict):
                raise ValueError("invalid candidate edge")
            src, dst = edge.get("source"), edge.get("target")
            if src in by_id and dst in by_id:
                candidate_edges.append((kind, src, dst))
    groups = defaultdict(int)
    evidence_by_group = {}
    seen = set()
    for start in sorted(by_id):
        if start in seen:
            continue
        q = deque([start])
        seen.add(start)
        members = set()
        while q:
            p = q.popleft()
            members.add(p)
            for nxt in adj[p]:
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        if len(members) < 2:
            continue
        families = Counter(by_id[n]["family"] for n in members)
        domains = Counter(domain(by_id[n]["family"]) for n in members)
        hints = Counter(k for k, src, dst in candidate_edges if src in members and dst in members)
        signature_data = {
            "families": dict(sorted(families.items())),
            "domains": dict(sorted(domains.items())),
            "candidate_edge_types": dict(sorted(hints.items())),
        }
        signature = sha256(json.dumps(signature_data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        groups[signature] += 1
        evidence_by_group[signature] = signature_data
    patterns = []
    for signature in sorted(groups):
        entry = evidence_by_group[signature]
        patterns.append({
            "signature_sha256": signature,
            "occurrences": groups[signature],
            **entry,
            "classification": "STATIC_CANDIDATE_ONLY",
            "cross_domain": len([d for d in entry["domains"] if d not in {"unknown", "observation"}]) >= 2,
            "runtime_proven": False,
            "uplift_accepted": False,
        })
    return {
        "schema": SCHEMA,
        "source_schema": SOURCE_SCHEMA,
        "analysis": "structure_only_no_causal_or_gameplay_qualification",
        "node_count": len(by_id),
        "connected_candidate_count": sum(groups.values()),
        "signature_count": len(patterns),
        "patterns": patterns,
        "limitations": [
            "Proximity is not signal conduction or causal influence.",
            "Edges labeled strong by the source analyzer are not runtime-verified here.",
            "Disconnected logical/scoreboard relationships can span physical components.",
            "These domain signatures are not qualified gates, clocks, machines or puzzles.",
            "Version uplift and gameplay equivalence require separate original/target runtime oracles.",
            "Unrepresented blocks, code and entities remain UNKNOWN, not absent.",
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    data = args.graph.read_bytes()
    result = inventory(json.loads(data))
    result["source_graph_sha256"] = sha256(data).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("schema", "node_count", "connected_candidate_count", "signature_count")},
                     sort_keys=True))


if __name__ == "__main__":
    main()
