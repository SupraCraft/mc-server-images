#!/usr/bin/env python3
"""Actual official 26.3 new-chunk autogeneration, custom-vs-vanilla controls.

Two *fresh temporary worlds* per seed. In neither world is /place feature used,
nor any setblock/fill/gamerule, nor player connected. Generated chunks are
activated by bounded forceload and queried in-situ via server-side predicates.
The custom biome has no vanilla vegetal features; each observed dead_bush must
come from its single registered placed-feature attempt (unless surface material
generation itself places such blocks, which vanilla noise settings do not).
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"fixtures/barsoom/terrain"))
sys.path.insert(0,str(ROOT/"fixtures/barsoom/habitat"))
sys.path.insert(0,str(ROOT/"fixtures/barsoom/biomes"))
from gen_dead_sea import build as terrain_build
from gen_habitat_263 import build as habitat_build
from gen_scarlet_wastes_263 import build as scarlet_build
from smoke_vanilla_runtime import download_verified_server
from qualify_barsoom_preset_263 import status_ready, prove
from probe_core_restoration_datapack_26_3 import send, stop_server, server_error_lines
from qualify_vanilla_world_artifact_activation_263 import require

TERRAIN_SHA="9d5ad764a2df4786666326e997a3ed724524583fe3191b60305677fbe5fb531e"
HABITAT_SHA="1bfbb244d9a172d00e1357370c464874e2e32a0e55a306e15f4a02dae4a332e7"
SITE=(80,80)
RANGE=range(64,96)


def measure(proc,log:Path,label:str)->dict:
    """In-situ 32x32 actual surface census; no counter-inflating fill/commands."""
    prefix="SCARLET_"+label+"_"
    queries=[]
    for x in RANGE:
        for z in RANGE:
            base=f"execute positioned {x} 0 {z} positioned over world_surface"
            queries.append((f"B_{x}_{z}",base+" if block ~ ~-1 ~ minecraft:dead_bush"))
    before=log.read_text(errors="replace")
    require(prefix not in before,"PREDICATE_MARKER_REUSE")
    for key,predicate in queries:
        send(proc,f"{predicate} run say {prefix}{key}")
    terminator=prefix+"END"
    send(proc,"say "+terminator)
    end=time.monotonic()+90
    while time.monotonic()<end:
        s=log.read_text(errors="replace")
        if terminator in s:
            witnessed=[key for key,_ in queries if prefix+key in s]
            return {"columns":len(queries),"dead_bush_surface_columns":len(witnessed),
                    "sample_first_12":witnessed[:12]}
        require(proc.poll() is None,"SERVER_EXIT_DURING_CENSUS")
        time.sleep(.2)
    raise RuntimeError("CENSUS_TIMEOUT:"+label)


def one_world(root:Path,jar:Path,evidence:dict,seed:int,kind:str,scarlet_path:Path,steps:list)->dict:
    world_root=root/f"{kind}-{seed}"
    packs=world_root/"world/datapacks"
    packs.mkdir(parents=True)
    import shutil
    shutil.copyfile(scarlet_path,packs/"scarlet.zip")
    terrain_receipt=terrain_build(packs/"terrain.zip")
    habitat_receipt=habitat_build(packs/"habitat.zip")
    require(terrain_receipt["sha256"]==TERRAIN_SHA,"TERRAIN_INPUT_DRIFT")
    require(habitat_receipt["sha256"]==HABITAT_SHA,"HABITAT_INPUT_DRIFT")
    (world_root/"eula.txt").write_text("eula=true\n")
    preset="barsoom_habitat:scarlet_province" if kind=="scarlet" else "barsoom:dead_sea"
    (world_root/"server.properties").write_text(
        "server-ip=127.0.0.1\nserver-port=25599\nonline-mode=false\n"
        "level-name=world\n"
        f"level-type={preset}\n"
        "initial-enabled-packs=vanilla,file/terrain.zip,file/habitat.zip,file/scarlet.zip\n"
        "view-distance=3\nsimulation-distance=2\nmax-players=1\n"
        "spawn-protection=0\ngenerate-structures=false\n"
        "enable-rcon=false\nenable-query=false\n"
        "sync-chunk-writes=true\n"
        f"level-seed={seed}\n"
        "motd=Barsoom Scarlet autonomous worldgen RDTE\n")
    log=world_root/"server.log"
    with log.open("w+",encoding="utf-8") as output:
        proc=subprocess.Popen(["java","-Xms512M","-Xmx1536M","-jar",str(jar),"nogui"],
                              cwd=world_root,stdin=subprocess.PIPE,stdout=output,
                              stderr=subprocess.STDOUT,text=True)
        try:
            try:
                status_ready(proc,log)
            except Exception as e:
                s=log.read_text(errors="replace")
                at=s.find("Registry loading errors:")
                raise RuntimeError("NATIVE_REGISTRY_DIAGNOSTIC:"+s[at:at+8000] if at>=0 else
                                   "NATIVE_START_DIAGNOSTIC:"+s[-4000:]) from e
            require(not server_error_lines(log),"SERVER_PARSE_LOAD_ERRORS")
            steps.append(f"{kind}_{seed}_native_boot")
            send(proc,"forceload add 64 64 95 95")
            time.sleep(1.0)
            expected_biome="barsoom_habitat:scarlet_wastes" if kind=="scarlet" else "minecraft:badlands"
            prove(proc,log,
                  f"execute positioned 80 0 80 positioned over world_surface if biome ~ ~ ~ {expected_biome}",
                  f"{kind}_{seed}_EXPECTED_BIOME")
            steps.append(f"{kind}_{seed}_biome_registered_and_selected")
            census=measure(proc,log,kind+"_"+str(seed))
            steps.append(f"{kind}_{seed}_surface_census")
            require(stop_server(proc)==0,f"{kind}_SAVE_STOP_FAILURE")
            steps.append(f"{kind}_{seed}_graceful_stop")
            return {"kind":kind,"seed":seed,"preset":preset,"biome":expected_biome,**census}
        finally:
            if proc.poll() is None:
                try:stop_server(proc)
                except Exception:
                    proc.kill();proc.wait(timeout=10)


def run(evidence:dict,seed:int,steps:list)->dict:
    ident=evidence["artifact_version_json"]
    require(ident["id"]=="26.3" and ident["protocol_version"]==777 and
            ident["java_version"]==25,"EXACT_26_3_RUNTIME_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="barsoom-scarlet-autogen-") as td:
        root=Path(td)
        jar=root/"server.jar"
        download_verified_server(evidence,jar)
        require(hashlib.sha256(jar.read_bytes()).hexdigest()==evidence["server_artifact"]["sha256"],
                "OFFICIAL_SERVER_DIGEST_DRIFT")
        scarlet_path=root/"scarlet.zip"
        scarlet=scarlet_build(scarlet_path)
        steps.append("native_26_3_and_immutable_input_preflights")
        positive=one_world(root,jar,evidence,seed,"scarlet",scarlet_path,steps)
        require(positive["dead_bush_surface_columns"]>=1,"NO_AUTOMATIC_VEGETATION_CREATED")
        steps.append("automatic_worldgen_vegetation_positive")
        negative=one_world(root,jar,evidence,seed,"vanilla_badlands",scarlet_path,steps)
        require(negative["biome"]=="minecraft:badlands","NEGATIVE_BIOME_ID_DRIFT")
        require(positive["biome"]=="barsoom_habitat:scarlet_wastes","CUSTOM_BIOME_ID_DRIFT")
        steps.append("default_dead_sea_biome_control_preserved")
        return {"scarlet_sha256":scarlet["sha256"],
                "terrain_sha256":TERRAIN_SHA,"habitat_sha256":HABITAT_SHA,
                "seed":seed,"positive":positive,"negative_control":negative,
                "actual_chunk_generation":True,
                "explicit_place_feature_calls":0,
                "manual_terrain_changes":0,
                "existing_save_mutation":False,
                "planetary_province_atlas":"NOT_QUALIFIED"}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence",type=Path,required=True)
    p.add_argument("--seed",type=int,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    steps=[]
    receipt={"schema":"supracraft.barsoom.scarlet-worldgen-native/1",
             "result":"FAIL","steps":steps,"first_failure":None,
             "stock_client_hil":"NOT_RUN","physical_truenas_apply":"HOLD"}
    try:
        receipt.update(run(json.loads(a.evidence.read_text()),a.seed,steps))
        receipt["result"]="PASS"
    except Exception as exc:
        receipt["first_failure"]=type(exc).__name__+": "+str(exc)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    print(json.dumps(receipt,sort_keys=True,indent=2))
    return 0 if receipt["result"]=="PASS" else 1

if __name__=="__main__":
    raise SystemExit(main())
