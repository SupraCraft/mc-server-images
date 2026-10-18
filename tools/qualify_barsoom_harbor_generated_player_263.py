#!/usr/bin/env python3
"""Two-seed real-player archaeology on *native generated* Barsoom Java 26.3.

Reuse, do not copy, the already-qualified MCWORLD generated-site module and
two-trip Mineflayer actor. Inject a physical playthrough after site build and
before the first save, then preserve the site's independent restart probes.
Authoritative game state is always probed from official vanilla 26.3 console.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import qualify_barsoom_harbor_generated_site_263 as site_test
from probe_core_restoration_datapack_26_3 import send
from qualify_vanilla_world_artifact_activation_263 import oracle as native_oracle, require, Refused

ROOT=Path(__file__).resolve().parents[1]
BOT=ROOT/'tools/probe_mineflayer_archaeology_generated_263.js'
BOT_NAME='SupraArchProbe'

def witness(proc, log, site: dict, seed: int) -> dict:
    """Bounded disposable test chest and two physical ladder/chest/quest trips."""
    x,y,z=map(int,(site['x'],site['y'],site['z']))
    require(BOT.is_file(),'GENERATED_SITE_PHYSICAL_ACTOR_ABSENT')
    # Grounded in the original qualified 26.3 archaeology producer.
    # This chest is a *test-only* ordinary Heart of the Sea and cannot pass
    # the restoration custom_data predicate. No player inventory is granted.
    send(proc,f'setblock {x+6} {y-10} {z+18} minecraft:chest[facing=west]')
    send(proc,f'item replace block {x+6} {y-10} {z+18} container.0 with minecraft:heart_of_the_sea 1')
    native_oracle(proc,log,
        f'execute if items block {x+6} {y-10} {z+18} container.0 minecraft:heart_of_the_sea',
        'GENERATED_NEGATIVE_CHEST_MATERIALIZED')
    native_oracle(proc,log,
        f'execute unless items block {x+6} {y-10} {z+18} container.0 minecraft:heart_of_the_sea[minecraft:custom_data~{{barsoom_arch:{{harbor_seal:1b}}}}]',
        'GENERATED_NEGATIVE_ITEM_UNMARKED')

    with tempfile.TemporaryDirectory(prefix=f'generated-player-{seed}-') as d:
        root=Path(d)
        ready_neg=root/'negative-ready'; ack_neg=root/'negative-ack'
        ready_pre=root/'prepositive-ready'; ack_pre=root/'prepositive-ack'
        ready_pos=root/'positive-ready'; ack_pos=root/'positive-ack'
        player_out=root/'player.json'; botlog=root/'bot.log'
        env={**os.environ,'MC_PORT':'25597',
            'BARSOOM_ARCH_BOT_RESULT':str(player_out),
            'BARSOOM_ARCH_PREBUILT':'1',
            'BARSOOM_ARCH_SITE_BASE':json.dumps({'x':x,'y':y,'z':z},sort_keys=True),
            'BARSOOM_ARCH_NEG_READY':str(ready_neg),'BARSOOM_ARCH_NEG_ACK':str(ack_neg),
            'BARSOOM_ARCH_PRE_READY':str(ready_pre),'BARSOOM_ARCH_PRE_ACK':str(ack_pre),
            'BARSOOM_ARCH_POS_READY':str(ready_pos),'BARSOOM_ARCH_POS_ACK':str(ack_pos)}
        stream=botlog.open('w',encoding='utf-8')
        actor=subprocess.Popen(['node',str(BOT)],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,text=True)
        stages=[]; first=None
        try:
            end=time.monotonic()+325
            while actor.poll() is None and time.monotonic()<end:
                if ready_neg.exists() and not ack_neg.exists():
                    native_oracle(proc,log,f'execute if entity @a[name={BOT_NAME}]','GENERATED_NEG_PLAYER_CONNECTED')
                    native_oracle(proc,log,f'execute if score #well barsoom_arch.state matches 0 if block {x} {y-1} {z} minecraft:cut_sandstone',
                                  'GENERATED_NEG_DRY_WELL_AND_ZERO_SCORE')
                    native_oracle(proc,log,f'execute if score {BOT_NAME} barsoom_arch.accept matches 0',
                                  'GENERATED_NEG_REJECTED_TRIGGER')
                    native_oracle(proc,log,
                                  f'execute if items entity {BOT_NAME} container.* minecraft:heart_of_the_sea',
                                  'GENERATED_NEG_PLAYER_RETAINS_UNMARKED')
                    native_oracle(proc,log,
                                  f'execute unless items entity {BOT_NAME} container.* minecraft:heart_of_the_sea[minecraft:custom_data~{{barsoom_arch:{{harbor_seal:1b}}}}]',
                                  'GENERATED_NEG_PLAYER_HAS_NO_MARKED')
                    native_oracle(proc,log,
                                  f'execute if items block {x+4} {y-10} {z+17} container.0 minecraft:heart_of_the_sea[minecraft:custom_data~{{barsoom_arch:{{harbor_seal:1b}}}}]',
                                  'GENERATED_NEG_ORIGINAL_ARCHIVE_UNTOUCHED')
                    native_oracle(proc,log,
                                  f'execute unless items block {x+6} {y-10} {z+18} container.0 minecraft:heart_of_the_sea',
                                  'GENERATED_NEG_TEST_CHEST_WITHDRAWN')
                    ack_neg.write_text('PASS\n')
                    stages.append('independent_live_unmarked_rejection')
                if ready_pre.exists() and ack_neg.exists() and not ack_pre.exists():
                    native_oracle(proc,log,
                                  f'execute unless items block {x+4} {y-10} {z+17} container.0 minecraft:heart_of_the_sea',
                                  'GENERATED_PRE_MARKED_ARCHIVE_WITHDRAWN')
                    send(proc,f'execute store result score #hearts barsoom_arch.state run clear {BOT_NAME} minecraft:heart_of_the_sea 0')
                    native_oracle(proc,log,'execute if score #hearts barsoom_arch.state matches 2',
                                  'GENERATED_PRE_TWO_SEALS_IN_PLAYER_INVENTORY')
                    send(proc,f'execute store result score #marked_hearts barsoom_arch.state run clear {BOT_NAME} minecraft:heart_of_the_sea[minecraft:custom_data~{{barsoom_arch:{{harbor_seal:1b}}}}] 0')
                    native_oracle(proc,log,'execute if score #marked_hearts barsoom_arch.state matches 1',
                                  'GENERATED_PRE_EXACTLY_ONE_MARKED')
                    ack_pre.write_text('PASS\n')
                    stages.append('independent_before_positive_two_seals_one_marked')
                if ready_pos.exists() and ack_pre.exists() and not ack_pos.exists():
                    native_oracle(proc,log,f'execute if entity @a[name={BOT_NAME}]','GENERATED_POS_PLAYER_CONNECTED')
                    native_oracle(proc,log,
                                  f'execute if score #well barsoom_arch.state matches 1 if block {x} {y-1} {z} minecraft:water',
                                  'GENERATED_POS_WELL_RESTORED')
                    native_oracle(proc,log,
                                  f'execute if block {x+6} {y} {z+2} minecraft:wheat',
                                  'GENERATED_POS_CROP_RESTORED')
                    send(proc,f'execute store result score #remaining_hearts barsoom_arch.state run clear {BOT_NAME} minecraft:heart_of_the_sea 0')
                    native_oracle(proc,log,
                                  'execute if score #remaining_hearts barsoom_arch.state matches 1',
                                  'GENERATED_POS_ONE_UNMARKED_REMAINS')
                    native_oracle(proc,log,
                                  f'execute if items entity {BOT_NAME} container.* minecraft:heart_of_the_sea',
                                  'GENERATED_POS_RETAINED_UNMARKED_LIVE')
                    native_oracle(proc,log,
                                  f'execute unless items entity {BOT_NAME} container.* minecraft:heart_of_the_sea[minecraft:custom_data~{{barsoom_arch:{{harbor_seal:1b}}}}]',
                                  'GENERATED_POS_ONLY_MARKED_CONSUMED')
                    ack_pos.write_text('PASS\n')
                    stages.append('independent_marked_consume_unmarked_retained')
                time.sleep(.4)
            if actor.poll() is None:
                actor.terminate()
                actor.wait(timeout=10)
                raise Refused('GENERATED_PLAYER_TWO_TRIP_TIMEOUT')
            stream.close()
            if player_out.is_file():
                player=json.loads(player_out.read_text())
            else:
                raise Refused('GENERATED_PLAYER_NO_RECEIPT:'+botlog.read_text(errors='replace')[-1200:])
            require(actor.returncode==0,'GENERATED_PLAYER_BOT_NONZERO:'+str(player.get('error')))
            require(all(p.exists() for p in [ack_neg,ack_pre,ack_pos]),
                    'GENERATED_PLAYER_NATIVE_GATE_MISSING')
            require(player.get('status')=='PASS'
                    and player.get('negative_player_attempt') is True
                    and player.get('positive_player_attempt') is True
                    and player.get('actual_container_withdrawal') is True,
                    'GENERATED_PLAYER_INCOMPLETE_RECEIPT')
            require(player.get('console_player_item_granted') is False
                    and player.get('console_player_positioned') is False,
                    'GENERATED_PLAYER_OPERATOR_SHORTCUT')
            base=player.get('base',{})
            require((base.get('x'),base.get('y'),base.get('z'))==(x,y,z),
                    'GENERATED_PLAYER_SITE_ANCHOR_MISMATCH')
            return {'result':'PASS','seed':seed,'site':site,'stages':stages,
                    'player':player,'first_failure':None,
                    'stock_graphical_client':'NOT_RUN'}
        finally:
            if actor.poll() is None:
                actor.terminate()
                try:actor.wait(timeout=10)
                except subprocess.TimeoutExpired:actor.kill();actor.wait(timeout=10)
            if not stream.closed:stream.close()

def run_seed(seed: int, spec: dict) -> dict:
    """Compose with the already-accepted site compiler at controlled hooks."""
    original_select=site_test.select_site
    original_stop=site_test.stop_server
    original_oracle=site_test.oracle
    context={'selected':None,'log':None,'player':None,'first_stop':False}
    def select(proc, log, constraints, rejected):
        selected=original_select(proc,log,constraints,rejected)
        context.update(selected=selected,log=log)
        return selected
    def first_stop(proc):
        if not context['first_stop']:
            require(context['selected'] is not None and context['log'] is not None,
                    'GENERATED_PLAYER_SITE_NOT_SELECTED')
            context['player']=witness(proc,context['log'],context['selected'],seed)
            context['first_stop']=True
        return original_stop(proc)
    def adapt_oracle(proc, log, predicate, marker):
        if marker=='SITE_DURABLE_ARCHIVE_DRY_WELL_AFTER_RESTART':
            x,y,z=(context['selected'][k] for k in ['x','y','z'])
            predicate=(f'execute if score #built barsoom_arch.state matches 1 '
                       f'if score #well barsoom_arch.state matches 1 '
                       f'if block {x+4} {y-10} {z+17} minecraft:chest '
                       f'if block {x} {y-1} {z} minecraft:water')
            marker='GENERATED_PLAYER_DURABLE_WELL_RESTORED'
        return original_oracle(proc, log, predicate, marker)
    try:
        site_test.select_site=select
        site_test.stop_server=first_stop
        site_test.oracle=adapt_oracle
        result=site_test.run_one(seed,spec)
        require(context['player'] is not None and context['player']['result']=='PASS',
                'GENERATED_PLAYER_NOT_QUALIFIED')
        result['real_player_quest_qualified']=True
        result['native_player_evidence']=context['player']
        result['persistence_after_player_quest']=True
        return result
    finally:
        site_test.select_site=original_select
        site_test.stop_server=original_stop
        site_test.oracle=original_oracle

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    runs=[];failure=None
    try:
        spec=json.loads(site_test.CONSTRAINTS.read_text())
        require(spec['schema']=='supracraft.mcworld.barsoom-harbor-site/0.1','GENERATED_PLAYER_SITE_SCHEMA')
        require(len(spec['seeds'])>=2,'GENERATED_PLAYER_REQUIRES_TWO_SEEDS')
        for seed in spec['seeds']:
            runs.append(run_seed(seed,spec))
    except Exception as exc:
        failure=type(exc).__name__+': '+str(exc)
    receipt={'schema':'supracraft.mcworld.barsoom-harbor-generated-player/0.1',
             'result':'PASS' if failure is None else 'FAIL','first_failure':failure,
             'runs':runs,'release':'26.3','stock_client_qualified':False,
             'human_visual_acceptance':'HOLD','production_deployment':'HOLD',
             'unreviewed_merge':'HOLD'}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps(receipt,indent=2,sort_keys=True))
    return 0 if failure is None else 1

if __name__=='__main__':
    sys.exit(main())
