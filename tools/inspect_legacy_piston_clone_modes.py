#!/usr/bin/env python3
"""Original 1.8.8 CORE clone mode evidence from exact fingerprinted source.

Reads selected command block tile entities only in pinned ephemeral source
custody. No raw commands, positions, private graph or world bytes exported.
Never asserts a command actually fired or that a piston moved.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from tools.inspect_legacy_piston_clone_payloads import map_clone_material_source_positions

SCHEMA="supracraft-legacy-piston-clone-mode-audit/1"
MASK_MODES={"replace","masked","filtered"}
CLONE_MODES={"normal","force","move"}


def classify_modes(graph, signature, commands):
    pairs=map_clone_material_source_positions(graph,signature)
    selected={cid for cid,_ in pairs}
    nodes={n["node_id"]:n for n in graph["nodes"]}
    mode_counts=Counter()
    mode2_counts=Counter()
    missing=0
    for cid in selected:
        raw=commands.get(cid)
        if raw is None:
            missing+=1
            continue
        node=nodes[cid]
        fingerprint=(node.get("command") or {}).get("sha256")
        if not isinstance(fingerprint,str) or hashlib.sha256(raw.encode("utf-8")).hexdigest()!=fingerprint:
            raise ValueError("exact original command fingerprint mismatch")
        tokens=raw.strip().lstrip("/").split()
        if not tokens or tokens[0].lower()!="clone" or len(tokens)<10:
            raise ValueError("source command is not a valid clone token layout")
        mask=tokens[10].lower() if len(tokens)>10 else "replace"
        mode=tokens[11].lower() if len(tokens)>11 else "normal"
        mode_counts[mask if mask in MASK_MODES else "unknown_mask_mode"]+=1
        mode2_counts[mode if mode in CLONE_MODES else "unknown_clone_mode"]+=1
    return {
        "schema":SCHEMA,
        "analysis":"fingerprinted_original_saved_clone_command_modes_only",
        "signature_sha256":signature,
        "source_matched_clone_command_count":len(selected)-missing,
        "missing_saved_clone_commands":missing,
        "candidate_clone_command_count":len(selected),
        "source_mask_mode_counts":dict(sorted(mode_counts.items())),
        "source_clone_mode_counts":dict(sorted(mode2_counts.items())),
        "command_execution":"NOT_OBSERVED",
        "actual_target_write":"NOT_OBSERVED",
        "piston_motion":"NOT_OBSERVED",
        "modern_equivalence":"NOT_RUN",
        "gameplay_promoted":False,
        "limitations":[
            "Saved text and command fingerprint establish authorship, not execution.",
            "Clone mask/move modes constrain possible copying, but runtime source state can change.",
            "Exact target effects, power, timing and reset require independently admitted native tests.",
        ],
    }


def read_commands(source_zip, wanted):
    """Bounded original ZIP handling, only selected command tile entity strings."""
    from tools.analyze_legacy_causal_machinery import iter_chunks,chunk_level,find_world_root,plain
    out={}
    with tempfile.TemporaryDirectory(prefix="core-clone-modes-") as td:
        root=Path(td)
        with zipfile.ZipFile(source_zip) as archive:
            info=archive.infolist()
            if len(info)>10000 or sum(x.file_size for x in info)>250*1024*1024:
                raise ValueError("unbounded original ZIP")
            if archive.testzip() is not None:
                raise ValueError("CRC mismatch")
            for entry in info:
                p=PurePosixPath(entry.filename)
                if p.is_absolute() or ".." in p.parts:
                    raise ValueError("unsafe archive path")
            archive.extractall(root)
        world=find_world_root(root)
        for region in sorted((world/"region").glob("r.*.*.mca")):
            for chunk in iter_chunks(region):
                for tile in chunk_level(chunk).get("TileEntities",[]):
                    if not all(k in tile for k in ("x","y","z")):
                        continue
                    pos=tuple(int(plain(tile[k])) for k in ("x","y","z"))
                    nid=",".join(str(v) for v in pos)
                    if nid not in wanted:
                        continue
                    if nid in out:
                        raise ValueError("duplicate original command tile entity")
                    if "Command" not in tile:
                        continue
                    out[nid]=str(plain(tile["Command"]))
    return out


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
    blob=a.graph.read_bytes()
    sha=hashlib.sha256(blob).hexdigest()
    if sha!=a.expected_graph_sha256:
        raise SystemExit("graph source identity mismatch")
    if hashlib.sha256(a.source_zip.read_bytes()).hexdigest()!=a.expected_source_sha256:
        raise SystemExit("source world identity mismatch")
    graph=json.loads(blob)
    selected={cid for cid,_ in map_clone_material_source_positions(graph,a.signature)}
    raw=read_commands(a.source_zip,selected)
    result=classify_modes(graph,a.signature,raw)
    result["source_graph_sha256"]=sha
    result["source_world_sha256"]=a.expected_source_sha256
    serialized=json.dumps(result,indent=2,sort_keys=True)+"\n"
    for token in ('"node_id"','"position"','"command"','"raw"','"target_position"','original-world.zip'):
        if token in serialized:
            raise SystemExit("raw original command egress refused")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(serialized,encoding="utf-8")
    print(json.dumps({
        "matched":result["source_matched_clone_command_count"],
        "missing":result["missing_saved_clone_commands"],
        "mask_modes":result["source_mask_mode_counts"],
        "clone_modes":result["source_clone_mode_counts"],
        "native":"NOT_RUN",
    },sort_keys=True))


if __name__=="__main__":
    main()
