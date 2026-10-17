#!/usr/bin/env python3
"""Native vanilla Minecraft Java 26.3 flora canary, disposable temporary save."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from probe_core_restoration_datapack_26_3 import send, stop_server, server_error_lines
from smoke_vanilla_runtime import download_verified_server
from qualify_vanilla_world_artifact_activation_263 import require
from qualify_barsoom_preset_263 import status_ready, prove

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'fixtures/barsoom/flora'))
sys.path.insert(0, str(ROOT / 'fixtures/barsoom/terrain'))
from gen_flora_263 import build as build_flora
from gen_dead_sea import build as build_terrain


def start_server(home: Path, jar: Path, log: Path):
    fh = log.open('w+', encoding='utf-8')
    proc = subprocess.Popen(['java', '-Xms512M', '-Xmx1536M', '-jar', str(jar), 'nogui'],
                            cwd=home, stdin=subprocess.PIPE, stdout=fh,
                            stderr=subprocess.STDOUT, text=True)
    return proc, fh


def run(evidence: dict) -> dict:
    require(evidence['artifact_version_json']['id'] == '26.3' and
            evidence['artifact_version_json']['java_version'] == 25, 'VERSION_INVALID')
    steps = []
    with tempfile.TemporaryDirectory(prefix='barsoom-flora-263-') as temp:
        home = Path(temp) / 'server'
        packs = home / 'world/datapacks'
        packs.mkdir(parents=True)
        jar = home / 'server.jar'
        download_verified_server(evidence, jar)
        require(hashlib.sha256(jar.read_bytes()).hexdigest() == evidence['server_artifact']['sha256'],
                'OFFICIAL_JAR_MISMATCH')
        flora = build_flora(packs / 'flora.zip')
        build_terrain(packs / 'terrain.zip')
        steps.append('official_26_3_flora_and_terrain_staged_before_first_boot')
        (home/'eula.txt').write_text('eula=true\n')
        (home/'server.properties').write_text(
            'server-ip=127.0.0.1\nserver-port=25599\nonline-mode=false\n'
            'level-name=world\nlevel-type=barsoom:dead_sea\n'
            'initial-enabled-packs=vanilla,file/terrain.zip,file/flora.zip\n'
            'view-distance=3\nsimulation-distance=2\nspawn-protection=0\n'
            'max-players=1\ngenerate-structures=false\n'
            'enable-rcon=false\nenable-query=false\nlevel-seed=1811001\n'
            'sync-chunk-writes=true\nmotd=Barsoom flora 26.3 disposable test\n')
        log = home/'native-server.log'
        for rep in range(2):
            proc, fh = start_server(home, jar, log)
            try:
                status_ready(proc, log)
                content = log.read_text(errors='replace')
                require(not server_error_lines(log) and 'Failed to load data packs' not in content,
                        'FLORA_LOAD_ERROR:' + content[-1600:])
                steps.append(f'native_boot_{rep+1}_passed')
                send(proc, 'forceload remove all')
                send(proc, 'forceload add 0 0')
                send(proc, 'forceload add 16 0')  # jawbloom is in the neighboring chunk
                time.sleep(1.2)
                if rep == 0:
                    prove(proc, log, 'execute if block 0 160 0 minecraft:air', 'NO_AUTOMATIC_PLANTING')
                    steps.append('no_implicit_world_mutation')
                    send(proc, 'execute positioned 0 160 0 run function barsoom_flora:demo')
                for name, probe in flora['probes'].items():
                    x, dy, z = probe['position']
                    prove(proc, log, f'execute if block {x} {160+dy} {z} {probe["state"]}',
                          'FLORA_' + name.upper() + '_REP' + str(rep+1))
                    steps.append(f'{name}_native_block_accepted_rep{rep+1}')
                prove(proc, log,
                      'execute positioned 20 160 0 if entity @e[type=minecraft:marker,tag=barsoom_flora.trap,distance=..2]',
                      'JAWBLOOM_MARKER_REP' + str(rep+1))
                steps.append(f'jawbloom_trap_marker_present_rep{rep+1}')
                require(stop_server(proc) == 0, 'GRACEFUL_STOP_FAILURE')
                steps.append(f'graceful_save_stop_rep{rep+1}')
            finally:
                if proc.poll() is None:
                    try: stop_server(proc)
                    except Exception: proc.kill(); proc.wait(timeout=10)
                fh.close()
    return {'schema': 'supracraft.barsoom.flora-native/1', 'result': 'PASS',
            'minecraft': '26.3', 'pack_sha256': flora['sha256'], 'species': flora['species'],
            'steps': steps, 'first_failure': None, 'human_client': 'NOT_RUN',
            'real_player_poison': 'NOT_RUN', 'natural_spawning': 'NOT_IMPLEMENTED',
            'physical_truenas_apply': 'HOLD'}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--evidence', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    receipt = {'schema': 'supracraft.barsoom.flora-native/1', 'result': 'FAIL'}
    try:
        receipt = run(json.loads(args.evidence.read_text()))
    except Exception as exc:
        receipt['first_failure'] = type(exc).__name__ + ': ' + str(exc)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt['result'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
