#!/usr/bin/env python3
"""Minimal Minecraft RCON tour driver for the public worldgen camera workflow."""

from __future__ import annotations

import argparse
import json
import socket
import struct
import time
from pathlib import Path


class Rcon:
    def __init__(self, host: str, port: int, password: str):
        self.sock = socket.create_connection((host, port), timeout=10)
        self.sock.settimeout(10)
        self.req = 1
        self._send(3, password)
        rid, _, _ = self._recv()
        if rid == -1:
            raise RuntimeError("RCON authentication failed")

    def _send(self, kind: int, payload: str) -> int:
        rid = self.req
        self.req += 1
        body = struct.pack("<ii", rid, kind) + payload.encode("utf-8") + b"\x00\x00"
        self.sock.sendall(struct.pack("<i", len(body)) + body)
        return rid

    def _read_exact(self, n: int) -> bytes:
        chunks = []
        remaining = n
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise EOFError("RCON socket closed")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _recv(self) -> tuple[int, int, str]:
        length = struct.unpack("<i", self._read_exact(4))[0]
        data = self._read_exact(length)
        rid, kind = struct.unpack("<ii", data[:8])
        payload = data[8:-2].decode("utf-8", errors="replace")
        return rid, kind, payload

    def command(self, command: str) -> str:
        rid = self._send(2, command)
        rrid, _, payload = self._recv()
        if rrid != rid:
            raise RuntimeError(f"RCON request mismatch: {rrid} != {rid}")
        return payload

    def close(self) -> None:
        self.sock.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--username", default="SupraTourBot")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=25572)
    ap.add_argument("--password", required=True)
    ap.add_argument("--seconds-per-site", type=float, default=3.0)
    ap.add_argument("--wait-player-seconds", type=float, default=120)
    ap.add_argument("--receipt", type=Path, required=True)
    args = ap.parse_args()

    # Compatibility with the pre-qualification camera name, which exceeded the
    # 16-character Minecraft username limit and was replaced by SupraTourBot.
    requested_username = username
    username = "SupraTourBot" if requested_username == "SupraCraftTourBot" else requested_username

    manifest = json.loads(args.manifest.read_text("utf-8"))
    sites = manifest.get("sites") or []
    if not sites:
        raise SystemExit("tour manifest has no sites")

    rcon = Rcon(args.host, args.port, args.password)
    try:
        deadline = time.monotonic() + args.wait_player_seconds
        last_list = ""
        while time.monotonic() < deadline:
            last_list = rcon.command("list")
            if username in last_list:
                break
            time.sleep(1)
        else:
            result = {
                "schema": "supracraft-rcon-tour/1",
                "status": "blocked",
                "blocker": "camera-player-did-not-join",
                "last_list": last_list,
                "username": username,
            "requested_username": requested_username,
            }
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result, indent=2))
            return 3

        rcon.command(f"gamemode spectator {username}")
        rcon.command(f"effect give {username} minecraft:night_vision infinite 0 true")
        visited = []
        for site in sites:
            p = site["position"]
            look = site.get("look_at")
            cmd = f"tp {username} {p[0]} {p[1]} {p[2]}"
            if look:
                cmd += f" facing {look[0]} {look[1]} {look[2]}"
            response = rcon.command(cmd)
            visited.append({
                "site_id": site.get("site_id"),
                "category": site.get("category"),
                "position": p,
                "look_at": look,
                "response": response,
            })
            time.sleep(args.seconds_per_site)

        result = {
            "schema": "supracraft-rcon-tour/1",
            "status": "success",
            "username": username,
            "requested_username": requested_username,
            "visited_sites": visited,
            "seconds_per_site": args.seconds_per_site,
        }
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        rcon.close()


if __name__ == "__main__":
    raise SystemExit(main())
