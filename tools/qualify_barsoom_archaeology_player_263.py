#!/usr/bin/env python3
"""Official vanilla 26.3 + Mineflayer physical archaeological quest admission.

Fail closed: synthetic player must use vanilla /trigger, walk, climb,
open a real chest, withdraw a seal, return and restore without console TP/give.
Does not qualify a stock GUI client or a production/canon named location.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,os,subprocess,tempfile,time
from pathlib import Path
from probe_core_restoration_datapack_26_3 import send,stop_server,server_error_lines
from smoke_vanilla_runtime import download_verified_server,status_query
from qualify_vanilla_world_artifact_activation_263 import Refused,require,oracle

ROOT=Path(__file__).resolve().parents[1]
BUILDER=ROOT/'fixtures/barsoom/archaeology/build_archive.py'
BOT_SCRIPT=ROOT/'tools/probe_mineflayer_archaeology_263.js'
EXPECTED_SHA='ff84fcc975411782e2b0dfa454f4a3a91687ab50cb8d210af0b3ebd53150d283'
BOT_NAME='SupraArchProbe';PORT=25597

def ready(proc,log,timeout=160):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        require(proc.poll() is None,'ARCH_PHYSICAL_SERVER_EXITED:'+log.read_text(errors='replace')[-1000:])
        try:
            st=status_query('127.0.0.1',PORT,777)
            if st.get('version',{}).get('protocol')==777 and 'Done (' in log.read_text(errors='replace'):return
        except (OSError,EOFError,TimeoutError,ValueError):pass
        time.sleep(.7)
    raise Refused('ARCH_PHYSICAL_SERVER_START_TIMEOUT')

def run(evidence, steps, result):
    version=evidence['artifact_version_json']
    require(version['id']=='26.3' and version['protocol_version']==777 and version['java_version']==25,'ARCH_PHYSICAL_VERSION_DRIFT')
    require(BUILDER.exists() and BOT_SCRIPT.exists(),'ARCH_PHYSICAL_SOURCE_MISSING')
    with tempfile.TemporaryDirectory(prefix='barsoom-physical-arch-') as t:
        root=Path(t);home=root/'server';home.mkdir();packs=home/'world/datapacks';packs.mkdir(parents=True)
        jar=home/'server.jar'; download_verified_server(evidence,jar)
        require(hashlib.sha256(jar.read_bytes()).hexdigest()==evidence['server_artifact']['sha256'],'ARCH_PHYSICAL_JAR_MISMATCH')
        sp=importlib.util.spec_from_file_location('arch_builder',BUILDER)
        module=importlib.util.module_from_spec(sp); sp.loader.exec_module(module)
        rc=module.build(packs/'barsoom-arch.zip')
        require(rc['sha256']==EXPECTED_SHA,'ARCH_PHYSICAL_PACK_DRIFT')
        steps.append('exact_original_archaeology_pack_verified')
        (home/'eula.txt').write_text('eula=true\n')
        (home/'server.properties').write_text(
            'server-ip=127.0.0.1\nserver-port=25597\nonline-mode=false\nwhite-list=false\nenforce-whitelist=false\n'
            'level-name=world\nlevel-seed=4242424242\nlevel-type=minecraft:normal\n'
            'initial-enabled-packs=vanilla,file/barsoom-arch.zip\n'
            'view-distance=4\nsimulation-distance=3\nspawn-protection=0\n'
            'generate-structures=false\nsync-chunk-writes=true\n'
            'enable-rcon=false\nenable-query=false\nmax-players=2\n')
        log=home/'server.log';out=root/'player.json';bout=root/'player.log'
        stream=log.open('w',encoding='utf-8')
        proc=subprocess.Popen(['java','-Xms512M','-Xmx1536M','-jar',str(jar),'nogui'],cwd=home,
             stdin=subprocess.PIPE,stdout=stream,stderr=subprocess.STDOUT,text=True)
        bot=None; bstream=None
        try:
            ready(proc,log);steps.append('official_java_263_server_ready')
            require(not server_error_lines(log) and 'Failed to load function' not in log.read_text(errors='replace'),'ARCH_PHYSICAL_PACK_LOAD_ERRORS')
            oracle(proc,log,'execute if score #built barsoom_arch.state matches 0 if score #well barsoom_arch.state matches 0','ARCH_PHYSICAL_ZERO_STATE')
            steps.append('archaeology_scoreboard_loaded')
            # MCWORLD build-time materialization: no player spawns *inside* a
            # destructively generated well. The player later explores on foot.
            send(proc,'forceload add -16 -16 24 32')
            send(proc,'execute positioned 0 85 0 run function barsoom_arch:establish')
            oracle(proc,log,'execute if score #built barsoom_arch.state matches 1 if score #well barsoom_arch.state matches 0 if block 4 75 17 minecraft:chest','ARCH_PREBUILT_SITE')
            send(proc,'setworldspawn 3 85 1')
            send(proc,'gamerule minecraft:spawn_radius 0')
            steps.append('world_materialized_at_fixed_coordinates_before_player_join')
            bstream=bout.open('w',encoding='utf-8')
            env={**os.environ,'MC_PORT':str(PORT),'BARSOOM_ARCH_BOT_RESULT':str(out),'BARSOOM_ARCH_PREBUILT':'1'}
            bot=subprocess.Popen(['node',str(BOT_SCRIPT)],cwd=ROOT,env=env,stdout=bstream,stderr=subprocess.STDOUT,text=True)
            deadline=time.monotonic()+162
            while bot.poll() is None and time.monotonic()<deadline:
                time.sleep(.5)
            if bot.poll() is None:
                bot.terminate();bot.wait(timeout=5)
                raise Refused('ARCH_PHYSICAL_PLAYER_TIMEOUT')
            require(out.exists(),'ARCH_PHYSICAL_BOT_NO_RECEIPT:'+bout.read_text(errors='replace')[-1000:])
            player=json.loads(out.read_text());result['player_receipt']=player
            steps.extend(player.get('stages',[]))
            require(bot.returncode==0 and not player.get('error'),'ARCH_PHYSICAL_PLAYER_FAILED:'+str(player.get('error'))[:900])
            require(player['actual_container_withdrawal'] is True,'ARCH_PHYSICAL_CHEST_WITHDRAWAL_NOT_CONFIRMED')
            require(player['console_player_positioned'] is False and player['console_player_item_granted'] is False,'ARCH_PHYSICAL_SHORTCUT_PRESENT')
            steps.append('player_physical_journey_complete')
            oracle(proc,log,'execute if score #built barsoom_arch.state matches 1 if score #well barsoom_arch.state matches 1','ARCH_PHYSICAL_RESTORED_SCORE')
            oracle(proc,log,'execute at @e[type=minecraft:marker,tag=barsoom_arch.well,limit=1] if block ~0 ~-1 ~0 minecraft:water','ARCH_PHYSICAL_WATER_ONLY')
            steps.append('independent_water_restoration_verified')
            oracle(proc,log,'execute at @e[type=minecraft:marker,tag=barsoom_arch.well,limit=1] if block ~6 ~-1 ~2 minecraft:farmland','ARCH_PHYSICAL_FARMLAND_ONLY')
            steps.append('independent_farmland_verified')
            oracle(proc,log,'execute at @e[type=minecraft:marker,tag=barsoom_arch.well,limit=1] if block ~6 ~0 ~2 minecraft:wheat','ARCH_PHYSICAL_CROP_ONLY')
            steps.append('independent_crop_verified')
            oracle(proc,log,'execute at @e[type=minecraft:marker,tag=barsoom_arch.well,limit=1] unless items block ~4 ~-10 ~17 container.0 minecraft:heart_of_the_sea','ARCH_PHYSICAL_CHEST_EMPTY')
            oracle(proc,log,f'execute unless items entity {BOT_NAME} inventory.* minecraft:heart_of_the_sea','ARCH_PHYSICAL_SEAL_CONSUMED')
            steps.append('independent_server_confirms_real_item_and_well_restoration')
            # Save and restart with independent scoreboard, water and player-authored mutation readbacks.
            send(proc,'save-all flush')
            require(stop_server(proc)==0,'ARCH_PHYSICAL_STOP_FAILURE');steps.append('saved_original_world')
            stream.close()
            log=home/'restarted.log';stream=log.open('w',encoding='utf-8')
            proc=subprocess.Popen(['java','-Xms512M','-Xmx1536M','-jar',str(jar),'nogui'],cwd=home,
                 stdin=subprocess.PIPE,stdout=stream,stderr=subprocess.STDOUT,text=True)
            ready(proc,log)
            oracle(proc,log,'execute if score #built barsoom_arch.state matches 1 if score #well barsoom_arch.state matches 1','ARCH_PHYSICAL_RESTART_SCORES')
            base=player['base']; x=int(base['x']); z=int(base['z'])
            send(proc,f'forceload add {x-16} {z-16} {x+24} {z+32}')
            time.sleep(1)
            oracle(proc,log,'execute at @e[type=minecraft:marker,tag=barsoom_arch.well,limit=1] if block ~0 ~-1 ~0 minecraft:water','ARCH_PHYSICAL_RESTART_WELL')
            steps.append('player_restored_well_survives_restart')
            require(stop_server(proc)==0,'ARCH_PHYSICAL_RESTART_STOP_FAILURE')
            require(not server_error_lines(log),'ARCH_PHYSICAL_RESTART_NATIVE_ERROR')
        finally:
            if bot is not None and bot.poll() is None:
                bot.terminate()
                try:bot.wait(timeout=5)
                except subprocess.TimeoutExpired:bot.kill();bot.wait(timeout=5)
            if bstream and not bstream.closed:bstream.close()
            if proc.poll() is None:
                try:stop_server(proc)
                except Exception:proc.kill();proc.wait(timeout=5)
            if not stream.closed:stream.close()
            if out.exists() and 'player_receipt' not in result:
                result['player_receipt']=json.loads(out.read_text())

def main():
    p=argparse.ArgumentParser();p.add_argument('--evidence',type=Path,required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    steps=[];receipt={'schema':'supracraft.barsoom.archaeology.physical-player/v0.1',
        'result':'FAIL','first_failure':None,'minecraft_version':'26.3',
        'archive_sha256':EXPECTED_SHA,'stages':steps,'human_stock_client_qualified':False,
        'production_deployment':'HOLD','player_item_recovery_qualified':False}
    try:
        run(json.loads(args.evidence.read_text()),steps,receipt)
        receipt.update(result='PASS',player_item_recovery_qualified=True)
    except Exception as e:receipt['first_failure']=type(e).__name__+': '+str(e)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n');print(json.dumps(receipt,indent=2,sort_keys=True))
    return 0 if receipt['result']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
