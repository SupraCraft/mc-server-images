#!/usr/bin/env python3
"""Candidate migration helper for removed minecraft:swing_animation.

26.3 splits legacy swing-animation behavior into attack/interact surfaces.
This helper intentionally requires an explicit mode and only rewrites direct
quoted item-component map keys. It does not automatically rewrite component
predicates, storage paths, or command control flow that may require command
duplication.

Modes:
- attack:   swing_animation -> attack_animation
- interact: swing_animation -> interact_animation
- both:     duplicate the component value into attack_animation and
            interact_animation

This is STRUCTURAL_REIMPLEMENTATION, not SAFE_SYNTACTIC.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


KEY = '"minecraft:swing_animation"'


def find_value_end(text: str, colon_index: int) -> int:
    i = colon_index + 1
    while i < len(text) and text[i].isspace():
        i += 1
    start = i
    if i >= len(text):
        raise ValueError("missing component value")

    if text[i] in "{[":
        opener = text[i]
        closer = "}" if opener == "{" else "]"
        depth = 0
        in_string = False
        quote = ""
        escape = False
        while i < len(text):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == quote:
                    in_string = False
            else:
                if ch in {'"', "'"}:
                    in_string = True
                    quote = ch
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        return i + 1
            i += 1
        raise ValueError("unterminated component value")

    in_string = False
    quote = ""
    escape = False
    while i < len(text):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
        else:
            if ch in {'"', "'"}:
                in_string = True
                quote = ch
            elif ch in ",}":
                return i
        i += 1
    return i


def rewrite_direct_component_keys(text: str, mode: str) -> tuple[str, list[dict[str, Any]]]:
    if mode not in {"attack", "interact", "both"}:
        raise ValueError(mode)

    out: list[str] = []
    cursor = 0
    receipts: list[dict[str, Any]] = []

    while True:
        start = text.find(KEY, cursor)
        if start < 0:
            out.append(text[cursor:])
            break

        # Negated component keys and arbitrary quoted text are not handled
        # automatically by this direct-map helper.
        if start > 0 and text[start - 1] == "!":
            out.append(text[cursor:start + len(KEY)])
            cursor = start + len(KEY)
            continue

        colon = start + len(KEY)
        while colon < len(text) and text[colon].isspace():
            colon += 1
        if colon >= len(text) or text[colon] != ":":
            out.append(text[cursor:start + len(KEY)])
            cursor = start + len(KEY)
            continue

        value_end = find_value_end(text, colon)
        value = text[colon + 1:value_end]
        out.append(text[cursor:start])

        if mode == "attack":
            replacement = '"minecraft:attack_animation":' + value
        elif mode == "interact":
            replacement = '"minecraft:interact_animation":' + value
        else:
            replacement = (
                '"minecraft:attack_animation":' + value
                + ',"minecraft:interact_animation":' + value
            )

        out.append(replacement)
        receipts.append({
            "offset": start,
            "mode": mode,
            "value_length": len(value),
        })
        cursor = value_end

    return "".join(out), receipts


def classify_unhandled(text: str) -> dict[str, int]:
    return {
        "negated_component_key": text.count('"!minecraft:swing_animation"'),
        "component_predicate": text.count("swing_animation={}"),
        "storage_or_path_reference": text.count(".minecraft:swing_animation"),
    }


def process_file(source: Path, output: Path, mode: str) -> dict[str, Any]:
    text = source.read_text("utf-8")
    updated, receipts = rewrite_direct_component_keys(text, mode)
    unhandled = classify_unhandled(text)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(updated, "utf-8")
    return {
        "schema": "supracraft-swing-animation-26.3-candidate/1",
        "source": str(source),
        "output": str(output),
        "mode": mode,
        "direct_component_rewrite_count": len(receipts),
        "unhandled_control_surface_counts": unhandled,
        "requires_structural_followup": any(unhandled.values()),
        "receipts": receipts,
        "source_unchanged": True,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--mode", choices=["attack", "interact", "both"], required=True)
    ap.add_argument("--receipt", type=Path)
    ap.add_argument("--require-change", action="store_true")
    args = ap.parse_args()

    if args.source.resolve() == args.output.resolve():
        ap.error("source and output must differ")

    receipt = process_file(args.source, args.output, args.mode)
    payload = json.dumps(receipt, indent=2, sort_keys=True)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(payload + "\n", "utf-8")
    else:
        print(payload)

    if args.require_change and receipt["direct_component_rewrite_count"] == 0:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
