#!/usr/bin/env python3
"""Observe natural 26.3 Barsoom Badlands before testing native vegetation.

Only a new temporary world is used. Terrain itself is not edited or prepared:
the only potential block changes come from invoking the admitted *native*
/place feature on an observed red-sand surface. Independent baseline and
post-placement reads prevent native dead bushes being counted as our output.
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

from probe_core_restoration_datapack_26_3 import send, stop_server, server_error_lines
from smoke_vanilla_runtime import download_verified_server
from qualify_vanilla_world_artifact_activation_263 import require
from qualify_barsoom_preset_263 import status_ready, prove

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fixtures/barsoom/terrain"))
sys.path.insert(0, str(ROOT / "fixtures/barsoom/habitat"))
from gen_dead_sea import build as build_terrain
from gen_habitat_263 import build as build_habitat

PINNED_HABITAT = "1bfbb244d9a172d00e1357370c464874e2e32a0e55a306e15f4a02dae4a332e7"
PINNED_TERRAIN = "9d5ad764a2df4786666326e997a3ed724524583fe3191b60305677fbe5fb531e"
SITES = [(80, 80), (-80, 64), (128, -96), (192, 32), (-192, -64), (320, 144)]
SOILS = ("red_sand", "terracotta", "orange_terracotta", "red_terracotta", "coarse_dirt",
         "grass_block", "sand", "stone")


def batch_query(proc, log: Path, prefix: str, queries: list[tuple[str, str]], timeout=30) -> set[str]:
    """Each query returns a marker iff a native execute predicate is true."""
    baseline = log.read_text(errors="replace")
    if prefix in baseline:
        raise ValueError("MARKER_REUSED:" + prefix)
    for key, predicate in queries:
        send(proc, f"{predicate} run say {prefix}{key}")
    terminator = prefix + "SCAN_DONE"
    send(proc, "say " + terminator)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        text = log.read_text(errors="replace")
        if terminator in text:
            return {key for key, _ in queries if prefix + key in text}
        require(proc.poll() is None, "NATIVE_SERVER_DIED_DURING_SCAN")
        time.sleep(.15)
    raise RuntimeError("NATIVE_SCAN_TIMEOUT:" + prefix + log.read_text(errors="replace")[-500:])


def scan_surface(proc, log: Path, center: tuple[int, int], site_index: int) -> dict:
    x0, z0 = center
    # Forces bounded chunks only; never changes blocks or gamerules.
    send(proc, f"forceload add {x0-12} {z0-12} {x0+12} {z0+12}")
    time.sleep(0.5)
    xs = (x0 - 4, x0 - 2, x0, x0 + 2, x0 + 4)
    zs = (z0 - 4, z0 - 2, z0, z0 + 2, z0 + 4)
    queries = []
    for x in xs:
        for z in zs:
            base = f"execute positioned {x} 0 {z} positioned over world_surface"
            queries.append((f"B_{x}_{z}", base + " if biome ~ ~ ~ minecraft:badlands"))
            for state in SOILS:
                queries.append((f"S_{x}_{z}_{state}", base +
                                f" if block ~ ~-1 ~ minecraft:{state}"))
    witnessed = batch_query(proc, log, f"BS_{site_index}_", queries)
    badlands = [(x, z) for x in xs for z in zs if f"B_{x}_{z}" in witnessed]
    soils = {state: [(x, z) for x in xs for z in zs if f"S_{x}_{z}_{state}" in witnessed]
             for state in SOILS}
    chosen = next(((kind, positions) for kind in
                   ("red_sand", "terracotta", "orange_terracotta", "red_terracotta")
                   if (positions := soils[kind])), (None, []))
    return {"center": [x0, z0], "badlands_sample_count": len(badlands),
            "surface_soil_counts": {k: len(v) for k, v in soils.items()},
            "red_sand_columns": [list(p) for p in soils["red_sand"]],
            "selected_substrate": chosen[0],
            "selected": chosen[1][len(chosen[1]) // 2] if chosen[1] else None}


def bush_witnesses(proc, log: Path, origin: tuple[int, int], serial: str) -> set[str]:
    x0, z0 = origin
    queries = []
    # The HeightMap cursor sits above the topmost surface, including any vegetation.
    # Thus the block immediately beneath it is a bush iff native terrain has a bush.
    for dx in range(-7, 8):
        for dz in range(-7, 8):
            x, z = x0 + dx, z0 + dz
            queries.append((f"P_{x}_{z}",
                            f"execute positioned {x} 0 {z} positioned over world_surface"
                            " if block ~ ~-1 ~ minecraft:dead_bush"))
    return batch_query(proc, log, "BW_" + serial + "_", queries, timeout=35)


def run(evidence: dict, steps: list[str], seed: int) -> dict:
    ident = evidence["artifact_version_json"]
    require(ident["id"] == "26.3" and ident["java_version"] == 25 and
            ident["protocol_version"] == 777, "VERSION_OR_PROTOCOL_MISMATCH")
    with tempfile.TemporaryDirectory(prefix="barsoom-natural-habitat-") as temp:
        home = Path(temp) / "server"
        packs = home / "world/datapacks"
        packs.mkdir(parents=True)
        jar = home / "server.jar"
        download_verified_server(evidence, jar)
        require(hashlib.sha256(jar.read_bytes()).hexdigest() ==
                evidence["server_artifact"]["sha256"], "OFFICIAL_MOJANG_JAR_SHA_MISMATCH")
        terrain = build_terrain(packs / "terrain.zip")
        habitat = build_habitat(packs / "habitat.zip")
        require(terrain["sha256"] == PINNED_TERRAIN and
                habitat["sha256"] == PINNED_HABITAT, "IMMUTABLE_GENERATOR_ARTIFACT_DRIFT")
        steps.append("two_qualified_producer_hashes_validated")
        (home / "eula.txt").write_text("eula=true\n")
        (home / "server.properties").write_text(
            "server-ip=127.0.0.1\nserver-port=25599\nonline-mode=false\n"
            "level-name=world\nlevel-type=barsoom:dead_sea\n"
            "initial-enabled-packs=vanilla,file/terrain.zip,file/habitat.zip\n"
            "view-distance=3\nsimulation-distance=2\nspawn-protection=0\nmax-players=1\n"
            "generate-structures=false\nsync-chunk-writes=true\n"
            "enable-rcon=false\nenable-query=false\n"
            f"level-seed={seed}\n"
            "motd=Barsoom natural Badlands habitat proof\n")
        log = home / "native.log"
        records = []
        winner = None
        with log.open("w+", encoding="utf-8") as stream:
            proc = subprocess.Popen(["java", "-Xms512M", "-Xmx1536M", "-jar",
                                     str(jar), "nogui"], cwd=home, stdin=subprocess.PIPE,
                                    stdout=stream, stderr=subprocess.STDOUT, text=True)
            try:
                status_ready(proc, log)
                require(not server_error_lines(log) and
                        "Failed to load data packs" not in log.read_text(errors="replace"),
                        "REGISTRY_OR_PACK_LOAD_REJECTED")
                steps.append("official_server_generated_unchanged_world")
                send(proc, "scoreboard objectives add habitat_probe dummy")
                for i, center in enumerate(SITES):
                    item = scan_surface(proc, log, center, i)
                    item["attempted_feature"] = False
                    records.append(item)
                    if item["badlands_sample_count"] == 0:
                        continue
                    selected = item["selected"]
                    if selected is None:
                        continue
                    x, z = selected
                    # First natural baseline measurement: no terrain preparation or
                    # destructive ground truth. Do not count existing natural bushes.
                    before = bush_witnesses(proc, log, (x, z), f"BEFORE_{i}")
                    item["before_bushes"] = len(before)
                    # At natural surface y+0, plant placement is the sole game mutation.
                    send(proc, f"execute positioned {x} 0 {z} positioned over world_surface"
                               " store result score #placed habitat_probe run "
                               "place feature barsoom_habitat:scarlet_patch ~ ~ ~")
                    prove(proc, log, "execute if score #placed habitat_probe matches 0..",
                          f"WILD_FEATURE_RESULT_{i}")
                    time.sleep(.5)
                    after = bush_witnesses(proc, log, (x, z), f"AFTER_{i}")
                    additions = after - before
                    item.update({"attempted_feature": True, "after_bushes": len(after),
                                 "new_bushes": len(additions),
                                 "new_bush_columns": sorted(additions)[:20]})
                    if additions:
                        winner = {"site": [x, z], "sample": item}
                        steps.append("native_wild_surface_produced_new_vegetation")
                        break
                require(winner is not None, "NO_POSITIVE_UNMODIFIED_BADLANDS_WITNESS:" +
                        json.dumps(records, separators=(",", ":"))[:3400])
                require(stop_server(proc) == 0, "GRACEFUL_STOP_FAILED")
                steps.append("graceful_save_stop")
            finally:
                if proc.poll() is None:
                    try:
                        stop_server(proc)
                    except Exception:
                        proc.kill()
                        proc.wait(timeout=10)
        return {
            "seed": seed, "world_preset": "barsoom:dead_sea",
            "terrain_sha256": terrain["sha256"], "habitat_sha256": habitat["sha256"],
            "sample_sites": records, "positive_site": winner["site"],
            "new_bushes_on_untouched_surface": winner["sample"]["new_bushes"],
            "world_surface_preparation": False,
            "single_native_place_feature_actuator": True,
            "natural_biome_automatic_distribution": "NOT_IMPLEMENTED",
        }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=1811001)
    a = p.parse_args()
    steps: list[str] = []
    receipt = {"schema": "supracraft.barsoom.natural-habitat/1", "result": "FAIL",
               "first_failure": None, "steps": steps,
               "stock_client": "NOT_RUN", "physical_truenas_apply": "HOLD"}
    try:
        receipt.update(run(json.loads(a.evidence.read_text()), steps, a.seed))
        receipt["result"] = "PASS"
    except Exception as e:
        receipt["first_failure"] = type(e).__name__ + ": " + str(e)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0 if receipt["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
