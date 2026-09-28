#!/usr/bin/env python3
"""Generate a bounded Minecraft 26.3 vanilla/control world for the public benchmark."""

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
from typing import Any

PROFILES = {
    "normal": {
        "level_type": "minecraft:normal",
        "generate_structures": "true",
        "generator_settings": "{}",
        "expected_role": "reference",
    },
    "flat-null-control": {
        "level_type": "minecraft:flat",
        "generate_structures": "false",
        "generator_settings": "{\"biome\":\"minecraft:plains\",\"layers\":[{\"block\":\"minecraft:bedrock\",\"height\":1},{\"block\":\"minecraft:dirt\",\"height\":2},{\"block\":\"minecraft:grass_block\",\"height\":1}]}",
        "expected_role": "low-complexity-control",
    },
}

XZS = (-48, -24, 0, 24, 48)
YS = (-64, -48, -32, -16, 0, 16, 32, 48, 64, 80, 96, 112, 128, 160, 192, 224, 256, 288, 320)


def digest(path: Path, algo: str) -> str:
    h = hashlib.new(algo)
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_server(evidence: dict[str, Any], dest: Path) -> None:
    server = evidence["server_artifact"]
    with urllib.request.urlopen(server["url"], timeout=300) as response:
        with dest.open("wb") as fh:
            shutil.copyfileobj(response, fh)
    if digest(dest, "sha1") != server["expected_sha1"]:
        raise RuntimeError("server SHA-1 mismatch")
    if digest(dest, "sha256") != server["sha256"]:
        raise RuntimeError("server SHA-256 mismatch")
    if dest.stat().st_size != int(server["size"]):
        raise RuntimeError("server size mismatch")


def wait_ready(process: subprocess.Popen[str], log_path: Path, timeout: int) -> float:
    start = time.monotonic()
    deadline = start + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if log_path.exists() and "Done (" in log_path.read_text("utf-8", errors="replace"):
            return time.monotonic() - start
        time.sleep(1)
    tail = log_path.read_text("utf-8", errors="replace")[-10000:] if log_path.exists() else ""
    raise RuntimeError(f"server did not reach readiness; exit={process.poll()} tail={tail!r}")


