#!/usr/bin/env python3
"""Fail-closed official 26.3 oracle for an archaeological world feature.

Engine-surface seam: exact Mojang server parse/dispatch, chest slot, ladder,
marker lifetime, world block persistence, scoreboard state after save/restart.
Do not count syntactic acceptance as a gameplay acceptance.
"""
import argparse,hashlib,json,subprocess,tempfile,time,sys
from pathlib import Path
from probe_core_restoration_datapack_26_3 import send,stop_server,wait_for_predicate,server_error_lines
from smoke_vanilla_runtime import download_verified_server,status_query
from qualify_vanilla_world_artifact_activation_263 import Refused,require

ROOT=Path(__file__).resolve().parents[1]
BUILDER=ROOT/'fixtures/barsoom/archaeology/build_archive.py'
PACK_SHA='48238281be8fa315f796d0b23c3d23921f154f68e72f0b1049c12c372d16cb0c'
PORT=25597

def ready(p, log, timeout=170):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        require(p.poll() is None,'ARCHIVE_SERVER_DIED:'+log.read_text(errors='replace')[-900:])
        try:
            a=status_query('127.0.0.1',PORT,777)
            if a.get('version',{}).get('protocol')==777 and 'Done (' in log.read_text(errors='replace'):return
        except (OSError,EOFError,TimeoutError,ValueError):pass
        time.sleep(.6)
    raise Refused('ARCHIVE_SERVER_TIMEOUT:'+log.read_text(errors='replace')[-1200:])

def check(p, log, predicate, marker, timeout=9):
    try:wait_for_predicate(p,log,marker=marker,predicate=predicate,timeout=timeout)
    except RuntimeError as e:raise Refused('ARCHIVE_NATIVE_ORACLE_'+marker) from e

def run(evidence,steps):
    ver=evidence['artifact_version_json']
    require(ver['id']=='26.3' and ver['java_version']==25 and ver['protocol_version']==777,'ARCHIVE_RELEASE_DRIFT')
    with tempfile.TemporaryDirectory(prefix='barsoom-archive-') as d:
        root=Path(d); server=root/'server';server.mkdir();world=server/'world';(world/'datapacks').mkdir(parents=True)
        jar=server/'server.jar';download_verified_server(evidence,jar)
        require(hashlib.sha256(jar.read_bytes()).hexdigest()==evidence['server_artifact']['sha256'],'ARCHIVE_OFFICIAL_JAR_DRIFT')
        import importlib.util
        spec=importlib.util.spec_from_file_location('archive_builder',BUILDER)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        rec=mod.build(world/'datapacks/archive.zip')
        require(rec['sha256']==PACK_SHA and rec['members']==9,'ARCHIVE_SOURCE_OR_PACK_DRIFT')
        steps.append('exact_archive_pack_sha256_verified')
        (server/'eula.txt').write_text('eula=true\n')
        (server/'server.properties').write_text(
          'server-ip=127.0.0.1\nserver-port=25597\n'
          'online-mode=false\nlevel-name=world\nlevel-seed=4242424242\n'
          'level-type=minecraft:normal\ninitial-enabled-packs=vanilla,file/archive.zip\n'
          'view-distance=3\nsimulation-distance=2\nspawn-protection=0\n'
          'generate-structures=false\nsync-chunk-writes=true\n'
          'enable-rcon=false\nenable-query=false\nmax-players=2\n')
        def launch(name):
            log=server/(name+'.log');stream=log.open('w',encoding='utf-8')
            proc=subprocess.Popen(['java','-Xms512M','-Xmx1536M','-jar',str(jar),'nogui'],cwd=server,stdin=subprocess.PIPE,stdout=stream,stderr=subprocess.STDOUT,text=True)
            ready(proc,log)
            return proc,log,stream
        proc,log,fh=launch('initial')
        try:
            require(not server_error_lines(log) and 'Failed to load function' not in log.read_text(errors='replace'),'ARCHIVE_PACK_PARSE_ERRORS')
            steps.append('official_263_server_loaded_pack')
            check(proc,log,'execute if score #built barsoom_arch.state matches 0 if score #well barsoom_arch.state matches 0','INITIAL_SCORES')
            send(proc,'forceload add -16 -16 24 32')
            send(proc,'execute positioned 0 85 0 run function barsoom_arch:establish')
            check(proc,log,'execute if score #built barsoom_arch.state matches 1 if score #well barsoom_arch.state matches 0','SITE_INITIALIZED')
            check(proc,log,'execute if block 4 75 17 minecraft:chest if block 0 85 4 minecraft:ladder[facing=south]','ROOM_AND_LADDER')
            check(proc,log,'execute if entity @e[type=minecraft:marker,tag=barsoom_arch.well] if entity @e[type=minecraft:marker,tag=barsoom_arch.archive]','SURFACE_AND_BURIED_MARKERS')
            check(proc,log,'execute if items block 4 75 17 container.0 minecraft:heart_of_the_sea','CANONICAL_ITEM_IN_REAL_CHEST')
            check(proc,log,'execute if block 0 84 0 minecraft:cut_sandstone','WELL_DRY_BEFORE_REPAIR')
            steps.append('bounded_surface_archive_shaft_markers_loot_verified')
            # Server-authored positive restoration tests the mechanical consequence,
            # NOT whether a player can recover/consume the seal; that requires the bot.
            send(proc,'function barsoom_arch:restore')
            check(proc,log,'execute if score #well barsoom_arch.state matches 1 if block 0 84 0 minecraft:water if block 6 85 2 minecraft:wheat','RESTORED_SURFACE_CONSEQUENCE')
            steps.append('water_and_field_consequence_native_oracle')
            send(proc,'setblock -10 85 7 minecraft:diamond_block')
            check(proc,log,'execute if block -10 85 7 minecraft:diamond_block','PLAYER_MUTATION_SET')
            require(stop_server(proc)==0,'ARCHIVE_FIRST_STOP_FAILED')
            fh.close()
            steps.append('first_save_stop')
            proc,log,fh=launch('restart')
            check(proc,log,'execute if score #built barsoom_arch.state matches 1 if score #well barsoom_arch.state matches 1','RESTART_SCORES')
            send(proc,'forceload add -16 -16 24 32')
            check(proc,log,'execute if block 0 84 0 minecraft:water if block -10 85 7 minecraft:diamond_block','RESTART_WELL_AND_MODIFICATION')
            steps.append('restart_durable_state_and_player_block')
            require(stop_server(proc)==0,'ARCHIVE_SECOND_STOP_FAILED')
            steps.append('graceful_stop')
        finally:
            if proc.poll() is None:
                try:stop_server(proc)
                except Exception:proc.kill();proc.wait(timeout=10)
            if not fh.closed:fh.close()

def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    steps=[];failure=None
    try:run(json.loads(a.evidence.read_text()),steps)
    except Exception as e:failure=type(e).__name__+': '+str(e)
    o={'schema':'supracraft.barsoom.archaeology/1','release':'26.3','pack_sha256':PACK_SHA,'status':'PASS' if failure is None else 'FAIL','first_failure':failure,'steps':steps,'physical_archive_retrieval_by_player_qualified':False,'stock_client_qualified':False,'true_named_canon_place_qualified':False,'physical_truenas_apply':'HOLD'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(o,indent=2,sort_keys=True)+'\n');print(json.dumps(o,indent=2))
    return 0 if failure is None else 1
if __name__=='__main__':sys.exit(main())
