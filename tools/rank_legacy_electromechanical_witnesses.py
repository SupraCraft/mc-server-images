#!/usr/bin/env python3
"""Source-backed electromechanical shortlist from a *complete* legacy graph.

This is discovery, not power delivery or piston motion. No raw world coordinates,
block positions, command bodies, node IDs or source files leave the scanner.
Run only with an admitted, ephemeral, exact-source graph.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path

from tools.classify_legacy_gameplay_motifs import (
    SOURCE_SCHEMA, domain, EDGE_KEYS,
)

SCHEMA = "supracraft-legacy-electromechanical-witness-rank/1"
PISTON = {"piston", "sticky_piston"}
REPEATER = {"repeater_off", "repeater_on"}
WIRE = {"redstone_wire"}
# These are typed *potential* power paths in the original legacy analyzer;
# neither saved power nor actual piston extension follows from their presence.
DIRECT_TYPE = "legacy_dust_direct_component_power"
FRONT_TYPE = "oriented_front_output_candidate"
DUST_TYPE = "legacy_dust_horizontal_connection"
REAR_TYPE = "oriented_rear_input_candidate"


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def rank(graph: dict, *, signature: str | None = None) -> dict:
    if not isinstance(graph, dict) or graph.get("schema") != SOURCE_SCHEMA:
        raise ValueError("unsupported original-epoch graph schema")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, dict):
        raise ValueError("a complete original graph is required")
    by_id = {}
    for n in nodes:
        if not isinstance(n, dict) or not isinstance(n.get("node_id"), str) or not isinstance(n.get("family"), str):
            raise ValueError("invalid original node")
        if n["node_id"] in by_id:
            raise ValueError("duplicate original node identity")
        by_id[n["node_id"]] = n
    adj = defaultdict(set)
    for row in edges.get("physical_adjacency_candidates", []):
        if not isinstance(row, dict):
            raise ValueError("malformed physical candidate")
        a, b = row.get("a"), row.get("b")
        if a not in by_id or b not in by_id or a == b:
            raise ValueError("invalid adjacency endpoint")
        adj[a].add(b)
        adj[b].add(a)
    if "physical_adjacency_candidates" not in edges:
        raise ValueError("missing full adjacency collection")

    # Preserve the exact source domain and direction of each accepted typed
    # candidate. Unknown edges are never invented as connections.
    sources = defaultdict(list)
    for kind in EDGE_KEYS:
        rows = edges.get(kind, [])
        if not isinstance(rows, list):
            raise ValueError("malformed typed collection")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("malformed typed record")
            a, b = row.get("source"), row.get("target")
            if a in by_id and b in by_id:
                sources[a].append((kind, row.get("edge_type"), b))

    seen = set()
    units = []
    for start in sorted(by_id):
        if start in seen:
            continue
        q = deque([start])
        seen.add(start)
        members = set()
        while q:
            v = q.popleft()
            members.add(v)
            for target in adj[v]:
                if target not in seen:
                    seen.add(target)
                    q.append(target)
        if len(members) < 2:
            continue
        families = Counter(by_id[n]["family"] for n in members)
        if not (set(families) & PISTON):
            continue
        domains = Counter(domain(by_id[n]["family"]) for n in members)
        named = Counter(
            kind for a in members
            for kind, _, b in sources.get(a, [])
            if b in members
        )
        sig = _digest({
            "families": dict(sorted(families.items())),
            "domains": dict(sorted(domains.items())),
            "candidate_edge_types": dict(sorted(named.items())),
        })
        if signature is not None and sig != signature:
            continue
        if not (set(families) & WIRE or set(families) & REPEATER):
            continue

        direct = set()
        front = set()
        rear = set()
        dust = set()
        for a in members:
            af = by_id[a]["family"]
            for kind, et, b in sources.get(a, []):
                if b not in members:
                    continue
                bf = by_id[b]["family"]
                if kind == "direct_redstone_edges" and et == DIRECT_TYPE and af in WIRE and bf in PISTON:
                    direct.add((a,b))
                if kind == "oriented_signal_candidates":
                    if et == FRONT_TYPE and af in REPEATER and bf in PISTON:
                        front.add((a,b))
                    elif et == REAR_TYPE and af in WIRE and bf in REPEATER:
                        rear.add((a,b))
                if kind == "direct_redstone_edges" and et == DUST_TYPE and af in WIRE and bf in WIRE:
                    dust.add((a,b))
        if direct:
            disposition = "DIRECT_DUST_TO_PISTON_STATIC_CANDIDATE"
        elif front:
            disposition = "ORIENTED_REPEATER_TO_PISTON_STATIC_CANDIDATE"
        else:
            disposition = "NO_NAMED_PISTON_INPUT"
        units.append({
            "signature_sha256": sig,
            "family_counts": dict(sorted(families.items())),
            "named_edge_type_counts": dict(sorted(named.items())),
            "direct_wire_to_piston_edges": len(direct),
            "oriented_repeater_to_piston_edges": len(front),
            "oriented_wire_to_repeater_edges": len(rear),
            "direct_wire_to_wire_edges": len(dust),
            "disposition": disposition,
            "runtime_qualified": False,
        })

    if signature is not None and not units:
        raise ValueError("target signature has no qualifying electromechanical component")

    grouped = {}
    for u in units:
        sig = u["signature_sha256"]
        if sig not in grouped:
            grouped[sig] = {k:v for k,v in u.items() if k != "runtime_qualified"}
            grouped[sig]["occurrences"] = 0
        grouped[sig]["occurrences"] += 1
        # Units of one signature must have the same structural features.
        for key in ("direct_wire_to_piston_edges","oriented_repeater_to_piston_edges",
                    "oriented_wire_to_repeater_edges","direct_wire_to_wire_edges"):
            if grouped[sig][key] != u[key]:
                raise ValueError("signature collision or inconsistent typed-edge topology")

    results = sorted(grouped.values(), key=lambda x: (
        0 if x["direct_wire_to_piston_edges"] else
        1 if x["oriented_repeater_to_piston_edges"] else 2,
        -x["occurrences"], x["signature_sha256"],
    ))
    return {
        "schema": SCHEMA,
        "source_graph_schema": SOURCE_SCHEMA,
        "analysis": "static_directional_candidate_only",
        "mechanical_signature_count": len(results),
        "mechanical_component_occurrences": len(units),
        "signatures": results,
        "native_original_version_execution": "NOT_RUN",
        "minecraft_26_3_equivalence": "NOT_RUN",
        "causal_power_or_motion_proven": False,
        "metadata_caveat": (
            "Repeater port orientation is a graph candidate only; piston "
            "quasi-connectivity, hidden solid-block conduction, timing, chunk "
            "load and dynamic wire power remain unqualified."
        ),
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--graph",type=Path,required=True)
    p.add_argument("--expected-graph-sha256",required=True)
    p.add_argument("--signature")
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    raw=args.graph.read_bytes()
    actual=hashlib.sha256(raw).hexdigest()
    if actual!=args.expected_graph_sha256:
        raise SystemExit("frozen source graph SHA256 mismatch")
    if args.output.exists():
        raise SystemExit("refuse overwrite")
    result=rank(json.loads(raw),signature=args.signature)
    result["source_graph_sha256"]=actual
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "mechanical_signature_count":result["mechanical_signature_count"],
        "mechanical_component_occurrences":result["mechanical_component_occurrences"],
        "native_original_version_execution":"NOT_RUN",
    },sort_keys=True))


if __name__ == "__main__":
    main()
