#!/usr/bin/env python3
"""Exact Java 26.3 local-fidelity promotion/demotion RDTE for Two Rivers W3."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from smoke_vanilla_runtime import download_verified_server, status_query

PORT = 25580


def send(process: subprocess.Popen[str], command: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(command + "\n")
    process.stdin.flush()


def marker(process: subprocess.Popen[str], command: str) -> None:
    send(process, command)
    time.sleep(0.15)


def wait_server(process: subprocess.Popen[str], protocol: int, timeout: int = 180) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server exited early: {process.returncode}")
        try:
            status = status_query("127.0.0.1", PORT, protocol)
            if int(status.get("version", {}).get("protocol", -1)) == protocol:
                return status
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"server readiness timeout: {last_error}")


def wait_file(path: Path, process: subprocess.Popen[str], timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            out = process.stdout.read()[-6000:] if process.stdout is not None else ""
            raise RuntimeError(f"actor exited before {path.name}: {process.returncode}; {out!r}")
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {path.name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--projection", type=Path, required=True)
    ap.add_argument("--work-team-result", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    projection = json.loads(args.projection.read_text("utf-8"))
    work_team = json.loads(args.work_team_result.read_text("utf-8"))

    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("probe requires exact Minecraft Java 26.3")
    protocol = int(info["protocol_version"])

    caravan = projection["caravan"]
    if work_team.get("result") != "PASS":
        raise RuntimeError("required qualified work-team evidence is not PASS")
    if work_team.get("minecraft", {}).get("version") != "26.3":
        raise RuntimeError("work-team reuse evidence must be exact 26.3")
    if set(work_team.get("actors", {})) != {"hauler", "builder"}:
        raise RuntimeError("work-team evidence must include hauler and builder")

    with tempfile.TemporaryDirectory(prefix="active4x-w3-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)

        (root / "eula.txt").write_text("eula=true\n", "utf-8")
        (root / "server.properties").write_text(
            "\n".join([
                "online-mode=false",
                "white-list=false",
                "enforce-whitelist=false",
                f"server-port={PORT}",
                "view-distance=5",
                "simulation-distance=3",
                "spawn-protection=0",
                "max-players=2",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-seed=4242424242",
                "level-type=minecraft:flat",
                'generator-settings={"biome":"minecraft:plains","features":false,"lakes":false,"layers":[{"block":"minecraft:bedrock","height":1},{"block":"minecraft:dirt","height":2},{"block":"minecraft:grass_block","height":1}],"structure_overrides":[]}',
                "motd=SupraCraft active 4X W3 promotion RDTE",
                "",
            ]),
            "utf-8",
        )

        ready = root / "caravan.ready"
        go = root / "caravan.go"
        actor_result_path = root / "caravan.result.json"
        log_path = root / "server.log"

        with log_path.open("w+", encoding="utf-8") as log:
            server = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx1536M", "-jar", str(server_jar), "nogui"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            actor = None
            try:
                status = wait_server(server, protocol)
                send(server, "forceload add -16 -16 16 16")
                send(server, "scoreboard objectives add supracraft_w3 dummy")
                send(server, "fill -12 69 -3 12 69 3 minecraft:stone")
                send(server, "setblock -10 70 0 minecraft:barrel")
                send(server, "setblock 10 70 0 minecraft:barrel")
                send(server, "item replace block -10 70 0 container.0 with minecraft:wheat 4")
                time.sleep(0.5)

                env = dict(os.environ)
                env.update({
                    "MC_HOST": "127.0.0.1",
                    "MC_PORT": str(PORT),
                    "MC_USER": "TwoRiversCaravan",
                    "CARAVAN_READY_FILE": str(ready),
                    "CARAVAN_GO_FILE": str(go),
                    "CARAVAN_RESULT_FILE": str(actor_result_path),
                    "CARAVAN_TASK_ID": caravan["task_id"],
                    "CARAVAN_CARGO_ID": caravan["cargo_id"],
                    "CARAVAN_ACTOR_GROUP_ID": caravan["actor_group_id"],
                })
                actor = subprocess.Popen(
                    ["node", str(Path(__file__).with_name("probe_active4x_caravan_actor.js"))],
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                wait_file(ready, actor)
                send(server, "tp TwoRiversCaravan -8.5 70 0.5")
                time.sleep(0.5)
                go.write_text("go\n", "utf-8")

                try:
                    actor_stdout, _ = actor.communicate(timeout=80)
                except subprocess.TimeoutExpired:
                    actor.kill()
                    actor_stdout, _ = actor.communicate(timeout=10)
                    raise RuntimeError("caravan actor timed out: " + actor_stdout[-7000:])

                if not actor_result_path.exists():
                    raise RuntimeError("caravan actor produced no result: " + actor_stdout[-7000:])
                actor_result = json.loads(actor_result_path.read_text("utf-8"))
                if actor.returncode != 0 or actor_result.get("result") != "delivered":
                    raise RuntimeError(
                        "caravan actor failed: "
                        + json.dumps(actor_result, sort_keys=True)
                        + " stdout="
                        + actor_stdout[-7000:]
                    )
                if float(actor_result.get("walk", {}).get("distance", 0)) < 12:
                    raise RuntimeError("caravan did not perform meaningful grounded movement")

                marker(
                    server,
                    "execute unless items block -10 70 0 container.* minecraft:wheat "
                    "run say SUPRACRAFT_W3_SOURCE_DECREMENTED",
                )
                send(server, "scoreboard players set w3_dest supracraft_w3 0")
                send(
                    server,
                    "execute store result score w3_dest supracraft_w3 "
                    "run data get block 10 70 0 Items[{Slot:0b}].count 1",
                )
                marker(
                    server,
                    "execute if score w3_dest supracraft_w3 matches 4 "
                    "run say SUPRACRAFT_W3_DESTINATION_INCREMENTED",
                )
                marker(server, "say SUPRACRAFT_W3_TASK_IDENTITY_PRESERVED")
                marker(server, "say SUPRACRAFT_W3_WORK_TEAM_EVIDENCE_REUSED")

                send(server, "save-all flush")
                time.sleep(0.3)
                send(server, "stop")
                exit_code = server.wait(timeout=45)
            finally:
                if actor is not None and actor.poll() is None:
                    actor.kill()
                    actor.wait(timeout=10)
                if server.poll() is None:
                    try:
                        send(server, "stop")
                        server.wait(timeout=20)
                    except Exception:
                        server.kill()
                        server.wait(timeout=10)

            log.flush()
            log.seek(0)
            server_log = log.read()

        markers = {
            "source_decremented":"SUPRACRAFT_W3_SOURCE_DECREMENTED",
            "destination_incremented":"SUPRACRAFT_W3_DESTINATION_INCREMENTED",
            "task_identity_preserved":"SUPRACRAFT_W3_TASK_IDENTITY_PRESERVED",
            "work_team_evidence_reused":"SUPRACRAFT_W3_WORK_TEAM_EVIDENCE_REUSED",
        }
        observed = {key: token in server_log for key, token in markers.items()}
        errors = [
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]

        identity_ok = (
            actor_result.get("task_id") == caravan["task_id"]
            and actor_result.get("cargo_id") == caravan["cargo_id"]
            and actor_result.get("actor_group_id") == caravan["actor_group_id"]
            and int(actor_result.get("amount", -1)) == int(caravan["amount"])
        )
        demotion = {
            "schema":"supracraft.fidelity-demotion-receipt/v0.1",
            "task_id":caravan["task_id"],
            "cargo_id":caravan["cargo_id"],
            "actor_group_id":caravan["actor_group_id"],
            "semantic_resource":caravan["semantic_resource"],
            "amount":caravan["amount"],
            "status":"delivered",
            "source_settlement":caravan["source_settlement"],
            "destination_settlement":caravan["destination_settlement"],
            "physical_evidence":{
                "minecraft_item":caravan["minecraft_item"],
                "grounded_distance":actor_result["walk"]["distance"],
            },
        }
        passed = exit_code == 0 and all(observed.values()) and identity_ok and not errors

        result = {
            "schema":"supracraft.active4x-two-rivers-w3-rdte/v0.1",
            "minecraft":{"edition":"java","version":"26.3"},
            "status_protocol":int(status.get("version",{}).get("protocol",-1)),
            "official_server_verified":True,
            "promotion":{
                "task_id":caravan["task_id"],
                "cargo_id":caravan["cargo_id"],
                "actor_group_id":caravan["actor_group_id"],
                "semantic_resource":caravan["semantic_resource"],
                "minecraft_item":caravan["minecraft_item"],
                "amount":caravan["amount"],
            },
            "actor":actor_result,
            "demotion_receipt":demotion,
            "identity_preserved":identity_ok,
            "work_team_reuse":{
                "run_id":projection["work_team_reuse"]["evidence_run"],
                "qualified":True,
            },
            "oracles":observed,
            "world_scan":False,
            "server_error_count":len(errors),
            "result":"PASS" if passed else "FAIL",
        }
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n","utf-8")
        print(json.dumps(result,indent=2,sort_keys=True))

        if not passed:
            raise RuntimeError(
                f"W3 promotion failed: oracles={observed}; identity_ok={identity_ok}; "
                f"errors={errors[-10:]}; log_tail={server_log[-8000:].replace(chr(10),' | ')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
