#!/usr/bin/env python3
"""Exact-Java-26.3 runtime oracle for one modular structure capability.

The official server is semantic authority. This probe proves:
- capability inactive before its physical architecture exists;
- partial construction does not activate it;
- completing the bounded architecture component activates one measurable metric;
- damaging the component revokes the capability again.

No world scan is used: only the registered work-site coordinates are checked.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from smoke_vanilla_runtime import download_verified_server, status_query

PORT = 25572


def send(process: subprocess.Popen[str], command: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(command + "\n")
    process.stdin.flush()


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


def abs_pos(anchor: list[int], rel: list[int]) -> tuple[int, int, int]:
    if len(anchor) != 3 or len(rel) != 3:
        raise ValueError("anchor and relative positions must each have three entries")
    return tuple(int(anchor[i]) + int(rel[i]) for i in range(3))


def evaluate_commands(projection: dict[str, Any]) -> list[str]:
    predicates = projection["completion_predicates"]
    if not predicates:
        raise ValueError("capability projection needs completion predicates")
    conditions = []
    for row in predicates:
        if row.get("kind") != "block":
            raise ValueError(f"unsupported predicate kind: {row.get('kind')!r}")
        x, y, z = abs_pos(projection["anchor"], row["at"])
        conditions.append(f"if block {x} {y} {z} {row['block']}")
    gate = " ".join(conditions)
    return [
        "scoreboard players set stock_watering supracraft_cap 0",
        f"scoreboard players set husbandry_capacity supracraft_metric {int(projection['semantic_effect']['base_value'])}",
        f"execute {gate} run scoreboard players set stock_watering supracraft_cap 1",
        (
            "execute if score stock_watering supracraft_cap matches 1 run "
            f"scoreboard players set husbandry_capacity supracraft_metric "
            f"{int(projection['semantic_effect']['active_value'])}"
        ),
    ]


def marker(process: subprocess.Popen[str], command: str) -> None:
    send(process, command)
    time.sleep(0.15)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--projection", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    projection = json.loads(args.projection.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("probe requires exact Minecraft Java 26.3 identity")
    protocol = int(info["protocol_version"])

    if projection.get("capability_id") != "stock_watering":
        raise RuntimeError("bounded RDTE only admits stock_watering")
    if len(projection.get("architecture_delta", [])) != 2:
        raise RuntimeError("bounded RDTE expects two architecture delta operations")

    with tempfile.TemporaryDirectory(prefix="structure-capability-26.3-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)

        (root / "eula.txt").write_text("eula=true\n", "utf-8")
        (root / "server.properties").write_text(
            "\n".join([
                "online-mode=false",
                f"server-port={PORT}",
                "view-distance=2",
                "simulation-distance=2",
                "spawn-protection=0",
                "max-players=1",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-seed=4242424242",
                "level-type=minecraft:flat",
                'generator-settings={"biome":"minecraft:plains","features":false,"lakes":false,"layers":[{"block":"minecraft:bedrock","height":1},{"block":"minecraft:dirt","height":2},{"block":"minecraft:grass_block","height":1}],"structure_overrides":[]}',
                "motd=SupraCraft structure capability RDTE",
                "",
            ]),
            "utf-8",
        )

        log_path = root / "server.log"
        with log_path.open("w+", encoding="utf-8") as log:
            process = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx1536M", "-jar", str(server_jar), "nogui"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                status = wait_server(process, protocol)

                send(process, "gamerule doMobSpawning false")
                send(process, "scoreboard objectives add supracraft_cap dummy")
                send(process, "scoreboard objectives add supracraft_metric dummy")

                # Register a bounded work site and explicitly clear only the two
                # component positions. There is no global discovery scan.
                positions = []
                for op in projection["architecture_delta"]:
                    if op.get("kind") != "setblock":
                        raise RuntimeError("unsupported architecture delta operation")
                    positions.append(abs_pos(projection["anchor"], op["at"]))
                for x, y, z in positions:
                    send(process, f"setblock {x} {y} {z} minecraft:air")

                eval_cmds = evaluate_commands(projection)

                # Base state: absent component means base capacity.
                for command in eval_cmds:
                    send(process, command)
                marker(
                    process,
                    "execute if score stock_watering supracraft_cap matches 0 "
                    "if score husbandry_capacity supracraft_metric matches 8 "
                    "run say SUPRACRAFT_BASE_INACTIVE",
                )

                # Partial construction: first trough alone must not activate.
                first = projection["architecture_delta"][0]
                x, y, z = abs_pos(projection["anchor"], first["at"])
                send(process, f"setblock {x} {y} {z} {first['block']}")
                marker(
                    process,
                    f"execute if block {x} {y} {z} {first['block']} "
                    "run say SUPRACRAFT_TROUGH_ONE_PRESENT",
                )
                for command in eval_cmds:
                    send(process, command)
                marker(
                    process,
                    "execute if score stock_watering supracraft_cap matches 0 "
                    "if score husbandry_capacity supracraft_metric matches 8 "
                    "run say SUPRACRAFT_PARTIAL_REJECTED",
                )

                # Complete the component and prove the measurable capability.
                second = projection["architecture_delta"][1]
                x2, y2, z2 = abs_pos(projection["anchor"], second["at"])
                send(process, f"setblock {x2} {y2} {z2} {second['block']}")
                marker(
                    process,
                    f"execute if block {x} {y} {z} {first['block']} "
                    "run say SUPRACRAFT_TROUGH_ONE_STILL_PRESENT",
                )
                marker(
                    process,
                    f"execute if block {x2} {y2} {z2} {second['block']} "
                    "run say SUPRACRAFT_TROUGH_TWO_PRESENT",
                )
                marker(
                    process,
                    f"execute if block {x} {y} {z} {first['block']} "
                    f"if block {x2} {y2} {z2} {second['block']} "
                    "run say SUPRACRAFT_BOTH_TROUGHS_PRESENT",
                )
                for command in eval_cmds:
                    send(process, command)
                marker(
                    process,
                    "execute if score stock_watering supracraft_cap matches 1 "
                    "if score husbandry_capacity supracraft_metric matches 12 "
                    "run say SUPRACRAFT_CAPABILITY_ACTIVATED",
                )

                # Damage one required component and revalidate the bounded site.
                send(process, f"setblock {x2} {y2} {z2} minecraft:air")
                for command in eval_cmds:
                    send(process, command)
                marker(
                    process,
                    "execute if score stock_watering supracraft_cap matches 0 "
                    "if score husbandry_capacity supracraft_metric matches 8 "
                    "run say SUPRACRAFT_DAMAGE_REVOKED",
                )

                send(process, "save-all flush")
                time.sleep(0.5)
                send(process, "stop")
                exit_code = process.wait(timeout=45)
            finally:
                if process.poll() is None:
                    try:
                        send(process, "stop")
                        process.wait(timeout=20)
                    except Exception:
                        process.kill()
                        process.wait(timeout=10)

            log.flush()
            log.seek(0)
            server_log = log.read()

        if exit_code != 0:
            raise RuntimeError(f"server exit code {exit_code}")

        required_markers = {
            "base_inactive": "SUPRACRAFT_BASE_INACTIVE",
            "partial_rejected": "SUPRACRAFT_PARTIAL_REJECTED",
            "complete_activated": "SUPRACRAFT_CAPABILITY_ACTIVATED",
            "damage_revoked": "SUPRACRAFT_DAMAGE_REVOKED",
        }
        observed = {key: value in server_log for key, value in required_markers.items()}
        diagnostics = {
            "trough_one_present": "SUPRACRAFT_TROUGH_ONE_PRESENT" in server_log,
            "trough_one_still_present": "SUPRACRAFT_TROUGH_ONE_STILL_PRESENT" in server_log,
            "trough_two_present": "SUPRACRAFT_TROUGH_TWO_PRESENT" in server_log,
            "both_troughs_present": "SUPRACRAFT_BOTH_TROUGHS_PRESENT" in server_log,
        }

        errors = [
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        passed = all(observed.values()) and not errors
        result = {
            "schema": "supracraft.structure-capability-runtime-rdte/v0.2",
            "minecraft": {"edition": "java", "version": "26.3"},
            "status_protocol": int(status.get("version", {}).get("protocol", -1)),
            "official_server_verified": True,
            "work_site_policy": "explicit_bounded_projection_only",
            "structure_id": projection["structure_id"],
            "architecture_blueprint_id": projection["architecture_blueprint_id"],
            "capability_id": projection["capability_id"],
            "semantic_effect": projection["semantic_effect"],
            "oracles": observed,
            "diagnostics": diagnostics,
            "server_error_count": len(errors),
            "result": "PASS" if passed else "FAIL",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))

        if errors:
            raise RuntimeError("server emitted ERROR lines: " + " | ".join(errors[-20:]))
        if not all(observed.values()):
            tail = server_log[-8000:].replace("\n", " | ")
            raise RuntimeError(
                f"missing capability oracle markers: {observed}; "
                f"diagnostics={diagnostics}; log_tail={tail}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
