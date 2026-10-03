#!/usr/bin/env python3
"""Produce provenance-safe structural receipts for external Minecraft datapacks.

The analyzer materializes the datapack view for one explicit pack format,
including matching overlays, then reuses SupraCraft's existing datapack causal
analyzer. It intentionally emits derived metadata only: no mcfunction command
text, JSON payloads, NBT payloads, or third-party files are retained.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "supracraft_datapack_causal",
    HERE / "analyze_datapack_causal_semantics.py",
)
_CAUSAL = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_CAUSAL)

KIND_NORMALIZATION = {
    "functions": "function",
    "advancements": "advancement",
    "predicates": "predicate",
    "loot_tables": "loot_table",
    "recipes": "recipe",
    "item_modifiers": "item_modifier",
    "structures": "structure",
}

WORLDGEN_KINDS = {
    "worldgen",
    "dimension",
    "dimension_type",
    "worldgen/biome",
    "worldgen/configured_carver",
    "worldgen/configured_feature",
    "worldgen/noise",
    "worldgen/noise_settings",
    "worldgen/placed_feature",
    "worldgen/processor_list",
    "worldgen/structure",
    "worldgen/structure_set",
    "worldgen/template_pool",
}


def parse_format(value: str) -> tuple[int, int]:
    parts = value.strip().split(".", 1)
    major = int(parts[0])
    minor = int(parts[1]) if len(parts) == 2 else 0
    return major, minor


def normalize_format(value) -> tuple[int, int]:
    if isinstance(value, int):
        return value, 0
    if isinstance(value, list) and value:
        return int(value[0]), int(value[1]) if len(value) > 1 else 0
    raise ValueError(f"unsupported pack format value: {value!r}")


def format_text(value: tuple[int, int]) -> str:
    return f"{value[0]}.{value[1]}"


def in_range(target: tuple[int, int], low, high) -> bool:
    return normalize_format(low) <= target <= normalize_format(high)


def load_pack_meta(root: Path) -> dict:
    path = root / "pack.mcmeta"
    if not path.is_file():
        raise FileNotFoundError(f"missing pack.mcmeta: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def selected_overlays(meta: dict, target: tuple[int, int]) -> list[dict]:
    out = []
    for entry in meta.get("overlays", {}).get("entries", []):
        if not isinstance(entry, dict) or "directory" not in entry:
            continue
        low = entry.get("min_format")
        high = entry.get("max_format")
        if low is None or high is None:
            continue
        if in_range(target, low, high):
            out.append(
                {
                    "directory": str(entry["directory"]),
                    "min_format": format_text(normalize_format(low)),
                    "max_format": format_text(normalize_format(high)),
                }
            )
    return out


def copy_merge(src: Path, dst: Path) -> int:
    if not src.exists():
        return 0
    files = [p for p in src.rglob("*") if p.is_file()]
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return len(files)


def materialize_effective_pack(
    source_root: Path, target_format: tuple[int, int], output_root: Path
) -> dict:
    meta = load_pack_meta(source_root)
    output_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_root / "pack.mcmeta", output_root / "pack.mcmeta")

    base_count = copy_merge(source_root / "data", output_root / "data")
    overlays = selected_overlays(meta, target_format)
    applied = []
    for entry in overlays:
        directory = entry["directory"]
        src = source_root / directory
        file_count = copy_merge(src / "data", output_root / "data")
        applied.append({**entry, "source_file_count": file_count, "present": src.exists()})

    return {
        "base_data_file_count": base_count,
        "selected_overlays": applied,
    }


def effective_digest(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix().encode("utf-8")
        h.update(len(rel).to_bytes(4, "big"))
        h.update(rel)
        data_hash = hashlib.sha256(path.read_bytes()).digest()
        h.update(data_hash)
    return h.hexdigest()


def resource_kind(path: Path, root: Path) -> str | None:
    rel = path.relative_to(root)
    parts = rel.parts
    if len(parts) < 4 or parts[0] != "data":
        return None
    kind = KIND_NORMALIZATION.get(parts[2], parts[2])
    if kind == "worldgen" and len(parts) >= 5:
        return f"worldgen/{parts[3]}"
    return kind


def summarize_resources(root: Path) -> dict:
    kinds = Counter()
    extensions = Counter()
    predicate_schema = Counter()
    parse_errors = 0

    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        extensions[path.suffix.lower() or "<none>"] += 1
        kind = resource_kind(path, root)
        if kind:
            kinds[kind] += 1

        rel_parts = path.relative_to(root).parts
        normalized_parts = {KIND_NORMALIZATION.get(x, x) for x in rel_parts}
        if "predicate" in normalized_parts and path.suffix.lower() == ".json":
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                parse_errors += 1
                predicate_schema["parse_error"] += 1
                continue
            if not isinstance(obj, dict):
                predicate_schema["non_object"] += 1
            elif "type" in obj and "condition" in obj:
                predicate_schema["both_type_and_condition"] += 1
            elif "type" in obj:
                predicate_schema["type"] += 1
            elif "condition" in obj:
                predicate_schema["condition"] += 1
            else:
                predicate_schema["other"] += 1

    return {
        "resource_kind_counts": dict(sorted(kinds.items())),
        "extension_counts": dict(sorted(extensions.items())),
        "predicate_top_level_schema_counts": dict(sorted(predicate_schema.items())),
        "json_parse_error_count": parse_errors,
    }


def story_feature_signals(causal: dict, resources: dict) -> dict:
    roles = causal.get("role_counts", {})
    verbs = causal.get("verb_counts", {})
    kinds = resources.get("resource_kind_counts", {})
    worldgen_count = sum(v for k, v in kinds.items() if k.startswith("worldgen/"))

    return {
        "classification": "structural_signals_not_qualified_semantics",
        "state_and_progression": {
            "semantic_state_command_count": roles.get("semantic_state", 0),
            "advancement_resource_count": kinds.get("advancement", 0),
            "scoreboard_objective_node_count": sum(
                1 for n in causal.get("nodes", []) if n.get("kind") == "scoreboard_objective"
            ),
            "command_storage_node_count": sum(
                1 for n in causal.get("nodes", []) if n.get("kind") == "command_storage"
            ),
        },
        "timing_and_orchestration": {
            "timer_clock_command_count": roles.get("timer_clock", 0),
            "orchestrator_command_count": roles.get("orchestrator", 0),
            "schedule_verb_count": verbs.get("schedule", 0),
            "function_call_edge_count": sum(
                1 for e in causal.get("edges", []) if e.get("edge_type") == "function_call"
            ),
            "function_schedule_edge_count": sum(
                1 for e in causal.get("edges", []) if e.get("edge_type") == "function_schedule"
            ),
        },
        "world_mutation": {
            "setblock": verbs.get("setblock", 0),
            "fill": verbs.get("fill", 0),
            "clone": verbs.get("clone", 0),
            "summon": verbs.get("summon", 0),
            "structure_resource_count": kinds.get("structure", 0),
            "worldgen_resource_count": worldgen_count,
        },
        "inventory_and_transformation": {
            "recipe_resource_count": kinds.get("recipe", 0),
            "loot_table_resource_count": kinds.get("loot_table", 0),
            "item_modifier_resource_count": kinds.get("item_modifier", 0),
            "item_command_count": verbs.get("item", 0),
            "loot_command_count": verbs.get("loot", 0),
        },
        "conditions_and_observation": {
            "condition_query_command_count": roles.get("condition_query", 0),
            "predicate_resource_count": kinds.get("predicate", 0),
            "presentation_feedback_command_count": roles.get("presentation_feedback", 0),
            "tellraw": verbs.get("tellraw", 0),
            "title": verbs.get("title", 0),
            "playsound": verbs.get("playsound", 0),
            "particle": verbs.get("particle", 0),
            "bossbar": verbs.get("bossbar", 0),
        },
        "multiplayer_coordination": {
            "team": verbs.get("team", 0),
            "tag": verbs.get("tag", 0),
            "gamemode": verbs.get("gamemode", 0),
            "spawnpoint": verbs.get("spawnpoint", 0),
        },
    }


def analyze(args) -> dict:
    source_root = Path(args.datapack_root).resolve()
    target = parse_format(args.target_pack_format)

    with tempfile.TemporaryDirectory(prefix="external-corpus-") as td:
        world = Path(td) / "world"
        effective = world / "datapacks" / "target"
        overlay_receipt = materialize_effective_pack(source_root, target, effective)
        resources = summarize_resources(effective)
        digest = effective_digest(effective)
        causal = _CAUSAL.analyze(world)

    return {
        "schema": "supracraft-external-datapack-corpus-receipt/1",
        "analysis_kind": "static_structural_feedback_blind_provenance_safe",
        "source": {
            "source_id": args.source_id,
            "claimed_minecraft_version": args.minecraft_version,
            "upstream_repository": args.upstream_repository,
            "upstream_commit": args.upstream_commit,
            "license_label": args.license_label,
        },
        "target_pack_format": format_text(target),
        "overlay_materialization": overlay_receipt,
        "effective_content_sha256": digest,
        "raw_content_retained": False,
        "resource_summary": resources,
        "causal_summary": {
            "pack_file_count": causal.get("pack_file_count", 0),
            "function_count": causal.get("function_count", 0),
            "json_resource_count": causal.get("json_resource_count", 0),
            "node_count": causal.get("node_count", 0),
            "edge_count": causal.get("edge_count", 0),
            "role_counts": causal.get("role_counts", {}),
            "verb_counts": causal.get("verb_counts", {}),
            "unresolved_reference_counts": causal.get("unresolved_reference_counts", {}),
            "advancement_reward_function_edge_count": causal.get(
                "advancement_reward_function_edge_count", 0
            ),
        },
        "story_feature_signals": story_feature_signals(causal, resources),
        "limitations": [
            "Static references and resource presence do not prove runtime reachability or behavior.",
            "Overlay materialization is selected only from pack-format ranges in pack.mcmeta.",
            "Selectors, macros, dynamic resource locations, NBT payload semantics and client presentation require separate analysis.",
            "Third-party raw content is deliberately not retained in this receipt.",
            "Corpus observations are prior art and never become SupraCraft semantic authority without independent exact-version qualification.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datapack-root", required=True, type=Path)
    ap.add_argument("--target-pack-format", required=True)
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
                "target_pack_format": result["target_pack_format"],
                "selected_overlays": [
                    o["directory"]
                    for o in result["overlay_materialization"]["selected_overlays"]
                ],
                "effective_content_sha256": result["effective_content_sha256"],
                "function_count": result["causal_summary"]["function_count"],
                "resource_kind_counts": result["resource_summary"]["resource_kind_counts"],
                "role_counts": result["causal_summary"]["role_counts"],
                "verb_counts": result["causal_summary"]["verb_counts"],
                "predicate_top_level_schema_counts": result["resource_summary"][
                    "predicate_top_level_schema_counts"
                ],
                "unresolved_reference_counts": result["causal_summary"][
                    "unresolved_reference_counts"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
