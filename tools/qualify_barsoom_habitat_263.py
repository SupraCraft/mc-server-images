#!/usr/bin/env python3
"""Native Java 26.3 admission for independently staged vegetation feature.

Two immutable data packs in one disposable exact version world. Tests the
minecraft:projected_random_patchy_square parser and actual /place feature,
with independent count of live produced bushes, not just command parsing.
A prepared substrate is required for deterministic oracle; automatic habitat
generation in arbitrary terrain remains a separate gate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from probe_core_restoration_datapack_26_3 import send, stop_server, server_error_lines
from smoke_vanilla_runtime import download_verified_server
from qualify_vanilla_world_artifact_activation_263 import require
from qualify_barsoom_preset_263 import status_ready, prove

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fixtures/barsoom/habitat"))
sys.path.insert(0, str(ROOT / "fixtures/barsoom/terrain"))
from gen_habitat_263 import build as habitat_build
from gen_dead_sea import build as terrain_build


def run(evidence: dict, steps: list[str]) -> dict:
    require(evidence["artifact_version_json"]["id"] == "26.3" and
            evidence["artifact_version_json"]["protocol_version"] == 777 and
            evidence["artifact_version_json"]["java_version"] == 25,
            "EXACT_NATIVE_RUNTIME_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="barsoom-habitat-263-") as t:
        home = Path(t) / "server"
        packs = home / "world/datapacks"
        packs.mkdir(parents=True)
        jar = home / "server.jar"
        download_verified_server(evidence, jar)
        require(hashlib.sha256(jar.read_bytes()).hexdigest() ==
                evidence["server_artifact"]["sha256"], "OFFICIAL_JAR_SHA_DRIFT")
        terrain = terrain_build(packs / "terrain.zip")
        habitat = habitat_build(packs / "habitat.zip")
        steps.append("source_hashes_recorded")
        (home / "eula.txt").write_text("eula=true\n")
        (home / "server.properties").write_text(
            "server-ip=127.0.0.1\nserver-port=25599\nonline-mode=false\n"
            "level-name=world\nlevel-type=barsoom:dead_sea\n"
            "initial-enabled-packs=vanilla,file/terrain.zip,file/habitat.zip\n"
            "view-distance=3\nsimulation-distance=2\nmax-players=1\n"
            "spawn-protection=0\ngenerate-structures=false\n"
            "enable-rcon=false\nenable-query=false\nlevel-seed=1811001\n"
            "sync-chunk-writes=true\nmotd=Barsoom habitat native 26.3 test\n"
        )
        log = home / "native.log"
        with log.open("w+", encoding="utf-8") as stream:
            proc = subprocess.Popen(["java", "-Xms512M", "-Xmx1536M",
                                    "-jar", str(jar), "nogui"],
                                    cwd=home, stdin=subprocess.PIPE, stdout=stream,
                                    stderr=subprocess.STDOUT, text=True)
            try:
                try:
                    status_ready(proc, log)
                except Exception as exc:
                    lines = log.read_text(errors="replace").splitlines()
                    relevant = [line for line in lines if any(
                        token in line.lower() for token in (
                            "error", "registry", "unknown", "failed", "unbound",
                            "parse", "decode", "scarlet", "habitat"))]
                    raise RuntimeError("NATIVE_REGISTRY_DIAGNOSTIC:" +
                                       " | ".join(relevant)[-9000:]) from exc
                require(not server_error_lines(log), "NATIVE_PACK_LOAD_ERROR")
                require("Failed to load data packs" not in log.read_text(errors="replace"),
                        "NATIVE_REGISTRY_PARSE_REJECTED")
                steps.append("official_server_two_packs_loaded")
                send(proc, "forceload add 64 64 80 80")
                time.sleep(.8)
                send(proc, "fill 64 158 64 80 158 80 minecraft:red_terracotta replace")
                send(proc, "fill 64 159 64 80 159 80 minecraft:red_sand replace")
                send(proc, "fill 64 160 64 80 170 80 minecraft:air replace")
                send(proc, "scoreboard objectives add habitat_count dummy")
                prove(proc, log, "execute if block 72 159 72 minecraft:red_sand",
                      "HABITAT_SUBSTRATE_LOADED")
                steps.append("soil_fixture_qualified")
                send(proc, "execute store result score #feature habitat_count run place feature barsoom_habitat:scarlet_patch 72 160 72")
                prove(proc, log, "execute if score #feature habitat_count matches 1..",
                      "HABITAT_PROJECTION_FEATURE_PLACED")
                steps.append("native_26_3_projected_feature_placed")
                # Destructive count only in temporary test fixture, not an acceptance shortcut:
                # feature must have actually left one or more plant blocks in the area.
                send(proc, "execute store result score #plants habitat_count run fill 64 160 64 80 160 80 minecraft:air replace minecraft:dead_bush")
                prove(proc, log, "execute if score #plants habitat_count matches 1..",
                      "HABITAT_OBSERVED_LIVE_BLOCKS")
                steps.append("native_plants_detected_via_actual_block_replacement_count")
                require(stop_server(proc) == 0, "SAVE_STOP_FAILURE")
                steps.append("graceful_stop")
            finally:
                if proc.poll() is None:
                    try:
                        stop_server(proc)
                    except Exception:
                        proc.kill()
                        proc.wait(timeout=10)
        return {"minecraft": "26.3", "feature_sha256": habitat["sha256"],
                "terrain_sha256": terrain["sha256"], "feature": habitat["feature"],
                "projected_vegetation_on_prepared_substrate": True,
                "automatic_natural_biome_distribution": "NOT_IMPLEMENTED"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    steps: list[str] = []
    receipt = {"schema": "supracraft.barsoom.habitat-native/1",
               "result": "FAIL", "first_failure": None, "steps": steps,
               "real_terrain_habitat": "NOT_QUALIFIED",
               "physical_truenas_apply": "HOLD"}
    try:
        receipt.update(run(json.loads(a.evidence.read_text()), steps))
        receipt["result"] = "PASS"
    except Exception as e:
        receipt["first_failure"] = type(e).__name__ + ": " + str(e)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0 if receipt["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
