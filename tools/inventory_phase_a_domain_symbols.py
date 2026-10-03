#!/usr/bin/env python3
"""Exact Java 26.3 Phase-A domain symbol inventory.

Discovery only. Class/method identity does not qualify runtime semantics.
Each domain is inventoried independently from the exact official server artifact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import discover_minecraft_observability as discovery
import inventory_modern_microscope_symbols as core


SCHEMA="supracraft-phase-a-domain-symbol-inventory/1"

ROLE_SETS={
    "mechanical":{
        "piston_base":"net/minecraft/world/level/block/piston/PistonBaseBlock.class",
        "piston_moving_entity":"net/minecraft/world/level/block/piston/PistonMovingBlockEntity.class",
    },
    "programmable":{
        "command_block":"net/minecraft/world/level/block/CommandBlock.class",
        "command_block_entity":"net/minecraft/world/level/block/entity/CommandBlockEntity.class",
        "command_dispatch":"net/minecraft/commands/Commands.class",
    },
    "inventory":{
        "hopper_block":"net/minecraft/world/level/block/HopperBlock.class",
        "hopper_block_entity":"net/minecraft/world/level/block/entity/HopperBlockEntity.class",
    },
}

TOKEN_HINTS={
    "piston_base":("piston","move","extend","retract","push","neighbor","trigger"),
    "piston_moving_entity":("tick","move","progress","final","piston"),
    "command_block":("neighbor","tick","command","execute"),
    "command_block_entity":("command","execute","perform"),
    "command_dispatch":("command","execute","perform"),
    "hopper_block":("neighbor","tick","hopper","state"),
    "hopper_block_entity":("tick","hopper","push","suck","eject","transfer","inventory","extract"),
}


def locate(runtime_jar: Path, domain: str) -> dict[str,str]:
    import zipfile
    with zipfile.ZipFile(runtime_jar) as zf:
        names=set(zf.namelist())
    rows={}
    for role,path in ROLE_SETS[domain].items():
        if path not in names:
            raise RuntimeError(f"{domain}:{role}: exact class absent: {path}")
        rows[role]=path[:-6].replace("/",".")
    return rows


def candidate_methods(role: str, methods: list[dict]) -> list[dict]:
    hints=TOKEN_HINTS[role]
    return [row for row in methods if any(h in row["name"].lower() for h in hints)]


def inventory(args):
    manifest=discovery.fetch_json(args.manifest_url)
    rows=discovery.resolve_frontier(manifest)
    row=next(r for r in rows if r["channel"]=="release")
    if row["minecraft_version"]!=args.expected_version:
        raise RuntimeError(
            f"release moved: expected {args.expected_version}, observed {row['minecraft_version']}"
        )
    if row["java_major"]!=args.expected_java:
        raise RuntimeError(
            f"Java moved: expected {args.expected_java}, observed {row['java_major']}"
        )

    work=Path(args.work_dir)
    work.mkdir(parents=True,exist_ok=True)
    server=work/"server.jar"
    discovery.download_verified(row,server)
    runtime=work/"embedded-runtime.jar"
    core.extract_runtime_jar(server,runtime)

    located=locate(runtime,args.domain)
    classes=[]
    for role,class_name in sorted(located.items()):
        methods=core.javap_methods(runtime,class_name)
        if not methods:
            raise RuntimeError(f"{args.domain}:{role}: no methods discovered")
        classes.append({
            "role":role,
            "runtime_class":class_name,
            "class_sha256":core.sha256_bytes(core.class_bytes(runtime,class_name)),
            "method_count":len(methods),
            "methods":methods,
            "name_token_candidates":candidate_methods(role,methods),
        })

    doc={
        "schema":SCHEMA,
        "edition":"java",
        "minecraft_version":row["minecraft_version"],
        "java_major":row["java_major"],
        "server_sha1":row["server_sha1"],
        "domain":args.domain,
        "classes":classes,
        "qualification_status":"inventory_only_not_semantics_qualified",
        "boundaries":[
            "each Phase-A domain is inventoried independently",
            "exact class/method identity is discovery evidence only",
            "name-token candidates are search aids only",
            "runtime semantics require source/bytecode review plus bounded vanilla runtime evidence",
            "no cross-domain transducer semantics are inferred here",
        ],
    }
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
        "domain":args.domain,
        "minecraft_version":doc["minecraft_version"],
        "classes":[
            {
                "role":c["role"],
                "runtime_class":c["runtime_class"],
                "class_sha256":c["class_sha256"],
                "method_count":c["method_count"],
                "candidate_count":len(c["name_token_candidates"]),
                "candidate_names":[m["name"] for m in c["name_token_candidates"]],
            }
            for c in classes
        ],
        "status":"pass",
    },indent=2,sort_keys=True))


def parser():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest-url",default=discovery.VERSION_MANIFEST_URL)
    p.add_argument("--domain",choices=sorted(ROLE_SETS),required=True)
    p.add_argument("--expected-version",default="26.3")
    p.add_argument("--expected-java",type=int,default=25)
    p.add_argument("--work-dir",required=True)
    p.add_argument("--output",required=True)
    p.set_defaults(func=inventory)
    return p


if __name__=="__main__":
    args=parser().parse_args()
    args.func(args)
