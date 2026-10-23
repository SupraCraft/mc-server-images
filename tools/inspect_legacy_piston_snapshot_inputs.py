#!/usr/bin/env python3
"""Custody-only original Java 1.8.8 saved-block survey near selected piston wires.

No runtime, injected stimulus, original-world edit or raw coordinate export.
Runs on the already pinned CORE v1.4 source/graph inside a disposable workcell.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from tools.classify_legacy_gameplay_motifs import EDGE_KEYS, domain
from tools.rank_legacy_electromechanical_witnesses import _digest, _position, rank

SCHEMA = "supracraft-legacy-piston-source-snapshot/1"
DIRECTIONS = ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))
POWER_IDS = {
    152: "saved_redstone_block_contact",
    76: "saved_lit_redstone_torch_contact",
    75: "saved_unlit_redstone_torch_contact",
    69: "saved_lever_contact",
    77: "saved_stone_button_contact",
    143: "saved_wooden_button_contact",
    70: "saved_stone_plate_contact",
    72: "saved_wooden_plate_contact",
    147: "saved_light_plate_contact",
    148: "saved_heavy_plate_contact",
}

def select_component_wires(graph: dict, signature: str) -> list[tuple[tuple[int,int,int], ...]]:
    """Private ephemeral component selection using same legacy motif signature."""
    if graph.get("schema") != "supracraft-legacy-causal-machinery/1":
        raise ValueError("unaccepted source graph")
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, dict):
        raise ValueError("incomplete source graph")
    by_id = {}
    for n in nodes:
        if not isinstance(n, dict) or not isinstance(n.get("node_id"), str) or not isinstance(n.get("family"), str):
            raise ValueError("malformed node")
        if n["node_id"] in by_id:
            raise ValueError("duplicate node identity")
        by_id[n["node_id"]] = n
    adj = defaultdict(set)
    physical = edges.get("physical_adjacency_candidates")
    if not isinstance(physical, list):
        raise ValueError("missing original adjacency")
    for row in physical:
        if not isinstance(row, dict):
            raise ValueError("malformed adjacency")
        a,b = row.get("a"),row.get("b")
        if a not in by_id or b not in by_id or a == b:
            raise ValueError("invalid physical endpoint")
        pa,pb = _position(by_id[a]),_position(by_id[b])
        if pa is None or pb is None or sum(abs(pa[i]-pb[i]) for i in range(3)) != 1:
            raise ValueError("untrusted physical adjacency")
        adj[a].add(b)
        adj[b].add(a)

    candidate_edges = []
    for kind in sorted(EDGE_KEYS):
        rows = edges.get(kind, [])
        if not isinstance(rows, list):
            raise ValueError("malformed named collection")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("malformed named edge")
            a,b = row.get("source"),row.get("target")
            if a in by_id and b in by_id:
                candidate_edges.append((kind,a,b))

    seen = set()
    components = []
    for start in sorted(by_id):
        if start in seen:
            continue
        pending = deque([start])
        seen.add(start)
        members=set()
        while pending:
            u=pending.popleft()
            members.add(u)
            for v in adj[u]:
                if v not in seen:
                    seen.add(v)
                    pending.append(v)
        families=Counter(by_id[n]["family"] for n in members)
        if "piston" not in families and "sticky_piston" not in families:
            continue
        domains=Counter(domain(by_id[n]["family"]) for n in members)
        hints=Counter(k for k,a,b in candidate_edges if a in members and b in members)
        current=_digest({
            "families":dict(sorted(families.items())),
            "domains":dict(sorted(domains.items())),
            "candidate_edge_types":dict(sorted(hints.items())),
        })
        if current != signature:
            continue
        wires=tuple(sorted(_position(by_id[n]) for n in members
                           if by_id[n]["family"]=="redstone_wire"))
        if not wires or any(p is None for p in wires):
            raise ValueError("invalid wire coordinates")
        components.append(wires)
    # Independent consistency with the existing directional ranker: no silent
    # alternative component identity or count.
    expected=rank(graph,signature=signature)["mechanical_component_occurrences"]
    if len(components) != expected:
        raise ValueError("original component census mismatch")
    return components


def summarize_contacts(components, saved_blocks: dict) -> dict:
    """Public-safe aggregate only. saved_blocks is ephemeral coordinate→block ID."""
    classes=Counter()
    sampled=0
    unknown=0
    for wires in components:
        for pos in wires:
            for delta in DIRECTIONS:
                np=tuple(pos[i]+delta[i] for i in range(3))
                sampled+=1
                block=saved_blocks.get(np)
                if block is None:
                    unknown+=1
                elif block in POWER_IDS:
                    classes[POWER_IDS[block]]+=1
    return {
        "component_count":len(components),
        "wire_occurrences":sum(len(w) for w in components),
        "saved_six_face_contact_samples":sampled,
        "unresolved_snapshot_contact_samples":unknown,
        "source_class_contact_counts":dict(sorted(classes.items())),
        "saved_adjacent_redstone_block_contacts":classes["saved_redstone_block_contact"],
        "saved_direct_block_source_status":(
            "SAVED_ADJACENT_REDSTONE_BLOCK_STATIC_CANDIDATE"
            if classes["saved_redstone_block_contact"]
            else "NO_SAVED_ADJACENT_REDSTONE_BLOCK_IN_SAMPLED_SIX_FACES"
        ),
        "actual_power_transfer":"NOT_OBSERVED",
        "original_version_native_execution":"NOT_RUN",
        "causal_power_or_motion_proven":False,
    }


def read_target_blocks(source_zip: Path, positions: set) -> dict:
    """No source block data escapes this function except by aggregate counts."""
    # Lazy import: source-free synthetic tests require no proprietary/world libs.
    from tools.analyze_legacy_causal_machinery import (
        iter_chunks, chunk_level, find_world_root, byte_values, nibble_at, plain,
    )
    target=defaultdict(set)
    for x,y,z in positions:
        if 0 <= y < 256:
            target[(x//16,z//16)].add((x,y,z))
    result={}
    with tempfile.TemporaryDirectory(prefix="core-snapshot-custody-") as td:
        root=Path(td)
        with zipfile.ZipFile(source_zip) as archive:
            infos=archive.infolist()
            if len(infos)>10000 or sum(x.file_size for x in infos)>250*1024*1024:
                raise ValueError("source archive exceeds bounded custody")
            if archive.testzip() is not None:
                raise ValueError("original ZIP CRC mismatch")
            for item in infos:
                p=PurePosixPath(item.filename)
                if p.is_absolute() or ".." in p.parts:
                    raise ValueError("unsafe archive path")
            archive.extractall(root)
        world=find_world_root(root)
        for region in sorted((world/"region").glob("r.*.*.mca")):
            for chunk in iter_chunks(region):
                level=chunk_level(chunk)
                coords=(int(plain(level.get("xPos",0))),int(plain(level.get("zPos",0))))
                if coords not in target:
                    continue
                sections={int(plain(sec.get("Y",0))):sec
                          for sec in level.get("Sections",[]) if sec.get("Blocks") is not None}
                # Grouping/lookup must obey legacy Anvil index layout.
                for x,y,z in target[coords]:
                    sec=sections.get(y//16)
                    if sec is None:
                        result[(x,y,z)]=0
                        continue
                    i=(x%16) + ((z%16)<<4) + ((y%16)<<8)
                    data=byte_values(sec["Blocks"])
                    block=data[i]
                    if sec.get("Add") is not None:
                        block |= nibble_at(sec["Add"],i)<<8
                    result[(x,y,z)]=block
    return result


def inspect(graph: dict, signature: str, saved_blocks: dict) -> dict:
    wires=select_component_wires(graph,signature)
    out=summarize_contacts(wires,saved_blocks)
    return {
        "schema":SCHEMA,
        "analysis":"original_saved_blocks_static_six_face_contacts_only",
        "signature_sha256":signature,
        **out,
        "limitations":[
            "Original saved blocks are not real-time 1.8.8 powered state.",
            "The six-face neighborhood excludes diagonal, indirect solid conduction and quasi-connectivity.",
            "Dynamic command-authored power and remotely changed blocks are unresolved.",
            "An absent saved redstone block is not evidence of no source or no gameplay.",
        ],
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--graph",type=Path,required=True)
    p.add_argument("--source-zip",type=Path,required=True)
    p.add_argument("--expected-graph-sha256",required=True)
    p.add_argument("--expected-source-sha256",required=True)
    p.add_argument("--signature",required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():
        raise SystemExit("refuse overwrite")
    raw=args.graph.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=args.expected_graph_sha256:
        raise SystemExit("graph source identity mismatch")
    if hashlib.sha256(args.source_zip.read_bytes()).hexdigest()!=args.expected_source_sha256:
        raise SystemExit("original ZIP source identity mismatch")
    graph=json.loads(raw)
    wires=select_component_wires(graph,args.signature)
    all_contacts={tuple(p[i]+d[i] for i in range(3))
                  for component in wires for p in component for d in DIRECTIONS}
    saved=read_target_blocks(args.source_zip,all_contacts)
    result=inspect(graph,args.signature,saved)
    result["source_graph_sha256"]=args.expected_graph_sha256
    result["source_world_sha256"]=args.expected_source_sha256
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    public=args.output.read_text()
    for secret in ('"node_id"','"position"','"command"','"world_target"','"raw_world"'):
        if secret in public:
            raise SystemExit("derived-only privacy check failure")
    print(json.dumps({
        "saved_adjacent_redstone_block_contacts":result["saved_adjacent_redstone_block_contacts"],
        "wire_occurrences":result["wire_occurrences"],
        "unresolved_snapshot_contact_samples":result["unresolved_snapshot_contact_samples"],
        "native":"NOT_RUN",
    },sort_keys=True))


if __name__=="__main__":
    main()
