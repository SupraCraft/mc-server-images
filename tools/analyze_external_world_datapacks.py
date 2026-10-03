#!/usr/bin/env python3
"""Summarize all datapacks in an external Minecraft world without retaining payloads."""

from __future__ import annotations

import argparse
import importlib.util
import json
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

RESOURCE_DIR_NORMALIZATION = {
    "functions": "function",
    "advancements": "advancement",
    "predicates": "predicate",
    "loot_tables": "loot_table",
    "recipes": "recipe",
    "item_modifiers": "item_modifier",
}


def pack_root_stats(world: Path) -> dict:
    dp = world / "datapacks"
    packs = {}
    if not dp.is_dir():
        return packs
    for entry in sorted(dp.iterdir()):
        if entry.is_dir():
            files=[p for p in entry.rglob("*") if p.is_file()]
            ext=Counter((p.suffix.lower() or "<none>") for p in files)
            resource=Counter()
            namespace=Counter()
            for p in files:
                rel=p.relative_to(entry)
                parts=rel.parts
                if len(parts)>=3 and parts[0]=="data":
                    namespace[parts[1]]+=1
                    kind=RESOURCE_DIR_NORMALIZATION.get(parts[2],parts[2])
                    if kind=="worldgen" and len(parts)>=4:
                        kind=f"worldgen/{parts[3]}"
                    resource[kind]+=1
            packs[entry.name]={
                "container":"directory",
                "file_count":len(files),
                "byte_count":sum(p.stat().st_size for p in files),
                "extension_counts":dict(sorted(ext.items())),
                "resource_kind_counts":dict(sorted(resource.items())),
                "namespace_file_counts":dict(sorted(namespace.items())),
            }
        elif entry.suffix.lower()==".zip":
            # The causal analyzer supports zip datapacks. For the privacy-safe
            # receipt we retain only file-system metadata for the zip container.
            packs[entry.name]={
                "container":"zip",
                "byte_count":entry.stat().st_size,
            }
    return packs


def story_signals(causal: dict) -> dict:
    roles=causal.get("role_counts",{})
    verbs=causal.get("verb_counts",{})
    edge_counts=Counter(e.get("edge_type") for e in causal.get("edges",[]))
    node_kinds=Counter(n.get("kind") for n in causal.get("nodes",[]))
    return {
        "classification":"static_structural_signals_not_runtime_semantics",
        "state_and_progression":{
            "semantic_state_roles":roles.get("semantic_state",0),
            "scoreboard_objective_nodes":node_kinds.get("scoreboard_objective",0),
            "command_storage_nodes":node_kinds.get("command_storage",0),
            "advancement_nodes":node_kinds.get("advancement",0),
            "trigger_commands":verbs.get("trigger",0),
            "advancement_commands":verbs.get("advancement",0),
        },
        "orchestration":{
            "orchestrator_roles":roles.get("orchestrator",0),
            "timer_clock_roles":roles.get("timer_clock",0),
            "function_commands":verbs.get("function",0),
            "schedule_commands":verbs.get("schedule",0),
            "function_call_edges":edge_counts.get("function_call",0),
            "function_schedule_edges":edge_counts.get("function_schedule",0),
        },
        "actors_and_multiplayer":{
            "team_commands":verbs.get("team",0),
            "tag_commands":verbs.get("tag",0),
            "gamemode_commands":verbs.get("gamemode",0),
            "spawnpoint_commands":verbs.get("spawnpoint",0),
            "tp_commands":verbs.get("tp",0)+verbs.get("teleport",0),
        },
        "items_and_rewards":{
            "give_commands":verbs.get("give",0),
            "clear_commands":verbs.get("clear",0),
            "item_commands":verbs.get("item",0),
            "loot_commands":verbs.get("loot",0),
            "effect_commands":verbs.get("effect",0),
        },
        "world_mutation":{
            "setblock_commands":verbs.get("setblock",0),
            "fill_commands":verbs.get("fill",0),
            "clone_commands":verbs.get("clone",0),
            "summon_commands":verbs.get("summon",0),
        },
        "observation_and_ui":{
            "presentation_feedback_roles":roles.get("presentation_feedback",0),
            "tellraw_commands":verbs.get("tellraw",0),
            "title_commands":verbs.get("title",0),
            "bossbar_commands":verbs.get("bossbar",0),
            "playsound_commands":verbs.get("playsound",0),
            "particle_commands":verbs.get("particle",0),
        },
    }


def analyze(args) -> dict:
    world=Path(args.world_root).resolve()
    causal=_CAUSAL.analyze(world)
    return {
        "schema":"supracraft-external-world-datapack-summary/1",
        "analysis_kind":"derived_static_structure_only",
        "source":{
            "source_id":args.source_id,
            "claimed_minecraft_version":args.minecraft_version,
            "upstream_repository":args.upstream_repository,
            "upstream_commit":args.upstream_commit,
            "license_label":args.license_label,
        },
        "pack_inventory":pack_root_stats(world),
        "causal_summary":{
            "pack_file_count":causal.get("pack_file_count",0),
            "function_count":causal.get("function_count",0),
            "json_resource_count":causal.get("json_resource_count",0),
            "node_count":causal.get("node_count",0),
            "edge_count":causal.get("edge_count",0),
            "role_counts":causal.get("role_counts",{}),
            "verb_counts":causal.get("verb_counts",{}),
            "unresolved_reference_counts":causal.get("unresolved_reference_counts",{}),
            "advancement_reward_function_edge_count":causal.get(
                "advancement_reward_function_edge_count",0
            ),
        },
        "story_feature_signals":story_signals(causal),
        "raw_content_retained":False,
        "limitations":[
            "Static references do not prove runtime reachability or behavior.",
            "The receipt does not retain function text, JSON payloads, NBT payloads, region data, images, audio or resource-pack content.",
            "Function/resource names may appear only as aggregate namespace or pack names; command payloads are not emitted.",
            "All-Rights-Reserved or otherwise restricted sources remain analysis-only and are never vendored or redistributed.",
            "External prior art never becomes SupraCraft semantic authority without independent exact-version qualification.",
        ],
    }


def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--world-root",required=True,type=Path)
    ap.add_argument("--source-id",required=True)
    ap.add_argument("--minecraft-version",required=True)
    ap.add_argument("--upstream-repository",required=True)
    ap.add_argument("--upstream-commit",required=True)
    ap.add_argument("--license-label",required=True)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    result=analyze(args)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "source":result["source"],
        "pack_inventory":result["pack_inventory"],
        "causal_summary":result["causal_summary"],
        "story_feature_signals":result["story_feature_signals"],
        "raw_content_retained":result["raw_content_retained"],
    },indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
