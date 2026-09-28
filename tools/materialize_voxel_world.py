#!/usr/bin/env python3
"""Materialize a generated voxel tensor into a disposable playable Minecraft Java world."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import nbtlib
import numpy as np
from nbtlib import Byte, Int


BWB_BLOCKS = {
    0: "minecraft:air",
    1: "minecraft:dirt",
    2: "minecraft:white_concrete",
    3: "minecraft:oak_planks",
    4: "minecraft:stone_bricks",
    5: "minecraft:grass_block",
    6: "minecraft:stone_brick_slab[type=bottom]",
    7: "minecraft:stone_brick_slab[type=top]",
    8: "minecraft:glass",
    9: "minecraft:stone_brick_slab[type=double]",
    10: "minecraft:bookshelf",
    11: "minecraft:gravel",
    12: "minecraft:green_concrete",
    13: "minecraft:oak_slab[type=bottom]",
    14: "minecraft:sandstone",
    15: "minecraft:stone_bricks",
}


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_verified_server(evidence: dict, destination: Path) -> None:
    server = evidence["server_artifact"]
    with urllib.request.urlopen(server["url"], timeout=300) as response:
        with destination.open("wb") as fh:
            shutil.copyfileobj(response, fh)
    if sha1_file(destination) != server["expected_sha1"]:
        raise RuntimeError("official Minecraft server SHA-1 mismatch")
    if destination.stat().st_size != int(server["size"]):
        raise RuntimeError("official Minecraft server size mismatch")


def write_datapack(world: Path, pack_format: int, commands: list[str], sites: list[dict]) -> None:
    pack = world / "datapacks" / "supracraft_generated"
    fn = pack / "data" / "supracraft" / "function"
    fn.mkdir(parents=True, exist_ok=True)
    (pack / "pack.mcmeta").write_text(
        json.dumps(
            {
                "pack": {
                    "description": "SupraCraft generated-world qualification and tour controls",
                    "min_format": [pack_format, 0],
                    "max_format": [pack_format, 0],
                }
            },
            indent=2,
        )
        + "\n",
        "utf-8",
    )
    (fn / "materialize.mcfunction").write_text("\n".join(commands) + "\n", "utf-8")

    tour = fn / "tour"
    tour.mkdir(parents=True, exist_ok=True)
    for site in sites:
        mode = site.get("gamemode", "spectator")
        x, y, z = site["position"]
        tx, ty, tz = site["look_at"]
        body = [
            f"gamemode {mode} @s",
            "effect give @s minecraft:night_vision infinite 0 true",
            f"tp @s {x} {y} {z} facing {tx} {ty} {tz}",
            f'tellraw @s {json.dumps({"text": site["label"], "color": "gold"})}',
        ]
        (tour / f'{site["id"]}.mcfunction').write_text("\n".join(body) + "\n", "utf-8")

    start = sites[0]
    (tour / "start.mcfunction").write_text(
        "\n".join(
            [
                "gamemode spectator @s",
                "effect give @s minecraft:night_vision infinite 0 true",
                f'function supracraft:tour/{start["id"]}',
                'tellraw @s {"text":"SupraCraft tour loaded. See SUPRACRAFT-TOUR.txt for all teleport functions.","color":"aqua"}',
            ]
        )
        + "\n",
        "utf-8",
    )


def build_commands(voxels: np.ndarray, origin: tuple[int, int, int]) -> tuple[list[str], dict]:
    ox, oy, oz = origin
    sx, sy, sz = map(int, voxels.shape)
    cmds = [
        "gamerule doMobSpawning false",
        "gamerule doDaylightCycle false",
        "time set noon",
        "difficulty peaceful",
        f"setworldspawn {ox + sx // 2} {oy + sy + 3} {oz + sz // 2}",
        f"fill {ox-6} {oy-2} {oz-6} {ox+sx+6} {oy-2} {oz+sz+6} minecraft:smooth_stone",
        f"fill {ox-1} {oy-1} {oz-1} {ox+sx} {oy+sy} {oz+sz} minecraft:air",
    ]
    counts: dict[str, int] = {}
    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                bid = int(voxels[x, y, z])
                block = BWB_BLOCKS.get(bid)
                if block is None:
                    raise ValueError(f"unknown Build-with-Bombs block id {bid}")
                counts[block] = counts.get(block, 0) + 1
                if block == "minecraft:air":
                    continue
                cmds.append(f"setblock {ox+x} {oy+y} {oz+z} {block}")
    return cmds, counts


def wait_ready(process: subprocess.Popen[str], log_path: Path, timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if log_path.exists() and "Done (" in log_path.read_text("utf-8", errors="replace"):
            return
        time.sleep(1)
    tail = log_path.read_text("utf-8", errors="replace")[-10000:] if log_path.exists() else ""
    raise RuntimeError(f"Minecraft server failed readiness; exit={process.poll()} tail={tail!r}")


def console(process: subprocess.Popen[str], command: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(command + "\n")
    process.stdin.flush()


def zip_tree(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(source.parent))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--npz", type=Path, required=True)
    ap.add_argument("--receipt", type=Path)
    ap.add_argument("--release-evidence", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--crop-center", type=int, default=12)
    args = ap.parse_args()

    release = json.loads(args.release_evidence.read_text("utf-8"))
    version = release["minecraft_version"]
    pack_format = int(release["artifact_version_json"]["pack_version"]["data_major"])
    java_version = int(release["artifact_version_json"]["java_version"])

    raw = np.load(args.npz)["voxels"]
    if raw.ndim != 3:
        raise ValueError(f"expected 3D voxel tensor, got {raw.shape}")

    crop = min(args.crop_center, *raw.shape)
    starts = [(int(n) - crop) // 2 for n in raw.shape]
    voxels = raw[
        starts[0] : starts[0] + crop,
        starts[1] : starts[1] + crop,
        starts[2] : starts[2] + crop,
    ]

    origin = (0, 80, 0)
    commands, counts = build_commands(voxels, origin)
    sx, sy, sz = map(int, voxels.shape)
    cx, cy, cz = origin[0] + sx // 2, origin[1] + sy // 2, origin[2] + sz // 2
    center_id = int(voxels[sx // 2, sy // 2, sz // 2])
    center_block = BWB_BLOCKS[center_id]

    sites = [
        {
            "id": "generated",
            "label": "Generated voxel structure — overview",
            "category": "highlight",
            "position": [cx, origin[1] + sy + 8, origin[2] - 12],
            "look_at": [cx, cy, cz],
            "gamemode": "spectator",
        },
        {
            "id": "cross_section",
            "label": "Generated structure — close inspection / cross-section",
            "category": "defect-inspection",
            "position": [origin[0] - 3, cy, cz],
            "look_at": [cx, cy, cz],
            "gamemode": "spectator",
        },
        {
            "id": "mundane",
            "label": "Mundane surrounding platform / world context",
            "category": "mundane",
            "position": [origin[0] + sx + 16, origin[1] + 7, origin[2] + sz + 16],
            "look_at": [cx, origin[1], cz],
            "gamemode": "spectator",
        },
        {
            "id": "play",
            "label": "Playability inspection — creative mode",
            "category": "playability",
            "position": [cx, origin[1] + sy + 2, cz],
            "look_at": [cx, cy, cz],
            "gamemode": "creative",
        },
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="supracraft-world-") as td:
        root = Path(td)
        world = root / "world"
        world.mkdir()
        write_datapack(world, pack_format, commands, sites)

        server_jar = root / "server.jar"
        download_verified_server(release, server_jar)
        (root / "eula.txt").write_text("eula=true\n", "utf-8")
        (root / "server.properties").write_text(
            "\n".join(
                [
                    "online-mode=false",
                    "server-port=25567",
                    "level-name=world",
                    "level-type=minecraft:flat",
                    "gamemode=creative",
                    "force-gamemode=true",
                    "allow-flight=true",
                    "spawn-protection=0",
                    "view-distance=4",
                    "simulation-distance=4",
                    "max-players=1",
                    "enable-rcon=false",
                    "enable-query=false",
                    "motd=SupraCraft generated world qualification",
                    "",
                ]
            ),
            "utf-8",
        )

        log_path = root / "server.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx2G", "-jar", str(server_jar), "nogui"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            wait_ready(process, log_path)
            console(process, "function supracraft:materialize")
            console(process, "save-all flush")
            time.sleep(12)
            console(process, f"execute if block {cx} {cy} {cz} {center_block} run say SUPRACRAFT_CENTER_MATCH")
            console(process, "save-all flush")
            time.sleep(3)
            console(process, "stop")
            exit_code = process.wait(timeout=60)

        log_text = log_path.read_text("utf-8", errors="replace")
        if exit_code != 0:
            raise RuntimeError(f"server exited {exit_code}")
        if "Unknown function supracraft:materialize" in log_text:
            raise RuntimeError("generated datapack materialize function was not loaded")
        if "Failed to load datapacks" in log_text:
            raise RuntimeError("generated datapack failed to load")

        level_path = world / "level.dat"
        nbt = nbtlib.load(level_path)
        data = nbt["Data"]
        data["allowCommands"] = Byte(1)
        data["GameType"] = Int(1)
        nbt.save()

        receipt = json.loads(args.receipt.read_text("utf-8")) if args.receipt and args.receipt.exists() else {}
        tour_manifest = {
            "schema": "supracraft-world-tour/1",
            "minecraft_version": version,
            "java_version": java_version,
            "pack_format": pack_format,
            "source_tensor": {
                "path": args.npz.name,
                "sha256": sha256_file(args.npz),
                "shape": list(map(int, raw.shape)),
                "materialized_crop_shape": list(map(int, voxels.shape)),
                "crop_starts": starts,
            },
            "generator_receipt": receipt,
            "origin": list(origin),
            "block_counts": counts,
            "sites": sites,
            "tour_start_command": "/function supracraft:tour/start",
            "materialization_function": "supracraft:materialize",
            "server_artifact_sha256": release["server_artifact"]["sha256"],
            "center_expected_block": center_block,
            "server_log_center_probe_observed": "SUPRACRAFT_CENTER_MATCH" in log_text,
        }
        (world / "SUPRACRAFT-TOUR.txt").write_text(
            "SupraCraft generated-world tour\n\n"
            "Open this world in Minecraft Java 26.3. Cheats are enabled and the world defaults to Creative.\n"
            "Start the guided teleport tour with:\n"
            "  /function supracraft:tour/start\n\n"
            + "\n".join(
                f'  /function supracraft:tour/{s["id"]}  - {s["label"]}' for s in sites
            )
            + "\n\nYou can switch freely between /gamemode spectator and /gamemode creative.\n",
            "utf-8",
        )

        manifest_path = args.output_dir / "tour-manifest.json"
        manifest_path.write_text(json.dumps(tour_manifest, indent=2, sort_keys=True) + "\n", "utf-8")
        (args.output_dir / "server-materialization.log").write_text(log_text[-20000:], "utf-8")
        zip_path = args.output_dir / f"supracraft-{version}-generated-world.zip"
        zip_tree(world, zip_path)

    summary = {
        "world_zip": str(zip_path),
        "world_sha256": sha256_file(zip_path),
        "tour_manifest": str(manifest_path),
        "sites": len(sites),
        "commands": len(commands),
        "center_probe": tour_manifest["server_log_center_probe_observed"],
    }
    (args.output_dir / "world-receipt.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
