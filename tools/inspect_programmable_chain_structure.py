#!/usr/bin/env python3
"""Exact Java 26.3 command-chain structure evidence. Programmable domain only."""

from __future__ import annotations
import argparse, json
from pathlib import Path

import discover_minecraft_observability as discovery
import inventory_modern_microscope_symbols as inv
import inspect_modern_microscope_hook_structure as inspect

CLASS="net.minecraft.world.level.block.CommandBlock"
EXPECTED_CLASS_SHA256="2cbe573c4833b44e74a1f41fc83473c1f2a6bc2e7d527b73df5af6b48708ad85"
TARGETS=(
    ("command_execute","execute",
     "(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/server/level/ServerLevel;Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/BaseCommandBlock;Z)V"),
    ("command_execute_chain","executeChain",
     "(Lnet/minecraft/server/level/ServerLevel;Lnet/minecraft/core/BlockPos;Lnet/minecraft/core/Direction;)V"),
    ("command_tick","tick",
     "(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/server/level/ServerLevel;Lnet/minecraft/core/BlockPos;Lnet/minecraft/util/RandomSource;)V"),
)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--work-dir",required=True)
    ap.add_argument("--output",required=True)
    args=ap.parse_args()

    manifest=discovery.fetch_json(discovery.VERSION_MANIFEST_URL)
    row=next(r for r in discovery.resolve_frontier(manifest) if r["channel"]=="release")
    if row["minecraft_version"]!="26.3" or row["java_major"]!=25:
        raise RuntimeError(f"frontier moved: {row['minecraft_version']} java={row['java_major']}")

    work=Path(args.work_dir); work.mkdir(parents=True,exist_ok=True)
    server=work/"server.jar"; discovery.download_verified(row,server)
    runtime=work/"runtime.jar"; inv.extract_runtime_jar(server,runtime)

    actual=inv.sha256_bytes(inv.class_bytes(runtime,CLASS))
    if actual!=EXPECTED_CLASS_SHA256:
        raise RuntimeError(f"CommandBlock class hash changed: {actual}")

    methods={(m["name"],m["descriptor"]) for m in inv.javap_methods(runtime,CLASS)}
    sections=inspect.parse_javap_sections(inspect.javap_code(runtime,CLASS),CLASS)
    rows=[]
    for target_id,name,descriptor in TARGETS:
        key=(name,descriptor)
        if key not in methods or key not in sections:
            raise RuntimeError(f"{target_id}: exact target absent")
        normalized,count=inspect.normalize_method_section(sections[key])
        refs=inspect.symbolic_references(sections[key],CLASS)
        rows.append({
            "id":target_id,
            "runtime_class":CLASS,
            "class_sha256":actual,
            "method_name":name,
            "method_descriptor":descriptor,
            "normalized_code_sha256":inspect.sha256_text(normalized),
            "instruction_count":count,
            **refs,
        })

    doc={
        "schema":"supracraft-programmable-chain-structure/1",
        "edition":"java","minecraft_version":"26.3","domain":"programmable",
        "methods":rows,
        "qualification_status":"structure_only_not_chain_semantics_qualified",
        "boundaries":[
            "execute/executeChain/tick structure is programmable-domain evidence only",
            "no electrical trigger semantics are inferred",
            "runtime chain order/condition behavior remains separately qualified",
        ]
    }
    Path(args.output).write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
        "status":"pass","domain":"programmable",
        "methods":[
            {"id":r["id"],"instruction_count":r["instruction_count"],
             "normalized_code_sha256":r["normalized_code_sha256"],
             "method_ref_count":len(r["method_refs"])}
            for r in rows
        ]
    },indent=2,sort_keys=True))

if __name__=="__main__": main()
