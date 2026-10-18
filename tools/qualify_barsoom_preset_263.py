#!/usr/bin/env python3
"""Vanilla 26.3 native world-preset admission on disposable official server.

The aim is to prove the world preset is truly used for world creation,
not just that its JSON parses, and that Nether and End survive.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from probe_core_restoration_datapack_26_3 import send,stop_server,wait_for_predicate,server_error_lines
from smoke_vanilla_runtime import download_verified_server, status_query
from qualify_vanilla_world_artifact_activation_263 import Refused,require
from sys import path as syspath

ROOT=Path(__file__).resolve().parents[1]
syspath.insert(0,str(ROOT/'fixtures/barsoom/terrain'))
from gen_dead_sea import build
from compose_barsoom_263 import compose
PORT=25599

def status_ready(proc, log, timeout=180):
 start=time.monotonic()
 while time.monotonic()-start<timeout:
  require(proc.poll() is None,'PRESET_SERVER_EXITED:'+log.read_text(errors='replace')[-1400:])
  try:
   obj=status_query('127.0.0.1',PORT,777)
   if obj.get('version',{}).get('protocol')==777 and 'Done (' in log.read_text(errors='replace'):return
  except (OSError,EOFError,TimeoutError,ValueError):pass
  time.sleep(.7)
 raise Refused('PRESET_SERVER_START_TIMEOUT:'+log.read_text(errors='replace')[-1800:])

def prove(proc, log, predicate, mark, timeout=10):
 try:wait_for_predicate(proc,log,marker=mark,predicate=predicate,timeout=timeout)
 except RuntimeError as exc:raise Refused('PRESET_PREDICATE_'+mark+':'+str(exc)[-900:]) from exc

def execute(evidence, out, outpost_pack=None):
 steps=[]
 require(evidence['artifact_version_json']['id']=='26.3' and evidence['artifact_version_json']['java_version']==25,'VERSION_INVALID')
 with tempfile.TemporaryDirectory(prefix='barsoom-dead-sea-') as tmp:
  d=Path(tmp);home=d/'server';home.mkdir()
  jar=home/'server.jar';download_verified_server(evidence,jar)
  require(hashlib.sha256(jar.read_bytes()).hexdigest()==evidence['server_artifact']['sha256'],'OFFICIAL_JAR_MISMATCH')
  world=home/'world';(world/'datapacks').mkdir(parents=True)
  terrain=d/'terrain.zip';build(terrain)
  if outpost_pack:
   rec=compose(outpost_pack,terrain,world/'datapacks/barsoom-dead-sea.zip')
   steps.append('exact_outpost_and_terrain_composed_before_creation')
  else:
   shutil.copyfile(terrain,world/'datapacks/barsoom-dead-sea.zip')
   rec={'sha256':hashlib.sha256(terrain.read_bytes()).hexdigest()}
   steps.append('pack_built_and_staged_before_creation')
  (home/'eula.txt').write_text('eula=true\n')
  (home/'server.properties').write_text(
   'server-ip=127.0.0.1\nserver-port=25599\nonline-mode=false\n'
   'level-name=world\nlevel-type=barsoom:dead_sea\n'
   'initial-enabled-packs=vanilla,file/barsoom-dead-sea.zip\n'
   'view-distance=3\nsimulation-distance=2\nspawn-protection=0\nmax-players=1\n'
   'generate-structures=false\nsync-chunk-writes=true\n'
   'enable-rcon=false\nenable-query=false\nlevel-seed=1811001\n'
   'motd=Barsoom dead-sea native terrain admission\n')
  log=home/'native-server.log'
  with log.open('w+',encoding='utf-8') as fh:
   proc=subprocess.Popen(['java','-Xms512M','-Xmx1536M','-jar',str(jar),'nogui'],cwd=home,
           stdin=subprocess.PIPE,stdout=fh,stderr=subprocess.STDOUT,text=True)
   try:
    status_ready(proc,log);steps.append('official_server_ready')
    content=log.read_text(errors='replace')
    require(not server_error_lines(log) and 'Failed to load data packs' not in content,'NATIVE_DATAPACK_LOAD_ERROR:'+content[-1600:])
    steps.append('no_server_load_errors')
    if outpost_pack:
     prove(proc,log,'execute if score #built barsoom.state matches 0 if score #canal barsoom.state matches 0','COMPOSITE_OUTPOST_FUNCTIONS_LOADED')
     steps.append('composed_outpost_datapack_initializes_state')
    # Worldgen state is checked from sampled *biome* reads. This will fail
    # if server silently creates default plains/forest/river terrain.
    send(proc,'forceload add 0 0')
    time.sleep(.8)
    prove(proc,log,'execute if biome 0 64 0 minecraft:badlands','ORIGIN_IS_BADLANDS');steps.append('origin_biome_badlands')
    # Distinct sampled chunks, independent of the initial spawn location.
    for x,z in [(80,80),(-80,64),(128,-96)]:
     send(proc,f'forceload add {x} {z}')
     time.sleep(.7)
     prove(proc,log,f'execute if biome {x} 64 {z} minecraft:badlands',f'BIOME_{x}_{z}');steps.append(f'badlands_at_{x}_{z}')
    prove(proc,log,'execute in minecraft:the_nether run say BARSOOM_NETHER_PRESENT','NETHER_PRESENT');steps.append('nether_dimension_registered')
    prove(proc,log,'execute in minecraft:the_end run say BARSOOM_END_PRESENT','END_PRESENT');steps.append('end_dimension_registered')
    require(stop_server(proc)==0,'GRACEFUL_STOP_FAILED');steps.append('save_stop_pass')
   finally:
    if proc.poll() is None:
     try:stop_server(proc)
     except Exception:proc.kill();proc.wait(timeout=10)
  return {'schema':'supracraft.barsoom.dead-sea-preset/1','classification':'WORLD_PRESET_NATIVE_FIXTURE_ONLY','result':'PASS','steps':steps,'sha256':rec['sha256'],
          'minecraft':'26.3','protocol':777,'stock_client_qualified':False,'custom_macrogeography_qualified':False,'physical_truenas_apply':'HOLD'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--outpost-pack',type=Path)
 a=p.parse_args();result={'result':'FAIL'}
 try:result=execute(json.loads(a.evidence.read_text()),a.out,a.outpost_pack)
 except Exception as exc:result.update({'error':type(exc).__name__+': '+str(exc),'classification':'NATIVE_PRESET_UNQUALIFIED','minecraft':'26.3'})
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
 print(json.dumps(result,sort_keys=True,indent=2))
 return 0 if result['result']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
