#!/usr/bin/env python3
"""Exact Java 26.3 structure evidence for HopperBlock.checkPoweredState.

This is boundary-discovery evidence only. It does not qualify the producer or
consumer semantics of any neighboring signal.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

import discover_minecraft_observability as discovery
import inventory_modern_microscope_symbols as inv
import inspect_modern_microscope_hook_structure as inspect

CLASS="net.minecraft.world.level.block.HopperBlock"
EXPECTED_CLASS_SHA256="f13ffbd946b38604fd4a38ce4097e4d69a81627cac8c73cce8ab9608890c30d9"
NAME="checkPoweredState"
DESCRIPTOR="(Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/block/state/BlockState;)V"

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
        raise RuntimeError(f"HopperBlock class hash changed: {actual}")

    methods={(m["name"],m["descriptor"]) for m in inv.javap_methods(runtime,CLASS)}
    if (NAME,DESCRIPTOR) not in methods:
        raise RuntimeError("exact checkPoweredState signature absent")

    sections=inspect.parse_javap_sections(inspect.javap_code(runtime,CLASS),CLASS)
    section=sections[(NAME,DESCRIPTOR)]
    normalized,count=inspect.normalize_method_section(section)
    refs=inspect.symbolic_references(section,CLASS)

    doc={
        "schema":"supracraft-inventory-boundary-structure/1",
        "edition":"java","minecraft_version":"26.3",
        "domain":"inventory",
        "runtime_class":CLASS,
        "class_sha256":actual,
        "method_name":NAME,
        "method_descriptor":DESCRIPTOR,
        "normalized_code_sha256":inspect.sha256_text(normalized),
        "instruction_count":count,
        **refs,
        "qualification_status":"structure_only_boundary_candidate",
        "boundary":"Method structure may identify a boundary dependency; symbolic references do not independently qualify cross-domain causality."
    }
    Path(args.output).write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
        "status":"pass",
        "method_name":NAME,
        "instruction_count":count,
        "normalized_code_sha256":doc["normalized_code_sha256"],
        "method_refs":doc["method_refs"],
        "field_refs":doc["field_refs"],
    },indent=2,sort_keys=True))

if __name__=="__main__": main()
