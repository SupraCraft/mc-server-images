#!/usr/bin/env python3
"""First bounded Barsoom archaeological harbor underworld. Vanilla 26.3.

An *unnamed* dried-out harbor ruin. No claim that these details are canon Korad.
Creates no new Minecraft block/item types. Build only in a fresh disposable world.
"""
import argparse, hashlib, json, zipfile
from pathlib import Path

OUT = 'Barsoom-Buried-Harbor-26.3.zip'
F={}
def put(name, text): F[name]=text.strip().encode('utf-8')+b'\n'
def func(name, text): put('data/barsoom_arch/function/'+name+'.mcfunction',text)
def obj(name,data):put(name,json.dumps(data,sort_keys=True,indent=2))
obj('pack.mcmeta', {'pack':{'description':'Barsoom: unnamed buried harbor v0, 26.3 fixture','min_format':[121,0],'max_format':[121,0]}})
obj('data/minecraft/tags/function/load.json',{'values':['barsoom_arch:load']})
obj('data/minecraft/tags/function/tick.json',{'values':['barsoom_arch:tick']})
func('load', '''scoreboard objectives add barsoom_arch.start trigger
scoreboard objectives add barsoom_arch.restore trigger
scoreboard objectives add barsoom_arch.state dummy
scoreboard objectives add barsoom_arch.accept dummy
scoreboard players add #built barsoom_arch.state 0
scoreboard players add #well barsoom_arch.state 0''')
func('tick', '''scoreboard players enable @a barsoom_arch.start
scoreboard players enable @a barsoom_arch.restore
execute as @a[scores={barsoom_arch.start=1..}] at @s unless score #built barsoom_arch.state matches 1.. run function barsoom_arch:establish
scoreboard players set @a[scores={barsoom_arch.start=1..}] barsoom_arch.start 0
execute as @a[scores={barsoom_arch.restore=1..}] at @s run function barsoom_arch:attempt_restore
scoreboard players set @a[scores={barsoom_arch.restore=1..}] barsoom_arch.restore 0''')
func('establish', '''# Explicit opt-in; absolute site uniqueness enforced by persistent score.
execute positioned ~ ~ ~ align xyz run function barsoom_arch:build
scoreboard players set #built barsoom_arch.state 1
tellraw @a {"text":"Ancient harbor remains revealed. Descend the ladder to the buried archive and recover the sea seal.","color":"gold"}''')
func('build', '''# Destructive bounded prototype: 25x34 columns and y -11..+5 about command position.
# Ground-level quay: clear residual vanilla terrain so route does not depend on spawn seed.
fill ~-12 ~0 ~-9 ~12 ~5 ~24 minecraft:air replace
fill ~-12 ~-2 ~-9 ~12 ~-2 ~24 minecraft:terracotta replace
fill ~-9 ~-1 ~-8 ~9 ~-1 ~8 minecraft:cut_sandstone replace
fill ~-9 ~0 ~-8 ~-9 ~3 ~8 minecraft:cracked_stone_bricks replace
fill ~9 ~0 ~-8 ~9 ~3 ~8 minecraft:cracked_stone_bricks replace
# A gate opening from the east approach road into the harbor court.
fill ~9 ~0 ~0 ~9 ~2 ~2 minecraft:air replace
fill ~-9 ~0 ~-8 ~9 ~3 ~-8 minecraft:cracked_stone_bricks replace
fill ~-3 ~0 ~-8 ~3 ~2 ~-8 minecraft:air replace
fill ~-3 ~0 ~-1 ~3 ~2 ~-1 minecraft:air replace
setblock ~-6 ~0 ~-5 minecraft:barrel
setblock ~7 ~0 ~-5 minecraft:chiseled_sandstone
# Visible dry well and separate narrow archaeological access to the southeast.
fill ~-2 ~0 ~-2 ~2 ~0 ~2 minecraft:cut_sandstone replace
setblock ~0 ~0 ~0 minecraft:air
setblock ~0 ~-1 ~0 minecraft:cut_sandstone
# Engineered buried warehouse: hollow with real floor and entrance to ladder gallery.
fill ~-8 ~-11 ~9 ~8 ~-5 ~23 minecraft:cracked_deepslate_bricks hollow
fill ~-7 ~-10 ~10 ~7 ~-6 ~22 minecraft:air replace
fill ~-2 ~-11 ~13 ~2 ~-11 ~20 minecraft:polished_blackstone replace
# The 2-wide descent shaft and air gallery are constructed separately from the room.
# Make the shaft/gallery floor independent of naturally generated caves below.
fill ~-1 ~-11 ~4 ~1 ~-11 ~12 minecraft:polished_blackstone replace
fill ~-1 ~-10 ~4 ~1 ~2 ~5 minecraft:air replace
fill ~-1 ~-10 ~5 ~1 ~-7 ~11 minecraft:air replace
# Backing wall supports physically climbable ladder (south-facing).
fill ~0 ~-11 ~3 ~0 ~2 ~3 minecraft:stone_bricks replace
fill ~0 ~-10 ~4 ~0 ~1 ~4 minecraft:ladder[facing=south] replace
# Safe one-block landing between the ladder and the east quay.
setblock ~1 ~-1 ~4 minecraft:cut_sandstone
# Connect into underground archive at Z=11, at walking height.
fill ~-1 ~-10 ~9 ~1 ~-7 ~12 minecraft:air replace
# Lower chamber storage, an artifact and inscriptions (books require text fixture later).
setblock ~4 ~-10 ~17 minecraft:chest[facing=west]
item replace block ~4 ~-10 ~17 container.0 with minecraft:heart_of_the_sea[minecraft:custom_data={barsoom_arch:{harbor_seal:1b}}] 1
item replace block ~4 ~-10 ~17 container.1 with minecraft:book 1
setblock ~-5 ~-10 ~17 minecraft:sea_lantern
setblock ~-4 ~-10 ~19 minecraft:chiseled_deepslate
summon minecraft:marker ~0 ~0 ~0 {Tags:["barsoom_arch.well"]}
summon minecraft:marker ~0 ~-10 ~17 {Tags:["barsoom_arch.archive"]}
# Exposed markers distinguish different building eras without granting loot.
setblock ~-11 ~0 ~5 minecraft:weathered_copper
setblock ~11 ~0 ~5 minecraft:oxidized_copper''')
func('attempt_restore', '''scoreboard players set @s barsoom_arch.accept 0
execute if score #built barsoom_arch.state matches 1.. if score #well barsoom_arch.state matches 0 if entity @e[type=minecraft:marker,tag=barsoom_arch.well,distance=..6] store result score @s barsoom_arch.accept run clear @s minecraft:heart_of_the_sea[minecraft:custom_data~{barsoom_arch:{harbor_seal:1b}}] 1
execute if score @s barsoom_arch.accept matches 1.. run function barsoom_arch:restore
execute unless score @s barsoom_arch.accept matches 1.. run tellraw @s {"text":"You need the archive's sea seal and must stand beside the old well.","color":"red"}''')
func('restore', '''scoreboard players set #well barsoom_arch.state 1
execute at @e[type=minecraft:marker,tag=barsoom_arch.well,limit=1] run setblock ~0 ~-1 ~0 minecraft:water
execute at @e[type=minecraft:marker,tag=barsoom_arch.well,limit=1] run setblock ~6 ~-1 ~2 minecraft:farmland[moisture=7]
execute at @e[type=minecraft:marker,tag=barsoom_arch.well,limit=1] run setblock ~6 ~0 ~2 minecraft:wheat[age=2]
tellraw @a {"text":"The lost harbor well flows again. A remnant of the ancient waterworks survives.","color":"aqua"}''')

def build(out):
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,content in sorted(F.items()):
            info=zipfile.ZipInfo(name,(2026,10,18,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,content)
    return {'sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'members':len(F),'path':str(out),'classification':'DISPOSABLE_NAMED_HARBOR_ARCHAEOLOGY_V0'}
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    print(json.dumps(build(a.out),sort_keys=True,indent=2))
