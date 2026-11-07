#!/usr/bin/env python3
"""Generate bounded vanilla Java 26.3 Dead Sea province WORLD PRESET fixture.

Intentionally a fixed-badlands baseline, NOT Barsoom's finished climate atlas.
The overworld generator uses ordinary vanilla noise for caves, ores and height.
Nether and End retained for vanilla progression. Source is deterministic.
"""
import hashlib
import json
from pathlib import Path
import zipfile
import argparse

PACK={
  "pack":{"description":"Barsoom Dead Sea baseline terrain — vanilla 26.3 research fixture", "min_format":[121,0],"max_format":[121,0]}
}
PRESET={
 "dimensions":{
  "minecraft:overworld":{
   "type":"minecraft:overworld",
   "generator":{
    "type":"minecraft:noise",
    "biome_source":{"type":"minecraft:fixed","biome":"minecraft:badlands"},
    "settings":"minecraft:overworld"
   }
  },
  "minecraft:the_nether":{
   "type":"minecraft:the_nether",
   "generator":{
    "type":"minecraft:noise",
    "biome_source":{"type":"minecraft:multi_noise","preset":"minecraft:nether"},
    "settings":"minecraft:nether"
   }
  },
  "minecraft:the_end":{
   "type":"minecraft:the_end",
   "generator":{
    "type":"minecraft:noise",
    "biome_source":{"type":"minecraft:the_end"},
    "settings":"minecraft:end"
   }
  }
 }
}
FILES={
 'pack.mcmeta':PACK,
 'data/barsoom/worldgen/world_preset/dead_sea.json':PRESET,
}

def build(path:Path) -> dict:
 path.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for name,obj in sorted(FILES.items()):
   info=zipfile.ZipInfo(name,(2026,10,17,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
   z.writestr(info,json.dumps(obj,indent=2,sort_keys=True)+'\n')
 return {'artifact':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'members':sorted(FILES),'profile':'barsoom:dead_sea','classification':'world_preset_fixed_badlands_baseline'}

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--manifest',type=Path)
 a=p.parse_args();rec=build(a.output)
 if a.manifest:a.manifest.write_text(json.dumps(rec,indent=2,sort_keys=True)+'\n')
 print(json.dumps(rec,indent=2))
