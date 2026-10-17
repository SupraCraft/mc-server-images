#!/usr/bin/env python3
"""Exact-26.3 three-producer integration: Dead Sea + canal quest + flora.

Reuse the already-qualified player quest without cloning its harness.
- Outpost crop-corrected pack: SHA pinned in compose_barsoom_263.
- Dead Sea preset: SHA pinned in compose_barsoom_263.
- Flora: independently staged, immutable deterministic candidate SHA.
Native state is observed before/after full original bot quest and restart.
All operations are in a temporary offline loopback world.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / ".deps/qualified-outpost-source"
sys.path.insert(0, str(PINNED / "tools"))
sys.path.insert(0, str(ROOT / "fixtures/barsoom/flora"))
sys.path.insert(0, str(ROOT / "fixtures/barsoom/terrain"))

import qualify_barsoom_263 as qualified
from gen_flora_263 import build as build_flora
from gen_dead_sea import build as build_terrain
from compose_barsoom_263 import compose
from probe_core_restoration_datapack_26_3 import send

FLORA_SHA = "098f6c1011871cdc786efc8e70abdf12c0318474d9ebda32a617d7c4b3276ffd"
BASE_COMPOSED_SHA = "d9a0d0463ad42d32b088b5fdd8f2c649fde0b978de5ca68cc55ca7b674991d94"
ORIGIN = (96, 160, 0)


def configure(home: Path, flora_zip: Path) -> None:
    (home / "eula.txt").write_text("eula=true\n")
    (home / "server.properties").write_text(
        "server-ip=127.0.0.1\nserver-port=25593\nonline-mode=false\n"
        "white-list=false\nenforce-whitelist=false\n"
        "level-name=world\nlevel-type=barsoom:dead_sea\n"
        "initial-enabled-packs=vanilla,file/barsoom.zip,file/flora.zip\n"
        "view-distance=3\nsimulation-distance=2\nmax-players=2\n"
        "spawn-protection=0\ngenerate-structures=false\n"
        "enable-rcon=false\nenable-query=false\n"
        "level-seed=4242424242\nsync-chunk-writes=true\n"
        "motd=Barsoom three-producer vanilla RDTE\n"
    )
    folder = home / "world/datapacks"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(flora_zip, folder / "flora.zip")


def observe_species(proc, log, original_oracle, flora, steps: list[str], phase: str):
    x0, y0, z0 = ORIGIN
    # This is an explicit build-time actuator for a disposable fixture.
    # Never call inside the canal's x~[-24,24] site.
    send(proc, "forceload add 96 0 128 0")
    time.sleep(1.0)
    for name, specimen in flora["probes"].items():
        x, dy, z = specimen["position"]
        absolute = (x0 + x, y0 + dy, z0 + z)
        original_oracle(proc, log,
                        f"execute if block {absolute[0]} {absolute[1]} {absolute[2]} {specimen['state']}",
                        "COMPOSE_FLORA_" + name.upper() + "_" + phase.upper())
        steps.append(f"{phase}_flora_{name}")
    original_oracle(proc, log,
                    "execute positioned 116 160 0 if entity @e[type=minecraft:marker,tag=barsoom_flora.trap,distance=..2]",
                    "COMPOSE_FLORA_MARKER_" + phase.upper())
    steps.append(f"{phase}_flora_marker")


def run(evidence: dict, steps: list[str]) -> dict:
    if evidence["artifact_version_json"]["id"] != "26.3":
        raise ValueError("EXACT_VERSION_REQUIRED")
    if not (PINNED / "fixtures/barsoom/build_barsoom.py").is_file():
        raise ValueError("IMMUTABLE_OUTPOST_SOURCE_NOT_CHECKED_OUT")
    original = qualified.validate_source()  # validates original and crop-corrected digests
    steps.append("immutable_original_outpost_rebuilt")
    with tempfile.TemporaryDirectory(prefix="barsoom-three-way-") as tmp:
        root = Path(tmp)
        terrain_file, flora_file, base_file = (root / v for v in
                                                ("terrain.zip", "flora.zip", "base.zip"))
        terrain = build_terrain(terrain_file)
        flora = build_flora(flora_file)
        if flora["sha256"] != FLORA_SHA:
            raise ValueError("FLORA_PRODUCER_SHA_DRIFT")
        composed = compose(original, terrain_file, base_file)
        if composed["sha256"] != BASE_COMPOSED_SHA:
            raise ValueError("BASE_OUTPOST_TERRAIN_COMPOSITION_SHA_DRIFT")
        if terrain["sha256"] != composed["terrain_sha256"]:
            raise ValueError("TERRAIN_SHA_DRIFT")
        steps.append("three_immutable_input_producers_verified")

        old_source = qualified.validate_source
        old_candidate = qualified.CANDIDATE
        old_config = qualified.server_config
        old_oracle = qualified.oracle
        observed = {"installed": False, "restart": False}

        def instrumented_oracle(proc, log, predicate, marker):
            old_oracle(proc, log, predicate, marker)
            # Inject the opt-in flora *after* genuine player-built outpost;
            # never alter existing quest test steps or their oracle predicates.
            if marker == "BARSOOM_OUTPOST_AND_RUIN_BUILT":
                if observed["installed"]:
                    raise ValueError("FLORA_INJECTION_DUPLICATED")
                x, y, z = ORIGIN
                send(proc, f"execute positioned {x} {y} {z} run function barsoom_flora:demo")
                observe_species(proc, log, old_oracle, flora, steps, "first")
                observed["installed"] = True
                steps.append("quest_outpost_and_flora_coexisted")
            if marker == "BARSOOM_RESTART_CANAL_WATER":
                if not observed["installed"] or observed["restart"]:
                    raise ValueError("FLORA_RESTART_CHECK_ORDER_INVALID")
                observe_species(proc, log, old_oracle, flora, steps, "restart")
                observed["restart"] = True
                steps.append("quest_canal_and_flora_persisted_after_restart")

        try:
            qualified.validate_source = lambda: base_file
            qualified.CANDIDATE = composed["sha256"]
            qualified.server_config = lambda home: configure(home, flora_file)
            qualified.oracle = instrumented_oracle
            qualified.run(evidence, steps)
            if not all(observed.values()):
                raise ValueError("COMPOSITION_MILESTONES_MISSING:" + json.dumps(observed))
        finally:
            qualified.validate_source = old_source
            qualified.CANDIDATE = old_candidate
            qualified.server_config = old_config
            qualified.oracle = old_oracle
        return {"base_sha256": composed["sha256"], "flora_sha256": flora["sha256"],
                "minecraft": "26.3", "gameplay": "original_full_player_quest",
                "composition": "two_distinct_packs_in_one_world",
                "flora": list(flora["probes"])}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    steps: list[str] = []
    result = {"schema": "supracraft.barsoom.three-way/1", "result": "FAIL",
              "first_failure": None, "steps": steps,
              "stock_mojang_client_visual": "NOT_RUN",
              "biome_ecology": "NOT_IMPLEMENTED",
              "physical_truenas_apply": "HOLD"}
    try:
        result.update(run(json.loads(a.evidence.read_text()), steps))
        result["result"] = "PASS"
    except Exception as e:
        result["first_failure"] = type(e).__name__ + ": " + str(e)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
