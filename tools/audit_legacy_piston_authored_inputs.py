#!/usr/bin/env python3
"""Read-only original CORE command-write joins for two piston candidate inputs.

Source graph is an independently pinned existing derivative. No source command
text, world coordinates, node identifiers or target coordinates in public output.
All matches are static hypotheses, not observed execution, power, or motion.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from tools.inspect_legacy_piston_snapshot_inputs import select_component_wires, DIRECTIONS
from tools.rank_legacy_electromechanical_witnesses import rank, _position

SCHEMA = "supracraft-legacy-piston-authored-input-sources/1"
SINK_FAMILIES = {"repeater_off", "repeater_on"}
SOURCE_FAMILIES = {"command_block", "chain_command_block", "repeating_command_block"}


def _exact_integer_position(raw):
    """Return integral world coordinates or UNKNOWN, never round the source."""
    import math
    if not isinstance(raw, list) or len(raw) != 3:
        return None
    if any(type(v) not in (int, float) or not math.isfinite(v) or int(v) != v for v in raw):
        return None
    return tuple(int(v) for v in raw)


def spatial_mutator_contacts(graph: dict, contacts: set) -> dict:
    """Bounding-write candidates only, derived from existing trusted target kinds.

    No source command parsing, command execution, expansion of huge fill volumes
    or publication of map coordinates. Payload/material is NOT qualified.
    """
    records = graph["edges"].get("command_world_targets", [])
    if not isinstance(records, list):
        raise ValueError("invalid command world target collection")
    groups = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("malformed command target")
        if record.get("target_kind") in {
            "region_start","region_end","source_start","source_end","destination"
        }:
            groups.setdefault(record.get("source"), []).append(record)
    resolved = Counter()
    overlap = Counter()
    unknown = Counter()
    for node in graph["nodes"]:
        if node.get("family") not in SOURCE_FAMILIES:
            continue
        verb = (node.get("command") or {}).get("verb")
        if verb not in {"fill","clone","execute"}:
            continue
        if verb == "execute":
            unknown["execute_nested_context"] += 1
            continue
        rows = groups.get(node["node_id"], [])
        expected = ({"region_start","region_end"} if verb=="fill" else
                    {"source_start","source_end","destination"})
        kinds = [r.get("target_kind") for r in rows]
        positions = {r.get("target_kind"):_exact_integer_position(r.get("target_position"))
                     for r in rows}
        if len(rows) != len(expected) or set(kinds) != expected or any(
            positions.get(k) is None for k in expected
        ):
            unknown[verb+"_unresolved_bounds"] += 1
            continue
        if verb == "fill":
            start,end = positions["region_start"],positions["region_end"]
            lo=tuple(min(start[i],end[i]) for i in range(3))
            hi=tuple(max(start[i],end[i]) for i in range(3))
        else:
            start,end,dest=(positions["source_start"],positions["source_end"],
                            positions["destination"])
            lo=dest
            hi=tuple(dest[i]+abs(end[i]-start[i]) for i in range(3))
        resolved[verb+"_resolved_target_footprint"] += 1
        if any(all(lo[i]<=c[i]<=hi[i] for i in range(3)) for c in contacts):
            overlap[verb+"_candidate_wire_contact_overlap"] += 1
    return {
        "resolved_spatial_write_footprints":dict(sorted(resolved.items())),
        "spatial_write_footprint_candidate_overlaps":dict(sorted(overlap.items())),
        "unresolved_spatial_commands":dict(sorted(unknown.items())),
        "spatial_footprint_interpretation":"POSSIBLE_TARGET_ONLY_MATERIAL_AND_EXECUTION_UNKNOWN",
    }


def audit(graph: dict, signature: str) -> dict:
    wires_by_component = select_component_wires(graph, signature)
    ranked = rank(graph, signature=signature)
    if ranked["mechanical_component_occurrences"] != len(wires_by_component):
        raise ValueError("ranker/source component mismatch")
    nodes = graph["nodes"]
    by_id = {n["node_id"]: n for n in nodes}
    if len(by_id) != len(nodes):
        raise ValueError("duplicate source nodes")
    rear_inputs = set()
    for row in graph["edges"].get("oriented_signal_candidates", []):
        if row.get("edge_type") != "oriented_rear_input_candidate":
            continue
        target = by_id.get(row.get("target"))
        source = by_id.get(row.get("source"))
        if target is None or source is None or target.get("family") not in SINK_FAMILIES or source.get("family") != "redstone_wire":
            continue
        sp, tp = _position(source), _position(target)
        facing = (target.get("metadata_semantics") or {}).get("facing_vector")
        if sp is None or tp is None or not isinstance(facing, list) or len(facing) != 3 or any(type(v) is not int for v in facing):
            continue
        if sp != tuple(tp[i] + facing[i] for i in range(3)):
            continue
        if any(sp in c for c in wires_by_component):
            rear_inputs.add(tuple(tp[i] + facing[i] for i in range(3)))

    contacts = set()
    for component in wires_by_component:
        for pos in component:
            for delta in DIRECTIONS:
                contacts.add(tuple(pos[i]+delta[i] for i in range(3)))
    counters = Counter()
    write_count = 0
    unsupported_command_count = 0
    seen = set()
    for node in nodes:
        if node.get("family") not in SOURCE_FAMILIES:
            continue
        command = node.get("command") or {}
        verb = command.get("verb")
        if verb in {"fill", "clone", "execute"}:
            unsupported_command_count += 1
        writes = command.get("authored_world_state_writes") or []
        if not isinstance(writes, list):
            raise ValueError("invalid source write list")
        for w in writes:
            if not isinstance(w, dict) or w.get("write_kind") != "setblock":
                raise ValueError("untrusted authored write kind")
            if verb != "setblock":
                raise ValueError("non-setblock source declared compact setblock writer")
            cls = w.get("state_class")
            if cls not in {"redstone_block", "air"}:
                raise ValueError("unqualified source state class")
            raw = w.get("position")
            if not isinstance(raw, list) or len(raw)!=3 or any(type(v) is not int for v in raw):
                raise ValueError("bad source-authored target")
            target = tuple(raw)
            identity = (node["node_id"],target,cls)
            if identity in seen:
                raise ValueError("duplicate source write")
            seen.add(identity)
            write_count += 1
            if target in contacts:
                counters[cls+"_six_face_wire_contact"] += 1
            if target in rear_inputs:
                counters[cls+"_repeater_rear_position"] += 1

    spatial = spatial_mutator_contacts(graph, contacts)
    near_redstone = sum(v for k,v in counters.items() if k.startswith("redstone_block"))
    return {
        "schema": SCHEMA,
        "evidence_class": "SOURCE_GRAPH_STATIC_ONLY",
        "source_signature_sha256": signature,
        "original_runtime": "1.8.8",
        "qualified_component_count": len(wires_by_component),
        "wire_occurrences":sum(len(c) for c in wires_by_component),
        "unique_six_face_positions_sampled": len(contacts),
        "source_authored_compact_setblock_write_count":write_count,
        "unsupported_fill_clone_execute_command_count":unsupported_command_count,
        "source_authored_relevant_write_counts":dict(sorted(counters.items())),
        **spatial,
        "source_dynamic_input_classification":(
            "SOURCE_AUTHORED_REDSTONE_BLOCK_CONTACT_STATIC_CANDIDATE"
            if near_redstone else "NO_COMPACT_SOURCE_AUTHORED_REDSTONE_BLOCK_CONTACT"
        ),
        "original_native_execution":"NOT_RUN",
        "actual_redstone_power":"NOT_OBSERVED",
        "piston_motion":"NOT_OBSERVED",
        "minecraft_26_3_equivalence":"NOT_RUN",
        "gameplay_promoted":False,
        "limitations":[
            "Only compact source-graph setblock redstone_block/air writes were resolved.",
            "Fill/clone bounds only indicate possible targets; source payload and execution are UNKNOWN.",
            "Execute, unresolved target semantics, nested selectors and unmodeled commands remain UNKNOWN.",
            "A written target is not a proof that the command executes.",
            "Indirect solid conduction, timing and quasi-connectivity remain UNKNOWN.",
            "Source coordinates and command text must not be exported.",
        ],
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--graph",type=Path,required=True)
    p.add_argument("--expected-graph-sha256",required=True)
    p.add_argument("--signature",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        raise SystemExit("refuse overwrite")
    data=a.graph.read_bytes()
    actual=hashlib.sha256(data).hexdigest()
    if actual != a.expected_graph_sha256:
        raise SystemExit("frozen graph SHA mismatch")
    result=audit(json.loads(data),a.signature)
    result["source_graph_sha256"]=actual
    serialized=json.dumps(result,sort_keys=True,indent=2)+"\n"
    for forbidden in ('"node_id"','"position"','"target_position"','"command"','"raw"','original-world.zip'):
        if forbidden in serialized:
            raise SystemExit("raw source in public derivative")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(serialized,encoding="utf-8")
    print(json.dumps({
        "classification":result["source_dynamic_input_classification"],
        "compact_writes":result["source_authored_compact_setblock_write_count"],
        "relevant_counts":result["source_authored_relevant_write_counts"],
        "native":"NOT_RUN",
    },sort_keys=True))


if __name__=="__main__":
    main()
