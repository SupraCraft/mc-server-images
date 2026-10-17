#!/usr/bin/env python3
"""Generate strictly vanilla Java 26.3 starter datapack and static receipts."""
import hashlib,json,re,sys,zipfile
from pathlib import Path
BASE=Path(__file__).resolve().parent
OUT=BASE/'dist';OUT.mkdir(exist_ok=True)
files={}
def raw(path,data):files[path]=data.strip()+"\n"
def func(name,code):raw(f'data/barsoom/function/{name}.mcfunction',code)
def jd(path,obj):files[path]=json.dumps(obj,indent=2,ensure_ascii=False)+'\n'
jd('pack.mcmeta',{'pack':{'description':'Barsoom v0.1: canal outpost survival slice (Java 26.3)','min_format':[121,0],'max_format':[121,0]}})
jd('data/minecraft/tags/function/load.json',{'values':['barsoom:load']})
jd('data/minecraft/tags/function/tick.json',{'values':['barsoom:tick']})
func('load', '''# Commands are replay-safe when /reload is used.
scoreboard objectives add barsoom.start trigger
scoreboard objectives add barsoom.repair trigger
scoreboard objectives add barsoom.guide trigger
scoreboard objectives add barsoom.state dummy
scoreboard objectives add barsoom.accept dummy
scoreboard players add #built barsoom.state 0
scoreboard players add #canal barsoom.state 0
''')
func('tick', '''# Players opt-in to creation and repair, no constant chunk scanning.
scoreboard players enable @a barsoom.start
scoreboard players enable @a barsoom.repair
scoreboard players enable @a barsoom.guide
execute as @a[scores={barsoom.start=1..}] at @s unless score #built barsoom.state matches 1.. run function barsoom:establish
execute as @a[scores={barsoom.start=1..}] if score #built barsoom.state matches 1.. run tellraw @s {"text":"Barsoomian outpost exists; /trigger barsoom.guide set 1 shows your objective.","color":"gold"}
scoreboard players set @a[scores={barsoom.start=1..}] barsoom.start 0
execute as @a[scores={barsoom.repair=1..}] at @s run function barsoom:attempt_repair
scoreboard players set @a[scores={barsoom.repair=1..}] barsoom.repair 0
execute as @a[scores={barsoom.guide=1..}] at @s run function barsoom:guide
scoreboard players set @a[scores={barsoom.guide=1..}] barsoom.guide 0
''')
func('establish','''# WARNING: destructive construction in a bounded 49x49 region. Use a NEW test world.
execute positioned ~ ~ ~ align xyz run function barsoom:build/base
execute positioned ~ ~ ~ align xyz run function barsoom:build/city
execute positioned ~ ~ ~ align xyz run function barsoom:build/camp
execute positioned ~ ~ ~ align xyz run function barsoom:build/ruin
execute positioned ~ ~ ~ align xyz run function barsoom:build/ecology
scoreboard players set #built barsoom.state 1
tellraw @a {"text":"Barsoom outpost established: the irrigation canal has failed. Find the regulator in the ancient ruin.","color":"gold"}
tellraw @s {"text":"Travel east to the ruin, recover the regulator, return to the central control post, then /trigger barsoom.repair set 1.","color":"aqua"}
tp @s ~12 ~1 ~-12
''')
func('build/base', '''# Footprint 49x49; do not execute in an established world.
fill ~-24 ~ ~-24 ~24 ~7 ~24 minecraft:air replace
fill ~-24 ~-2 ~-24 ~24 ~-2 ~24 minecraft:terracotta replace
fill ~-24 ~-1 ~-24 ~24 ~-1 ~24 minecraft:red_sandstone replace
# Canal line, stone lining, empty trough before repair
fill ~-2 ~-2 ~-23 ~2 ~-2 ~23 minecraft:smooth_sandstone replace
fill ~-1 ~-1 ~-23 ~1 ~-1 ~23 minecraft:air replace
fill ~-3 ~-1 ~-23 ~-3 ~-1 ~23 minecraft:cut_red_sandstone replace
fill ~3 ~-1 ~-23 ~3 ~-1 ~23 minecraft:cut_red_sandstone replace
# Central stone control and bridge to make both halves navigable
fill ~-4 ~-1 ~-1 ~4 ~-1 ~1 minecraft:smooth_sandstone replace
setblock ~2 ~0 ~0 minecraft:lightning_rod
setblock ~4 ~0 ~0 minecraft:lectern
summon minecraft:marker ~0 ~0 ~0 {Tags:["barsoom.canal_control"]}
# Wayfinding marker
setblock ~0 ~0 ~-3 minecraft:lantern
''')
func('build/city', '''# Red Martian civic dwelling and barterhouse, west-facing entry
fill ~9 ~0 ~-21 ~23 ~5 ~-7 minecraft:smooth_sandstone hollow
fill ~10 ~-1 ~-20 ~22 ~-1 ~-8 minecraft:terracotta replace
fill ~9 ~4 ~-21 ~23 ~4 ~-7 minecraft:cut_red_sandstone replace
fill ~9 ~5 ~-21 ~23 ~5 ~-7 minecraft:orange_terracotta replace
fill ~15 ~0 ~-21 ~17 ~2 ~-21 minecraft:air replace
fill ~9 ~2 ~-16 ~9 ~3 ~-12 minecraft:glass replace
fill ~23 ~2 ~-16 ~23 ~3 ~-12 minecraft:glass replace
setblock ~13 ~0 ~-16 minecraft:crafting_table
setblock ~14 ~0 ~-16 minecraft:furnace
setblock ~15 ~0 ~-16 minecraft:barrel
setblock ~18 ~0 ~-15 minecraft:chest[facing=north]
item replace block ~18 ~0 ~-15 container.0 with minecraft:bread 8
item replace block ~18 ~0 ~-15 container.1 with minecraft:oak_sapling 8
item replace block ~18 ~0 ~-15 container.2 with minecraft:stone_pickaxe 1
item replace block ~18 ~0 ~-15 container.3 with minecraft:stone_axe 1
item replace block ~18 ~0 ~-15 container.4 with minecraft:wheat_seeds 16
item replace block ~18 ~0 ~-15 container.5 with minecraft:water_bucket 1
setblock ~12 ~0 ~-11 minecraft:red_bed[facing=east,part=foot]
setblock ~13 ~0 ~-11 minecraft:red_bed[facing=east,part=head]
setblock ~20 ~0 ~-10 minecraft:torch
summon minecraft:villager ~20 ~0 ~-15 {Tags:["barsoom.red_civic"],VillagerData:{profession:"minecraft:farmer",level:2,type:"minecraft:desert"},PersistenceRequired:1b}
summon minecraft:villager ~14 ~0 ~-12 {Tags:["barsoom.red_civic"],VillagerData:{profession:"minecraft:weaponsmith",level:2,type:"minecraft:desert"},PersistenceRequired:1b}
''')
func('build/camp', '''# Green-Martian nomadic camp (villager/camel are declared proxies, not canonical species)
fill ~-23 ~-1 ~-22 ~-8 ~-1 ~-8 minecraft:green_terracotta replace
fill ~-22 ~0 ~-21 ~-9 ~0 ~-9 minecraft:air replace
fill ~-22 ~0 ~-22 ~-22 ~2 ~-9 minecraft:spruce_fence replace
fill ~-9 ~0 ~-22 ~-9 ~2 ~-9 minecraft:spruce_fence replace
fill ~-22 ~0 ~-22 ~-9 ~2 ~-22 minecraft:spruce_fence replace
fill ~-22 ~0 ~-9 ~-9 ~2 ~-9 minecraft:spruce_fence replace
fill ~-17 ~0 ~-9 ~-15 ~1 ~-9 minecraft:air replace
setblock ~-14 ~0 ~-15 minecraft:campfire
setblock ~-18 ~0 ~-17 minecraft:hay_block
setblock ~-12 ~0 ~-13 minecraft:barrel
summon minecraft:camel ~-19 ~0 ~-14 {Tags:["barsoom.thoat_proxy"],PersistenceRequired:1b}
summon minecraft:villager ~-12 ~0 ~-17 {Tags:["barsoom.green_proxy"],VillagerData:{profession:"minecraft:leatherworker",level:2,type:"minecraft:savanna"},PersistenceRequired:1b}
''')
func('build/ruin', '''# Broken tree-root archive / regulator ruin
fill ~9 ~-1 ~7 ~22 ~-1 ~22 minecraft:polished_blackstone replace
fill ~9 ~0 ~7 ~9 ~5 ~22 minecraft:cracked_deepslate_bricks replace
fill ~22 ~0 ~7 ~22 ~4 ~22 minecraft:cracked_deepslate_bricks replace
fill ~9 ~0 ~22 ~22 ~4 ~22 minecraft:cracked_deepslate_bricks replace
fill ~9 ~0 ~7 ~22 ~3 ~7 minecraft:cracked_deepslate_bricks replace
fill ~12 ~0 ~7 ~15 ~2 ~7 minecraft:air replace
fill ~11 ~0 ~11 ~19 ~0 ~19 minecraft:polished_blackstone_bricks replace
setblock ~17 ~1 ~17 minecraft:chest[facing=north]
item replace block ~17 ~1 ~17 container.0 with minecraft:lightning_rod 1
item replace block ~17 ~1 ~17 container.1 with minecraft:emerald 3
item replace block ~17 ~1 ~17 container.2 with minecraft:book 1
setblock ~12 ~1 ~13 minecraft:sea_lantern
setblock ~19 ~1 ~19 minecraft:sea_lantern
summon minecraft:marker ~15 ~0 ~15 {Tags:["barsoom.root_archive"]}
''')
func('build/ecology', '''# Failed canal means no water; plants deteriorate if not repaired.
fill ~4 ~-1 ~3 ~6 ~-1 ~19 minecraft:farmland[moisture=0] replace
fill ~4 ~0 ~3 ~6 ~0 ~19 minecraft:wheat[age=3] replace
fill ~-6 ~-1 ~3 ~-4 ~-1 ~19 minecraft:farmland[moisture=0] replace
fill ~-6 ~0 ~3 ~-4 ~0 ~19 minecraft:wheat[age=3] replace
setblock ~-12 ~0 ~9 minecraft:dead_bush
setblock ~-16 ~0 ~7 minecraft:dead_bush
setblock ~-13 ~0 ~15 minecraft:dead_bush
''')
func('guide', '''tellraw @s {"text":"BARSOOM: The Root Below the Canal — prototype (Java 26.3)","color":"gold"}
tellraw @s {"text":"Stand in a clear spot on a NEW world, then /trigger barsoom.start set 1. One outpost per world.","color":"white"}
tellraw @s {"text":"Civic dwelling: +X,-Z; Green camp: -X,-Z; ruined archive: +X,+Z; canal control: center.","color":"aqua"}
tellraw @s {"text":"Find the lightning rod in the archive chest. At the center control post, use /trigger barsoom.repair set 1.","color":"yellow"}
execute if score #canal barsoom.state matches 1.. run tellraw @s {"text":"Canal status: RESTORED", "color":"green"}
execute unless score #canal barsoom.state matches 1.. run tellraw @s {"text":"Canal status: FAILED", "color":"red"}
''')
func('attempt_repair', '''scoreboard players set @s barsoom.accept 0
execute if score #built barsoom.state matches 1.. if score #canal barsoom.state matches 0 if entity @e[type=minecraft:marker,tag=barsoom.canal_control,distance=..8] store result score @s barsoom.accept run clear @s minecraft:lightning_rod 1
execute if score @s barsoom.accept matches 1.. run function barsoom:restore
execute unless score @s barsoom.accept matches 1.. run tellraw @s {"text":"Repair not possible: bring one lightning rod to the central control, or canal was already restored.","color":"red"}
''')
func('restore', '''# Positions relative to marker anchor; preserve world state and avoid repeated repair.
scoreboard players set #canal barsoom.state 1
execute at @e[type=minecraft:marker,tag=barsoom.canal_control,limit=1] run fill ~-1 ~-1 ~-23 ~1 ~-1 ~23 minecraft:water replace
execute at @e[type=minecraft:marker,tag=barsoom.canal_control,limit=1] run fill ~3 ~-1 ~3 ~3 ~-1 ~19 minecraft:water replace
execute at @e[type=minecraft:marker,tag=barsoom.canal_control,limit=1] run fill ~-3 ~-1 ~3 ~-3 ~-1 ~19 minecraft:water replace
execute at @e[type=minecraft:marker,tag=barsoom.canal_control,limit=1] run fill ~4 ~-1 ~3 ~6 ~-1 ~19 minecraft:farmland[moisture=7] replace
execute at @e[type=minecraft:marker,tag=barsoom.canal_control,limit=1] run fill ~-6 ~-1 ~3 ~-4 ~-1 ~19 minecraft:farmland[moisture=7] replace
execute at @e[type=minecraft:marker,tag=barsoom.canal_control,limit=1] run fill ~4 ~0 ~3 ~6 ~0 ~19 minecraft:wheat[age=2] replace
execute at @e[type=minecraft:marker,tag=barsoom.canal_control,limit=1] run fill ~-6 ~0 ~3 ~-4 ~0 ~19 minecraft:wheat[age=2] replace
tellraw @a {"text":"The canal flows again. Fields are restored and the outpost has a future.","color":"green"}
playsound minecraft:block.beacon.activate master @a ~ ~ ~ 1 1
''')
# Vanilla-shaped crafted substitute: repair may also be created from minerals.
jd('data/barsoom/recipe/canal_regulator.json',{'type':'minecraft:crafting_shaped','pattern':[' C ','CRC',' I '],'key':{'C':'minecraft:copper_ingot','R':'minecraft:redstone','I':'minecraft:iron_ingot'},'result':{'id':'minecraft:lightning_rod','count':1}})
# Output exact reproducible zip
zip_path=OUT/'Barsoom-Canal-Outpost-26.3-datapack.zip'
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for name,body in sorted(files.items()):
  info=zipfile.ZipInfo(name,(2026,10,17,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,body)
manifest={'version':'0.1.0','minecraft':'Java 26.3','data_pack_format':[121,0],
 'runtime_test':'NOT_RUN: no Java 25/server JAR/network in build environment','file_count':len(files),
 'file_hashes':{p:hashlib.sha256(x.encode()).hexdigest() for p,x in sorted(files.items())},
 'sha256':hashlib.sha256(zip_path.read_bytes()).hexdigest()}
(OUT/'barsoom-source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
# syntax/structure static checks (no false runtime qualification)
assert len(files)>=10
assert all(p=='pack.mcmeta' or p.startswith('data/') for p in files)
assert all(not any(c.lstrip().startswith('/') for c in s.splitlines()) for p,s in files.items() if p.endswith('.mcfunction'))
for p,s in files.items():
 if p.endswith('.json') or p.endswith('.mcmeta'): json.loads(s)
 if p.endswith('.mcfunction'):
  for line in s.splitlines():
   if line.startswith('execute') or line.startswith('tellraw'):
    found=re.search(r'(\{"text".*\})',line)
    if found: json.loads(found.group(1))
assert 'minecraft:water' in files['data/barsoom/function/restore.mcfunction']
assert all('barsoom:load' in files['data/minecraft/tags/function/load.json'] for _ in [0])
print(json.dumps({'archive':str(zip_path),'sha256':manifest['sha256'],'static_checks':'PASS','files':len(files)},indent=2))
