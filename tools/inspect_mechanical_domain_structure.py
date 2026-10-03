#!/usr/bin/env python3
"""Exact Java 26.3 piston method-structure evidence. Mechanical domain only."""

from __future__ import annotations
import argparse, json
from pathlib import Path

import discover_minecraft_observability as discovery
import inventory_modern_microscope_symbols as inv
import inspect_modern_microscope_hook_structure as inspect

CLASS="net.minecraft.world.level.block.piston.PistonBaseBlock"
EXPECTED_CLASS_SHA256="47b87b5736027ca99add513835ddb594417ab6b8943c2fa746870af101b105d9"
TARGETS=(
    ("piston_check_if_extend","checkIfExtend",
     "(Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;Lnet/minecraft/world/level/block/state/BlockState;)V"),
    ("piston_is_pushable","isPushable",
     "(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;Lnet/minecraft/core/Direction;ZLnet/minecraft/core/Direction;)Z"),
    ("piston_move_blocks","moveBlocks",
     "(Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;Lnet/minecraft/core/Direction;Z)Z"),
    ("piston_trigger_event","triggerEvent",
     "(Lnet/minecraft/world/level/block/state/BlockState;Lnet/minecraft/world/level/Level;Lnet/minecraft/core/BlockPos;II)Z"),
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

    actual_hash=inv.sha256_bytes(inv.class_bytes(runtime,CLASS))
    if actual_hash!=EXPECTED_CLASS_SHA256:
        raise RuntimeError(f"PistonBaseBlock class hash changed: {actual_hash}")

    methods={(m["name"],m["descriptor"]) for m in inv.javap_methods(runtime,CLASS)}
    output=inspect.javap_code(runtime,CLASS)
    sections=inspect.parse_javap_sections(output,CLASS)

    rows=[]
    for target_id,name,descriptor in TARGETS:
        key=(name,descriptor)
        if key not in methods or key not in sections:
            raise RuntimeError(f"{target_id}: exact target absent")
        normalized,count=inspect.normalize_method_section(sections[key])
        refs=inspect.symbolic_references(sections[key],CLASS)
        if count<1: raise RuntimeError(f"{target_id}: empty bytecode")
        rows.append({
            "id":target_id,
            "runtime_class":CLASS,
            "class_sha256":actual_hash,
            "method_name":name,
            "method_descriptor":descriptor,
            "normalized_code_sha256":inspect.sha256_text(normalized),
            "instruction_count":count,
            **refs,
        })

    doc={
        "schema":"supracraft-mechanical-domain-structure/1",
        "edition":"java","minecraft_version":"26.3","domain":"mechanical",
        "server_sha1":row["server_sha1"],"methods":rows,
        "qualification_status":"structure_only_not_semantics_qualified",
        "boundaries":[
            "piston structure only; no Redstone trigger semantics are promoted",
            "method identity/fingerprint/references do not prove piston runtime behavior",
            "runtime qualification must independently exercise extension/retraction and moved geometry",
        ],
    }
    Path(args.output).write_text(json.dumps(doc,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":"pass","domain":"mechanical","methods":[
        {"id":x["id"],"instruction_count":x["instruction_count"],
         "normalized_code_sha256":x["normalized_code_sha256"],
         "method_ref_count":len(x["method_refs"])}
        for x in rows]},indent=2,sort_keys=True))

if __name__=="__main__": main()
