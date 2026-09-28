#!/usr/bin/env python3
"""Independent deterministic validation for one bootstrap worldgen run directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

APPROVED_RUNNERS = {"ubuntu-latest", "ubuntu-24.04", "ubuntu-26.04", "macos-26"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--release-evidence", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    errors: list[str] = []
    receipt = json.loads((args.run_dir / "receipt.json").read_text())
    provenance = json.loads((args.run_dir / "provenance.json").read_text())
    terrain = json.loads((args.run_dir / "analysis" / "terrain.json").read_text())
    release = json.loads(args.release_evidence.read_text())

    execution = receipt.get("execution", {})
    if execution.get("repository_visibility") != "public":
        errors.append("receipt repository_visibility is not public")
    if execution.get("money_usd") != 0:
        errors.append("receipt money_usd is not zero")
    if execution.get("runner_label") not in APPROVED_RUNNERS:
        errors.append(f"receipt runner_label {execution.get('runner_label')!r} is not approved")
    if receipt.get("minecraft_version") != "26.3":
        errors.append("receipt minecraft_version is not 26.3")
    if provenance.get("server_artifact_sha256") != release["server_artifact"]["sha256"]:
        errors.append("server artifact SHA-256 does not match qualified 26.3 evidence")

    artifact_map = {item["path"]: item for item in receipt.get("artifacts", [])}
    for rel in ("world.zip", "analysis/terrain.json", "tour/manifest.json", "provenance.json"):
        path = args.run_dir / rel
        if not path.exists():
            errors.append(f"missing artifact {rel}")
            continue
        recorded = artifact_map.get(rel, {}).get("sha256")
        actual = sha256(path)
        if recorded != actual:
            errors.append(f"artifact hash mismatch for {rel}: recorded={recorded} actual={actual}")

    world_zip = args.run_dir / "world.zip"
    world_entries: list[str] = []
    if world_zip.exists():
        with zipfile.ZipFile(world_zip) as zf:
            world_entries = zf.namelist()
        if "world/level.dat" not in world_entries:
            errors.append("world.zip lacks world/level.dat")
        if not any(name.startswith("world/region/") and name.endswith(".mca") for name in world_entries):
            errors.append("world.zip lacks overworld region data")
        if "world/SUPRACRAFT-TOUR.json" not in world_entries:
            errors.append("world.zip lacks embedded SupraCraft tour manifest")
        if "world/datapacks/supracraft_benchmark/pack.mcmeta" not in world_entries:
            errors.append("world.zip lacks SupraCraft tour datapack")

    if terrain.get("observed_count", 0) <= 0:
        errors.append("terrain probe observed no non-air samples")

    result = {
        "schema": "supracraft-worldgen-bootstrap-validation/1",
        "run_id": receipt.get("run_id"),
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "checks": {
            "public_repository_receipt": execution.get("repository_visibility") == "public",
            "zero_money_receipt": execution.get("money_usd") == 0,
            "approved_runner_receipt": execution.get("runner_label") in APPROVED_RUNNERS,
            "minecraft_26_3": receipt.get("minecraft_version") == "26.3",
            "qualified_server_sha256": provenance.get("server_artifact_sha256") == release["server_artifact"]["sha256"],
            "world_level_dat": "world/level.dat" in world_entries,
            "world_region_data": any(name.startswith("world/region/") and name.endswith(".mca") for name in world_entries),
            "embedded_tour_manifest": "world/SUPRACRAFT-TOUR.json" in world_entries,
            "embedded_tour_datapack": "world/datapacks/supracraft_benchmark/pack.mcmeta" in world_entries,
            "terrain_probe_nonempty": terrain.get("observed_count", 0) > 0,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
