#!/usr/bin/env python3
"""Generate a bounded recurring-volcano vanilla datapack.

Story semantics are separated from this command-orchestrated lowering.
"""

from __future__ import annotations
import argparse, json
from pathlib import Path

PACK_NAME="supracraft_volcano"
NS="supracraft_volcano"

def _write(path: Path, lines):
    path.parent.mkdir(parents=True,exist_ok=True)
    if isinstance(lines,str):
        text=lines
    else:
        text="\n".join(lines)+"\n"
    path.write_text(text,"utf-8")

def cone_commands(cx:int,base_y:int,cz:int,cycle:int):
    top=base_y+cycle*2
    max_radius=cycle+2
    cmds=[]
    for y in range(base_y,top+1):
        rise=y-base_y
        radius=max(1,max_radius-(rise//2))
        cmds.append(
            f"fill {cx-radius} {y} {cz-radius} {cx+radius} {y} {cz+radius} minecraft:basalt"
        )
        if radius>=2:
            inner=radius-1
            cmds.append(
                f"fill {cx-inner} {y} {cz-inner} {cx+inner} {y} {cz+inner} minecraft:blackstone"
            )
            cmds.append(f"setblock {cx} {y} {cz} minecraft:basalt")
    cmds += [
        f"setblock {cx} {top} {cz} minecraft:lava",
        f"setblock {cx+1} {top} {cz} minecraft:lava",
        f"say SUPRACRAFT_VOLCANO_ERUPTION cycle={cycle} top_y={top}",
    ]
    return cmds,top,max_radius

def resource_commands(cx:int,base_y:int,cz:int,cycle:int):
    ores=[
        ("minecraft:copper_ore",(1,1,0)),
        ("minecraft:iron_ore",(-1,1,0)),
        ("minecraft:gold_ore",(0,1,1)),
    ]
    cmds=[]
    for idx,(block,(dx,dy,dz)) in enumerate(ores[:min(cycle,len(ores))],1):
        cmds.append(f"setblock {cx+dx} {base_y+dy+cycle-1} {cz+dz} {block}")
    cmds.append(f"say SUPRACRAFT_VOLCANO_RESOURCES_READY cycle={cycle}")
    return cmds

def write_volcano_pack(
    world:Path,
    data_pack_major:int,
    *,
    cx:int=0,
    base_y:int=100,
    cz:int=0,
    underwater:bool=True,
    water_surface_y:int=104,
    max_cycles:int=3,
    warning_ticks:int=5,
    eruption_ticks:int=5,
    cooling_ticks:int=5,
    dormant_ticks:int=5,
):
    if max_cycles<2:
        raise ValueError("max_cycles must be >=2 for recurring-volcano contract")
    if min(warning_ticks,eruption_ticks,cooling_ticks,dormant_ticks)<1:
        raise ValueError("all schedule delays must be >=1 tick")

    pack=world/"datapacks"/PACK_NAME
    funcs=pack/"data"/NS/"function"
    funcs.mkdir(parents=True,exist_ok=True)
    meta={"pack":{
        "min_format":[int(data_pack_major),0],
        "max_format":[int(data_pack_major),0],
        "description":"SupraCraft recurring resource volcano vertical slice"
    }}
    _write(pack/"pack.mcmeta",json.dumps(meta,indent=2)+"\n")

    _write(funcs/"start.mcfunction",[
        "scoreboard objectives add scv_cycle dummy",
        "scoreboard objectives add scv_phase dummy",
        "scoreboard players set #volcano scv_cycle 0",
        "scoreboard players set #volcano scv_phase 0",
        "say SUPRACRAFT_VOLCANO_START",
        f"schedule function {NS}:warning {warning_ticks}t replace",
    ])
    _write(funcs/"warning.mcfunction",[
        "scoreboard players set #volcano scv_phase 1",
        f"particle minecraft:smoke {cx} {base_y+max_cycles*2+2} {cz} 1 1 1 0.03 20 force",
        "say SUPRACRAFT_VOLCANO_WARNING",
        f"schedule function {NS}:erupt {eruption_ticks}t replace",
    ])
    erupt=[
        "scoreboard players set #volcano scv_phase 2",
        "scoreboard players add #volcano scv_cycle 1",
    ]
    for cycle in range(1,max_cycles+1):
        erupt.append(
            f"execute if score #volcano scv_cycle matches {cycle} run function {NS}:eruption/{cycle}"
        )
    erupt.append(f"schedule function {NS}:cool {cooling_ticks}t replace")
    _write(funcs/"erupt.mcfunction",erupt)

    cool=[
        "scoreboard players set #volcano scv_phase 3",
    ]
    for cycle in range(1,max_cycles+1):
        cool.append(
            f"execute if score #volcano scv_cycle matches {cycle} run function {NS}:cool/{cycle}"
        )
    if underwater:
        emergence_y=water_surface_y+1
        cool += [
            f"execute if block {cx} {emergence_y} {cz} minecraft:basalt run function {NS}:island_emerged"
        ]
    cool += [
        "scoreboard players set #volcano scv_phase 4",
        f"execute if score #volcano scv_cycle matches ..{max_cycles-1} run schedule function {NS}:dormant {dormant_ticks}t replace",
        f"execute if score #volcano scv_cycle matches {max_cycles} run say SUPRACRAFT_VOLCANO_COMPLETE",
    ]
    _write(funcs/"cool.mcfunction",cool)

    _write(funcs/"dormant.mcfunction",[
        "scoreboard players set #volcano scv_phase 0",
        "say SUPRACRAFT_VOLCANO_DORMANT",
        f"schedule function {NS}:warning {warning_ticks}t replace",
    ])

    _write(funcs/"island_emerged.mcfunction",[
        "say SUPRACRAFT_VOLCANO_ISLAND_EMERGED",
    ])

    max_top=base_y
    max_radius=0
    for cycle in range(1,max_cycles+1):
        cmds,top,radius=cone_commands(cx,base_y,cz,cycle)
        _write(funcs/f"eruption/{cycle}.mcfunction",cmds)
        max_top=max(max_top,top); max_radius=max(max_radius,radius)
        cool_cmds=[
            f"fill {cx-radius} {base_y} {cz-radius} {cx+radius} {top+1} {cz+radius} minecraft:obsidian replace minecraft:lava",
            *resource_commands(cx,base_y,cz,cycle),
            f"say SUPRACRAFT_VOLCANO_COOL_COMPLETE cycle={cycle}",
        ]
        _write(funcs/f"cool/{cycle}.mcfunction",cool_cmds)

    manifest={
        "schema":"supracraft-volcano-lowering/1",
        "story_id":"recurring_resource_volcano_v1",
        "edition":"java",
        "implementation_mode":"command_orchestrated",
        "pack_id":f"file/{PACK_NAME}",
        "namespace":NS,
        "center":[cx,base_y,cz],
        "underwater":underwater,
        "water_surface_y":water_surface_y if underwater else None,
        "max_cycles":max_cycles,
        "max_top_y":max_top,
        "max_radius":max_radius,
        "resource_blocks":["minecraft:copper_ore","minecraft:iron_ore","minecraft:gold_ore"],
        "phase_order":["dormant","warning","eruption","cooling","resource_ready"],
        "limitations":[
            "Command-authored geometry is a story lowering, not qualified native geology.",
            "Lava placement is representational; realistic fluid dynamics are not modeled.",
            "Resource placement is deterministic story content, not geological ore generation.",
            "Island emergence is defined by persistent volcano geometry crossing a configured water surface."
        ]
    }
    _write(world/"SUPRACRAFT-VOLCANO.json",json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    return manifest

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--world",type=Path,required=True)
    ap.add_argument("--data-pack-major",type=int,required=True)
    ap.add_argument("--cx",type=int,default=0)
    ap.add_argument("--base-y",type=int,default=100)
    ap.add_argument("--cz",type=int,default=0)
    ap.add_argument("--water-surface-y",type=int,default=104)
    ap.add_argument("--max-cycles",type=int,default=3)
    ap.add_argument("--surface",action="store_true")
    args=ap.parse_args()
    m=write_volcano_pack(
        args.world,args.data_pack_major,cx=args.cx,base_y=args.base_y,cz=args.cz,
        underwater=not args.surface,water_surface_y=args.water_surface_y,
        max_cycles=args.max_cycles,
    )
    print(json.dumps(m,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
