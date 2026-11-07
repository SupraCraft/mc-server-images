#!/usr/bin/env python3
"""Minimal vanilla 26.3 crop restoration candidate, with exact source digest gate.

Observed native probes: function bulk-fill and scheduled replant did not leave crops;
a direct conditional setblock at the world anchor did. Keep the next candidate
bounded: four representative crops in the already-qualified restore function.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import zipfile

ORIGINAL_SHA='e6ec6e428718ec4916780c41b828d9ef1d345886a786d0e5b48303070d738752'
RESTORE='data/barsoom/function/restore.mcfunction'


def patch(original:Path,dest:Path)->dict:
    assert original.is_file() and hashlib.sha256(original.read_bytes()).hexdigest()==ORIGINAL_SHA
    with zipfile.ZipFile(original) as z:
        members={name:z.read(name).decode('utf-8') for name in z.namelist()}
    source=members[RESTORE]
    planting=[line for line in source.splitlines() if 'minecraft:wheat[age=2]' in line]
    assert len(planting)==2
    for line in planting:source=source.replace(line+'\n','')
    positions=[(5,5),(4,4),(6,10),(-5,5)]
    rows=[f'execute at @e[type=minecraft:marker,tag=barsoom.canal_control,limit=1] run setblock ~{x} ~0 ~{z} minecraft:wheat[age=2]' for x,z in positions]
    source=source.replace('tellraw @a ',('\n'.join(rows))+'\ntellraw @a ',1)
    members[RESTORE]=source
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
