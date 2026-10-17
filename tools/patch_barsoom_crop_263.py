#!/usr/bin/env python3
"""Minimal candidate correction of *exact original* Barsoom 26.3 datapack.

Retain source bytes and unchanged entries. Fix delayed crop placement only. Never
silently rewrite the original candidate or confuse a new digest with baseline.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import zipfile

ORIGINAL_SHA='e6ec6e428718ec4916780c41b828d9ef1d345886a786d0e5b48303070d738752'
RESTORE='data/barsoom/function/restore.mcfunction'
REPLANT='data/barsoom/function/replant.mcfunction'


def patch(original:Path,dest:Path)->dict:
    assert original.is_file() and hashlib.sha256(original.read_bytes()).hexdigest()==ORIGINAL_SHA, 'original digest drift'
    with zipfile.ZipFile(original) as z:
        members={name:z.read(name).decode('utf-8') for name in z.namelist()}
    assert REPLANT not in members
    source=members[RESTORE]
    planting=[line for line in source.splitlines() if 'minecraft:wheat[age=2]' in line]
    assert len(planting)==2 and all(line.startswith('execute at @e[') for line in planting)
    # Stagger crop placement until after irrigation's neighbor/fluid updates settle.
    for line in planting:source=source.replace(line+'\n','')
    assert 'minecraft:wheat' not in source
    source=source.replace('tellraw @a ', 'schedule function barsoom:replant 40t replace\ntellraw @a ',1)
    members[RESTORE]=source
    # 26.3 native falsification: /fill wheat returns without durable crop;
    # individual /setblock wheat survives on exactly the same hydrated farmland.
    plant_commands=[
        (f'execute if score #canal barsoom.state matches 1.. '
         f'at @e[type=minecraft:marker,tag=barsoom.canal_control,limit=1] '
         f'run setblock ~{x} ~0 ~{z} minecraft:wheat[age=2]')
        for x in (-6,-5,-4,4,5,6) for z in range(3,20)
    ]
    assert len(plant_commands)==102
    members[REPLANT]='# Scheduled 40t after irrigation; 26.3-qualified individual block-placement family.\n'+('\n'.join(plant_commands))+'\n'
    dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,body in sorted(members.items()):
            info=zipfile.ZipInfo(name,(2026,10,17,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,body)
    return {'baseline_sha256':ORIGINAL_SHA,'candidate_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'members':len(members)}


def main():
    a=argparse.ArgumentParser();a.add_argument('--original',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    args=a.parse_args();print(patch(args.original,args.out))
if __name__=='__main__':main()