def command(process: subprocess.Popen[str], line: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(line + "\n")
    process.stdin.flush()


def zip_world(world: Path, out: Path) -> None:
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(world.rglob("*")):
            if path.is_file() and path.name != "session.lock":
                zf.write(path, Path("world") / path.relative_to(world))


def parse_probe(log: str) -> dict[str, Any]:
    observed: dict[tuple[int, int], list[int]] = {}
    for line in log.splitlines():
        marker = "WGPROBE "
        if marker not in line:
            continue
        try:
            tail = line.split(marker, 1)[1]
            x_s, z_s, y_s = tail.split()[:3]
            key = (int(x_s), int(z_s))
            observed.setdefault(key, []).append(int(y_s))
        except Exception:
            continue

    surfaces = []
    points = []
    for x in XZS:
        for z in XZS:
            vals = observed.get((x, z), [])
            highest = max(vals) if vals else None
            points.append({"x": x, "z": z, "highest_sampled_non_air_y": highest})
            if highest is not None:
                surfaces.append(highest)

    if surfaces:
        lo, hi = min(surfaces), max(surfaces)
        mean = sum(surfaces) / len(surfaces)
        relief = hi - lo
    else:
        lo = hi = mean = relief = None

    return {
        "schema": "supracraft-worldgen-terrain-bootstrap/1",
        "probe_kind": "coarse-highest-non-air",
        "xzs": list(XZS),
        "ys": list(YS),
        "sample_count": len(points),
        "observed_count": len(surfaces),
        "surface_min_y": lo,
        "surface_max_y": hi,
        "surface_mean_y": mean,
        "coarse_relief": relief,
        "points": points,
        "limitations": [
            "Coarse vertical samples are a bootstrap control metric, not a final terrain analyzer.",
            "Non-air includes water, vegetation, and structures.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", choices=sorted(PROFILES), required=True)
    ap.add_argument("--seed", required=True)
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--timeout-seconds", type=int, default=180)
    args = ap.parse_args()

    profile = PROFILES[args.profile]
    evidence = json.loads(args.evidence.read_text("utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir = args.output_dir / "analysis"
    analysis_dir.mkdir(exist_ok=True)

    started_wall = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started = time.monotonic()

    with tempfile.TemporaryDirectory(prefix=f"worldgen-{args.profile}-") as td:
        root = Path(td)
        world = root / "world"
        server = root / "server.jar"
        download_server(evidence, server)

        (root / "eula.txt").write_text("eula=true\n", "utf-8")
        props = {
            "online-mode": "false",
            "server-port": "25568",
            "view-distance": "4",
            "simulation-distance": "4",
            "spawn-protection": "0",
            "max-players": "1",
            "enable-rcon": "false",
            "enable-query": "false",
            "allow-flight": "true",
            "gamemode": "creative",
            "difficulty": "peaceful",
            "level-name": "world",
            "level-seed": str(args.seed),
            "level-type": profile["level_type"],
            "generate-structures": profile["generate_structures"],
            "generator-settings": profile["generator_settings"],
            "motd": f"SupraCraft worldgen benchmark {args.profile}",
        }
        (root / "server.properties").write_text(
            "\n".join(f"{k}={v}" for k, v in props.items()) + "\n",
            "utf-8",
        )

        log_path = root / "server.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx3G", "-jar", str(server), "nogui"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            ready_seconds = wait_ready(process, log_path, args.timeout_seconds)

            # 9x9 chunks around origin: bounded, identical area for both profiles.
            command(process, "forceload add -64 -64 64 64")
            command(process, "save-all flush")
            time.sleep(20)

            # Coarse terrain probe. Emit a log marker for every sampled non-air block.
            for x in XZS:
                for z in XZS:
                    for y in YS:
                        command(
                            process,
                            f"execute unless block {x} {y} {z} minecraft:air run say WGPROBE {x} {z} {y}",
                        )
            command(process, "save-all flush")
            time.sleep(8)
            command(process, "forceload remove all")
            command(process, "save-all flush")
            time.sleep(2)
            command(process, "stop")
            exit_code = process.wait(timeout=60)

        server_log = log_path.read_text("utf-8", errors="replace")
        shutil.copy2(log_path, args.output_dir / "server.log")
        if exit_code != 0:
            raise RuntimeError(f"server exited with {exit_code}; tail={server_log[-8000:]!r}")
        error_lines = [
            line for line in server_log.splitlines()
            if "/ERROR]:" in line or "/ERROR] " in line
        ]
        if error_lines:
            raise RuntimeError(
                "server emitted ERROR lines: " + " | ".join(error_lines[-20:])
            )

        terrain = parse_probe(server_log)
        terrain["profile"] = args.profile
        terrain["expected_role"] = profile["expected_role"]
        (analysis_dir / "terrain.json").write_text(
            json.dumps(terrain, indent=2, sort_keys=True) + "\n", "utf-8"
        )

        world_zip = args.output_dir / "world.zip"
        zip_world(world, world_zip)

    elapsed = time.monotonic() - started
    provenance = {
        "schema": "supracraft-worldgen-provenance/1",
        "profile": args.profile,
        "generator": "Minecraft Java vanilla 26.3",
        "family": "procedural" if args.profile == "normal" else "control",
        "seed": str(args.seed),
        "level_type": profile["level_type"],
        "generate_structures": profile["generate_structures"] == "true",
        "generator_settings": profile["generator_settings"],
        "bounded_forceload_block_range": [-64, -64, 64, 64],
        "minecraft_release_identity_sha256": digest(args.evidence, "sha256"),
        "server_artifact_sha1": evidence["server_artifact"]["expected_sha1"],
        "server_artifact_sha256": evidence["server_artifact"]["sha256"],
        "protocol": evidence["artifact_version_json"]["protocol_version"],
        "world_version": evidence["artifact_version_json"]["world_version"],
    }
    (args.output_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", "utf-8"
    )

    artifacts = []
    for kind, path in [
        ("minecraft-world-zip", args.output_dir / "world.zip"),
        ("terrain-analysis", analysis_dir / "terrain.json"),
        ("provenance", args.output_dir / "provenance.json"),
    ]:
        artifacts.append({"kind": kind, "path": str(path.relative_to(args.output_dir)), "sha256": digest(path, "sha256")})

    receipt = {
        "schema_version": 1,
        "run_id": f"bootstrap-{args.profile}-{args.seed}",
        "generator_ref": f"vanilla-26.3/{args.profile}",
        "pipeline_ref": None,
        "seed": str(args.seed),
        "scenario": "bootstrap-control-pair",
        "minecraft_version": "26.3",
        "execution": {
            "repository_visibility": "public",
            "runner_label": "ubuntu-latest",
            "runner_image": None,
            "money_usd": 0,
            "started_at": started_wall,
            "elapsed_seconds": round(elapsed, 3),
        },
        "artifacts": artifacts,
        "status": "success",
        "blocker": None,
        "ready_seconds": round(ready_seconds, 3),
    }
    (args.output_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    print(json.dumps({
        "profile": args.profile,
        "seed": args.seed,
        "world_sha256": digest(args.output_dir / "world.zip", "sha256"),
        "terrain": terrain,
        "elapsed_seconds": round(elapsed, 3),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
