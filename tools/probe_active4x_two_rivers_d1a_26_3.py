#!/usr/bin/env python3
"""Exact Java 26.3 world-local persistence RDTE for Two Rivers D1A.

Qualifies vanilla command storage as a world-local persistence anchor across
save/stop/restart cycles. This does not move strategic simulation into commands;
W5 remains the semantic CAS/idempotence authority.
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

PORT = 25581


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


def start_server(root: Path, log_path: Path) -> tuple[subprocess.Popen[str], Any]:
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
    projection = json.loads(args.projection.read_text("utf-8"))
    info = evidence["artifact_version_json"]
    if info["id"] != "26.3":
        raise RuntimeError("D1A requires exact Minecraft Java 26.3")
    protocol = int(info["protocol_version"])
    if protocol != int(projection["target"]["protocol"]):
        raise RuntimeError("projection protocol does not match exact release identity")

    revisions = projection["storage"]["revisions"]
    first, second = revisions
    storage_id = projection["storage"]["id"]

    with tempfile.TemporaryDirectory(prefix="active4x-d1a-26.3-") as td:
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
                "motd=SupraCraft active 4X D1A world storage RDTE",
                "",
            ]),
            "utf-8",
        )

        logs: list[str] = []
        statuses: list[dict[str, Any]] = []

        # Cycle 1: create revision 1 and one journal entry.
        p1, log1 = start_server(root, root / "cycle1.log")
        try:
            statuses.append(wait_server(p1, protocol))
            send(
                p1,
                f'data modify storage {storage_id} state set value '
                f'{{revision:{int(first["revision"])},world_id:"{first["world_id"]}",'
                f'phase:"{first["phase"]}"}}',
            )
            send(p1, f"data modify storage {storage_id} journal set value []")
            send(
                p1,
                f'data modify storage {storage_id} journal append value '
                f'{{revision:{int(first["revision"])},'
                f'operation_id:"{first["operation_id"]}"}}',
            )
            send(
                p1,
                f'execute if data storage {storage_id} '
                f'state{{revision:{int(first["revision"])},world_id:"{first["world_id"]}",'
                f'phase:"{first["phase"]}"}} '
                f'if data storage {storage_id} '
                f'journal[0]{{revision:{int(first["revision"])},'
                f'operation_id:"{first["operation_id"]}"}} '
                f'unless data storage {storage_id} journal[1] '
                "run say SUPRACRAFT_D1A_REV1_WRITTEN",
            )
            time.sleep(0.5)
            stop_server(p1)
        finally:
            if p1.poll() is None:
                p1.kill()
                p1.wait(timeout=10)
            logs.append(read_log(log1))
            log1.close()

        # Cycle 2: prove revision 1 survived, then advance to revision 2.
        p2, log2 = start_server(root, root / "cycle2.log")
        try:
            statuses.append(wait_server(p2, protocol))
            send(
                p2,
                f'execute if data storage {storage_id} '
                f'state{{revision:{int(first["revision"])},world_id:"{first["world_id"]}",'
                f'phase:"{first["phase"]}"}} '
                f'if data storage {storage_id} '
                f'journal[0]{{revision:{int(first["revision"])},'
                f'operation_id:"{first["operation_id"]}"}} '
                "run say SUPRACRAFT_D1A_REV1_SURVIVED_RESTART",
            )
            send(
                p2,
                f'data modify storage {storage_id} state set value '
                f'{{revision:{int(second["revision"])},world_id:"{second["world_id"]}",'
                f'phase:"{second["phase"]}"}}',
            )
            send(
                p2,
                f'data modify storage {storage_id} journal append value '
                f'{{revision:{int(second["revision"])},'
                f'operation_id:"{second["operation_id"]}"}}',
            )
            send(
                p2,
                f'execute if data storage {storage_id} '
                f'state{{revision:{int(second["revision"])},world_id:"{second["world_id"]}",'
                f'phase:"{second["phase"]}"}} '
                f'if data storage {storage_id} '
                f'journal[0]{{revision:{int(first["revision"])},'
                f'operation_id:"{first["operation_id"]}"}} '
                f'if data storage {storage_id} '
                f'journal[1]{{revision:{int(second["revision"])},'
                f'operation_id:"{second["operation_id"]}"}} '
                f'unless data storage {storage_id} journal[2] '
                "run say SUPRACRAFT_D1A_REV2_WRITTEN",
            )
            time.sleep(0.5)
            stop_server(p2)
        finally:
            if p2.poll() is None:
                p2.kill()
                p2.wait(timeout=10)
            logs.append(read_log(log2))
            log2.close()

        # Cycle 3: read-only restart must preserve revision 2 and exactly two
        # journal entries. No append occurs in this cycle.
        p3, log3 = start_server(root, root / "cycle3.log")
        try:
            statuses.append(wait_server(p3, protocol))
            send(
                p3,
                f'execute if data storage {storage_id} '
                f'state{{revision:{int(second["revision"])},world_id:"{second["world_id"]}",'
                f'phase:"{second["phase"]}"}} '
                f'if data storage {storage_id} '
                f'journal[0]{{revision:{int(first["revision"])},'
                f'operation_id:"{first["operation_id"]}"}} '
                f'if data storage {storage_id} '
                f'journal[1]{{revision:{int(second["revision"])},'
                f'operation_id:"{second["operation_id"]}"}} '
                f'unless data storage {storage_id} journal[2] '
                "run say SUPRACRAFT_D1A_REV2_SURVIVED_READ_ONLY_RESTART",
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
            "revision_1_written": "SUPRACRAFT_D1A_REV1_WRITTEN",
            "revision_1_survived_restart": "SUPRACRAFT_D1A_REV1_SURVIVED_RESTART",
            "revision_2_written": "SUPRACRAFT_D1A_REV2_WRITTEN",
            "revision_2_survived_read_only_restart": (
                "SUPRACRAFT_D1A_REV2_SURVIVED_READ_ONLY_RESTART"
            ),
        }
        observed = {key: token in combined for key, token in markers.items()}
        errors = [
            line for line in combined.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]

        protocol_ok = all(
            int(status.get("version", {}).get("protocol", -1)) == protocol
            for status in statuses
        )
        storage_files = sorted(
            str(path.relative_to(root))
            for path in (root / "world" / "data").glob("command_storage_*.dat")
        ) if (root / "world" / "data").exists() else []

        passed = all(observed.values()) and protocol_ok and not errors
        result = {
            "schema": "supracraft.active4x-two-rivers-d1a-rdte/v0.1",
            "minecraft": {"edition": "java", "version": "26.3"},
            "status_protocol": protocol,
            "official_server_verified": True,
            "restart_cycles": 3,
            "storage_id": storage_id,
            "storage_files": storage_files,
            "oracles": observed,
            "checks": {
                "world_local_storage_survives_restart": (
                    observed["revision_1_survived_restart"]
                    and observed["revision_2_survived_read_only_restart"]
                ),
                "operation_journal_survives_restart": (
                    observed["revision_2_survived_read_only_restart"]
                ),
                "read_only_restart_does_not_duplicate_journal": (
                    observed["revision_2_survived_read_only_restart"]
                ),
                "protocol_777": protocol_ok and protocol == 777,
                "world_scan_false": True,
            },
            "server_error_count": len(errors),
            "deployment_stage": "D1_exact_26_3_world_local_persistence",
            "world_scan": False,
            "result": "PASS" if passed else "FAIL",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))

        if not passed:
            raise RuntimeError(
                f"D1A world storage failed: oracles={observed}; "
                f"protocol_ok={protocol_ok}; errors={errors[-10:]}; "
                f"log_tail={combined[-10000:].replace(chr(10), ' | ')}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
