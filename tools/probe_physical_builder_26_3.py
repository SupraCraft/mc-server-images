#!/usr/bin/env python3
"""Exact Java 26.3 physical-builder realization RDTE.

A real exact-version client withdraws the BOM from the registered depot and
physically realizes the two stock-watering architecture components block by
block. The atomic construction actuator is deliberately not invoked.

The resulting architecture must activate the same structure capability and
semantic effect as the previously qualified atomic path.
"""

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
from probe_blueprint_depot_26_3 import capability_eval_commands, xyz

PORT = 25578


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
            raise RuntimeError(f"builder exited before {path.name}: {process.returncode}; {out!r}")
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {path.name}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--projection", type=Path, required=True)
    ap.add_argument("--work-site", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    projection = json.loads(args.projection.read_text("utf-8"))
    work_site = json.loads(args.work_site.read_text("utf-8"))

    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("probe requires exact Minecraft Java 26.3")
    protocol = int(info["protocol_version"])

    if projection.get("world_scan") is not False:
        raise RuntimeError("physical-builder RDTE forbids world scanning")
    if projection.get("atomic_construction_actuator_used") is not False:
        raise RuntimeError("physical-builder rep must not use the atomic actuator")

    with tempfile.TemporaryDirectory(prefix="physical-builder-26.3-") as td:
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
                "motd=SupraCraft physical builder RDTE",
                "",
            ]),
            "utf-8",
        )

        log_path = root / "server.log"
        ready = root / "builder.ready"
        go = root / "builder.go"
        result_path = root / "builder.result.json"

        with log_path.open("w+", encoding="utf-8") as log:
            server = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx1536M", "-jar", str(server_jar), "nogui"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            builder = None
            try:
                status = wait_server(server, protocol)
                send(server, "forceload add -16 -16 16 16")
                send(server, "scoreboard objectives add supracraft_cap dummy")
                send(server, "scoreboard objectives add supracraft_metric dummy")

                # Walkable bounded site with explicit support blocks beneath the
                # two target watering components.
                send(server, "fill -10 69 -10 10 69 6 minecraft:stone")
                depot = xyz(work_site["depot"]["at"])
                send(server, f"setblock {depot} {work_site['depot']['block']}")
                send(server, "setblock -5 70 -5 minecraft:stone_bricks")
                send(server, "setblock 5 70 -5 minecraft:stone_bricks")
                for row in work_site["architecture_delta"]:
                    send(server, f"setblock {xyz(row['at'])} minecraft:air")

                # Pre-place the complete BOM in the registered depot. This rep
                # isolates realization path; player/hauler delivery was already
                # qualified independently.
                send(server, f"item replace block {depot} container.0 with minecraft:cauldron 2")
                send(server, f"item replace block {depot} container.1 with minecraft:water_bucket")
                send(server, f"item replace block {depot} container.2 with minecraft:water_bucket")
                time.sleep(0.5)

                env = dict(os.environ)
                env.update({
                    "MC_HOST": "127.0.0.1",
                    "MC_PORT": str(PORT),
                    "MC_USER": projection["builder"]["username"],
                    "BUILDER_READY_FILE": str(ready),
                    "BUILDER_GO_FILE": str(go),
                    "BUILDER_RESULT_FILE": str(result_path),
                })
                builder = subprocess.Popen(
                    ["node", str(Path(__file__).with_name("probe_physical_builder.js"))],
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

                wait_file(ready, builder)
                send(server, f"tp {projection['builder']['username']} 0.5 70 3.5")
                time.sleep(0.5)
                go.write_text("go\n", "utf-8")

                try:
                    builder_stdout, _ = builder.communicate(timeout=70)
                except subprocess.TimeoutExpired:
                    builder.kill()
                    builder_stdout, _ = builder.communicate(timeout=10)
                    raise RuntimeError("physical builder timed out: " + builder_stdout[-7000:])

                if not result_path.exists():
                    raise RuntimeError("physical builder produced no result: " + builder_stdout[-7000:])
                builder_result = json.loads(result_path.read_text("utf-8"))
                if builder.returncode != 0 or builder_result.get("result") != "built":
                    raise RuntimeError(
                        "physical builder failed: "
                        + json.dumps(builder_result, sort_keys=True)
                        + " stdout="
                        + builder_stdout[-7000:]
                    )

                a0, a1 = work_site["architecture_delta"]
                marker(
                    server,
                    f"execute if block {xyz(a0['at'])} {a0['block']} "
                    "run say SUPRACRAFT_PHYSICAL_BUILDER_FIRST_COMPONENT",
                )
                marker(
                    server,
                    f"execute if block {xyz(a1['at'])} {a1['block']} "
                    "run say SUPRACRAFT_PHYSICAL_BUILDER_SECOND_COMPONENT",
                )

                # No run_builder() call occurs anywhere in this rep.
                for command in capability_eval_commands(work_site):
                    send(server, command)
                marker(
                    server,
                    "execute if score stock_watering supracraft_cap matches 1 "
                    "if score husbandry_capacity supracraft_metric matches 12 "
                    "run say SUPRACRAFT_PHYSICAL_BUILDER_CAPABILITY_ACTIVATED",
                )
                marker(server, "say SUPRACRAFT_ATOMIC_ACTUATOR_NOT_USED")

                send(server, "save-all flush")
                time.sleep(0.3)
                send(server, "stop")
                exit_code = server.wait(timeout=45)
            finally:
                if builder is not None and builder.poll() is None:
                    builder.kill()
                    builder.wait(timeout=10)
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
            "first_component": "SUPRACRAFT_PHYSICAL_BUILDER_FIRST_COMPONENT",
            "second_component": "SUPRACRAFT_PHYSICAL_BUILDER_SECOND_COMPONENT",
            "capability_activated": "SUPRACRAFT_PHYSICAL_BUILDER_CAPABILITY_ACTIVATED",
            "atomic_actuator_not_used": "SUPRACRAFT_ATOMIC_ACTUATOR_NOT_USED",
        }
        observed = {key: token in server_log for key, token in markers.items()}
        errors = [
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        passed = exit_code == 0 and all(observed.values()) and not errors

        result = {
            "schema": "supracraft.physical-builder-runtime-rdte/v0.1",
            "minecraft": {"edition": "java", "version": "26.3"},
            "status_protocol": int(status.get("version", {}).get("protocol", -1)),
            "official_server_verified": True,
            "world_scan": False,
            "realization_path": "physical_builder_client",
            "atomic_construction_actuator_used": False,
            "builder": builder_result,
            "oracles": observed,
            "semantic_effect": projection["expected_semantic_effect"],
            "semantic_convergence_target": {
                "atomic_path_run": 37341673072,
                "metric": "husbandry_capacity",
                "active_value": 12,
            },
            "server_error_count": len(errors),
            "result": "PASS" if passed else "FAIL",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))

        if not passed:
            raise RuntimeError(
                f"physical-builder RDTE failed: oracles={observed}; "
                f"errors={errors[-10:]}; log_tail={server_log[-8000:].replace(chr(10), ' | ')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
