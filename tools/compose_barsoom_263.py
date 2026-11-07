#!/usr/bin/env python3
"""Compose two fixed-source vanilla Java 26.3 datapacks without losing provenance.

No wholesale world-save rewriting; no plugin/mod; exact SHA guard on both inputs.
"""
import argparse,hashlib,json,zipfile
from pathlib import Path

OUTPOST_SHA='e3cf6c59121f8a85cf4291780d7549fd3f4ae95af285b8da41e97719e933f4dc'
TERRAIN_SHA='9d5ad764a2df4786666326e997a3ed724524583fe3191b60305677fbe5fb531e'

def digest(body):return hashlib.sha256(body).hexdigest()

def compose(outpost:Path, terrain:Path, output:Path)->dict:
 if digest(outpost.read_bytes())!=OUTPOST_SHA:raise ValueError('OUTPOST_IMMUTABLE_SOURCE_MISMATCH')
 if digest(terrain.read_bytes())!=TERRAIN_SHA:raise ValueError('TERRAIN_IMMUTABLE_SOURCE_MISMATCH')
 with zipfile.ZipFile(outpost) as f:
  assert f.testzip() is None
  files={n:f.read(n) for n in f.namelist()}
 with zipfile.ZipFile(terrain) as f:
  assert f.testzip() is None
  addition={n:f.read(n) for n in f.namelist()}
 assert set(addition)=={'pack.mcmeta','data/barsoom/worldgen/world_preset/dead_sea.json'}
 assert files['pack.mcmeta']!=b''
 assert json.loads(files['pack.mcmeta'])['pack']['min_format']==[121,0]
 assert json.loads(addition['pack.mcmeta'])['pack']['min_format']==[121,0]
 assert not any(n in files for n in addition if n!='pack.mcmeta')
 files.update({n:v for n,v in addition.items() if n!='pack.mcmeta'})
 output.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for name,content in sorted(files.items()):
   info=zipfile.ZipInfo(name,(2026,10,17,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
   z.writestr(info,content)
 return {'schema':'supracraft.barsoom.composed-datapack/1','sha256':digest(output.read_bytes()),'members':len(files),'preset':'barsoom:dead_sea','outpost_sha256':OUTPOST_SHA,'terrain_sha256':TERRAIN_SHA}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--outpost',type=Path,required=True);p.add_argument('--terrain',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();print(json.dumps(compose(a.outpost,a.terrain,a.output),indent=2))
