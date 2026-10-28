#!/usr/bin/env python3
"""Native two-biome four-parity-cell checkerboard acceptance harness.

Each independently run seed uses a fresh disposable official Java 26.3 world.
Never touches existing saves or manually places vegetation. No stock-client HIL.
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

ROOT = Path(__file__).resolve().parents[1]
for path in ("fixtures/barsoom/terrain", "fixtures/barsoom/habitat",
             "fixtures/barsoom/biomes", "fixtures/barsoom/provinces"):
    sys.path.insert(0, str(ROOT / path))
from gen_dead_sea import build as build_terrain
from gen_habitat_263 import build as build_habitat
from gen_scarlet_wastes_263 import build as build_scarlet
from gen_checkerboard_263 import build as build_checkerboard, PARENT_SHA256, biome_at
from smoke_vanilla_runtime import download_verified_server
from probe_core_restoration_datapack_26_3 import send, stop_server, server_error_lines
from qualify_barsoom_preset_263 import status_ready, prove
from qualify_vanilla_world_artifact_activation_263 import require

REGIONS = [(64, 64), (192, 64), (64, 192), (192, 192)]
# Independent geographic controls outside the original positive-only x/z quadrant.
NEGATIVE_REGIONS = [(-64, 64), (-64, -64), (64, -64), (-192, 64)]
# Exact native stripe transition witnesses in both positive and negative space.
BOUNDARY_PAIRS = [
    ((127, 64), (128, 64)), ((64, 127), (64, 128)),
    ((-1, 64), (0, 64)), ((64, -1), (64, 0)),
]
REGION_RADIUS = 16


def census(proc, log: Path, center: tuple[int, int], prefix: str) -> dict:
    """Read-only native 32x32 surface columns; no counter-changing fill tricks."""
    x0,z0=center
    text=log.read_text(errors="replace")
    require(prefix not in text, "MARKER_PREFIX_REUSED:" + prefix)
    targets = []
    for x in range(x0 - REGION_RADIUS, x0 + REGION_RADIUS):
        for z in range(z0 - REGION_RADIUS, z0 + REGION_RADIUS):
            key=f"B_{x}_{z}"
            cmd=f"execute positioned {x} 0 {z} positioned over world_surface if block ~ ~-1 ~ minecraft:dead_bush"
            targets.append((key,cmd))
    for key,cmd in targets:
        send(proc, f"{cmd} run say {prefix}{key}")
    terminator=prefix+"DONE"
    send(proc, "say "+terminator)
    stop=time.monotonic()+100
    while time.monotonic()<stop:
        contents=log.read_text(errors="replace")
        if terminator in contents:
            found=[k for k,_ in targets if prefix+k in contents]
            return {"center": [x0,z0], "samples":len(targets),
                    "dead_bush_columns":len(found), "witness_columns_first_12":found[:12]}
        require(proc.poll() is None, "NATIVE_WORLD_EXITED_DURING_CENSUS")
        time.sleep(.2)
    raise RuntimeError("CENSUS_TIMEOUT:"+prefix)


def run(evidence: dict, seed: int, steps: list[str]) -> dict:
    ident=evidence["artifact_version_json"]
    require(ident["id"]=="26.3" and ident["protocol_version"]==777 and
            ident["java_version"]==25, "EXACT_JAVA26_3_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="barsoom-checkerboard-native-") as temporary:
        home=Path(temporary)/"server"
        packs=home/"world/datapacks"
        packs.mkdir(parents=True)
        jar=home/"server.jar"
        download_verified_server(evidence,jar)
        require(hashlib.sha256(jar.read_bytes()).hexdigest()==evidence["server_artifact"]["sha256"],
                "MOJANG_SERVER_SHA_DRIFT")
        receipt_by_name={
            "terrain":build_terrain(packs/"terrain.zip"),
            "habitat":build_habitat(packs/"habitat.zip"),
            "scarlet":build_scarlet(packs/"scarlet.zip"),
        }
        for name,expected in PARENT_SHA256.items():
            value=receipt_by_name[name].get("sha256")
            require(value==expected, "UPSTREAM_PRODUCER_HASH_DRIFT:"+name+":"+str(value))
        separate=build_checkerboard(packs/"checkerboard.zip")
        steps.append("all_three_parent_producer_hashes_verified")
        (home/"eula.txt").write_text("eula=true\n",encoding="utf-8")
        (home/"server.properties").write_text(
            "server-ip=127.0.0.1\nserver-port=25599\nonline-mode=false\n"
            "level-name=world\nlevel-type=barsoom_habitat:checkerboard_provinces\n"
            "initial-enabled-packs=vanilla,file/terrain.zip,file/habitat.zip,file/scarlet.zip,file/checkerboard.zip\n"
            "view-distance=3\nsimulation-distance=2\nmax-players=1\n"
            "spawn-protection=0\ngenerate-structures=false\n"
            "enable-rcon=false\nenable-query=false\n"
            "sync-chunk-writes=true\n"
            f"level-seed={seed}\n"
            "motd=Barsoom checkerboard two-province RDTE\n",encoding="utf-8")
        log=home/"server.log"
        with log.open("w+",encoding="utf-8") as stream:
            proc=subprocess.Popen(["java","-Xms512M","-Xmx1536M","-jar",str(jar),"nogui"],
                                  cwd=home,stdin=subprocess.PIPE,stdout=stream,
                                  stderr=subprocess.STDOUT,text=True)
            try:
                try:
                    status_ready(proc,log)
                except Exception as exc:
                    contents=log.read_text(errors="replace")
                    index=contents.find("Registry loading errors:")
                    snippet=contents[index:index+10000] if index>=0 else contents[-5000:]
                    raise RuntimeError("CHECKERBOARD_NATIVE_START_REJECTED:"+snippet) from exc
                require(not server_error_lines(log), "NATIVE_DATA_PACK_LOAD_ERROR")
                steps.append("native_preset_and_biome_registry_loaded")
                observations={}
                sites=[]
                for n,(x,z) in enumerate(REGIONS):
                    send(proc, f"forceload add {x-20} {z-20} {x+19} {z+19}")
                    time.sleep(.8)
                    expected_biome=biome_at(x,z)
                    for dx,dz in ((0,0),(-12,0),(12,0),(0,-12),(0,12)):
                        prove(proc,log,
                              f"execute positioned {x+dx} 0 {z+dz} positioned over world_surface if biome ~ ~ ~ {expected_biome}",
                              f"SITE_{n}_OFFSET_{dx}_{dz}_BIOME")
                    observed=census(proc,log,(x,z),f"CB_{seed}_{n}_")
                    # Preserve the legacy first-site per-biome summary for consumers;
                    # add all four independent parity witnesses without overwriting.
                    observations.setdefault(expected_biome,observed)
                    sites.append({"site_index":n,"biome":expected_biome,**observed})
                    steps.append(f"seed_{seed}_region_{n}_biome_and_plant_witness")
                scarlet=[site["dead_bush_columns"] for site in sites
                         if site["biome"]=="barsoom_habitat:scarlet_wastes"]
                vanilla=[site["dead_bush_columns"] for site in sites
                         if site["biome"]=="minecraft:badlands"]
                require(len(scarlet)==2 and len(vanilla)==2,
                        "FOUR_CELL_BIOME_PARITY_INVALID")
                # Require both Scarlet parity cells to beat both vanilla
                # controls, not merely a favorable mean or one hot spot.
                require(min(scarlet)>max(vanilla) and min(scarlet)>=30,
                        f"FOUR_CELL_AUTOGEN_NOT_DIFFERENTIATED:{scarlet}:{vanilla}")
                steps.append("same_world_positive_and_negative_biome_differentiated")
                steps.append("four_parity_cells_independently_censused")
                # Separate negative-quadrant source-vs-native geographic
                # falsification. These sentinels do not need a second plant
                # census; original four-site plant sample remains unchanged.
                negative_sites=[]
                for n,(x,z) in enumerate(NEGATIVE_REGIONS):
                    expected=biome_at(x,z)
                    for dx,dz in ((0,0),(-12,0),(12,0),(0,-12),(0,12)):
                        prove(proc,log,
                              f"execute positioned {x+dx} 0 {z+dz} positioned over world_surface if biome ~ ~ ~ {expected}",
                              f"NEG_SITE_{n}_OFFSET_{dx}_{dz}_BIOME")
                    negative_sites.append({"center":[x,z],"expected_biome":expected,
                                           "native_biome_predicates":5})
                require(len(negative_sites)==4 and len({
                    item["expected_biome"] for item in negative_sites})==2,
                    "NEGATIVE_GEOGRAPHY_PARITY_INVALID")
                steps.append("four_negative_coordinate_regions_native_verified")

                # A center-only probe can miss off-by-one boundaries. Require
                # the exact adjacent blocks across +128 and zero boundaries
                # to be different under the model and match native lookup.
                boundary_pairs=[]
                for n,((ax,az),(bx,bz)) in enumerate(BOUNDARY_PAIRS):
                    left,right=biome_at(ax,az),biome_at(bx,bz)
                    require(left!=right,"BOUNDARY_ORACLE_NOT_DISCRIMINATING")
                    for side,(x,z,expected) in enumerate(
                            ((ax,az,left),(bx,bz,right))):
                        prove(proc,log,
                              f"execute positioned {x} 0 {z} positioned over world_surface if biome ~ ~ ~ {expected}",
                              f"BOUNDARY_{n}_SIDE_{side}_BIOME")
                    boundary_pairs.append({"cells":[[ax,az],[bx,bz]],
                                           "biomes":[left,right],
                                           "native_biome_predicates":2})
                steps.append("eight_boundary_side_predicates_native_verified")
                require(stop_server(proc)==0,"GRACEFUL_STOP_FAILURE")
                steps.append("graceful_stop")
            finally:
                if proc.poll() is None:
                    try:stop_server(proc)
                    except Exception:proc.kill();proc.wait(timeout=10)
        return {"seed":seed,"checkerboard_pack_sha256":separate["pack_sha256"],
                "parent_pack_sha256":PARENT_SHA256,"regions":observations,
                "native_biomes_in_one_world":True,"explicit_place_feature_calls":0,
                "manual_terrain_changes":0,"existing_save_mutations":False,
                "four_parity_cells_verified":True,"sites":sites,
                "negative_geography_verified":True,"negative_sites":negative_sites,
                "native_boundary_verified":True,"boundary_pairs":boundary_pairs,
                "production_deployment":"HOLD"}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--evidence",type=Path,required=True)
    parser.add_argument("--seed",type=int,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    steps=[]
    receipt={"schema":"supracraft.barsoom.two-province-native/1","result":"FAIL",
             "first_failure":None,"steps":steps,"stock_client_hil":"NOT_RUN",
             "production_truenas":"HOLD"}
    try:
        receipt.update(run(json.loads(args.evidence.read_text()),args.seed,steps))
        receipt["result"]="PASS"
    except Exception as exc:
        receipt["first_failure"]=type(exc).__name__+": "+str(exc)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,sort_keys=True,indent=2))
    return 0 if receipt["result"]=="PASS" else 1

if __name__=="__main__":
    raise SystemExit(main())
