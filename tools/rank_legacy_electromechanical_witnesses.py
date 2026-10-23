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
    SOURCE_SCHEMA, domain, EDGE_KEYS, SENSORS,
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
SENSOR_TYPE = "legacy_sensor_direct_dust_power"


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _position(node: dict) -> tuple[int, int, int] | None:
    """Only exact integral physical coordinates; no semantic assumption."""
    raw = node.get("position")
    identity = node.get("node_id", "")
    try:
        ids = tuple(int(x) for x in identity.split(","))
    except (TypeError, ValueError):
        return None
    if len(ids) != 3:
        return None
    if raw is not None:
        if not isinstance(raw, (list, tuple)) or len(raw) != 3:
            return None
        # Reject booleans/fractions and mismatched supplied source positions.
        if any(type(v) is not int for v in raw) or tuple(raw) != ids:
            return None
    return ids


def _horizontal_neighbor(a: dict, b: dict) -> bool:
    pa, pb = _position(a), _position(b)
    return pa is not None and pb is not None and (
        pa[1] == pb[1] and abs(pa[0] - pb[0]) + abs(pa[2] - pb[2]) == 1
    )


def _oriented_port(repeater: dict, neighbor: dict, *, rear: bool) -> bool:
    rp, np = _position(repeater), _position(neighbor)
    delta = (repeater.get("metadata_semantics") or {}).get("facing_vector")
    if rp is None or np is None or not isinstance(delta, list) or len(delta) != 3:
        return False
    if any(type(v) is not int for v in delta):
        return False
    if delta[1] != 0 or abs(delta[0])+abs(delta[2]) != 1:
        return False
    mult = 1 if rear else -1
    return np == tuple(rp[i] + mult*delta[i] for i in range(3))


def _piston_non_head_input(source: dict, piston: dict) -> bool:
    """Exclude the piston head face from ordinary direct-input candidates.

    The Java 1.8.8 piston check skips the face it is extending toward.
    This is only a static port filter: power shape, quasi-connectivity,
    block updates and successful motion still require native observation.
    """
    sp, pp = _position(source), _position(piston)
    meta = piston.get("metadata_semantics")
    if sp is None or pp is None or not isinstance(meta, dict):
        return False
    facing = meta.get("facing_vector")
    if not isinstance(facing, list) or len(facing) != 3:
        return False
    if any(type(v) is not int for v in facing):
        return False
    if sum(abs(v) for v in facing) != 1:
        return False
    return sp != tuple(pp[i] + facing[i] for i in range(3))


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
        pa, pb = _position(by_id[a]), _position(by_id[b])
        if pa is None or pb is None or sum(abs(pa[i]-pb[i]) for i in range(3)) != 1:
            raise ValueError("physical adjacency is not an exact face neighbor")
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
        sensors = set()
        for a in members:
            af = by_id[a]["family"]
            for kind, et, b in sources.get(a, []):
                if b not in members:
                    continue
                bf = by_id[b]["family"]
                if (kind == "direct_redstone_edges" and et == DIRECT_TYPE and
                    af in WIRE and bf in PISTON and
                    _horizontal_neighbor(by_id[a],by_id[b]) and
                    _piston_non_head_input(by_id[a],by_id[b])):
                    direct.add((a,b))
                if kind == "oriented_signal_candidates":
                    if (et == FRONT_TYPE and af in REPEATER and bf in PISTON and
                            _oriented_port(by_id[a],by_id[b],rear=False) and
                            _piston_non_head_input(by_id[a],by_id[b])):
                        front.add((a,b))
                    elif (et == REAR_TYPE and af in WIRE and bf in REPEATER and
                          _oriented_port(by_id[b],by_id[a],rear=True)):
                        rear.add((a,b))
                if (kind == "direct_redstone_edges" and et == DUST_TYPE and
                    af in WIRE and bf in WIRE and b in adj[a] and
                    _horizontal_neighbor(by_id[a],by_id[b])):
                    dust.add((a,b))
                if (kind == "direct_redstone_edges" and et == SENSOR_TYPE and
                    af in SENSORS and bf in WIRE and b in adj[a] and
                    _position(by_id[a]) is not None and _position(by_id[b]) is not None):
                    sensors.add((a,b))

        # Walk only valid named wire links BACK from a named sink input.
        # A connected dust run is not a proven live-powered source.
        upstream = defaultdict(set)
        for a,b in dust:
            upstream[b].add(a)
        roots = {a for a,b in (direct | rear)}
        reachable_wires = set(roots)
        pending = list(roots)
        while pending:
            for src in upstream.get(pending.pop(), ()):
                if src not in reachable_wires:
                    reachable_wires.add(src)
                    pending.append(src)
        reachable_named_sensors = {a for a,b in sensors if b in reachable_wires}
        if not roots:
            input_status = "NO_NAMED_WIRE_TO_ACTUATOR_OR_REPEATER"
        elif not reachable_named_sensors:
            input_status = "NO_NAMED_LOCAL_SENSOR_ON_TYPED_WIRE_PATH"
        else:
            input_status = "NAMED_LOCAL_SENSOR_STATIC_CANDIDATE"
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
            "upstream_named_wire_count": len(reachable_wires),
            "upstream_named_sensor_count": len(reachable_named_sensors),
            "source_input_status": input_status,
            "disposition": disposition,
            "runtime_qualified": False,
        })

    if signature is not None and not units:
        raise ValueError("target signature has no qualifying electromechanical component")

    # Original motif signatures aggregate *counts*, not topology. The same
    # signature may contain genuinely different actuator-facing orientations.
    # Split subtypes rather than silently overgeneralize or discard evidence.
    grouped = {}
    count_keys = (
        "direct_wire_to_piston_edges",
        "oriented_repeater_to_piston_edges",
        "oriented_wire_to_repeater_edges",
        "direct_wire_to_wire_edges",
        "upstream_named_wire_count",
        "upstream_named_sensor_count",
    )
    for u in units:
        key = (u["signature_sha256"], *(u[field] for field in count_keys))
        if key not in grouped:
            grouped[key] = {k:v for k,v in u.items() if k != "runtime_qualified"}
            grouped[key]["occurrences"] = 0
            grouped[key]["directional_subtype_sha256"] = _digest({
                "signature_sha256": u["signature_sha256"],
                "typed_port_candidate_counts": {k:u[k] for k in count_keys},
                "source_input_status":u["source_input_status"],
            })
        grouped[key]["occurrences"] += 1

    results = sorted(grouped.values(), key=lambda x: (
        0 if x["direct_wire_to_piston_edges"] else
        1 if x["oriented_repeater_to_piston_edges"] else 2,
        -x["occurrences"], x["signature_sha256"],
    ))
    return {
        "schema": SCHEMA,
        "source_graph_schema": SOURCE_SCHEMA,
        "analysis": "static_directional_candidate_only",
        "mechanical_signature_count": len({u["signature_sha256"] for u in units}),
        "mechanical_directional_subtype_count": len(results),
        "mechanical_component_occurrences": len(units),
        "signatures": results,
        "native_original_version_execution": "NOT_RUN",
        "minecraft_26_3_equivalence": "NOT_RUN",
        "causal_power_or_motion_proven": False,
        "metadata_caveat": (
            "Repeater port orientation is a graph candidate only; piston "
            "quasi-connectivity, hidden solid-block conduction, timing, chunk "
            "load, piston head-face exclusion and dynamic wire power remain unqualified; "
            "absence of a named local sensor is not absence of external or indirect power."
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
