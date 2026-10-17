#!/usr/bin/env python3
"""Bounded Barsoom 0.1.3 acceptance rep using accepted public 26.3 oracles.

Public-safe fixture only. Official vanilla Java25 server, pinned 26.3 Mineflayer,
real offline player triggers, independent commands, saved world restart.
NOT stock Mojang client, aesthetic review, or production acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import zipfile

from probe_core_restoration_datapack_26_3 import send, stop_server, server_error_lines
from qualify_vanilla_world_artifact_activation_263 import (
    PORT, Refused, launch, oracle, server_config, require,
)
from smoke_vanilla_runtime import download_verified_server

ROOT=Path(__file__).resolve().parents[1]
BUILDER=ROOT/'fixtures/barsoom/build_barsoom.py'
BOT=ROOT/'tools/probe_mineflayer_barsoom_263.js'
EXPECTED='e6ec6e428718ec4916780c41b828d9ef1d345886a786d0e5b48303070d738752'
NAME='SupraCraftProbe'


def validate_source() -> Path:
    require(BUILDER.is_file() and BOT.is_file(), 'BARSOOM_SOURCE_MISSING')
    subprocess.run(['python3',str(BUILDER)], check=True,capture_output=True,text=True,timeout=30)
    candidate=BUILDER.parent/'dist/Barsoom-Canal-Outpost-26.3-datapack.zip'
    require(candidate.is_file(), 'BARSOOM_INNER_ZIP_MISSING')
    body=candidate.read_bytes()
    require(hashlib.sha256(body).hexdigest()==EXPECTED, 'BARSOOM_EXACT_ARTIFACT_DIGEST_DRIFT')
    with zipfile.ZipFile(candidate) as z:
        require(z.testzip() is None and 'pack.mcmeta' in z.namelist(), 'BARSOOM_BAD_ZIP')
        for path in z.namelist():
            require(not path.startswith('/') and '..' not in Path(path).parts, 'BARSOOM_UNSAFE_MEMBER')
            if path.endswith('.json') or path.endswith('pack.mcmeta'):
                json.loads(z.read(path))
    return candidate


def wait_for_file(path:Path,proc:subprocess.Popen,timeout=50) -> None:
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if path.is_file(): return
        require(proc.poll() is None, 'BARSOOM_BOT_EXITED_PREMATURELY')
        time.sleep(.2)
    raise Refused('BARSOOM_BOT_READY_TIMEOUT')


def bot_start(root:Path,stage:str,server_log:Path):
    folder=root/stage
    folder.mkdir()
    env={**os.environ,'MC_PORT':str(PORT),'BARSOOM_PROBE_ROOT':str(folder)}
    process=subprocess.Popen(['node',str(BOT)],env=env,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    wait_for_file(folder/'bot.ready',process)
    record=json.loads((folder/'bot-status.json').read_text())
    require(record.get('minecraft_version')=='26.3' and record.get('protocol_version')==777 and record.get('connected') is True, 'BARSOOM_PLAYER_PROTOCOL_DRIFT')
    require(f'{NAME} joined the game' in server_log.read_text(errors='replace'), 'BARSOOM_PLAYER_JOIN_UNPROVEN')
    return process,folder


def bot_command(folder:Path,command:str,index:int) -> None:
    request=folder/'bot-request.json'
    acknowledge=folder/'bot-ack.json'
    require(not request.exists(), 'BARSOOM_BOT_IPC_BUSY')
    if acknowledge.exists(): acknowledge.unlink()
    request.write_text(json.dumps({'id':index,'command':command}))
    until=time.monotonic()+15
    while time.monotonic()<until:
        if acknowledge.is_file():
            data=json.loads(acknowledge.read_text())
            require(data.get('id')==index and data.get('command')==command,'BARSOOM_BOT_ACK_INVALID')
            time.sleep(.5) # game tick must process before oracle polling
            return
        time.sleep(.15)
    raise Refused('BARSOOM_BOT_COMMAND_TIMEOUT')


def no_errors(log:Path,stage:str) -> None:
    error_lines=server_error_lines(log)
    require(not error_lines, 'BARSOOM_SERVER_ERRORS_'+stage+':'+str(error_lines[-2:])[:450])
    content=log.read_text(errors='replace')
    require('Failed to load function' not in content and 'Failed to load data packs' not in content, 'BARSOOM_PACK_PARSE_FAILED_'+stage)


def run(evidence:dict,steps:list[str]) -> None:
    info=evidence['artifact_version_json']
    require(info['id']=='26.3' and info['protocol_version']==777 and info['java_version']==25,'BARSOOM_VERSION_DRIFT')
    candidate=validate_source(); steps.append('exact_original_datapack_verified')
    with tempfile.TemporaryDirectory(prefix='barsoom-qualified-') as t:
        root=Path(t);home=root/'server';home.mkdir();jar=home/'server.jar'
        download_verified_server(evidence,jar)
        require(hashlib.sha256(jar.read_bytes()).hexdigest()==evidence['server_artifact']['sha256'],'BARSOOM_MOJANG_JAR_DIGEST_DRIFT')
        server_config(home)
        packs=home/'world/datapacks';packs.mkdir(parents=True)
        shutil.copyfile(candidate,packs/'barsoom.zip')
        require(hashlib.sha256((packs/'barsoom.zip').read_bytes()).hexdigest()==EXPECTED,'BARSOOM_STAGE_MUTATION')
        handles=[];bot=None
        try:
            proc,log=launch(home,jar,evidence,'barsoom-candidate',handles)
            steps.append('official_server_26_3_ready')
            no_errors(log,'load')
            oracle(proc,log,'execute if score #built barsoom.state matches 0 if score #canal barsoom.state matches 0','BARSOOM_LOAD_STATE_ZERO')
            steps.append('datapack_load_and_zero_state_verified')
            bot,folder=bot_start(root,'first-bot',log)
            steps.append('actual_protocol777_player_joined')
            send(proc,f'tp {NAME} 0.5 85.0 0.5')
            time.sleep(1)
            bot_command(folder,'/trigger barsoom.repair set 1',1)
            oracle(proc,log,'execute if score #built barsoom.state matches 0 if score #canal barsoom.state matches 0','BARSOOM_REJECT_PREBUILD_REPAIR')
            steps.append('prebuild_repair_denied')
            bot_command(folder,'/trigger barsoom.start set 1',2)
            oracle(proc,log,'execute if score #built barsoom.state matches 1 if score #canal barsoom.state matches 0 if block 18 85 -15 minecraft:chest if entity @e[type=minecraft:marker,tag=barsoom.canal_control]','BARSOOM_OUTPOST_AND_RUIN_BUILT')
            oracle(proc,log,'execute if entity @e[type=minecraft:villager,tag=barsoom.red_civic] if entity @e[type=minecraft:villager,tag=barsoom.green_proxy] if entity @e[type=minecraft:camel,tag=barsoom.thoat_proxy]','BARSOOM_NPCS_AND_MOUNT_PROXIES')
            steps.append('synthetic_player_built_three_sites_and_proxies')
            send(proc,f'tp {NAME} 0.5 85.0 0.5');time.sleep(.4)
            bot_command(folder,'/trigger barsoom.repair set 1',3)
            oracle(proc,log,'execute if score #canal barsoom.state matches 0','BARSOOM_NO_ITEM_REJECTED')
            steps.append('repair_without_artifact_denied')
            send(proc,f'give {NAME} minecraft:lightning_rod 1')
            send(proc,f'tp {NAME} 12.5 86.0 -12.5');time.sleep(.4)
            bot_command(folder,'/trigger barsoom.repair set 1',4)
            oracle(proc,log,'execute if score #canal barsoom.state matches 0','BARSOOM_WRONG_LOCATION_REJECTED')
            steps.append('repair_far_from_control_denied')
            send(proc,f'execute store result score #rod_probe barsoom.state run clear {NAME} minecraft:lightning_rod 0')
            oracle(proc,log,'execute if score #rod_probe barsoom.state matches 1..','BARSOOM_ROD_PRESENT_AFTER_FAR_NEGATIVE')
            steps.append('rod_inventory_preserved_far')
            send(proc,f'tp {NAME} 0.5 85.0 0.5');time.sleep(.4)
            bot_command(folder,'/trigger barsoom.repair set 1',5)
            oracle(proc,log,'execute if score #canal barsoom.state matches 1','BARSOOM_REPAIR_ACCEPTED_SCORE')
            steps.append('repair_command_accepted')
            oracle(proc,log,'execute if block 0 84 5 minecraft:water','BARSOOM_RESTORED_WATER')
            steps.append('central_canal_water_verified')
            oracle(proc,log,'execute if block 5 85 5 minecraft:wheat','BARSOOM_RESTORED_CROP')
            steps.append('field_crops_verified')
            send(proc,f'execute store result score #rod_probe barsoom.state run clear {NAME} minecraft:lightning_rod 0')
            oracle(proc,log,'execute if score #rod_probe barsoom.state matches 0','BARSOOM_ROD_CONSUMED')
            steps.append('rod_consumed_once')
            steps.append('real_player_caused_canal_restoration')
            send(proc,'setblock -20 85 10 minecraft:diamond_block')
            oracle(proc,log,'execute if block -20 85 10 minecraft:diamond_block','BARSOOM_PLAYER_MUTATION_MARKED')
            bot.terminate();bot.wait(timeout=12);bot=None
            require(stop_server(proc)==0,'BARSOOM_SAVE_STOP_FAILED')
            no_errors(log,'build_repair')
            steps.append('first_server_save_and_stop')
            proc,log=launch(home,jar,evidence,'barsoom-restarted',handles)
            oracle(proc,log,'execute if score #built barsoom.state matches 1 if score #canal barsoom.state matches 1 if block 0 84 5 minecraft:water if block -20 85 10 minecraft:diamond_block','BARSOOM_RESTART_PERSISTENCE')
            steps.append('world_and_canal_survive_restart')
            bot,folder=bot_start(root,'second-bot',log)
            send(proc,f'tp {NAME} 0.5 85.0 0.5');time.sleep(.5)
            bot_command(folder,'/trigger barsoom.start set 1',1)
            oracle(proc,log,'execute if block -20 85 10 minecraft:diamond_block if score #built barsoom.state matches 1 if score #canal barsoom.state matches 1','BARSOOM_DUPLICATE_NO_REWIPE')
            steps.append('repeat_creation_non_destructive')
            bot.terminate();bot.wait(timeout=12);bot=None
            require(stop_server(proc)==0,'BARSOOM_RESTART_STOP_FAILED')
            no_errors(log,'restart')
        finally:
            if bot is not None and bot.poll() is None: bot.terminate();bot.wait(timeout=10)
            for process,stream in handles:
                if process.poll() is None:
                    try:stop_server(process)
                    except Exception:process.kill()
                stream.close()


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--evidence',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    steps=[];error=None
    try:
        run(json.loads(args.evidence.read_text()),steps)
    except Exception as exc:
        error=type(exc).__name__+': '+str(exc)
    receipt={'schema':'supracraft-barsoom-qualifier/v0.1','original_inner_sha256':EXPECTED,
             'minecraft_version':'26.3','server_backend':'official_vanilla',
             'synthetic_client':'offline_mineflayer_26.3','stages':steps,
             'result':'PASS' if error is None else 'FAIL','first_failure':error,
             'stock_client_qualified':False,'human_visual_review':False,
             'worldgen_macrogeography_qualified':False,'physical_truenas_apply':'HOLD'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps(receipt,indent=2,sort_keys=True))
    return 0 if error is None else 1
if __name__=='__main__':raise SystemExit(main())
