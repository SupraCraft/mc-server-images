#!/usr/bin/env python3
"""Boot an exact Minecraft server with one datapack and emit a bounded runtime receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any


HARD_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"failed to load",
        r"couldn.?t load",
        r"could not load",
        r"couldn.?t parse",
        r"could not parse",
        r"unknown function",
        r"unknown item",
        r"unknown block",
        r"exception loading",
        r"error loading",
        r"failed to parse",
        r"failed to execute function",
    ]
]


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_verified_server(evidence: dict[str, Any], destination: Path) -> None:
    server = evidence["server_artifact"]
    with urllib.request.urlopen(server["url"], timeout=300) as response:
        data = response.read()
    destination.write_bytes(data)
    if sha1_file(destination) != server["expected_sha1"]:
        raise RuntimeError("server SHA-1 mismatch")
    if len(data) != int(server["size"]):
        raise RuntimeError("server size mismatch")


def write_varint(value: int) -> bytes:
    value &= 0xFFFFFFFF
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            b |= 0x80
        out.append(b)
        if not value:
            return bytes(out)


def read_varint(sock: socket.socket) -> int:
    value = 0
    pos = 0
    while True:
        raw = sock.recv(1)
        if not raw:
            raise EOFError("socket closed")
        b = raw[0]
        value |= (b & 0x7F) << pos
        if (b & 0x80) == 0:
            return value
        pos += 7
        if pos >= 35:
            raise ValueError("VarInt too long")


def read_exact(sock: socket.socket, n: int) -> bytes:
    data = bytearray()
    while len(data) < n:
        part = sock.recv(n - len(data))
        if not part:
            raise EOFError("socket closed")
        data.extend(part)
    return bytes(data)


def status_query(host: str, port: int, protocol: int) -> dict[str, Any]:
    addr = host.encode()
    handshake = (
        write_varint(0)
        + write_varint(protocol)
        + write_varint(len(addr))
        + addr
        + struct.pack(">H", port)
        + write_varint(1)
    )
    request = write_varint(0)
    with socket.create_connection((host, port), timeout=3) as sock:
        sock.settimeout(3)
        sock.sendall(write_varint(len(handshake)) + handshake)
        sock.sendall(write_varint(len(request)) + request)
        _packet_len = read_varint(sock)
        packet_id = read_varint(sock)
        if packet_id != 0:
            raise ValueError(f"unexpected packet id {packet_id}")
        json_len = read_varint(sock)
        return json.loads(read_exact(sock, json_len).decode())


def send(process: subprocess.Popen[str], command: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(command + "\n")
    process.stdin.flush()


def wait_for_text(log_path: Path, needle: str, deadline: float) -> bool:
    while time.monotonic() < deadline:
        if log_path.exists():
            text = log_path.read_text("utf-8", errors="replace")
            if needle in text:
                return True
        time.sleep(0.25)
    return False


def extract_objective_snapshots(lines: list[str]) -> list[dict[str, Any]]:
    out = []
    # Current server wording is intentionally not hard-coded beyond the count prefix.
    rx = re.compile(r"There are (\d+) objective")
    for line in lines:
        m = rx.search(line)
        if not m:
            continue
        names = []
        if ": [" in line:
            tail = line.split(": [", 1)[1]
            if "]" in tail:
                names = [x.strip() for x in tail.split("]", 1)[0].split(",") if x.strip()]
        out.append({"count": int(m.group(1)), "names": names, "line": line[-2000:]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--datapack-dir", type=Path, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--port", type=int, default=25565)
    ap.add_argument("--timeout-seconds", type=int, default=180)
    args = ap.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    version = str(evidence["artifact_version_json"]["id"])
    protocol = int(evidence["artifact_version_json"]["protocol_version"])

    with tempfile.TemporaryDirectory(prefix=f"supracraft-pack-{args.label}-") as td:
        root = Path(td)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)

        pack_target = root / "world" / "datapacks" / "voidblock"
        pack_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(args.datapack_dir, pack_target)

        (root / "eula.txt").write_text("eula=true\n", "utf-8")
        (root / "server.properties").write_text(
            "\n".join([
                "online-mode=false",
                f"server-port={args.port}",
                "view-distance=2",
                "simulation-distance=2",
                "spawn-protection=0",
                "max-players=1",
                "enable-rcon=false",
                "enable-query=false",
                "generate-structures=false",
                "level-type=minecraft:flat",
                "motd=SupraCraft datapack uplift runtime",
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

            deadline = time.monotonic() + args.timeout_seconds
            status = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    s = status_query("127.0.0.1", args.port, protocol)
                    if int(s.get("version", {}).get("protocol", -1)) == protocol:
                        status = s
                        break
                except Exception:
                    pass
                time.sleep(1)

            if status is None:
                if process.poll() is None:
                    send(process, "stop")
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                log.flush()
                log.seek(0)
                tail = log.read()[-12000:]
                raise RuntimeError(f"server failed readiness: exit={process.returncode}; tail={tail!r}")

            # Give tick/load functions bounded time to initialize.
            time.sleep(3)
            commands = [
                "say SUPRACRAFT_PROFILE_PRE",
                "datapack list enabled",
                "scoreboard objectives list",
                "execute if block 0 62 0 minecraft:bedrock run say SUPRACRAFT_VOIDBLOCK_SETUP_BEDROCK_PASS",
                "reload",
            ]
            for command in commands:
                send(process, command)
                time.sleep(0.5)

            if not wait_for_text(log_path, "Reload complete", time.monotonic() + 30):
                # Reload wording can vary; still continue and classify from log.
                pass

            time.sleep(2)
            for command in [
                "say SUPRACRAFT_PROFILE_POST",
                "datapack list enabled",
                "scoreboard objectives list",
                "execute if block 0 62 0 minecraft:bedrock run say SUPRACRAFT_VOIDBLOCK_SETUP_BEDROCK_POST_RELOAD_PASS",
                "save-all flush",
            ]:
                send(process, command)
                time.sleep(0.5)

            send(process, "stop")
            try:
                exit_code = process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                process.kill()
                exit_code = process.wait(timeout=10)

            log.flush()
            log.seek(0)
            server_log = log.read()

        lines = server_log.splitlines()
        error_lines = [
            line for line in lines
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        hard_lines = [
            line for line in lines
            if any(rx.search(line) for rx in HARD_PATTERNS)
        ]

        # Preserve generic ERROR equivalence without redistributing raw
        # third-party log text. Normalize volatile timestamp/thread prefixes
        # and retain only SHA-256 fingerprints + multiplicities.
        error_fingerprint_counts: dict[str, int] = {}
        for line in error_lines:
            message = line
            if "]: " in message:
                message = message.split("]: ", 1)[1]
            elif "] " in message:
                message = message.split("] ", 1)[1]
            digest = hashlib.sha256(message.encode("utf-8", errors="replace")).hexdigest()
            error_fingerprint_counts[digest] = error_fingerprint_counts.get(digest, 0) + 1

        datapack_lines = [line for line in lines if "data pack" in line.lower() or "datapack" in line.lower()]
        objective_snapshots = extract_objective_snapshots(lines)
        bedrock_pre = "SUPRACRAFT_VOIDBLOCK_SETUP_BEDROCK_PASS" in server_log
        bedrock_post = "SUPRACRAFT_VOIDBLOCK_SETUP_BEDROCK_POST_RELOAD_PASS" in server_log
        ready = "Done (" in server_log
        reload_markers = [line for line in lines if "reload" in line.lower()][-30:]

        result = {
            "schema": "supracraft-datapack-runtime-profile/1",
            "label": args.label,
            "minecraft_version": version,
            "protocol": protocol,
            "server_ready": ready,
            "graceful_stop_exit_code": exit_code,
            "error_log_count": len(error_lines),
            "error_fingerprint_counts": dict(sorted(error_fingerprint_counts.items())),
            "hard_datapack_error_count": len(hard_lines),
            "bedrock_setup_probe_pre_reload": bedrock_pre,
            "bedrock_setup_probe_post_reload": bedrock_post,
            "objective_snapshots": objective_snapshots,
            "datapack_log_tail": datapack_lines[-50:],
            "reload_log_tail": reload_markers,
            "hard_error_tail": hard_lines[-50:],
            "server_log_tail": server_log[-8000:],
        }
        result["canary_pass"] = bool(
            ready
            and exit_code == 0
            and not hard_lines
            and bedrock_pre
            and bedrock_post
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
        print(json.dumps({
            "label": args.label,
            "minecraft_version": version,
            "canary_pass": result["canary_pass"],
            "error_log_count": result["error_log_count"],
            "hard_datapack_error_count": result["hard_datapack_error_count"],
            "bedrock_pre": bedrock_pre,
            "bedrock_post": bedrock_post,
            "objective_snapshot_counts": [x["count"] for x in objective_snapshots],
        }, sort_keys=True))

        if not result["canary_pass"]:
            raise RuntimeError("datapack runtime canary failed")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
