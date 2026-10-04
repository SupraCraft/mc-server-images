#!/usr/bin/env python3
"""Safely uplift Java 26.2 predicate JSON to the 26.3 predicate schema.

Scope is deliberately schema-aware:
- the file root is a predicate value;
- all_of/any_of terms are predicate values;
- inverted.term is a predicate value;
- legacy minecraft:reference predicate values collapse to their referenced id.

Arbitrary nested dictionaries such as entity predicate/component payloads are
not recursively treated as predicates merely because they contain a key named
"condition".
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


COMPOSITES = {"minecraft:all_of", "minecraft:any_of"}


def uplift_predicate_value(value: Any, pointer: str = "") -> tuple[Any, list[dict[str, Any]]]:
    changes: list[dict[str, Any]] = []

    if isinstance(value, str):
        return value, changes
    if not isinstance(value, dict):
        return copy.deepcopy(value), changes

    out = copy.deepcopy(value)
    old_condition = out.get("condition")
    predicate_type = out.get("type")

    if isinstance(old_condition, str) and predicate_type is None:
        out["type"] = out.pop("condition")
        predicate_type = old_condition
        changes.append({
            "rule": "predicate_condition_to_type",
            "pointer": pointer or "/",
            "from": old_condition,
            "to": old_condition,
        })

    if predicate_type == "minecraft:reference":
        name = out.get("name")
        allowed = {"type", "name"}
        if isinstance(name, str) and set(out) <= allowed:
            changes.append({
                "rule": "predicate_reference_to_id",
                "pointer": pointer or "/",
                "reference": name,
            })
            return name, changes

    if predicate_type in COMPOSITES:
        terms = out.get("terms")
        if isinstance(terms, list):
            new_terms = []
            for i, term in enumerate(terms):
                new_term, nested = uplift_predicate_value(
                    term, f"{pointer}/terms/{i}" if pointer else f"/terms/{i}"
                )
                new_terms.append(new_term)
                changes.extend(nested)
            out["terms"] = new_terms

    elif predicate_type == "minecraft:inverted":
        if "term" in out:
            new_term, nested = uplift_predicate_value(
                out["term"], f"{pointer}/term" if pointer else "/term"
            )
            out["term"] = new_term
            changes.extend(nested)

    return out, changes


def uplift_predicate_document(data: Any) -> tuple[Any, list[dict[str, Any]]]:
    return uplift_predicate_value(data)


def process_file(source: Path, output: Path) -> dict[str, Any]:
    data = json.loads(source.read_text("utf-8"))
    updated, changes = uplift_predicate_document(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n", "utf-8")
    return {
        "schema": "supracraft-predicate-26.2-to-26.3-uplift/1",
        "source": str(source),
        "output": str(output),
        "change_count": len(changes),
        "counts_by_rule": {
            rule: sum(1 for x in changes if x["rule"] == rule)
            for rule in sorted({x["rule"] for x in changes})
        },
        "changes": changes,
        "source_unchanged": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--receipt", type=Path)
    ap.add_argument("--require-change", action="store_true")
    args = ap.parse_args()

    if args.source.resolve() == args.output.resolve():
        ap.error("source and output must differ")

    receipt = process_file(args.source, args.output)
    payload = json.dumps(receipt, indent=2, sort_keys=True)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(payload + "\n", "utf-8")
    else:
        print(payload)

    if args.require_change and receipt["change_count"] == 0:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
