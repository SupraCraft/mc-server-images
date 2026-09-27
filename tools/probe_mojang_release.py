#!/usr/bin/env python3
"""Probe one official Minecraft Java release without retaining the JAR."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

VERSION_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"


def fetch(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_version_json(jar_bytes: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(jar_bytes)) as outer:
        try:
            return json.loads(outer.read("version.json").decode("utf-8"))
        except KeyError:
            pass

        for name in sorted(outer.namelist()):
            if not (name.startswith("META-INF/versions/") and name.endswith(".jar")):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as nested:
                try:
                    return json.loads(nested.read("version.json").decode("utf-8"))
                except KeyError:
                    continue
    raise RuntimeError("version.json not found in server artifact")


def inspect_class_layout(jar_bytes: bytes, expected_classes: list[str]) -> dict[str, Any]:
    """Report whether expected readable class names exist in the effective game JAR."""
    with zipfile.ZipFile(io.BytesIO(jar_bytes)) as outer:
        direct = set(outer.namelist())
        direct_hits = {name: name in direct for name in expected_classes}
        if any(direct_hits.values()):
            return {
                "container": "direct",
                "classes": direct_hits,
            }

        for name in sorted(outer.namelist()):
            if not (name.startswith("META-INF/versions/") and name.endswith(".jar")):
                continue
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as nested:
                entries = set(nested.namelist())
                hits = {class_name: class_name in entries for class_name in expected_classes}
                if any(hits.values()):
                    return {
                        "container": name,
                        "classes": hits,
                    }

    return {
        "container": None,
        "classes": {name: False for name in expected_classes},
    }


def probe_artifact(
    detail: dict[str, Any],
    kind: str,
    expected_classes: list[str],
) -> tuple[dict[str, Any], bytes]:
    meta = (detail.get("downloads") or {}).get(kind)
    if not meta:
        raise RuntimeError(f"no official {kind} artifact")

    data = fetch(str(meta["url"]), timeout=300)
    actual_sha1 = sha1(data)
    expected_sha1 = meta.get("sha1")
    if expected_sha1 and actual_sha1 != expected_sha1:
        raise RuntimeError(
            f"{kind} SHA-1 mismatch: expected {expected_sha1}, got {actual_sha1}"
        )
    expected_size = meta.get("size")
    if expected_size is not None and len(data) != int(expected_size):
        raise RuntimeError(
            f"{kind} size mismatch: expected {expected_size}, got {len(data)}"
        )

    return {
        "url": meta.get("url"),
        "expected_sha1": expected_sha1,
        "actual_sha1": actual_sha1,
        "sha256": sha256(data),
        "size": len(data),
        "class_layout": inspect_class_layout(data, expected_classes),
    }, data


def resolve_entry(index: dict[str, Any], version: str) -> dict[str, Any]:
    for entry in index.get("versions", []):
        if entry.get("id") == version:
            return entry
    raise RuntimeError(f"Minecraft version not found: {version}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    index_raw = fetch(VERSION_MANIFEST_URL)
    index = json.loads(index_raw)
    entry = resolve_entry(index, args.version)

    detail_raw = fetch(str(entry["url"]))
    detail = json.loads(detail_raw)
    server_artifact, server_bytes = probe_artifact(
        detail,
        "server",
        [
            "net/minecraft/network/protocol/game/GameProtocols.class",
            "net/minecraft/network/protocol/game/ServerboundAcceptTeleportationPacket.class",
            "net/minecraft/network/protocol/game/ServerboundPlayerActionPacket.class",
        ],
    )
    client_artifact, _ = probe_artifact(
        detail,
        "client",
        [
            "net/minecraft/client/player/LocalPlayer.class",
            "net/minecraft/client/multiplayer/ClientPacketListener.class",
            "net/minecraft/client/Minecraft.class",
            "net/minecraft/network/protocol/game/ServerboundPunchPacket.class",
        ],
    )

    version_info = read_version_json(server_bytes)
    observed_version = version_info.get("id") or version_info.get("name")
    if observed_version != args.version:
        raise RuntimeError(
            f"artifact identity mismatch: requested {args.version}, artifact reports {observed_version}"
        )

    result = {
        "schema": "supracraft-mojang-release-identity/1",
        "minecraft_version": args.version,
        "launcher_entry": {
            "type": entry.get("type"),
            "time": entry.get("time"),
            "releaseTime": entry.get("releaseTime"),
            "metadata_url": entry.get("url"),
        },
        "provenance": {
            "launcher_manifest_url": VERSION_MANIFEST_URL,
            "launcher_manifest_sha256": sha256(index_raw),
            "version_metadata_sha256": sha256(detail_raw),
        },
        "server_artifact": server_artifact,
        "client_artifact": client_artifact,
        "artifact_version_json": version_info,
        "mappings": {
            kind: {
                "available": key in (detail.get("downloads") or {}),
                "url": ((detail.get("downloads") or {}).get(key) or {}).get("url"),
                "sha1": ((detail.get("downloads") or {}).get(key) or {}).get("sha1"),
            }
            for kind, key in (
                ("client", "client_mappings"),
                ("server", "server_mappings"),
            )
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps({
        "version": args.version,
        "protocol_version": version_info.get("protocol_version", version_info.get("protocolVersion")),
        "world_version": version_info.get("world_version", version_info.get("worldVersion")),
        "server_sha256": result["server_artifact"]["sha256"],
        "output": str(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
