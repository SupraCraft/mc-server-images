#!/usr/bin/env python3
"""Behavioral qualification of Barsoom jawbloom using an actual 26.3 offline client.

Separate from block-state and restart canary. Reuses the exact accepted
Mineflayer protocol-777 transport from the existing Barsoom PR #91 source.
Tests player status effects IN and OUT of proximity and after trap removal.
Only fresh temporary official 26.3 world, no production-world modification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / ".deps/qualified-outpost-source"
sys.path.insert(0, str(PINNED / "tools"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "fixtures/barsoom/flora"))
sys.path.insert(0, str(ROOT / "fixtures/barsoom/terrain"))

from gen_flora_263 import build as build_flora
from gen_dead_sea import build as build_terrain
from smoke_vanilla_runtime import download_verified_server
from probe_core_restoration_datapack_26_3 import send, stop_server, server_error_lines
from qualify_vanilla_world_artifact_activation_263 import Refused, launch, oracle, require
from qualify_barsoom_263 import NAME

PORT = 25593
POISON_PATH = 'active_effects[{id:"minecraft:poison"}]'


def bot_start_diagnostic(root: Path, stage: str, server_log: Path):
    """Capture original Mineflayer transport's actual failure instead of timing out blind."""
    folder = root / stage
    folder.mkdir()
    env = {**os.environ, "MC_PORT": str(PORT), "BARSOOM_PROBE_ROOT": str(folder)}
    bot_log = folder / "bot.log"
    with bot_log.open("w", encoding="utf-8") as stream:
        proc = subprocess.Popen(
            ["node", str(PINNED / "tools/probe_mineflayer_barsoom_263.js")],
            env=env, cwd=PINNED, stdout=stream, stderr=subprocess.STDOUT)
    try:
        end = time.monotonic() + 45
        while time.monotonic() < end:
            status_file = folder / "bot-status.json"
            status = json.loads(status_file.read_text()) if status_file.is_file() else {}
            if (folder / "bot.ready").is_file():
                require(status.get("minecraft_version") == "26.3" and
                        status.get("protocol_version") == 777 and
                        status.get("connected") is True, "BOT_VERSION_PROTOCOL_DRIFT")
                require(f"{NAME} joined the game" in server_log.read_text(errors="replace"),
                        "BOT_JOIN_UNPROVEN")
                return proc, folder
            if status.get("error") or proc.poll() is not None:
                raise Refused(
                    "BOT_START_REJECTED:status=" + json.dumps(status)[-1100:] +
                    ":node=" + bot_log.read_text(errors="replace")[-1100:] +
                    ":server=" + server_log.read_text(errors="replace")[-1400:])
            time.sleep(.25)
        raise Refused("BOT_START_NO_READY:status=" +
                      (folder / "bot-status.json").read_text()[-1000:]
                      if (folder / "bot-status.json").exists() else
                      "BOT_START_NO_STATUS:node=" + bot_log.read_text(errors="replace")[-900:] +
                      ":server=" + server_log.read_text(errors="replace")[-1300:])
    except Exception:
        if proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        raise


