#!/usr/bin/env python3
"""Read-only Java 1.8.8 CORE clone source→destination saved-state contrast.

Source graphs, original archive and exact coordinates stay in ephemeral custody.
Public derivative contains aggregate material/equality counts only, never raw
source positions, commands, NBT, block IDs, or per-command identities.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from tools.audit_legacy_piston_authored_inputs import _exact_integer_position
from tools.inspect_legacy_piston_clone_payloads import (
    GROUPED_CLASSES, map_clone_material_source_positions,
)
from tools.inspect_legacy_piston_clone_modes import read_commands, classify_modes

SCHEMA = "supracraft-legacy-piston-clone-saved-delta/1"
ROLES = {"source_start", "source_end", "destination"}


def clone_source_dest_pairs(graph: dict, signature: str):
    """Internally recover the destination for each already qualified source cell."""
    source_pairs = map_clone_material_source_positions(graph, signature)
    targets = defaultdict(list)
    for row in graph["edges"].get("command_world_targets", []):
        if not isinstance(row, dict):
            raise ValueError("malformed source target")
        if row.get("target_kind") in ROLES:
            targets[row.get("source")].append(row)
    resolved = {}
    for cid in {cid for cid, _ in source_pairs}:
        rows = targets.get(cid, [])
        if len(rows) != 3 or {r.get("target_kind") for r in rows} != ROLES:
            raise ValueError("ambiguous original clone endpoint")
        positions = {r["target_kind"]: _exact_integer_position(r.get("target_position"))
                     for r in rows}
        if any(p is None for p in positions.values()):
            raise ValueError("nonintegral original clone endpoint")
        src_lo = tuple(min(positions["source_start"][i],
                           positions["source_end"][i]) for i in range(3))
        resolved[cid] = (src_lo, positions["destination"])
    pairs = []
    seen = set()
    for cid, src in source_pairs:
        lo, dst = resolved[cid]
        dest = tuple(dst[i] + src[i] - lo[i] for i in range(3))
        ident = (cid, src, dest)
        if ident in seen:
            raise ValueError("duplicate clone source→destination sample")
        seen.add(ident)
        pairs.append((src, dest))
    return pairs


def classify_deltas(pairs: list, blocks: dict) -> dict:
    state_outcomes = Counter()
    sources = Counter()
    destinations = Counter()
    transitions = Counter()
    unknown = 0
    for src, dst in pairs:
        a, b = blocks.get(src), blocks.get(dst)
        if a is None or b is None:
            unknown += 1
            continue
        # Exactly two primitive attributes are compared, not execution results.
        if any(type(v) is not int for v in (*a, *b)):
            raise ValueError("nonintegral saved block state")
        if not (0 <= a[0] <= 4095 and 0 <= b[0] <= 4095 and
                0 <= a[1] <= 15 and 0 <= b[1] <= 15):
            raise ValueError("impossible saved block ID/metadata")
        sa = GROUPED_CLASSES.get(a[0], "other_saved_block_id")
        sb = GROUPED_CLASSES.get(b[0], "other_saved_block_id")
        sources[sa] += 1
        destinations[sb] += 1
        if a == b:
            state_outcomes["exact_id_and_metadata_equal"] += 1
        elif a[0] == b[0]:
            state_outcomes["same_id_different_metadata"] += 1
        else:
            state_outcomes["different_block_id"] += 1
        transitions[sa + "_to_" + sb] += 1
    return {
        "candidate_pair_samples": len(pairs),
        "resolved_saved_pairs":len(pairs) - unknown,
        "unresolved_saved_pairs":unknown,
        "saved_state_equality_counts":dict(sorted(state_outcomes.items())),
        "source_material_class_counts":dict(sorted(sources.items())),
        "destination_material_class_counts":dict(sorted(destinations.items())),
        "source_to_destination_class_pairs":dict(sorted(transitions.items())),
        "candidate_nonidentical_saved_pairs": (
            state_outcomes["same_id_different_metadata"] +
            state_outcomes["different_block_id"]
        ),
        "candidate_world_write":"NOT_EXECUTED",
        "source_state_runtime_stability":"UNKNOWN",
        "piston_motion":"NOT_OBSERVED",
        "modern_26_3_equivalence":"NOT_RUN",
        "gameplay_promoted":False,
    }


def audit(graph: dict, signature: str, blocks: dict,
          commands: dict) -> dict:
    pairs = clone_source_dest_pairs(graph, signature)
    expected_ids = {cid for cid, _ in
                    map_clone_material_source_positions(graph, signature)}
    modes = classify_modes(graph, signature, commands)
    if modes["source_matched_clone_command_count"] != len(expected_ids):
        raise ValueError("clone command source provenance missing")
    if (modes["source_mask_mode_counts"] != {"replace":len(expected_ids)}
            or modes["source_clone_mode_counts"] != {"normal":len(expected_ids)}):
        raise ValueError("clone mode is not pinned replace normal")
    return {
        "schema":SCHEMA,
        "analysis":"original_saved_source_destination_static_comparison_only",
        "signature_sha256":signature,
        "verified_source_clone_commands":len(expected_ids),
        "verified_clone_mask_mode":"replace",
        "verified_clone_execution_mode":"normal",
        **classify_deltas(pairs, blocks),
        "limitations":[
            "Original saved snapshots are not an executed clone and may be stale at runtime.",
            "Block ID and 4-bit metadata parity excludes tile entity NBT, entities and ticks.",
            "Potential differences establish a restoration/reconfiguration candidate only.",
            "Command activation, power propagation, piston movement and reset are NOT RUN.",
        ],
    }


def read_saved_states(source_zip: Path, positions: set) -> dict:
    """Read only bounded original Anvil cells and their 1.8.8 block metadata."""
    from tools.analyze_legacy_causal_machinery import (
        iter_chunks, chunk_level, find_world_root, byte_values, nibble_at, plain,
    )
    grouped = defaultdict(set)
    for p in positions:
        if len(p) != 3 or any(type(v) is not int for v in p):
            raise ValueError("invalid requested private position")
        if 0 <= p[1] < 256:
            grouped[(p[0]//16,p[2]//16)].add(p)
    states = {}
    with tempfile.TemporaryDirectory(prefix="core-clone-delta-") as td:
        root=Path(td)
        with zipfile.ZipFile(source_zip) as archive:
            entries=archive.infolist()
            if len(entries)>10000 or sum(x.file_size for x in entries)>250*1024*1024:
                raise ValueError("unbounded original ZIP")
            if archive.testzip() is not None:
                raise ValueError("original ZIP CRC mismatch")
            for entry in entries:
                p=PurePosixPath(entry.filename)
                if p.is_absolute() or ".." in p.parts:
                    raise ValueError("unsafe ZIP path")
            archive.extractall(root)
        world=find_world_root(root)
        visited=set()
        for region in sorted((world/"region").glob("r.*.*.mca")):
            for chunk in iter_chunks(region):
                level=chunk_level(chunk)
                coord=(int(plain(level.get("xPos",0))),
                       int(plain(level.get("zPos",0))))
                if coord not in grouped:
                    continue
                if coord in visited:
                    raise ValueError("duplicate requested original chunk")
                visited.add(coord)
                sections={int(plain(s.get("Y",0))):s
                          for s in level.get("Sections",[])
                          if s.get("Blocks") is not None}
                arrays={}
                for p in grouped[coord]:
                    sec=sections.get(p[1]//16)
                    if sec is None:
                        states[p]=(0,0)  # existing chunk, absent section = air
                        continue
                    if sec.get("Data") is None:
                        continue  # missing metadata => unresolved, never assume 0
                    sy=p[1]//16
                    if sy not in arrays:
                        arrays[sy]=(byte_values(sec["Blocks"]),
                                    sec["Data"], sec.get("Add"))
                    base,data,added=arrays[sy]
                    i=(p[0]%16)+((p[2]%16)<<4)+((p[1]%16)<<8)
                    block=base[i]
                    if added is not None:
                        block |= nibble_at(added,i)<<8
                    states[p]=(block,nibble_at(data,i))
    return states


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--graph",type=Path,required=True)
    p.add_argument("--source-zip",type=Path,required=True)
    p.add_argument("--expected-graph-sha256",required=True)
    p.add_argument("--expected-source-sha256",required=True)
    p.add_argument("--signature",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():
        raise SystemExit("refuse overwrite")
    raw=a.graph.read_bytes()
    gh=hashlib.sha256(raw).hexdigest()
    if gh!=a.expected_graph_sha256:
        raise SystemExit("frozen graph SHA mismatch")
    if hashlib.sha256(a.source_zip.read_bytes()).hexdigest()!=a.expected_source_sha256:
        raise SystemExit("frozen original ZIP SHA mismatch")
    graph=json.loads(raw)
    pairs=clone_source_dest_pairs(graph,a.signature)
    wanted={p for src,dst in pairs for p in (src,dst)}
    blocks=read_saved_states(a.source_zip,wanted)
    cmds={cid for cid, _ in map_clone_material_source_positions(graph,a.signature)}
    original_commands=read_commands(a.source_zip,cmds)
    result=audit(graph,a.signature,blocks,original_commands)
    result["source_graph_sha256"]=gh
    result["source_world_sha256"]=a.expected_source_sha256
    serialized=json.dumps(result,sort_keys=True,indent=2)+"\n"
    for fragment in ('"node_id"','"position"','"command"','"target_position"',
                     'original-world.zip','"raw"'):
        if fragment in serialized:
            raise SystemExit("raw source in public derivative")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(serialized,encoding="utf-8")
    print(json.dumps({
        "total":result["candidate_pair_samples"],
        "resolved":result["resolved_saved_pairs"],
        "delta_classes":result["saved_state_equality_counts"],
        "candidate_not_equal":result["candidate_nonidentical_saved_pairs"],
        "source_materials":result["source_material_class_counts"],
        "destination_materials":result["destination_material_class_counts"],
        "native":"NOT_RUN",
    },sort_keys=True))


if __name__=="__main__":
    main()
