#!/usr/bin/env python3
"""Probe current Minecraft world storage shapes without dumping content payloads."""

from __future__ import annotations
import argparse, gzip, io, json, struct, tempfile, zipfile, zlib
from collections import Counter
from pathlib import Path
import nbtlib

def decompress(payload, kind):
    if kind==1: return gzip.decompress(payload)
    if kind==2: return zlib.decompress(payload)
    if kind==3: return payload
    raise ValueError(kind)

def iter_region(path):
    blob=path.read_bytes()
    if len(blob)<8192: return
    for slot in range(1024):
        off=slot*4
        sector=int.from_bytes(blob[off:off+3],"big")
        count=blob[off+3]
        if not sector or not count: continue
        pos=sector*4096
        if pos+5>len(blob): continue
        length=struct.unpack(">I",blob[pos:pos+4])[0]
        end=pos+4+length
        if length<1 or end>len(blob): continue
        yield nbtlib.File.parse(io.BytesIO(decompress(blob[pos+5:end],blob[pos+4])))

def keys(obj):
    return sorted(str(k) for k in obj.keys()) if hasattr(obj,"keys") else []

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--world-zip",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="world-shape-") as td:
        root=Path(td)
        with zipfile.ZipFile(args.world_zip) as zf: zf.extractall(root)
        world=root/"world"
        od=world/"dimensions"/"minecraft"/"overworld"
        region_dir=od/"region"
        entity_dir=od/"entities"

        chunk_top=Counter()
        section_shapes=Counter()
        block_entity_keys=Counter()
        block_entity_ids=Counter()
        block_entity_list_names=Counter()
        entity_top=Counter()
        entity_keys=Counter()
        entity_ids=Counter()
        entity_list_names=Counter()
        chunk_count=0
        entity_chunk_count=0

        for rp in sorted(region_dir.glob("r.*.*.mca")):
            for ch in iter_region(rp):
                chunk_count+=1
                for k in keys(ch): chunk_top[k]+=1
                for name in ("block_entities","BlockEntities","TileEntities"):
                    val=ch.get(name) if hasattr(ch,"get") else None
                    if val is not None:
                        block_entity_list_names[name]+=1
                        for be in val:
                            for k in keys(be): block_entity_keys[k]+=1
                            ident=be.get("id") if hasattr(be,"get") else None
                            if ident is not None: block_entity_ids[str(ident)]+=1
                for name in ("sections","Sections"):
                    val=ch.get(name) if hasattr(ch,"get") else None
                    if val is not None:
                        for sec in val:
                            section_shapes[",".join(keys(sec))]+=1

        for rp in sorted(entity_dir.glob("r.*.*.mca")):
            for ch in iter_region(rp):
                entity_chunk_count+=1
                for k in keys(ch): entity_top[k]+=1
                for name in ("Entities","entities"):
                    val=ch.get(name) if hasattr(ch,"get") else None
                    if val is not None:
                        entity_list_names[name]+=1
                        for ent in val:
                            for k in keys(ent): entity_keys[k]+=1
                            ident=ent.get("id") if hasattr(ent,"get") else None
                            if ident is not None: entity_ids[str(ident)]+=1

        result={
          "schema":"supracraft-modern-world-storage-shape/1",
          "chunk_count":chunk_count,
          "entity_chunk_count":entity_chunk_count,
          "chunk_top_level_keys":dict(chunk_top),
          "section_key_shapes":dict(section_shapes),
          "block_entity_list_names":dict(block_entity_list_names),
          "block_entity_keys":dict(block_entity_keys),
          "block_entity_id_counts":dict(block_entity_ids),
          "entity_chunk_top_level_keys":dict(entity_top),
          "entity_list_names":dict(entity_list_names),
          "entity_keys":dict(entity_keys),
          "entity_id_counts":dict(entity_ids),
          "limitations":[
             "This probe records key names and identifier counts only, not player or entity payloads.",
             "Absence of a block/entity type in the vanilla bootstrap world does not imply format absence."
          ]
        }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
