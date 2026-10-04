#!/usr/bin/env python3
"""Apply an explicit project-scoped filled-map map_color replacement recipe.

The helper is intentionally not a universal Minecraft migration. It requires a
mapping file that names each legacy integer color and its chosen 26.3 item_model.
Unknown values and already-modeled items are preserved and reported.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


START = "minecraft:filled_map["
MAP_COLOR_RE = re.compile(r"(?<![A-Za-z0-9_:])map_color\s*=\s*(\d+)")
ITEM_MODEL_RE = re.compile(r"(?<![A-Za-z0-9_:])item_model\s*=")


def find_matching_square(text: str, open_index: int) -> int:
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(open_index, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in {'"', "'"}:
            in_string = True
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unterminated filled-map component list")


def rewrite_text(text: str, mapping: dict[str, str]) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    out: list[str] = []
    cursor = 0
    receipts: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    while True:
        start = text.find(START, cursor)
        if start < 0:
            out.append(text[cursor:])
            break

        open_index = start + len(START) - 1
        close_index = find_matching_square(text, open_index)
        body = text[open_index + 1:close_index]

        out.append(text[cursor:start])
        replacement = text[start:close_index + 1]

        color_match = MAP_COLOR_RE.search(body)
        if color_match and not ITEM_MODEL_RE.search(body):
            color = color_match.group(1)
            model = mapping.get(color)
            if model is None:
                unresolved.append({
                    "offset": start,
                    "map_color": color,
                    "reason": "unmapped_color",
                })
            else:
                new_body = (
                    body[:color_match.start()]
                    + f'item_model="{model}"'
                    + body[color_match.end():]
                )
                replacement = START[:-1] + "[" + new_body + "]"
                receipts.append({
                    "offset": start,
                    "map_color": color,
                    "item_model": model,
                })
        elif color_match and ITEM_MODEL_RE.search(body):
            unresolved.append({
                "offset": start,
                "map_color": color_match.group(1),
                "reason": "item_model_already_present",
            })

        out.append(replacement)
        cursor = close_index + 1

    return "".join(out), receipts, unresolved


def load_mapping(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text("utf-8"))
    mapping = data.get("mapping")
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("mapping file must contain a non-empty mapping object")
    out = {}
    for key, value in mapping.items():
        if not str(key).isdigit() or not isinstance(value, str) or not value:
            raise ValueError(f"invalid mapping entry: {key!r}: {value!r}")
        out[str(key)] = value
    return out


def process_file(source: Path, output: Path, mapping_path: Path) -> dict[str, Any]:
    mapping = load_mapping(mapping_path)
    text = source.read_text("utf-8")
    updated, receipts, unresolved = rewrite_text(text, mapping)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(updated, "utf-8")
    return {
        "schema": "supracraft-map-color-project-materialization/1",
        "source": str(source),
        "output": str(output),
        "mapping": str(mapping_path),
        "changed_occurrence_count": len(receipts),
        "unresolved_occurrence_count": len(unresolved),
        "receipts": receipts,
        "unresolved": unresolved,
        "source_unchanged": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--mapping", type=Path, required=True)
    ap.add_argument("--receipt", type=Path)
    ap.add_argument("--require-change", action="store_true")
    ap.add_argument("--fail-on-unresolved", action="store_true")
    args = ap.parse_args()

    if args.source.resolve() == args.output.resolve():
        ap.error("source and output must differ")

    receipt = process_file(args.source, args.output, args.mapping)
    payload = json.dumps(receipt, indent=2, sort_keys=True)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(payload + "\n", "utf-8")
    else:
        print(payload)

    if args.require_change and receipt["changed_occurrence_count"] == 0:
        return 2
    if args.fail_on_unresolved and receipt["unresolved_occurrence_count"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