def run(evidence: dict, steps: list[str]) -> dict:
    require(PINNED.is_dir(), "PINNED_ACCEPTED_BARSOOM_TRANSPORT_MISSING")
    require(evidence["artifact_version_json"]["id"] == "26.3" and
            evidence["artifact_version_json"]["protocol_version"] == 777 and
            evidence["artifact_version_json"]["java_version"] == 25,
            "VERSION_PROTOCOL_JDK_DRIFT")
    with tempfile.TemporaryDirectory(prefix="barsoom-flora-player-") as td:
        base = Path(td)
        home = base / "server"
        home.mkdir()
        jar = home / "server.jar"
        download_verified_server(evidence, jar)
        require(hashlib.sha256(jar.read_bytes()).hexdigest() ==
                evidence["server_artifact"]["sha256"], "OFFICIAL_SERVER_SHA256_DRIFT")
        packs = home / "world/datapacks"
        packs.mkdir(parents=True)
        f = build_flora(packs / "flora.zip")
        build_terrain(packs / "terrain.zip")
        (home / "eula.txt").write_text("eula=true\n", encoding="utf-8")
        (home / "server.properties").write_text(
            "server-ip=127.0.0.1\nserver-port=25593\nonline-mode=false\n"
            "white-list=false\nenforce-whitelist=false\n"
            "level-name=world\nlevel-type=barsoom:dead_sea\n"
            "initial-enabled-packs=vanilla,file/terrain.zip,file/flora.zip\n"
            "view-distance=3\nsimulation-distance=2\nmax-players=2\n"
            "spawn-protection=0\ngenerate-structures=false\n"
            "enable-rcon=false\nenable-query=false\nlevel-seed=1811001\n"
            "sync-chunk-writes=true\ndifficulty=peaceful\n"
            "motd=Barsoom jawbloom actor acceptance RDTE\n", encoding="utf-8")
        handles = []
        bot = None
        proc = None
        try:
            proc, log = launch(home, jar, evidence, "flora-player", handles)
            require(not server_error_lines(log), "SERVER_LOAD_ERRORS")
            steps.append("official_26_3_server_ready")
            send(proc, "forceload add 0 0")
            send(proc, "forceload add 16 0")
            send(proc, "execute positioned 0 160 0 run function barsoom_flora:demo")
            oracle(proc, log,
                   "execute positioned 20 160 0 if entity @e[type=minecraft:marker,tag=barsoom_flora.trap,distance=..2]",
                   "FLORA_PLAYER_TRAP_PRESENT")
            steps.append("jawbloom_garden_and_trap_initialized")
            bot, folder = bot_start_diagnostic(base, "flora-bot", log)
            steps.append("real_protocol_777_player_joined")
            send(proc, f"tp {NAME} 0.5 160 0.5")
            send(proc, f"effect clear {NAME} minecraft:poison")
            time.sleep(2.5)
            oracle(proc, log,
                   f"execute unless data entity {NAME} {POISON_PATH}",
                   "FLORA_OUTSIDE_POISON_ABSENT")
            steps.append("outside_radius_no_poison")
            send(proc, f"tp {NAME} 20.5 160 0.5")
            oracle(proc, log,
                   f"execute if data entity {NAME} {POISON_PATH}",
                   "FLORA_INSIDE_POISON_PRESENT")
            steps.append("inside_radius_actual_player_poison")
            send(proc, f"tp {NAME} 0.5 160 0.5")
            send(proc, f"effect clear {NAME} minecraft:poison")
            time.sleep(3.0)
            oracle(proc, log,
                   f"execute unless data entity {NAME} {POISON_PATH}",
                   "FLORA_OUTSIDE_AFTER_ESCAPE_NO_POISON")
            steps.append("outside_radius_after_escape_no_poison")
            send(proc, "kill @e[type=minecraft:marker,tag=barsoom_flora.trap]")
            oracle(proc, log,
                   "execute positioned 20 160 0 unless entity @e[type=minecraft:marker,tag=barsoom_flora.trap,distance=..2]",
                   "FLORA_TRAP_REMOVED")
            send(proc, f"tp {NAME} 20.5 160 0.5")
            send(proc, f"effect clear {NAME} minecraft:poison")
            time.sleep(3.0)
            oracle(proc, log,
                   f"execute unless data entity {NAME} {POISON_PATH}",
                   "FLORA_TRAP_REMOVAL_NO_POISON")
            steps.append("trap_removal_prevents_poison")
            require(not server_error_lines(log), "SERVER_RUNTIME_ERRORS")
            require(stop_server(proc) == 0, "GRACEFUL_STOP_FAILED")
            proc = None
            steps.append("graceful_save_stop")
        finally:
            if bot is not None and bot.poll() is None:
                bot.terminate()
                try:
                    bot.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    bot.kill()
                    bot.wait(timeout=6)
            if proc is not None and proc.poll() is None:
                try:
                    stop_server(proc)
                except Exception:
                    proc.kill()
                    proc.wait(timeout=10)
            for _, stream in handles:
                stream.close()
    return {"schema": "supracraft.barsoom.flora-player/1",
            "result": "PASS", "first_failure": None, "steps": steps,
            "minecraft": "26.3", "protocol": 777,
            "flora_sha256": f["sha256"],
            "player_poison_verified": True,
            "stock_client_visual": "NOT_RUN",
            "production_truenas": "HOLD"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    steps: list[str] = []
    receipt = {"schema": "supracraft.barsoom.flora-player/1",
               "result": "FAIL", "steps": steps}
    try:
        receipt = run(json.loads(args.evidence.read_text()), steps)
    except Exception as exc:
        receipt["first_failure"] = type(exc).__name__ + ": " + str(exc)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
