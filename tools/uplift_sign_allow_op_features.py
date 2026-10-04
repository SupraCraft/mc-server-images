#!/usr/bin/env python3
"""Uplift direct sign command payloads that require op text features in Java 26.3.

Safe scope is intentionally narrow:
- mcfunction setblock commands, including execute ... run setblock;
- the block id itself proves a sign or hanging-sign target;
- the same block-entity SNBT contains a click_event with action:"run_command";
- allow_op_features is not already present.

Cross-command cases where a sign is created first and privileged text is merged or
copied later are deliberately not rewritten here.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SIGN_ID_RE = re.compile(
    r"^(?:minecraft:)?[a-z0-9_.-]+:(?:[a-z0-9_./-]*_)?(?:wall_)?(?:hanging_)?sign$"
    r"|^(?:minecraft:)?(?:[a-z0-9_./-]*_)?(?:wall_)?(?:hanging_)?sign$"
)
RUN_COMMAND_RE = re.compile(
    r'click_event\s*:\s*\{[^{}]*action\s*:\s*["\']run_command["\']',
    re.IGNORECASE,
)


def find_matching_brace(text: str, start: int) -> int:
    if start >= len(text) or text[start] != "{":
        raise ValueError("expected opening brace")
    depth = 0
    in_string = False
    quote = ""
    escape = False
    for i in range(start, len(text)):
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
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unterminated block-entity SNBT")


def base_block_id(block_spec: str) -> str:
    return block_spec.split("[", 1)[0]


def is_sign_id(block_id: str) -> bool:
    token = block_id
    if ":" not in token:
        token = "minecraft:" + token
    ns, path = token.split(":", 1)
    if ns != "minecraft":
        return False
    return path.endswith("_sign") or path.endswith("_wall_sign") or path.endswith("_hanging_sign") or path.endswith("_wall_hanging_sign")


def top_level_has_key(body: str, key: str) -> bool:
    depth_curly = depth_square = 0
    in_string = False
    quote = ""
    escape = False
    i = 0
    while i < len(body):
        ch = body[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            i += 1
            continue
        if ch in {'"', "'"}:
            in_string = True
            quote = ch
            i += 1
            continue
        if ch == "{":
            depth_curly += 1
        elif ch == "}":
            depth_curly -= 1
        elif ch == "[":
            depth_square += 1
        elif ch == "]":
            depth_square -= 1
        elif depth_curly == 0 and depth_square == 0 and body.startswith(key, i):
            before_ok = i == 0 or not (body[i - 1].isalnum() or body[i - 1] in "_:")
            j = i + len(key)
            after_ok = j >= len(body) or not (body[j].isalnum() or body[j] in "_:")
            k = j
            while k < len(body) and body[k].isspace():
                k += 1
            if before_ok and after_ok and k < len(body) and body[k] == ":":
                return True
        i += 1
    return False


def rewrite_line(line: str, line_offset: int) -> tuple[str, dict[str, Any] | None]:
    pos = line.find("setblock ")
    if pos < 0:
        return line, None

    prefix = line[:pos]
    if prefix.strip() and not prefix.rstrip().endswith("run"):
        return line, None

    tail = line[pos + len("setblock "):]
    parts = tail.split(maxsplit=3)
    if len(parts) < 4:
        return line, None
    _x, _y, _z, rest = parts

    open_brace = rest.find("{")
    if open_brace < 0:
        return line, None
    block_spec = rest[:open_brace].strip()
    block_id = base_block_id(block_spec)
    if not is_sign_id(block_id):
        return line, None

    close_brace = find_matching_brace(rest, open_brace)
    nbt = rest[open_brace:close_brace + 1]
    body = nbt[1:-1]
    if not RUN_COMMAND_RE.search(body):
        return line, None
    if top_level_has_key(body, "allow_op_features"):
        return line, None

    new_body = body + ("," if body.strip() else "") + "allow_op_features:1b"
    new_nbt = "{" + new_body + "}"
    updated_rest = rest[:open_brace] + new_nbt + rest[close_brace + 1:]
    updated = line[:pos + len("setblock ")] + " ".join(parts[:3]) + " " + updated_rest

    return updated, {
        "offset": line_offset + pos,
        "block_id": block_id,
        "change": "add_allow_op_features_true",
    }


def rewrite_text(text: str) -> tuple[str, list[dict[str, Any]]]:
    out: list[str] = []
    receipts: list[dict[str, Any]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        ending = ""
        core = line
        if line.endswith("\r\n"):
            core, ending = line[:-2], "\r\n"
        elif line.endswith("\n"):
            core, ending = line[:-1], "\n"
        updated, receipt = rewrite_line(core, offset)
        out.append(updated + ending)
        if receipt:
            receipts.append(receipt)
        offset += len(line)

    if text and not text.endswith(("\n", "\r")) and not out:
        updated, receipt = rewrite_line(text, 0)
        return updated, [receipt] if receipt else []
    return "".join(out), receipts


def process_file(source: Path, output: Path) -> dict[str, Any]:
    text = source.read_text("utf-8")
    updated, receipts = rewrite_text(text)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(updated, "utf-8")
    return {
        "schema": "supracraft-sign-op-features-26.2-to-26.3-uplift/1",
        "source": str(source),
        "output": str(output),
        "changed_direct_sign_count": len(receipts),
        "receipts": receipts,
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

    if args.require_change and receipt["changed_direct_sign_count"] == 0:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
