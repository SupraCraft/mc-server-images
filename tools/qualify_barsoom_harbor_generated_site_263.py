#!/usr/bin/env python3
"""Native 26.3 MCWORLD site selector/materializer on generated Barsoom terrain.

Two immutable producer packs, no world-rewrite, no canonical place attribution.
All world modifications are limited to disposable TempDirectory worlds.
This first stage qualifies site selection + persistence, NOT actual player HIL.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import time
from pathlib import Path

from probe_core_restoration_datapack_26_3 import send, stop_server, server_error_lines
from smoke_vanilla_runtime import download_verified_server
from qualify_barsoom_archaeology_unmarked_263 import ready
from qualify_vanilla_world_artifact_activation_263 import oracle, require, Refused

ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS = ROOT / 'fixtures/barsoom/archaeology/generated_site_constraints.json'
BUILDER = ROOT / 'fixtures/barsoom/archaeology/build_archive.py'
TERRAIN = ROOT / 'fixtures/barsoom/terrain/gen_dead_sea.py'
ARCH_SHA = 'a81eb98447f097d373233342786d94d2b8634c2f28d2d26543fd5b205663fd81'
TERRAIN_SHA = '9d5ad764a2df4786666326e997a3ed724524583fe3191b60305677fbe5fb531e'
PORT = 25597

def import_file(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def contains_after(log: Path, mark: str, before: int) -> bool:
    return log.read_text(errors='replace').count(mark) > before

def native_score_integer(proc, log, entry: str, label: str, lower=0, upper=255) -> int:
    """Read a native scoreboard through two exhaustive, logged branch oracles.
    No fabricated or pre-known site Y and no out-of-band world-format parser.
    """
    lo, hi = lower, upper
    while lo < hi:
        mid = (lo + hi) // 2
        left = f'BARSOOM_HEIGHT_{label}_{mid}_LE'
        right = f'BARSOOM_HEIGHT_{label}_{mid}_GT'
        l0 = log.read_text(errors='replace').count(left)
        r0 = log.read_text(errors='replace').count(right)
        send(proc, f'execute if score {entry} barsoom_arch.state matches ..{mid} run say {left}')
        send(proc, f'execute unless score {entry} barsoom_arch.state matches ..{mid} run say {right}')
        until = time.monotonic() + 7
        result = None
        while time.monotonic() < until:
            l = contains_after(log, left, l0)
            r = contains_after(log, right, r0)
            require(not (l and r), 'SITE_ORACLE_CONTRADICTORY_BRANCH:' + label)
            if l or r:
                result = (l, r)
                break
            time.sleep(.12)
        require(result is not None, 'SITE_NATIVE_SCORE_TIMEOUT:' + label)
        if result[0]:
            hi = mid
        else:
            lo = mid + 1
    return lo

def surface(proc, log, x: int, z: int, ident: int) -> int:
    tag = f'barsoom_site_probe_{ident}'
    key = f'#site_height_{ident}'
    send(proc, f'execute positioned {x} 0 {z} positioned over motion_blocking_no_leaves run summon minecraft:marker ~ ~ ~ {{Tags:["{tag}"]}}')
    oracle(proc, log, f'execute if entity @e[type=minecraft:marker,tag={tag},limit=1]',
           f'SITE_HEIGHT_MARKER_{ident}', timeout=7)
    send(proc, f'execute store result score {key} barsoom_arch.state run data get entity @e[type=minecraft:marker,tag={tag},limit=1] Pos[1] 1')
    oracle(proc, log, f'execute if score {key} barsoom_arch.state matches 0..255',
           f'SITE_NATIVE_HEIGHT_SAVED_{ident}', timeout=7)
    y = native_score_integer(proc, log, key, str(ident))
    send(proc, f'kill @e[type=minecraft:marker,tag={tag}]')
    return y

def select_site(proc, log, spec, rejected):
    c = spec['constraints']
    for x, z in spec['candidates']:
        heights = []
        try:
            send(proc, f'forceload add {x-16} {z-16} {x+80} {z+32}')
            oracle(proc, log, f'execute if biome {x} 64 {z} minecraft:badlands',
                   f'WORLDGEN_ANCHOR_BIOME_{x}_{z}', timeout=5)
            oracle(proc, log, f'execute if biome {x+64} 64 {z} minecraft:badlands',
                   f'WORLDGEN_APPROACH_BIOME_{x}_{z}', timeout=5)
            for idx, (dx, dz) in enumerate(c['samples']):
                y = surface(proc, log, x+dx, z+dz, idx)
                heights.append(y)
                if idx == 0:
                    require(c['anchor_height_min'] <= y <= c['anchor_height_max'],
                            'SITE_ANCHOR_HEIGHT_OUTSIDE_BOUNDS')
                else:
                    require(abs(y - heights[0]) <= c['absolute_max_height_delta'],
                            'SITE_SURFACE_GRADE_EXCEEDS_BOUND')
            return {'x':x, 'y':heights[0], 'z':z, 'native_heights':heights,
                    'biome':'minecraft:badlands', 'placement_backend':'vanilla_26.3_build_time'}
        except Exception as exc:
            rejected.append({'candidate':[x,z], 'observed_heights':heights,
                             'rejection':type(exc).__name__+': '+str(exc)[:380]})
    raise Refused('NO_GENERATED_SITE_SATISFIES_FROZEN_CONSTRAINTS')

def run_one(seed: int, spec: dict) -> dict:
    evidence=json.loads((ROOT/'probes/26.3-release-identity.json').read_text())
    ver=evidence['artifact_version_json']
    require(ver['id']=='26.3' and ver['java_version']==25 and ver['protocol_version']==777,'SITE_RELEASE_DRIFT')
    with tempfile.TemporaryDirectory(prefix=f'barsoom-site-{seed}-') as d:
        root=Path(d); home=root/'server'; home.mkdir()
        packs=home/'world/datapacks'; packs.mkdir(parents=True)
        jar=home/'server.jar'; download_verified_server(evidence,jar)
        require(hashlib.sha256(jar.read_bytes()).hexdigest()==evidence['server_artifact']['sha256'],
                'OFFICIAL_SERVER_JAR_DRIFT')
        terrain=import_file(TERRAIN,'barsoom_terrain_site')
        arch=import_file(BUILDER,'barsoom_archive_site')
        t=terrain.build(packs/'terrain.zip'); a=arch.build(packs/'archive.zip')
        require(t['sha256']==TERRAIN_SHA and a['sha256']==ARCH_SHA,'SOURCE_PACK_SHA_DRIFT')
        (home/'eula.txt').write_text('eula=true\n')
        (home/'server.properties').write_text(
            'server-ip=127.0.0.1\nserver-port=25597\nonline-mode=false\n'
            'level-name=world\nlevel-type=barsoom:dead_sea\n'
            'initial-enabled-packs=vanilla,file/terrain.zip,file/archive.zip\n'
            'view-distance=4\nsimulation-distance=3\nspawn-protection=0\n'
            'generate-structures=false\nsync-chunk-writes=true\n'
            f'level-seed={seed}\nmax-players=2\nenable-rcon=false\nenable-query=false\n')
        def launch(filename: str):
            path=home/filename
            stream=path.open('w',encoding='utf-8')
            p=subprocess.Popen(['java','-Xms512M','-Xmx1536M','-jar',str(jar),'nogui'],
                               cwd=home,stdin=subprocess.PIPE,stdout=stream,
                               stderr=subprocess.STDOUT,text=True)
            ready(p,path)
            require(not server_error_lines(path) and 'Failed to load function' not in path.read_text(errors='replace'),
                    'SITE_NATIVE_DATAPACK_OR_SERVER_ERRORS')
            return p,path,stream
        proc,log,stream=launch('initial.log')
        rejected=[]
        try:
            oracle(proc,log,'execute if score #built barsoom_arch.state matches 0 if score #well barsoom_arch.state matches 0',
                   'SITE_INITIAL_STATE')
            site=select_site(proc,log,spec,rejected)
            x,y,z=(site[k] for k in ['x','y','z'])
            # The native heightmap-selected surface anchors the exact existing
            # archive producer. Its 25x34 region intentionally includes air:
            # only use against a newly created, throwaway world.
            send(proc,f'execute positioned {x} {y} {z} run function barsoom_arch:establish')
            oracle(proc,log,f'execute if score #built barsoom_arch.state matches 1 if block {x+4} {y-10} {z+17} minecraft:chest if block {x} {y} {z+4} minecraft:ladder[facing=south]',
                   'SITE_BURIED_ROOM_AND_LADDER')
            oracle(proc,log,f'execute if items block {x+4} {y-10} {z+17} container.0 minecraft:heart_of_the_sea[minecraft:custom_data~{{barsoom_arch:{{harbor_seal:1b}}}}]',
                   'SITE_MARKED_SEAL_NOT_LOST')
            oracle(proc,log,f'execute if block {x} {y-1} {z} minecraft:cut_sandstone if score #well barsoom_arch.state matches 0',
                   'SITE_DRY_WELL_AT_NATIVE_SURFACE')
            # Bounded build-time footpath and safe arrival pad. This is
            # an actuator with exact pre-checked native terrain grades, NOT
            # evidence that vanilla authored a natural flat dock here.
            send(proc,f'fill {x+3} {y-1} {z} {x+80} {y-1} {z+3} minecraft:cut_sandstone replace')
            send(proc,f'fill {x+52} {y-1} {z-12} {x+76} {y-1} {z+12} minecraft:cut_sandstone replace')
            send(proc,f'fill {x+13} {y} {z-1} {x+80} {y+5} {z+4} minecraft:air replace')
            send(proc,f'fill {x+52} {y} {z-12} {x+76} {y+5} {z+12} minecraft:air replace')
            oracle(proc,log,f'execute if block {x+64} {y-1} {z} minecraft:cut_sandstone if block {x+64} {y} {z} minecraft:air',
                   'SITE_SAFE_ARRIVAL_PREBUILT')
            send(proc,f'setworldspawn {x+64} {y} {z}')
            send(proc,'gamerule minecraft:spawn_radius 0')
            oracle(proc,log,f'execute if biome {x} 64 {z} minecraft:badlands',
                   'SITE_BADLANDS_STILL_GENERATED_AFTER_MATERIALIZATION')
            require(stop_server(proc)==0,'SITE_FIRST_STOP_FAILED')
            stream.close()
            proc,log,stream=launch('restarted.log')
            send(proc,f'forceload add {x-16} {z-16} {x+80} {z+32}')
            oracle(proc,log,f'execute if score #built barsoom_arch.state matches 1 if score #well barsoom_arch.state matches 0 if block {x+4} {y-10} {z+17} minecraft:chest',
                   'SITE_DURABLE_ARCHIVE_DRY_WELL_AFTER_RESTART')
            oracle(proc,log,f'execute if block {x+64} {y-1} {z} minecraft:cut_sandstone if block {x+64} {y} {z} minecraft:air',
                   'SITE_DURABLE_APPROACH_AFTER_RESTART')
            require(stop_server(proc)==0,'SITE_SECOND_STOP_FAILED')
            return {'seed':seed,'result':'PASS','selected_site':site,'rejected_candidates':rejected,
                    'site_grade_limit':spec['constraints']['absolute_max_height_delta'],
                    'terrain_sha256':TERRAIN_SHA,'archive_sha256':ARCH_SHA,
                    'real_player_quest_qualified':False,'natural_shoreline_attested':False}
        finally:
            if proc.poll() is None:
                try:stop_server(proc)
                except Exception:proc.kill();proc.wait(timeout=10)
            if not stream.closed:stream.close()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    runs=[];failure=None
    try:
        spec=json.loads(CONSTRAINTS.read_text())
        require(spec['schema']=='supracraft.mcworld.barsoom-harbor-site/0.1','SITE_MANIFEST_UNKNOWN')
        for seed in spec['seeds']:
            runs.append(run_one(seed,spec))
    except Exception as exc:
        failure=type(exc).__name__+': '+str(exc)
    receipt={'schema':'supracraft.mcworld.barsoom-harbor-generated/0.1',
             'status':'PASS' if failure is None else 'FAIL',
             'first_failure':failure,'runs':runs,'release':'26.3',
             'stock_client_qualified':False,'physical_player_in_generated_terrain_qualified':False,
             'physical_truenas_apply':'HOLD','merge':'HOLD'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    print(json.dumps(receipt,sort_keys=True,indent=2))
    return 0 if failure is None else 1
if __name__=='__main__':
    raise SystemExit(main())
