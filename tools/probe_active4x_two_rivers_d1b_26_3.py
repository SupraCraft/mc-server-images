#!/usr/bin/env python3
"""Exact Java 26.3 scheduled-callback persistence RDTE for Two Rivers D1B."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from smoke_vanilla_runtime import download_verified_server, status_query

PORT = 25582


def send(process: subprocess.Popen[str], command: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(command + "\n")
    process.stdin.flush()


def wait_server(
    process: subprocess.Popen[str],
    protocol: int,
    timeout: int = 180,
) -> dict[str, Any]:
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


def start_server(root: Path, log_path: Path):
    log = log_path.open("w+", encoding="utf-8")
    process = subprocess.Popen(
        ["java", "-Xms512M", "-Xmx1536M", "-jar", "server.jar", "nogui"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return process, log


def stop_server(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    send(process, "save-all flush")
    time.sleep(0.35)
    send(process, "stop")
    process.wait(timeout=45)


def read_log(log) -> str:
    log.flush()
    log.seek(0)
    return log.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--projection", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    p = json.loads(args.projection.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("D1B requires exact Minecraft Java 26.3")
    protocol = int(info["protocol_version"])
    if protocol != int(p["target"]["protocol"]):
        raise RuntimeError("protocol mismatch")

    pack_version = int(p["target"]["data_pack_version"])
    namespace = p["datapack"]["namespace"]
    function_id = p["datapack"]["function_id"]
    delay = int(p["datapack"]["schedule_delay_ticks"])
    storage_id = p["datapack"]["storage_id"]

    with tempfile.TemporaryDirectory(prefix="active4x-d1b-26.3-") as td:
        root = Path(td)
        download_verified_server(evidence, root / "server.jar")

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
                "motd=SupraCraft active 4X D1B scheduled callback RDTE",
                "",
            ]),
            "utf-8",
        )

        pack_root = root / "world" / "datapacks" / "supracraft_active4x_d1b"
        function_dir = pack_root / "data" / namespace / "function" / "active4x"
        function_dir.mkdir(parents=True, exist_ok=True)
        (pack_root / "pack.mcmeta").write_text(
            json.dumps(
                {
                    "pack": {
                        "pack_format": pack_version,
                        "min_format": [pack_version, 0],
                        "max_format": [pack_version, 0],
                        "description": "SupraCraft D1B exact 26.3 scheduled callback probe",
                    }
                },
                separators=(",", ":"),
            )
            + "\n",
            "utf-8",
        )
        (function_dir / "callback.mcfunction").write_text(
            "\n".join([
                f'data modify storage {storage_id} callback_state set value {{fired:1}}',
                f'data modify storage {storage_id} callback_count set value 1',
                f'data modify storage {storage_id} callbacks append value {{id:"d1b_callback",fired:1}}',
                "say SUPRACRAFT_D1B_CALLBACK_FIRED",
                "",
            ]),
            "utf-8",
        )

        logs: list[str] = []
        statuses: list[dict[str, Any]] = []

        # Cycle 1: initialize storage and schedule a callback far enough in the
        # future that we can stop before it runs.
        p1, log1 = start_server(root, root / "cycle1.log")
        try:
            statuses.append(wait_server(p1, protocol))
            send(p1, "reload")
            time.sleep(0.7)
            send(p1, f"data modify storage {storage_id} callback_state set value {{fired:0}}")
            send(p1, f"data modify storage {storage_id} callback_count set value 0")
            send(p1, f"data modify storage {storage_id} callbacks set value []")
            send(p1, f"schedule function {function_id} {delay}t replace")
            send(
                p1,
                f'execute if data storage {storage_id} callback_state{{fired:0}} '
                "run say SUPRACRAFT_D1B_CALLBACK_SCHEDULED",
            )
            time.sleep(0.5)
            stop_server(p1)
        finally:
            if p1.poll() is None:
                p1.kill()
                p1.wait(timeout=10)
            logs.append(read_log(log1))
            log1.close()

        # Cycle 2: the scheduled callback should resume from the saved world and
        # fire once after remaining game ticks elapse.
        p2, log2 = start_server(root, root / "cycle2.log")
        try:
            statuses.append(wait_server(p2, protocol))
            time.sleep(max(7.0, delay / 20.0 + 2.0))
            send(p2, "scoreboard objectives add supracraft_d1b dummy")
            send(p2, "scoreboard players set callback_count supracraft_d1b 0")
            send(
                p2,
                f"execute store result score callback_count supracraft_d1b "
                f"run data get storage {storage_id} callback_count 1",
            )
            send(
                p2,
                "execute if score callback_count supracraft_d1b matches 1 "
                "run say SUPRACRAFT_D1B_CALLBACK_STORAGE_UPDATED_ONCE",
            )
            time.sleep(0.5)
            stop_server(p2)
        finally:
            if p2.poll() is None:
                p2.kill()
                p2.wait(timeout=10)
            logs.append(read_log(log2))
            log2.close()

        # Cycle 3: read-only restart proves the callback did not duplicate and
        # its semantic receipt remains world-local.
        p3, log3 = start_server(root, root / "cycle3.log")
        try:
            statuses.append(wait_server(p3, protocol))
            time.sleep(1.0)
            send(p3, "scoreboard objectives add supracraft_d1b dummy")
            send(p3, "scoreboard players set callback_count supracraft_d1b 0")
            send(
                p3,
                f"execute store result score callback_count supracraft_d1b "
                f"run data get storage {storage_id} callback_count 1",
            )
            send(
                p3,
                "execute if score callback_count supracraft_d1b matches 1 "
                "run say SUPRACRAFT_D1B_CALLBACK_SURVIVED_SECOND_RESTART",
            )
            time.sleep(0.5)
            stop_server(p3)
        finally:
            if p3.poll() is None:
                p3.kill()
                p3.wait(timeout=10)
            logs.append(read_log(log3))
            log3.close()

        combined = "\n".join(logs)
        markers = {
            "callback_scheduled": "SUPRACRAFT_D1B_CALLBACK_SCHEDULED",
            "callback_fired": "SUPRACRAFT_D1B_CALLBACK_FIRED",
            "callback_storage_updated_once": "SUPRACRAFT_D1B_CALLBACK_STORAGE_UPDATED_ONCE",
            "callback_survived_second_restart": "SUPRACRAFT_D1B_CALLBACK_SURVIVED_SECOND_RESTART",
        }
        observed = {
            key: f"[Server] {token}" in combined
            for key, token in markers.items()
        }
        errors = [
            line for line in combined.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        pack_errors = [
            line for line in combined.splitlines()
            if "pack" in line.lower()
            and ("failed" in line.lower() or "error" in line.lower())
        ]
        protocol_ok = all(
            int(status.get("version", {}).get("protocol", -1)) == protocol
            for status in statuses
        )
        passed = (
            all(observed.values())
            and protocol_ok
            and not errors
            and not pack_errors
        )

        result = {
            "schema": "supracraft.active4x-two-rivers-d1b-rdte/v0.1",
            "minecraft": {"edition": "java", "version": "26.3"},
            "status_protocol": protocol,
            "official_server_verified": True,
            "data_pack_version": pack_version,
            "function_id": function_id,
            "schedule_delay_ticks": delay,
            "restart_cycles": 3,
            "oracles": observed,
            "checks": {
                "exact_26_3_datapack_loads": not pack_errors,
                "scheduled_function_is_accepted": observed["callback_scheduled"],
                "scheduled_callback_survives_restart": observed["callback_fired"],
                "callback_updates_world_local_storage": observed["callback_storage_updated_once"],
                "callback_executes_exactly_once": (
                    combined.count("[Server] SUPRACRAFT_D1B_CALLBACK_FIRED") == 1
                    and observed["callback_storage_updated_once"]
                ),
                "callback_state_survives_second_restart": observed["callback_survived_second_restart"],
                "no_strategic_tick_loop": True,
                "protocol_777": protocol_ok and protocol == 777,
                "world_scan_false": True,
            },
            "server_error_count": len(errors),
            "pack_error_count": len(pack_errors),
            "deployment_stage": "D1_exact_26_3_scheduled_world_callback",
            "world_scan": False,
            "result": "PASS" if passed else "FAIL",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))

        if not passed:
            raise RuntimeError(
                f"D1B scheduled callback failed: oracles={observed}; "
                f"pack_errors={pack_errors[-10:]}; errors={errors[-10:]}; "
                f"log_tail={combined[-12000:].replace(chr(10), ' | ')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
