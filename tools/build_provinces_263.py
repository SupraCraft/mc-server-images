#!/usr/bin/env python3
"""Add candidate native 26.3 climate provinces without mutating accepted Dead Sea source."""
from __future__ import annotations
import argparse, hashlib, json, zipfile
from pathlib import Path

BASE_SHA = 'd9a0d0463ad42d32b088b5fdd8f2c649fde0b978de5ca68cc55ca7b674991d94'
MEMBER = 'data/barsoom/worldgen/world_preset/provinces_v0.json'

def point(biome, t, h, c=0.0, e=0.0, w=0.0):
    return {'biome': 'minecraft:'+biome,
      'parameters': {'temperature': t, 'humidity': h, 'continentalness': c,
                     'erosion': e, 'weirdness': w, 'depth': 0.0, 'offset': 0.0}}

PROVINCES = [
    point('badlands', 0.15, -0.30, 0.15, 0.0),
    point('eroded_badlands', 0.45, -0.8, 0.1, -0.55),
    point('desert', 0.9, -0.8, 0.0, 0.0),
    point('wooded_badlands', 0.35, 0.20, 0.45, -0.05),
    point('savanna', 0.8, 0.3, 0.15, 0.4),
    point('sparse_jungle', 0.65, 0.85, -0.05, 0.15),
    point('swamp', 0.10, 0.85, -0.4, 0.0),
    point('stony_peaks', -0.45, -0.2, 0.45, -0.6),
    point('snowy_plains', -0.9, 0.15, 0.15, 0.10),
]

def digest(b): return hashlib.sha256(b).hexdigest()

def build(source:Path, output:Path):
    original=source.read_bytes()
    if digest(original)!=BASE_SHA:raise ValueError('IMMUTABLE_COMPOSITE_SOURCE_DIGEST_DRIFT')
    with zipfile.ZipFile(source) as z:
        if z.testzip() is not None:raise ValueError('BAD_COMPOSITE_ZIP')
        files={x.filename:z.read(x) for x in z.infolist()}
    if MEMBER in files:raise ValueError('PRESET_NAME_COLLISION')
    original_preset=json.loads(files['data/barsoom/worldgen/world_preset/dead_sea.json'])
    preset=json.loads(json.dumps(original_preset))
    source_spec=preset['dimensions']['minecraft:overworld']['generator']['biome_source']
    if source_spec != {'type':'minecraft:fixed','biome':'minecraft:badlands'}:raise ValueError('SOURCE_PRESET_CHANGED')
    preset['dimensions']['minecraft:overworld']['generator']['biome_source']={'type':'minecraft:multi_noise','biomes':PROVINCES}
    files[MEMBER]=(json.dumps(preset,sort_keys=True,indent=2)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,b in sorted(files.items()):
            z.writestr(zipfile.ZipInfo(name,(2026,10,18,0,0,0)),b,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
    receipt={'schema':'supracraft.barsoom.provinces/1','source_sha256':BASE_SHA,
             'candidate_sha256':digest(output.read_bytes()),'world_preset':'barsoom:provinces_v0',
             'biomes':[x['biome'] for x in PROVINCES],'members':len(files)}
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(build(a.source,a.output),indent=2))
