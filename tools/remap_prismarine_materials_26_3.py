#!/usr/bin/env python3
"""Exact-source 26.2->26.3 material speed ID uplift for local Prismarine tests.

The pinned 26.3 dataPaths.json points materials to 26.2 even though items have
different numeric IDs. Preserve original material multipliers by item NAME,
then convert them to the 26.3 IDs. Only edits the disposable clone supplied by
the caller; no upstream fork, hardcoded ID translation table, or global state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_if_changed(path: Path, obj) -> None:
    value = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == value:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("minecraft_data_checkout", type=Path)
    args = ap.parse_args()
    root = args.minecraft_data_checkout.resolve() / "data"
    paths_file = root / "dataPaths.json"
    paths = read(paths_file)
    source = paths["pc"]["26.3"].get("materials")
    if source not in ("pc/26.2", "pc/26.3"):
        raise SystemExit("Unexpected 26.3 material source; fail closed: " + str(source))
    materials = read(root / "pc/26.2/materials.json")
    items_old = read(root / "pc/26.2/items.json")
    items_new = read(root / "pc/26.3/items.json")
    old_names = {str(item["id"]): item["name"] for item in items_old}
    new_ids = {item["name"]: item["id"] for item in items_new}
    uplifted = {}
    seen = 0
    for material, speeds in materials.items():
        mapping = {}
        for old_id, speed in speeds.items():
            name = old_names.get(str(old_id))
            if not name or name not in new_ids:
                raise SystemExit("Unmapped version-specific tool: " + str(old_id))
            new_id = str(new_ids[name])
            if new_id in mapping:
                raise SystemExit("Duplicate translated tool ID: " + new_id)
            mapping[new_id] = speed
            seen += 1
        uplifted[material] = mapping
    # Exact pinned-data regression gates, not inferred Minecraft mechanics.
    if len(uplifted) != 25 or seen != 182:
        raise SystemExit("Pinned source count changed: " + str((len(uplifted), seen)))
    if (new_ids.get("diamond_pickaxe") != 1052 or
            uplifted.get("mineable/pickaxe", {}).get("1052") != 8):
        raise SystemExit("26.3 diamond-pickaxe speed-map regression")
    output = root / "pc/26.3/materials.json"
    write_if_changed(output, uplifted)
    paths["pc"]["26.3"]["materials"] = "pc/26.3"
    write_if_changed(paths_file, paths)
    # Verify exactly what will feed the node-minecraft-data generator.
    assert read(output) == uplifted
    assert read(paths_file)["pc"]["26.3"]["materials"] == "pc/26.3"
    print(json.dumps({
        "schema": "supracraft.prismarine-material-uplift-26.3/v0.1",
        "from": "pc/26.2", "to": "pc/26.3",
        "material_groups": len(uplifted), "tool_mappings": seen,
        "diamond_pickaxe_id": 1052, "diamond_pickaxe_pickaxe_speed": 8,
        "result": "PASS",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
