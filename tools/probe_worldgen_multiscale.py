#!/usr/bin/env python3
"""Probe an existing Minecraft 26.3 world at multiple spatial scales and nominate tour sites."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

SCALES = {
    "local": (-48, -24, 0, 24, 48),
    "regional": (-256, -128, 0, 128, 256),
    "macro": (-1024, -512, 0, 512, 1024),
}
YS = tuple(range(-64, 321, 16))


def digest(path: Path, algo: str = "sha256") -> str:
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


def wait_ready(process: subprocess.Popen[str], log_path: Path, timeout: int = 180) -> float:
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if log_path.exists() and "Done (" in log_path.read_text("utf-8", errors="replace"):
            return time.monotonic() - started
        time.sleep(1)
    tail = log_path.read_text("utf-8", errors="replace")[-10000:] if log_path.exists() else ""
    raise RuntimeError(f"server readiness failed; exit={process.poll()} tail={tail!r}")


def send(process: subprocess.Popen[str], line: str) -> None:
    if process.stdin is None:
        raise RuntimeError("server stdin unavailable")
    process.stdin.write(line + "\n")
    process.stdin.flush()


def parse(log: str) -> dict[str, list[dict[str, Any]]]:
    hits: dict[tuple[str, int, int], list[int]] = {}
    for line in log.splitlines():
        marker = "MSPROBE "
        if marker not in line:
            continue
        try:
            tail = line.split(marker, 1)[1]
            scale, x_s, z_s, y_s = tail.split()[:4]
            hits.setdefault((scale, int(x_s), int(z_s)), []).append(int(y_s))
        except Exception:
            continue

    result: dict[str, list[dict[str, Any]]] = {}
    for scale, coords in SCALES.items():
        points = []
        for x in coords:
            for z in coords:
                vals = hits.get((scale, x, z), [])
                points.append({
                    "scale": scale,
                    "x": x,
                    "z": z,
                    "surface_y": max(vals) if vals else None,
                })
        result[scale] = points
    return result


def summarize(points: list[dict[str, Any]]) -> dict[str, Any]:
    vals = [p["surface_y"] for p in points if p["surface_y"] is not None]
    if not vals:
        return {"count": 0, "min": None, "max": None, "mean": None, "relief": None, "stdev": None}
    mean = sum(vals) / len(vals)
    variance = sum((v - mean) ** 2 for v in vals) / len(vals)
    return {
        "count": len(vals),
        "min": min(vals),
        "max": max(vals),
        "mean": mean,
        "relief": max(vals) - min(vals),
        "stdev": math.sqrt(variance),
    }


def neighbor_variation(point: dict[str, Any], by_coord: dict[tuple[int, int], dict[str, Any]], step: int) -> float:
    y = point["surface_y"]
    if y is None:
        return 9999.0
    vals = []
    for dx, dz in ((step, 0), (-step, 0), (0, step), (0, -step)):
        q = by_coord.get((point["x"] + dx, point["z"] + dz))
        if q and q["surface_y"] is not None:
            vals.append(abs(y - q["surface_y"]))
    return sum(vals) / len(vals) if vals else 0.0


def nominate(probes: dict[str, list[dict[str, Any]]], run_id: str) -> list[dict[str, Any]]:
    candidates = []
    for scale, points in probes.items():
        coords = SCALES[scale]
        step = abs(coords[1] - coords[0])
        by_coord = {(p["x"], p["z"]): p for p in points}
        stats = summarize(points)
        mean = stats["mean"]
        for p in points:
            y = p["surface_y"]
            if y is None:
                score = 10000.0
                deviation = None
            else:
                deviation = abs(y - mean) if mean is not None else 0.0
                score = deviation + 2.0 * neighbor_variation(p, by_coord, step)
            candidates.append({**p, "score": score, "deviation": deviation})

    valid = [p for p in candidates if p["surface_y"] is not None]
    if not valid:
        return [{
            "site_id": "anomaly_no_surface",
            "category": "anomaly-defect",
            "position": [0, 160, 0],
            "look_at": [0, 64, 0],
            "reason": "No surface samples were observed; inspect generator/probe failure.",
            "metrics_ref": "analysis/multiscale-terrain.json",
        }]

    # Distinct deterministic nominations.
    top = max(valid, key=lambda p: (p["score"], abs(p["x"]) + abs(p["z"])))
    dull = min(valid, key=lambda p: (p["score"], abs(p["x"]) + abs(p["z"])))
    all_mean = sum(p["surface_y"] for p in valid) / len(valid)
    rep = min(valid, key=lambda p: (abs(p["surface_y"] - all_mean), abs(p["x"]) + abs(p["z"])))
    missing = next((p for p in candidates if p["surface_y"] is None), None)
    random_control = min(valid, key=lambda p: hashlib.sha256(f"{run_id}:{p['scale']}:{p['x']}:{p['z']}".encode()).hexdigest())

    selected = [
        ("top_interest", "top-interest", top, f"Highest deterministic terrain-interest score ({top['score']:.2f}) from elevation deviation + neighbor variation."),
        ("bottom_dull", "bottom-dull", dull, f"Lowest deterministic terrain-interest score ({dull['score']:.2f}); intentionally retained dull/control view."),
        ("representative", "representative", rep, f"Surface elevation closest to the aggregate sampled mean ({all_mean:.2f})."),
        ("spawn_overview", "spawn-progression", min(valid, key=lambda p: abs(p["x"]) + abs(p["z"])), "Nearest sampled site to world origin/spawn region."),
        ("random_control", "random-control", random_control, "Deterministic hash-selected control site independent of saliency score."),
    ]
    if missing is not None:
        selected.append(("anomaly_missing_surface", "anomaly-defect", missing, "Probe observed no non-air sample at this coordinate; inspect for void/probe anomaly."))

    sites = []
    seen = set()
    for site_id, category, p, reason in selected:
        key = (p["x"], p["z"], category)
        if key in seen:
            continue
        seen.add(key)
        y = p["surface_y"] if p["surface_y"] is not None else 64
        camera_y = min(315, y + 64)
        sites.append({
            "site_id": site_id,
            "category": category,
            "position": [p["x"], camera_y, p["z"] - 32],
            "look_at": [p["x"], y, p["z"]],
            "reason": f"[{p['scale']}] {reason}",
            "teleport": f"/tp @s {p['x']} {camera_y} {p['z'] - 32} facing {p['x']} {y} {p['z']}",
            "metrics_ref": "analysis/multiscale-terrain.json",
        })
    return sites


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world-zip", type=Path, required=True)
    ap.add_argument("--release-evidence", type=Path, required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()

    evidence = json.loads(args.release_evidence.read_text("utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "analysis").mkdir(exist_ok=True)
    (args.output_dir / "tour").mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="worldgen-multiscale-") as td:
        root = Path(td)
        with zipfile.ZipFile(args.world_zip) as zf:
            zf.extractall(root)
        world = root / "world"
        if not (world / "level.dat").exists():
            raise RuntimeError("world zip missing level.dat")

        server = root / "server.jar"
        download_server(evidence, server)
        (root / "eula.txt").write_text("eula=true\n", "utf-8")
        (root / "server.properties").write_text(
            "\n".join([
                "online-mode=false",
                "white-list=false",
                "server-port=25570",
                "view-distance=3",
                "simulation-distance=3",
                "spawn-protection=0",
                "max-players=1",
                "enable-rcon=false",
                "enable-query=false",
                "allow-flight=true",
                "gamemode=spectator",
                "difficulty=peaceful",
                "spawn-monsters=false",
                "spawn-animals=false",
                "level-name=world",
                "motd=SupraCraft multiscale worldgen analysis",
                "",
            ]),
            "utf-8",
        )

        log_path = root / "analysis-server.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                ["java", "-Xms512M", "-Xmx3G", "-jar", str(server), "nogui"],
                cwd=root,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            ready = wait_ready(process, log_path)

            # Generate/load sparse probe chunks only. This is a disposable analysis copy.
            for coords in SCALES.values():
                for x in coords:
                    for z in coords:
                        send(process, f"forceload add {x} {z}")
            send(process, "gamerule doMobSpawning false")
            send(process, "save-all flush")
            time.sleep(25)

            for scale, coords in SCALES.items():
                for x in coords:
                    for z in coords:
                        for y in YS:
                            send(process, f"execute unless block {x} {y} {z} minecraft:air run say MSPROBE {scale} {x} {z} {y}")
            send(process, "save-all flush")
            time.sleep(10)
            send(process, "forceload remove all")
            send(process, "save-all flush")
            time.sleep(2)
            send(process, "stop")
            code = process.wait(timeout=60)

        log_text = log_path.read_text("utf-8", errors="replace")
        if code != 0:
            raise RuntimeError(f"analysis server exited {code}; tail={log_text[-8000:]!r}")
        errors = [line for line in log_text.splitlines() if "/ERROR]:" in line or "/ERROR] " in line]
        if errors:
            raise RuntimeError("analysis server emitted ERROR lines: " + " | ".join(errors[-20:]))

        probes = parse(log_text)
        summaries = {scale: summarize(points) for scale, points in probes.items()}
        analysis = {
            "schema": "supracraft-worldgen-multiscale-terrain/1",
            "run_id": args.run_id,
            "source_world_sha256": digest(args.world_zip),
            "minecraft_version": "26.3",
            "server_sha256": evidence["server_artifact"]["sha256"],
            "ready_seconds": round(ready, 3),
            "scales": summaries,
            "points": probes,
            "limitations": [
                "Bootstrap terrain analysis uses coarse 16-block vertical sampling.",
                "Non-air includes water, vegetation, and structures.",
                "Sparse regional/macro chunks are generated in a disposable copy, not written back to the canonical source world.",
                "No biome/resource/ecology claims are made by this terrain-only analyzer.",
            ],
        }
        (args.output_dir / "analysis" / "multiscale-terrain.json").write_text(
            json.dumps(analysis, indent=2, sort_keys=True) + "\n", "utf-8"
        )

        sites = nominate(probes, args.run_id)
        tour = {
            "schema_version": 1,
            "run_id": args.run_id,
            "sites": sites,
            "tour_start_command": sites[0]["teleport"] if sites else "",
            "pack_id": "external-analysis-manifest",
            "data_pack_major": evidence["artifact_version_json"]["pack_version"]["data_major"],
        }
        (args.output_dir / "tour" / "manifest.json").write_text(
            json.dumps(tour, indent=2, sort_keys=True) + "\n", "utf-8"
        )
        shutil.copy2(log_path, args.output_dir / "analysis" / "server.log")

    receipt = {
        "schema": "supracraft-worldgen-multiscale-analysis-receipt/1",
        "run_id": args.run_id,
        "source_world_sha256": digest(args.world_zip),
        "analysis_sha256": digest(args.output_dir / "analysis" / "multiscale-terrain.json"),
        "tour_manifest_sha256": digest(args.output_dir / "tour" / "manifest.json"),
        "money_usd": 0,
        "repository_visibility": "public",
        "runner_label": "ubuntu-latest",
        "status": "success",
    }
    (args.output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps({"run_id": args.run_id, "scales": summaries, "sites": sites}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
