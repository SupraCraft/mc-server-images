#!/usr/bin/env python3
"""Boot one verified official Minecraft server and prove a real status handshake."""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
    position = 0
    while True:
        raw = sock.recv(1)
        if not raw:
            raise EOFError("socket closed while reading VarInt")
        byte = raw[0]
        value |= (byte & 0x7F) << position
        if (byte & 0x80) == 0:
            return value
        position += 7
        if position >= 35:
            raise ValueError("VarInt too long")


def read_exact(sock: socket.socket, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise EOFError("socket closed while reading payload")
        data.extend(chunk)
    return bytes(data)


def status_query(host: str, port: int, protocol: int) -> dict[str, Any]:
    address = host.encode("utf-8")
    handshake = (
        write_varint(0)
        + write_varint(protocol)
        + write_varint(len(address))
        + address
        + struct.pack(">H", port)
        + write_varint(1)
    )
    request = write_varint(0)

    with socket.create_connection((host, port), timeout=3) as sock:
        sock.settimeout(3)
        sock.sendall(write_varint(len(handshake)) + handshake)
        sock.sendall(write_varint(len(request)) + request)

        packet_length = read_varint(sock)
        packet_id = read_varint(sock)
        if packet_id != 0:
            raise ValueError(f"unexpected status response packet id {packet_id}")
        json_length = read_varint(sock)
        payload = read_exact(sock, json_length)
        if packet_length < json_length:
            raise ValueError("invalid status packet length")
        return json.loads(payload.decode("utf-8"))


def download_verified_server(evidence: dict[str, Any], destination: Path) -> None:
    server = evidence["server_artifact"]
    with urllib.request.urlopen(server["url"], timeout=300) as response:
        data = response.read()
    destination.write_bytes(data)

    actual_sha1 = sha1_file(destination)
    expected_sha1 = server["expected_sha1"]
    if actual_sha1 != expected_sha1:
        raise RuntimeError(
            f"server SHA-1 mismatch: expected {expected_sha1}, got {actual_sha1}"
        )
    if len(data) != int(server["size"]):
        raise RuntimeError(
            f"server size mismatch: expected {server['size']}, got {len(data)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=150)
    args = parser.parse_args()

    evidence = json.loads(args.evidence.read_text("utf-8"))
    version_info = evidence["artifact_version_json"]
    version = str(version_info["id"])
    protocol = int(version_info["protocol_version"])
    required_java = int(version_info["java_version"])

    java_version = subprocess.run(
        ["java", "-version"],
        text=True,
        capture_output=True,
        check=True,
    )
    java_text = (java_version.stderr or java_version.stdout).strip()

    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"minecraft-{version}-") as tmp:
        root = Path(tmp)
        server_jar = root / "server.jar"
        download_verified_server(evidence, server_jar)

        (root / "eula.txt").write_text("eula=true\n", "utf-8")
        (root / "server.properties").write_text(
            "\n".join(
                [
                    "online-mode=false",
                    "server-port=25565",
                    "level-type=minecraft:flat",
                    "view-distance=2",
                    "simulation-distance=2",
                    "spawn-protection=0",
                    "max-players=1",
                    "enable-rcon=false",
                    "enable-query=false",
                    "motd=SupraCraft 26.3 qualification",
                    "",
                ]
            ),
            "utf-8",
        )

        log_path = root / "server.log"
        with log_path.open("w+", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    "java",
                    "-Xms512M",
                    "-Xmx1536M",
                    "-jar",
                    str(server_jar),
                    "nogui",
                ],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )

            status: dict[str, Any] | None = None
            last_error = ""
            deadline = time.monotonic() + args.timeout_seconds
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                try:
                    status = status_query("127.0.0.1", 25565, protocol)
                    observed_protocol = int(status.get("version", {}).get("protocol", -1))
                    if observed_protocol == protocol:
                        break
                    last_error = (
                        f"status protocol {observed_protocol} != expected {protocol}"
                    )
                except Exception as exc:  # bounded readiness polling
                    last_error = str(exc)
                time.sleep(1)

            if status is None or int(status.get("version", {}).get("protocol", -1)) != protocol:
                if process.poll() is None and process.stdin is not None:
                    process.stdin.write("stop\n")
                    process.stdin.flush()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
                log.flush()
                log.seek(0)
                tail = log.read()[-8000:]
                raise RuntimeError(
                    "server never produced a matching status response; "
                    f"last_error={last_error!r}; exit={process.returncode}; log_tail={tail!r}"
                )

            ready_elapsed = time.monotonic() - started

            if process.stdin is None:
                raise RuntimeError("server stdin unavailable for graceful stop")
            process.stdin.write("stop\n")
            process.stdin.flush()
            try:
                exit_code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                exit_code = process.wait(timeout=10)

            log.flush()
            log.seek(0)
            server_log = log.read()

        if exit_code != 0:
            raise RuntimeError(f"server exited {exit_code} after successful status probe")

    status_version = status.get("version", {}) if status else {}
    if int(status_version.get("protocol", -1)) != protocol:
        raise RuntimeError("status protocol identity mismatch")

    result = {
        "schema": "supracraft-vanilla-runtime-smoke/1",
        "minecraft_version": version,
        "expected_protocol": protocol,
        "required_java_version": required_java,
        "java_runtime": java_text,
        "server_artifact": {
            "sha1": evidence["server_artifact"]["actual_sha1"],
            "sha256": evidence["server_artifact"]["sha256"],
        },
        "status_response": status,
        "ready_elapsed_seconds": round(ready_elapsed, 3),
        "graceful_stop_exit_code": exit_code,
        "server_log_tail": server_log[-4000:],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(
        json.dumps(
            {
                "minecraft_version": version,
                "protocol": protocol,
                "status_version": status_version,
                "ready_elapsed_seconds": result["ready_elapsed_seconds"],
                "exit_code": exit_code,
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
