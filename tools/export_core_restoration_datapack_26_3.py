#!/usr/bin/env python3
"""Export the already-authored vanilla 26.3 core-restoration datapack as a candidate.

This is a real vanilla datapack, NOT a complete Minecraft world, Two Rivers
campaign acceptance, or evidence of COLLAGE deployment. Reuses the existing
exact-runtime restoration probe's datapack generator without reimplementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import tempfile
import zipfile

from probe_core_restoration_datapack_26_3 import write_datapack

REPO = pathlib.Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
FIXED_DATE = (1980, 1, 1, 0, 0, 0)
EXPECTED_MEMBERS = (
    "pack.mcmeta",
    "data/minecraft/tags/function/tick.json",
    "data/supracraft_core_restore/function/tick.mcfunction",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def exact_source_commit() -> str:
    p = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                       capture_output=True, text=True, timeout=10, check=True)
    sha = p.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("unqualified source revision")
    return sha


def export(out: pathlib.Path, manifest: pathlib.Path, *,
           world_id: str, release_id: str) -> dict:
    if not IDENTIFIER.fullmatch(world_id) or not IDENTIFIER.fullmatch(release_id):
        raise ValueError("world_id/release_id must be bounded identifiers")
    if out.resolve() == manifest.resolve() or out.suffix != ".zip":
        raise ValueError("distinct .zip artifact and manifest paths required")

    with tempfile.TemporaryDirectory(prefix="supracraft-datapack-export-") as td:
        root = pathlib.Path(td)
        authored = write_datapack(root)
        pack = root / "world" / "datapacks" / "supracraft_core_restore"
        members = sorted(p.relative_to(pack).as_posix()
                         for p in pack.rglob("*") if p.is_file())
        if tuple(members) != tuple(sorted(EXPECTED_MEMBERS)):
            raise RuntimeError("datapack generator emitted an unexpected member set")
        if authored["metadata"]["pack"]["min_format"] != [121, 0] or (
                authored["metadata"]["pack"]["max_format"] != [121, 0]):
            raise RuntimeError("vanilla 26.3 datapack format drift")
        payloads = {name: (pack / name).read_bytes() for name in members}

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as zf:
        for name in members:
            entry = zipfile.ZipInfo(name, date_time=FIXED_DATE)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = (0o100644 << 16)
            zf.writestr(entry, payloads[name], compresslevel=9)
    content = out.read_bytes()
    if len(content) > 1024 * 1024:
        raise RuntimeError("bounded datapack exceeded one MiB")
    evidence = {
        "schema": "supracraft-vanilla-datapack-candidate/1",
        "classification": "SOURCE_ARTIFACT_EXPORTED",
        "kind": "datapack",
        "world_id": world_id,
        "release_id": release_id,
        "minecraft_version": "26.3",
        "backend": "vanilla",
        "producer": "SupraCraft/mc-server-images@" + exact_source_commit(),
        "relative_path": out.name,
        "sha256": sha256(content),
        "archive_size": len(content),
        "members": [{"path": name, "sha256": sha256(payloads[name]),
                     "bytes": len(payloads[name])} for name in members],
        "pack_format": [121, 0],
        "source_generator": "tools/probe_core_restoration_datapack_26_3.py:write_datapack",
        "artifact_format_verified": True,
        "world_save_included": False,
        "full_two_rivers_world_qualified": False,
        "collage_deployed": False,
        "minecraft_runtime_verified_by_this_export": False,
        "next_gate": "IMMUTABLE_ARTIFACT_STAGE_TO_REAL_DISPOSABLE_VANILLA_WORLD",
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--manifest", required=True, type=pathlib.Path)
    parser.add_argument("--world-id", required=True)
    parser.add_argument("--release-id", required=True)
    args = parser.parse_args()
    receipt = export(args.out, args.manifest, world_id=args.world_id,
                     release_id=args.release_id)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
