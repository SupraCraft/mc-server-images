#!/usr/bin/env python3
"""Fail-closed official 26.3 disposable flora pack qualification."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fixtures/barsoom/flora"))
from gen_flora_263 import build
from probe_core_restoration_datapack_26_3 import send, stop_server, wait_for_predicate, server_error_lines
from smoke_vanilla_runtime import download_verified_server, status_query

PORT = 25596
BASE = (520, 192, 520)

def ready(proc, logfile, timeout=180):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if proc.poll() is not None:
            raise RuntimeError("NATIVE_SERVER_EXITED: " + logfile.read_text(errors="replace")[-1700:])
        try:
            status = status_query("127.0.0.1", PORT, 777)
            if status.get("version", {}).get("protocol") == 777 and "Done (" in logfile.read_text(errors="replace"):
                return
        except (OSError, EOFError, TimeoutError, ValueError):
            pass
        time.sleep(0.6)
    raise RuntimeError("NATIVE_SERVER_START_TIMEOUT: " + logfile.read_text(errors="replace")[-1700:])

def prove(proc, logfile, predicate, marker):
    wait_for_predicate(proc, logfile, marker=marker, predicate=predicate, timeout=12)

def inspect_log(logfile):
    text = logfile.read_text(errors="replace")
    errors = server_error_lines(logfile)
    if errors or "Failed to load data packs" in text or "Unknown function" in text:
        raise RuntimeError("NATIVE_PACK_ERROR: " + repr((errors, text[-1700:])))

def config(home):
    (home / "eula.txt").write_text("eula=true\n")
    (home / "server.properties").write_text(
        "server-ip=127.0.0.1\nserver-port=25596\nonline-mode=false\n"
        "level-name=world\ninitial-enabled-packs=vanilla,file/barsoom-flora.zip\n"
        "view-distance=3\nsimulation-distance=2\nspawn-protection=0\n"
        "max-players=1\ngenerate-structures=false\n"
        "enable-rcon=false\nenable-query=false\nlevel-seed=1811002\n"
        "sync-chunk-writes=true\nmotd=Barsoom flora 26.3 native fixture\n"
    )

def run(evidence, steps):
    if evidence["artifact_version_json"]["id"] != "26.3" or evidence["artifact_version_json"]["java_version"] != 25:
        raise RuntimeError("WRONG_OFFICIAL_RUNTIME")
    with tempfile.TemporaryDirectory(prefix="barsoom-flora-native-") as temp:
        root = Path(temp)
        home = root / "server"
        (home / "world/datapacks").mkdir(parents=True)
        jar = home / "server.jar"
        download_verified_server(evidence, jar)
        if hashlib.sha256(jar.read_bytes()).hexdigest() != evidence["server_artifact"]["sha256"]:
            raise RuntimeError("OFFICIAL_SERVER_DIGEST_FAILED")
        steps.append("official_server_26_3_sha256_verified")
        pack = home / "world/datapacks/barsoom-flora.zip"
        receipt = build(pack)
        steps.append("flora_pack_sha256_" + receipt["sha256"])
        config(home)
        for attempt in (1, 2):
            logfile = home / f"flora-native-{attempt}.log"
            with logfile.open("w", encoding="utf-8") as log:
                proc = subprocess.Popen(
                    ["java", "-Xms512M", "-Xmx1536M", "-jar", str(jar), "nogui"],
                    cwd=home, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, text=True
                )
                try:
                    ready(proc, logfile)
                    inspect_log(logfile)
                    steps.append(f"official_server_boot_{attempt}_pack_load")
                    send(proc, "forceload add 512 512 544 544")
                    time.sleep(0.8)
                    if attempt == 1:
                        prove(proc, logfile,
                              "execute unless entity @e[type=minecraft:marker,tag=barsoom_flora.predator]",
                              "FLORA_NO_HAZARD_BEFORE_DEMO")
                        send(proc, "execute positioned 520 192 520 run function barsoom_flora:demo")
                        time.sleep(1.5)
                    else:
                        steps.append("restarted_saved_world_without_replant")
                    checks = [
                        ("grass", "execute if block 512 192 520 minecraft:crimson_roots"),
                        ("shrub", "execute if block 516 192 520 minecraft:sweet_berry_bush[age=3]"),
                        ("tree_stem", "execute if block 520 192 520 minecraft:warped_stem"),
                        ("tree_canopy", "execute if block 520 196 520 minecraft:warped_wart_block"),
                        ("crop", "execute if block 525 192 520 minecraft:wheat[age=7]"),
                        ("irrigation", "execute if block 526 191 520 minecraft:water"),
                        ("carnivore", "execute if block 529 192 520 minecraft:crimson_fungus"),
                        ("hazard_anchor", "execute if entity @e[type=minecraft:marker,tag=barsoom_flora.predator]"),
                    ]
                    for key, predicate in checks:
                        prove(proc, logfile, predicate, f"FLORA_{attempt}_{key.upper()}")
                        steps.append(f"boot_{attempt}_{key}_native_pass")
                    if attempt == 1:
                        send(proc, "execute positioned 520 192 520 run function barsoom_flora:demo")
                        send(proc, "scoreboard objectives add flora_count dummy")
                        send(proc, "execute store result score #anchors flora_count if entity @e[type=minecraft:marker,tag=barsoom_flora.predator]")
                        prove(proc, logfile, "execute if score #anchors flora_count matches 1",
                              "FLORA_DEMO_IDEMPOTENT_SINGLE_MARKER")
                        steps.append("repeated_demo_single_hazard_anchor")
                    send(proc, "function barsoom_flora:hazard_tick")
                    time.sleep(0.5)
                    inspect_log(logfile)
                    steps.append(f"boot_{attempt}_hazard_function_executed_without_parser_errors")
                    if stop_server(proc) != 0:
                        raise RuntimeError("STOP_NONZERO")
                    steps.append(f"boot_{attempt}_graceful_save_stop")
                finally:
                    if proc.poll() is None:
                        try:
                            stop_server(proc)
                        except Exception:
                            proc.kill()
                            proc.wait(timeout=10)
        return receipt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    steps = []
    result = {
        "schema": "supracraft.barsoom.flora-native/1",
        "minecraft": "26.3", "result": "FAIL", "steps": steps,
        "stock_client_visual_HIL": "NOT_RUN",
        "poison_damage_player_oracle": "NOT_RUN",
        "natural_worldgen_ecology": "NOT_IMPLEMENTED",
        "physical_truenas_apply": "HOLD",
    }
    try:
        receipt = run(json.loads(args.evidence.read_text()), steps)
        result.update({"result": "PASS", "first_failure": None, "candidate_sha256": receipt["sha256"]})
    except Exception as error:
        result["first_failure"] = type(error).__name__ + ": " + str(error)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
