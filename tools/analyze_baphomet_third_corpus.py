#!/usr/bin/env python3
"""Analyze Baphomet42/Data-Packs exact 26.2 -> 26.3 tags as a third corpus."""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
from pathlib import Path
from typing import Any


PREDICATE_SEG = "/predicate/"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def exists(repo: Path, spec: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", spec],
        capture_output=True,
    ).returncode == 0


def show(repo: Path, spec: str) -> str:
    return git(repo, "show", spec)


def parse_json(repo: Path, spec: str) -> Any:
    return json.loads(show(repo, spec))


def canonical(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    changed = [p for p in git(args.repo, "diff", "--name-only", args.old, args.new).splitlines() if p]
    predicate_exact = []
    predicate_candidates = []
    predicate_discriminator_migrated = []
    predicate_additional_delta = []
    predicate_discriminator_mismatch = []
    display_state_candidates = []
    carried_state_candidates = []
    loot_modifier_candidates = []
    swing_attack_candidates = []
    pack_formats = {}

    for ref in (args.old, args.new):
        spec = f"{ref}:datapacks/42source/pack.mcmeta"
        pm = parse_json(args.repo, spec)
        pack_formats[ref] = {
            "min_format": pm["pack"].get("min_format"),
            "max_format": pm["pack"].get("max_format"),
        }

    for path in changed:
        if not exists(args.repo, f"{args.old}:{path}") or not exists(args.repo, f"{args.new}:{path}"):
            continue

        if path.endswith(".json") and PREDICATE_SEG in f"/{path}":
            try:
                old = parse_json(args.repo, f"{args.old}:{path}")
                new = parse_json(args.repo, f"{args.new}:{path}")
            except Exception:
                continue
            if isinstance(old, dict) and "condition" in old and "type" not in old:
                predicate_candidates.append(path)
                migrated = (
                    isinstance(new, dict)
                    and new.get("type") == old.get("condition")
                    and "condition" not in new
                )
                if migrated:
                    predicate_discriminator_migrated.append(path)
                else:
                    predicate_discriminator_mismatch.append(path)

                transformed = dict(old)
                transformed["type"] = transformed.pop("condition")
                if canonical(transformed) == canonical(new):
                    predicate_exact.append(path)
                elif migrated:
                    predicate_additional_delta.append(path)

        if path.endswith(".mcfunction"):
            old_text = show(args.repo, f"{args.old}:{path}")
            new_text = show(args.repo, f"{args.new}:{path}")

            if "carriedBlockState:{Name:" in old_text and "carriedBlockState:{id:" in new_text:
                carried_state_candidates.append(path)

            if re.search(r'DisplayState:\{Name:"minecraft:[^"]+"\}', old_text) and re.search(
                r'DisplayState:"minecraft:[^"]+"', new_text
            ):
                display_state_candidates.append(path)

            if (
                "functions:[" in old_text
                and "modifier:[" in new_text
                and 'function:"set_components"' in old_text
                and 'type:"set_components"' in new_text
            ):
                loot_modifier_candidates.append(path)

            if "minecraft:swing_animation" in old_text and "minecraft:attack_animation" in new_text:
                swing_attack_candidates.append(path)

    result = {
        "schema": "supracraft-third-corpus-baphomet-26.2-26.3/1",
        "repository": "Baphomet42/Data-Packs",
        "source_boundary": (
            "No LICENSE/COPYING file detected at 26.3 tag; repository README grants showcase/fork use with credit. "
            "Analysis remains ephemeral and only derived receipts are retained."
        ),
        "old_ref": args.old,
        "new_ref": args.new,
        "old_commit": git(args.repo, "rev-parse", args.old).strip(),
        "new_commit": git(args.repo, "rev-parse", args.new).strip(),
        "pack_formats": pack_formats,
        "changed_file_count": len(changed),
        "predicate_condition_to_type": {
            "candidate_files": len(predicate_candidates),
            "discriminator_migrated_files": len(predicate_discriminator_migrated),
            "discriminator_mismatch_files": len(predicate_discriminator_mismatch),
            "exact_json_equivalent_files": len(predicate_exact),
            "additional_delta_files": len(predicate_additional_delta),
            "exact_paths": predicate_exact[:100],
            "additional_delta_paths": predicate_additional_delta[:100],
            "mismatch_paths": predicate_discriminator_mismatch[:100],
        },
        "candidate_new_migration_families": {
            "carried_block_state_Name_to_id_files": len(carried_state_candidates),
            "display_state_compound_to_scalar_files": len(display_state_candidates),
            "loot_functions_to_modifier_type_files": len(loot_modifier_candidates),
            "swing_animation_to_attack_animation_files": len(swing_attack_candidates),
        },
        "candidate_samples": {
            "carried_block_state": carried_state_candidates[:25],
            "display_state": display_state_candidates[:25],
            "loot_modifier": loot_modifier_candidates[:25],
            "swing_attack": swing_attack_candidates[:25],
        },
        "classification": (
            "THIRD_CORPUS_PREDICATE_RULE_CONFIRMED"
            if (
                predicate_candidates
                and len(predicate_candidates) == len(predicate_discriminator_migrated)
                and not predicate_discriminator_mismatch
            )
            else "THIRD_CORPUS_REQUIRES_REVIEW"
        ),
        "boundary": (
            "Predicate confirmation is scoped to discriminator migration: old condition value must become the "
            "new top-level type and condition must disappear. Files may contain additional independent 26.3 edits. "
            "Other repeated deltas remain discovery candidates until separately qualified."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))

    if result["classification"] != "THIRD_CORPUS_PREDICATE_RULE_CONFIRMED":
        raise SystemExit(2)

    print("SUPRACRAFT_THIRD_CORPUS_BAPHOMET_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
