#!/usr/bin/env python3
"""Composition acceptance: qualified outpost quest on real 26.3 Dead Sea terrain.

Reuses exact accepted OP4E Barsoom source fixture by immutable commit (not
copied or modified), and substitutes only a documented world preset and ZIP.
No mods, plugins, operator console shortcuts beyond the accepted player test.
"""
from __future__ import annotations
import argparse,hashlib,json,sys,tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
PINNED=HERE/'.deps/qualified-outpost-source'
sys.path.insert(0,str(PINNED/'tools'))
sys.path.insert(0,str(HERE/'fixtures/barsoom/terrain'))
import qualify_barsoom_263 as qualified
from gen_dead_sea import build
from compose_barsoom_263 import compose


def config(home:Path)->None:
 (home/'eula.txt').write_text('eula=true\n')
 (home/'server.properties').write_text(
  'server-ip=127.0.0.1\nserver-port=25593\nonline-mode=false\n'
  'white-list=false\nenforce-whitelist=false\n'
  'level-name=world\nlevel-type=barsoom:dead_sea\n'
  'initial-enabled-packs=vanilla,file/barsoom.zip\n'
  'view-distance=3\nsimulation-distance=2\nmax-players=2\n'
  'spawn-protection=0\ngenerate-structures=false\n'
  'enable-rcon=false\nenable-query=false\n'
  'level-seed=4242424242\nsync-chunk-writes=true\n'
  'motd=Barsoom composed 26.3 native quest qualification\n')

def run(evidence,steps):
 assert (PINNED/'fixtures/barsoom/build_barsoom.py').is_file(),'pinned fixture checkout missing'
 original=qualified.validate_source() # re-run exact source/digest gate
 steps.append('qualified_immutable_original_outpost_rebuilt')
 with tempfile.TemporaryDirectory(prefix='barsoom-composed-') as d:
  root=Path(d);terrain=root/'terrain.zip';combined=root/'combined.zip'
  trec=build(terrain);receipt=compose(original,terrain,combined)
  steps.append('composed_digest_'+receipt['sha256'])
  assert trec['sha256']==receipt['terrain_sha256']
  qualified.validate_source=lambda:combined
  qualified.CANDIDATE=receipt['sha256']
  qualified.server_config=config
  qualified.run(evidence,steps)
 return receipt

def main():
 p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 a=p.parse_args();steps=[];result={'schema':'supracraft.barsoom.composite-player/1','classification':'VANILLA_BOT_WORLDGEN_AND_QUEST','result':'FAIL','steps':steps,
                        'stock_mojang_client_qualified':False,'physical_truenas_apply':'HOLD'}
 try:
  c=run(json.loads(a.evidence.read_text()),steps)
  result.update({'result':'PASS','candidate_sha256':c['sha256'],'first_failure':None})
 except Exception as ex:result.update({'first_failure':type(ex).__name__+': '+str(ex)})
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
 print(json.dumps(result,indent=2,sort_keys=True))
 return 0 if result['result']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
