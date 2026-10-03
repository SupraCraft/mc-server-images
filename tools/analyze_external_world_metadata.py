#!/usr/bin/env python3
"""Summarize external Minecraft world-save metadata without retaining payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import nbtlib


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def plain(value):
    if hasattr(value, "unpack"):
        try:
            return value.unpack()
        except Exception:
            pass
    return value


def as_mapping(value):
    return value if hasattr(value, "get") and hasattr(value, "keys") else None


def top_keys(value):
    return sorted(str(k) for k in value.keys()) if hasattr(value, "keys") else []


def first_mapping(root):
    for key in ("Data", "data"):
        value = root.get(key) if hasattr(root, "get") else None
        if as_mapping(value) is not None:
            return value
    return root


def count_list(container, names):
    if not hasattr(container, "get"):
        return 0
    for name in names:
        value = container.get(name)
        if value is not None:
            try:
                return len(value)
            except Exception:
                return 0
    return 0


def inspect_level(path: Path) -> dict:
    root = nbtlib.load(path)
    data = first_mapping(root)
    version = data.get("Version") if hasattr(data, "get") else None
    version_map = as_mapping(version)
    datapacks = data.get("DataPacks") if hasattr(data, "get") else None
    datapacks_map = as_mapping(datapacks)
    game_rules = data.get("GameRules") if hasattr(data, "get") else None

    result = {
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "root_keys": top_keys(root),
        "data_keys": top_keys(data),
        "data_version": int(plain(data.get("DataVersion"))) if data.get("DataVersion") is not None else None,
        "game_type": int(plain(data.get("GameType"))) if data.get("GameType") is not None else None,
        "hardcore": bool(plain(data.get("hardcore"))) if data.get("hardcore") is not None else None,
        "allow_commands": bool(plain(data.get("allowCommands"))) if data.get("allowCommands") is not None else None,
        "initialized": bool(plain(data.get("initialized"))) if data.get("initialized") is not None else None,
        "was_modded": bool(plain(data.get("WasModded"))) if data.get("WasModded") is not None else None,
        "game_rule_count": len(game_rules) if hasattr(game_rules, "keys") else 0,
        "enabled_datapack_count": count_list(datapacks_map, ("Enabled", "enabled")) if datapacks_map else 0,
        "disabled_datapack_count": count_list(datapacks_map, ("Disabled", "disabled")) if datapacks_map else 0,
    }
    if version_map is not None:
        result["version"] = {
            "name": str(plain(version_map.get("Name"))) if version_map.get("Name") is not None else None,
            "id": int(plain(version_map.get("Id"))) if version_map.get("Id") is not None else None,
            "snapshot": bool(plain(version_map.get("Snapshot"))) if version_map.get("Snapshot") is not None else None,
            "keys": top_keys(version_map),
        }
    else:
        result["version"] = None
    return result


def inspect_scoreboard(path: Path) -> dict:
    if not path.is_file():
        return {"present": False}
    root = nbtlib.load(path)
    data = first_mapping(root)
    return {
        "present": True,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "root_keys": top_keys(root),
        "data_keys": top_keys(data),
        "objective_count": count_list(data, ("Objectives", "objectives")),
        "score_record_count": count_list(data, ("PlayerScores", "Scores", "scores")),
        "team_count": count_list(data, ("Teams", "teams")),
        "display_slot_count": len(data.get("DisplaySlots", {}))
        if hasattr(data.get("DisplaySlots", {}), "keys")
        else 0,
    }


def inspect_dat_file(path: Path) -> dict:
    try:
        root = nbtlib.load(path)
        data = first_mapping(root)
        return {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "parse": "ok",
            "root_keys": top_keys(root),
            "data_keys": top_keys(data),
        }
    except Exception as exc:
        return {
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
            "parse": "error",
            "error_class": type(exc).__name__,
        }


def count_region_files(world: Path) -> dict:
    counts = Counter()
    for path in world.rglob("*.mca"):
        parts = set(path.parts)
        if "entities" in parts:
            counts["entity_region"] += 1
        elif "poi" in parts:
            counts["poi_region"] += 1
        else:
            counts["chunk_region"] += 1
    return dict(sorted(counts.items()))


def grouped_data_files(world: Path) -> dict:
    data_dir = world / "data"
    if not data_dir.is_dir():
        return {"data_file_count": 0, "groups": {}, "files": {}}

    groups = Counter()
    files = {}
    for path in sorted(p for p in data_dir.glob("*.dat") if p.is_file()):
        name = path.name
        if name.startswith("map_"):
            groups["map"] += 1
            continue
        groups["other"] += 1
        files[name] = inspect_dat_file(path)
    return {
        "data_file_count": sum(groups.values()),
        "groups": dict(sorted(groups.items())),
        "files": files,
    }


def analyze(args) -> dict:
    world = Path(args.world_root).resolve()
    level = world / "level.dat"
    if not level.is_file():
        raise FileNotFoundError(f"missing level.dat: {level}")

    player_counts = {
        "playerdata_files": len(list((world / "playerdata").glob("*.dat"))) if (world / "playerdata").is_dir() else 0,
        "advancement_files": len(list((world / "advancements").glob("*.json"))) if (world / "advancements").is_dir() else 0,
        "stats_files": len(list((world / "stats").glob("*.json"))) if (world / "stats").is_dir() else 0,
    }
    datapack_entries = len(list((world / "datapacks").iterdir())) if (world / "datapacks").is_dir() else 0
    resourcepack_entries = len(list((world / "resourcepacks").iterdir())) if (world / "resourcepacks").is_dir() else 0

    level_info = inspect_level(level)
    level_name = (
        level_info.get("version", {}).get("name")
        if isinstance(level_info.get("version"), dict)
        else None
    )
    claimed = str(args.minecraft_version)
    claimed_match = level_name == claimed

    return {
        "schema": "supracraft-external-world-metadata-receipt/1",
        "analysis_kind": "save_metadata_and_shape_only_no_player_payloads",
        "source": {
            "source_id": args.source_id,
            "claimed_minecraft_version": args.minecraft_version,
            "upstream_repository": args.upstream_repository,
            "upstream_commit": args.upstream_commit,
            "license_label": args.license_label,
        },
        "level": level_info,
        "provenance_checks": {
            "claimed_version_matches_level_name": claimed_match,
            "exact_version_world_authority": claimed_match,
            "classification": (
                "EXACT_VERSION_LEVEL_METADATA_MATCH"
                if claimed_match
                else "STALE_OR_TEMPLATE_LEVEL_METADATA"
            ),
            "rule": (
                "Repository labels, branches, datapack overlays and README claims do not "
                "override level.dat version metadata. A mismatch prevents this source from "
                "serving as exact-version world authority."
            ),
        },
        "scoreboard": inspect_scoreboard(world / "data" / "scoreboard.dat"),
        "world_state_data": grouped_data_files(world),
        "region_file_counts": count_region_files(world),
        "datapack_entry_count": datapack_entries,
        "resourcepack_entry_count": resourcepack_entries,
        "player_artifact_counts_only": player_counts,
        "raw_player_identity_retained": False,
        "raw_nbt_payload_retained": False,
        "limitations": [
            "This receipt records save metadata, counts, key shapes and content hashes only.",
            "Player UUIDs, names, score-holder identities, command payloads and NBT values other than bounded version/game metadata are not retained.",
            "Absence of region files in a source repository does not imply the released downloadable world lacks generated chunks.",
            "Save metadata is prior-art evidence only and does not establish runtime semantics.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--world-root", required=True, type=Path)
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--minecraft-version", required=True)
    ap.add_argument("--upstream-repository", required=True)
    ap.add_argument("--upstream-commit", required=True)
    ap.add_argument("--license-label", required=True)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    result = analyze(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "source_id": result["source"]["source_id"],
                "level": {
                    "data_version": result["level"]["data_version"],
                    "version": result["level"]["version"],
                    "game_rule_count": result["level"]["game_rule_count"],
                    "enabled_datapack_count": result["level"]["enabled_datapack_count"],
                    "disabled_datapack_count": result["level"]["disabled_datapack_count"],
                    "was_modded": result["level"]["was_modded"],
                },
                "provenance_checks": result["provenance_checks"],
                "scoreboard": result["scoreboard"],
                "world_state_groups": result["world_state_data"]["groups"],
                "world_state_file_names": sorted(result["world_state_data"]["files"]),
                "region_file_counts": result["region_file_counts"],
                "datapack_entry_count": result["datapack_entry_count"],
                "resourcepack_entry_count": result["resourcepack_entry_count"],
                "player_artifact_counts_only": result["player_artifact_counts_only"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
