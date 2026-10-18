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
BOT_SCRIPT=ROOT/'tools/probe_mineflayer_archaeology_generated_263.js'
from qualify_barsoom_harbor_generated_site_263 import select_site, CONSTRAINTS, TERRAIN, TERRAIN_SHA, import_file
EXPECTED_SHA='a81eb98447f097d373233342786d94d2b8634c2f28d2d26543fd5b205663fd81'
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

def run(evidence, steps, result, seed):
    version=evidence['artifact_version_json']
    require(version['id']=='26.3' and version['protocol_version']==777 and version['java_version']==25,'ARCH_PHYSICAL_VERSION_DRIFT')
    require(BUILDER.exists() and BOT_SCRIPT.exists(),'ARCH_PHYSICAL_SOURCE_MISSING')
    with tempfile.TemporaryDirectory(prefix=f'barsoom-generated-arch-{seed}-') as t:
        root=Path(t);home=root/'server';home.mkdir();packs=home/'world/datapacks';packs.mkdir(parents=True)
        jar=home/'server.jar'; download_verified_server(evidence,jar)
        require(hashlib.sha256(jar.read_bytes()).hexdigest()==evidence['server_artifact']['sha256'],'ARCH_PHYSICAL_JAR_MISMATCH')
        sp=importlib.util.spec_from_file_location('arch_builder',BUILDER)
        module=importlib.util.module_from_spec(sp); sp.loader.exec_module(module)
        rc=module.build(packs/'barsoom-arch.zip')
        require(rc['sha256']==EXPECTED_SHA,'ARCH_PHYSICAL_PACK_DRIFT')
        steps.append('exact_original_archaeology_pack_verified')
        terrain_module=import_file(TERRAIN,'barsoom_terrain_player')
        terrain_receipt=terrain_module.build(packs/'terrain.zip')
        require(terrain_receipt['sha256']==TERRAIN_SHA,'ARCH_GENERATED_TERRAIN_PACK_DRIFT')
        steps.append('exact_26_3_generated_dead_sea_preset_pinned')
        (home/'eula.txt').write_text('eula=true\n')
        (home/'server.properties').write_text(
            'server-ip=127.0.0.1\nserver-port=25597\nonline-mode=false\nwhite-list=false\nenforce-whitelist=false\n'
            f'level-name=world\nlevel-seed={seed}\nlevel-type=barsoom:dead_sea\n'
            'initial-enabled-packs=vanilla,file/terrain.zip,file/barsoom-arch.zip\n'
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
            spec=json.loads(CONSTRAINTS.read_text())
            rejected=[]
            site=select_site(proc,log,spec,rejected)
            result['selected_site']=site
            result['rejected_candidates']=rejected
            x,y,z=site['x'],site['y'],site['z']
            steps.append('native_generated_terrain_site_constraints_accepted')
            send(proc,f'execute positioned {x} {y} {z} run function barsoom_arch:establish')
            oracle(proc,log,f'execute if score #built barsoom_arch.state matches 1 if score #well barsoom_arch.state matches 0 if block {x+4} {y-10} {z+17} minecraft:chest','ARCH_PREBUILT_SITE')
            # Disposable lookalike chest: physically player-accessible inside the
            # archive, but never populated by /give, /tp or operator inventory edits.
            # Original archive and all accepted #97/#98 fixtures stay immutable.
            send(proc,f'setblock {x+6} {y-10} {z+18} minecraft:chest[facing=west]')
            send(proc,f'item replace block {x+6} {y-10} {z+18} container.0 with minecraft:heart_of_the_sea 1')
            oracle(proc,log,
                f'execute if items block {x+6} {y-10} {z+18} container.0 minecraft:heart_of_the_sea',
                'ARCH_UNMARKED_CHEST_LOADED')
            oracle(proc,log,
                f'execute unless items block {x+6} {y-10} {z+18} container.0 minecraft:heart_of_the_sea[minecraft:custom_data~{{barsoom_arch:{{harbor_seal:1b}}}}]',
                'ARCH_UNMARKED_CHEST_HAS_NO_ORIGIN_MARK')
            steps.append('ordinary_item_only_in_disposable_test_chest')
            # Recovered spawn-search semantics require a genuinely safe
            # materialized arrival site. Do not rely on setworldspawn alone:
            # an invalid location causes vanilla to select a nearby surface.
            # Place the spawn *outside* the authored ruin and provide a dry
            # level stone pedestrian approach to the surface quay.
            send(proc,f'fill {x+3} {y-1} {z} {x+80} {y-1} {z+3} minecraft:cut_sandstone replace')
            send(proc,f'fill {x+52} {y-1} {z-12} {x+76} {y-1} {z+12} minecraft:cut_sandstone replace')
            send(proc,f'fill {x+13} {y} {z-1} {x+80} {y+5} {z+4} minecraft:air replace')
            send(proc,f'fill {x+52} {y} {z-12} {x+76} {y+5} {z+12} minecraft:air replace')
            oracle(proc,log,f'execute if block {x+64} {y-1} {z} minecraft:cut_sandstone if block {x+64} {y} {z} minecraft:air if block {x+64} {y+1} {z} minecraft:air','ARCH_ARRIVAL_PAD')
            send(proc,f'setworldspawn {x+64} {y} {z}')
            send(proc,'gamerule minecraft:spawn_radius 0')
            steps.append('safe_external_arrival_pad_materialized_before_player_join')
            bstream=bout.open('w',encoding='utf-8')
            neg_ready=root/'unmarked-attempt-awaits-native-oracle'
            neg_ack=root/'unmarked-native-verified'
            pre_ready=root/'marked-acquired-awaits-native-oracle'
            pre_ack=root/'marked-acquired-native-verified'
            pos_ready=root/'marked-attempt-awaits-native-oracle'
            pos_ack=root/'marked-native-verified'
            env={**os.environ,'MC_PORT':str(PORT),'BARSOOM_ARCH_BOT_RESULT':str(out),
                 'BARSOOM_ARCH_PREBUILT':'1','BARSOOM_ARCH_BASE_JSON':json.dumps({'x':x,'y':y,'z':z}),
                 'BARSOOM_ARCH_NEG_READY':str(neg_ready),'BARSOOM_ARCH_NEG_ACK':str(neg_ack),
                 'BARSOOM_ARCH_PRE_READY':str(pre_ready),'BARSOOM_ARCH_PRE_ACK':str(pre_ack),
                 'BARSOOM_ARCH_POS_READY':str(pos_ready),'BARSOOM_ARCH_POS_ACK':str(pos_ack)}
            bot=subprocess.Popen(['node',str(BOT_SCRIPT)],cwd=ROOT,env=env,stdout=bstream,stderr=subprocess.STDOUT,text=True)
            deadline=time.monotonic()+332
            negative_verified=False
            pre_verified=False
            positive_verified=False
            while bot.poll() is None and time.monotonic()<deadline:
                if neg_ready.exists() and not negative_verified:
                    oracle(proc,log,f'execute if entity @a[name={BOT_NAME}]','ARCH_NEG_PLAYER_ONLINE')
                    oracle(proc,log,f'execute if score #well barsoom_arch.state matches 0 if block {x} {y-1} {z} minecraft:cut_sandstone','ARCH_NEG_DRY_WELL_AND_ZERO_SCORE')
                    oracle(proc,log,f'execute if score {BOT_NAME} barsoom_arch.accept matches 0','ARCH_NEG_REJECTED_ACCEPT_SCORE')
                    oracle(proc,log,f'execute if items entity {BOT_NAME} container.* minecraft:heart_of_the_sea',
                        'ARCH_NEG_ITEM_RETAINED_BY_PLAYER')
                    oracle(proc,log,f'execute unless items entity {BOT_NAME} container.* minecraft:heart_of_the_sea[minecraft:custom_data~{{barsoom_arch:{{harbor_seal:1b}}}}]',
                        'ARCH_NEG_PLAYER_HAS_NO_MARKED_ITEM')
                    oracle(proc,log,f'execute unless items block {x+6} {y-10} {z+18} container.0 minecraft:heart_of_the_sea',
                        'ARCH_NEG_DISPOSABLE_CHEST_WITHDRAWN')
                    oracle(proc,log,f'execute if items block {x+4} {y-10} {z+17} container.0 minecraft:heart_of_the_sea[minecraft:custom_data~{{barsoom_arch:{{harbor_seal:1b}}}}]',
                        'ARCH_NEG_ORIGINAL_MARKED_ARCHIVE_UNTOUCHED')
                    negative_verified=True
                    steps.append('independent_live_player_unmarked_rejection_dry_well_item_retained')
                    neg_ack.write_text('verified\n',encoding='utf-8')
                if pre_ready.exists() and negative_verified and not pre_verified:
                    oracle(proc,log,f'execute if entity @a[name={BOT_NAME}]','ARCH_PRE_PLAYER_ONLINE')
                    # /clear <player> <predicate> 0 counts without removing items.
                    # Verify BOTH items in the genuine server inventory BEFORE
                    # the player submits the second, positive restore trigger.
                    send(proc,f'execute store result score #hearts barsoom_arch.state run clear {BOT_NAME} minecraft:heart_of_the_sea 0')
                    oracle(proc,log,'execute if score #hearts barsoom_arch.state matches 2','ARCH_PRE_EXACT_TWO_SEALS')
                    send(proc,f'execute store result score #marked_hearts barsoom_arch.state run clear {BOT_NAME} minecraft:heart_of_the_sea[minecraft:custom_data~{{barsoom_arch:{{harbor_seal:1b}}}}] 0')
                    oracle(proc,log,'execute if score #marked_hearts barsoom_arch.state matches 1','ARCH_PRE_EXACT_ONE_MARKED')
                    oracle(proc,log,f'execute unless items block {x+4} {y-10} {z+17} container.0 minecraft:heart_of_the_sea','ARCH_PRE_CANONICAL_CHEST_WITHDRAWN')
                    pre_verified=True
                    steps.append('native_pre_positive_two_seals_one_marked')
                    pre_ack.write_text('verified\n',encoding='utf-8')
                if pos_ready.exists() and pre_verified and not positive_verified:
                    oracle(proc,log,f'execute if entity @a[name={BOT_NAME}]','ARCH_POS_PLAYER_ONLINE')
                    oracle(proc,log,f'execute if score #well barsoom_arch.state matches 1 if block {x} {y-1} {z} minecraft:water',
                        'ARCH_POS_RESTORED_WELL_AND_SCORE')
                    send(proc,f'execute store result score #hearts barsoom_arch.state run clear {BOT_NAME} minecraft:heart_of_the_sea 0')
                    oracle(proc,log,'execute if score #hearts barsoom_arch.state matches 1','ARCH_POS_EXACT_ONE_SEAL_REMAINS')
                    oracle(proc,log,f'execute if items entity {BOT_NAME} container.* minecraft:heart_of_the_sea',
                        'ARCH_POS_UNMARKED_ITEM_RETAINED')
                    oracle(proc,log,f'execute unless items entity {BOT_NAME} container.* minecraft:heart_of_the_sea[minecraft:custom_data~{{barsoom_arch:{{harbor_seal:1b}}}}]',
                        'ARCH_POS_MARKED_ITEM_CONSUMED_ONLY')
                    oracle(proc,log,f'execute unless items block {x+4} {y-10} {z+17} container.0 minecraft:heart_of_the_sea',
                        'ARCH_POS_ORIGINAL_ARCHIVE_CHEST_EMPTY')
                    positive_verified=True
                    steps.append('independent_live_player_marked_consume_unmarked_retention')
                    pos_ack.write_text('verified\n',encoding='utf-8')
                time.sleep(.5)
            if bot.poll() is None:
                bot.terminate();bot.wait(timeout=5)
                raise Refused('ARCH_PHYSICAL_PLAYER_TIMEOUT')
            require(out.exists(),'ARCH_PHYSICAL_BOT_NO_RECEIPT:'+bout.read_text(errors='replace')[-1000:])
            require(negative_verified and pre_verified and positive_verified,'ARCH_PHYSICAL_NEGATIVE_PRE_OR_POSITIVE_LIVE_GATE_NOT_COMPLETED')
            player=json.loads(out.read_text());result['player_receipt']=player
            steps.extend(player.get('stages',[]))
            require(bot.returncode==0 and not player.get('error'),'ARCH_PHYSICAL_PLAYER_FAILED:'+str(player.get('error'))[:900])
            require(player['actual_container_withdrawal'] is True and player.get('negative_player_attempt') is True and player.get('positive_player_attempt') is True,'ARCH_PHYSICAL_TWO_PLAYER_CHEST_TRIPS_NOT_CONFIRMED')
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
            base=player['base']; require(base=={'x':x,'y':y,'z':z},'ARCH_PLAYER_SELECTED_SITE_MISMATCH')
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
    p=argparse.ArgumentParser()
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    result={'schema':'supracraft.mcworld.barsoom-harbor-generated-player/0.1',
            'result':'FAIL','first_failure':None,'minecraft_version':'26.3',
            'archive_sha256':EXPECTED_SHA,'terrain_sha256':TERRAIN_SHA,
            'runs':[],'human_stock_client_qualified':False,
            'production_deployment':'HOLD','merge':'HOLD',
            'multi_seed_player_negative_positive_qualified':False}
    try:
        evidence=json.loads(args.evidence.read_text())
        spec=json.loads(CONSTRAINTS.read_text())
        require(spec['schema']=='supracraft.mcworld.barsoom-harbor-site/0.1','ARCH_SITE_SPEC_DRIFT')
        for seed in spec['seeds']:
            one={'seed':seed,'stages':[]}
            result['runs'].append(one)
            run(evidence,one['stages'],one,seed)
            one['result']='PASS'
        result.update(result='PASS',multi_seed_player_negative_positive_qualified=True)
    except Exception as exc:
        result['first_failure']=type(exc).__name__+': '+str(exc)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result['result']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())
