#!/usr/bin/env python3
"""Upgrade a copied Java 26.2 worldgen overlay toward Java 26.3.

This tool is intentionally narrow. It operates on a *copy* already produced by
the generic uplift materializer and records every transform. Deterministic
schema migrations are separated from structural reimplementations whose runtime
behavior must still be qualified.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

BINARY_DENSITY = {"minecraft:add", "minecraft:mul", "minecraft:min", "minecraft:max"}
UNARY_DENSITY = {
    "minecraft:abs", "minecraft:square", "minecraft:cube",
    "minecraft:half_negative", "minecraft:quarter_negative", "minecraft:squeeze",
    "minecraft:interpolated", "minecraft:flat_cache", "minecraft:cache_2d",
    "minecraft:cache_once", "minecraft:cache_all_in_cell", "minecraft:blend_density",
}
PROVIDER_RENAMES = {
    "minecraft:dual_noise_provider": "minecraft:dual_noise",
    "minecraft:noise_provider": "minecraft:noise",
    "minecraft:noise_threshold_provider": "minecraft:noise_threshold",
    "minecraft:randomized_int_state_provider": "minecraft:randomized_int",
    "minecraft:rule_based_state_provider": "minecraft:rule_based",
    "minecraft:simple_state_provider": "minecraft:simple",
    "minecraft:weighted_state_provider": "minecraft:weighted",
}


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def contains_type(v: Any, wanted: str) -> bool:
    if isinstance(v, dict):
        if v.get("type") == wanted:
            return True
        return any(contains_type(x, wanted) for x in v.values())
    if isinstance(v, list):
        return any(contains_type(x, wanted) for x in v)
    return False


def transform_provider_types(v: Any, receipt: list[dict[str, Any]], path: str, ptr: str = "") -> None:
    if isinstance(v, dict):
        t = v.get("type")
        if isinstance(t, str) and t in PROVIDER_RENAMES:
            new = PROVIDER_RENAMES[t]
            v["type"] = new
            receipt.append({
                "rule": "block_state_provider_type_rename",
                "class": "SAFE_SYNTACTIC",
                "path": path, "pointer": ptr or "/",
                "from": t, "to": new,
            })
        for k, child in list(v.items()):
            transform_provider_types(child, receipt, path, f"{ptr}/{k}")
    elif isinstance(v, list):
        for i, child in enumerate(v):
            transform_provider_types(child, receipt, path, f"{ptr}/{i}")


def transform_density(v: Any, receipt: list[dict[str, Any]], path: str,
                      cell_xz: int | None = None, cell_y: int | None = None,
                      ptr: str = "") -> Any:
    if isinstance(v, list):
        return [
            transform_density(x, receipt, path, cell_xz, cell_y, f"{ptr}/{i}")
            for i, x in enumerate(v)
        ]
    if not isinstance(v, dict):
        return v

    v = copy.deepcopy(v)
    t = v.get("type")

    if t == "minecraft:shifted_noise":
        v["type"] = "minecraft:noise"
        receipt.append({"rule": "density_shifted_noise_to_noise", "class": "SAFE_SYNTACTIC", "path": path, "pointer": ptr or "/"})
        t = v["type"]

    if t == "minecraft:y_clamped_gradient":
        v["type"] = "minecraft:gradient"
        v["axis"] = "y"
        v["tiling"] = "clamp_to_edge"
        if "from_y" in v:
            v["from_coordinate"] = v.pop("from_y")
        if "to_y" in v:
            v["to_coordinate"] = v.pop("to_y")
        receipt.append({"rule": "density_y_clamped_gradient_to_gradient", "class": "SAFE_SYNTACTIC", "path": path, "pointer": ptr or "/"})
        t = v["type"]

    if t in BINARY_DENSITY:
        if "argument1" in v and "left" not in v:
            v["left"] = v.pop("argument1")
        if "argument2" in v and "right" not in v:
            v["right"] = v.pop("argument2")
        receipt.append({"rule": "density_binary_argument_rename", "class": "SAFE_SYNTACTIC", "path": path, "pointer": ptr or "/", "type": t})

    if t in UNARY_DENSITY:
        if "argument" in v and "input" not in v:
            v["input"] = v.pop("argument")
            receipt.append({"rule": "density_unary_argument_to_input", "class": "SAFE_SYNTACTIC", "path": path, "pointer": ptr or "/", "type": t})

    if t in {"minecraft:shift_a", "minecraft:shift_b", "minecraft:shift"}:
        if "argument" in v and "noise" not in v:
            v["noise"] = v.pop("argument")
            receipt.append({"rule": "density_shift_argument_to_noise", "class": "SAFE_SYNTACTIC", "path": path, "pointer": ptr or "/"})

    if t == "minecraft:constant" and "argument" in v and "value" not in v:
        v["value"] = v.pop("argument")
        receipt.append({"rule": "density_constant_argument_to_value", "class": "SAFE_SYNTACTIC", "path": path, "pointer": ptr or "/"})

    if t == "minecraft:invert":
        v["type"] = "minecraft:reciprocal"
        receipt.append({"rule": "density_invert_to_reciprocal", "class": "SAFE_SYNTACTIC", "path": path, "pointer": ptr or "/"})
        t = v["type"]

    if t == "minecraft:end_islands":
        v["type"] = "minecraft:end_outer_islands"
        receipt.append({"rule": "density_end_islands_to_end_outer_islands", "class": "STRUCTURAL_REIMPLEMENTATION", "path": path, "pointer": ptr or "/"})
        t = v["type"]

    if t == "minecraft:cache_once":
        v["type"] = "minecraft:cache"
        receipt.append({"rule": "density_cache_once_to_cache", "class": "SAFE_SYNTACTIC", "path": path, "pointer": ptr or "/"})
        t = v["type"]
    elif t == "minecraft:cache_2d":
        v["type"] = "minecraft:cache"
        receipt.append({"rule": "density_cache_2d_to_cache", "class": "STRUCTURAL_REIMPLEMENTATION", "path": path, "pointer": ptr or "/"})
        t = v["type"]
    elif t in {"minecraft:flat_cache", "minecraft:cache_all_in_cell"}:
        raise RuntimeError(f"unsupported removed density cache {t} at {path}{ptr}")

    # Recurse after field renames.
    for k, child in list(v.items()):
        if k == "type":
            continue
        v[k] = transform_density(child, receipt, path, cell_xz, cell_y, f"{ptr}/{k}")

    if v.get("type") == "minecraft:interpolated":
        if cell_xz is None or cell_y is None:
            raise RuntimeError(f"interpolated density lacks recovered cell sizes at {path}{ptr}")
        if "cell_size_xz" not in v:
            v["cell_size_xz"] = cell_xz
        if "cell_size_y" not in v:
            v["cell_size_y"] = cell_y
        receipt.append({
            "rule": "density_interpolated_explicit_cell_size",
            "class": "STRUCTURAL_REIMPLEMENTATION",
            "path": path, "pointer": ptr or "/",
            "cell_size_xz": cell_xz, "cell_size_y": cell_y,
        })

    return v


def transform_spawn_overrides(v: Any, receipt: list[dict[str, Any]], path: str) -> None:
    if not isinstance(v, dict):
        return
    overrides = v.get("spawn_overrides")
    if not isinstance(overrides, dict):
        return
    for category, spec in overrides.items():
        if not isinstance(spec, dict):
            continue
        spawns = spec.get("spawns")
        if not isinstance(spawns, list):
            continue
        for i, entry in enumerate(spawns):
            if not isinstance(entry, dict) or "count" in entry:
                continue
            if "minCount" not in entry or "maxCount" not in entry:
                continue
            lo, hi = entry.pop("minCount"), entry.pop("maxCount")
            if lo == hi:
                entry["count"] = lo
            else:
                entry["count"] = {
                    "type": "minecraft:uniform",
                    "min_inclusive": lo,
                    "max_inclusive": hi,
                }
            receipt.append({
                "rule": "structure_spawn_minmax_to_count",
                "class": "STRUCTURAL_REIMPLEMENTATION",
                "path": path,
                "pointer": f"/spawn_overrides/{category}/spawns/{i}",
                "old_min": lo, "old_max": hi,
            })


def transform_feature(path: Path, data: dict[str, Any], receipt: list[dict[str, Any]]) -> dict[str, Any]:
    if isinstance(data.get("config"), dict):
        config = data.pop("config")
        collisions = sorted(set(config) & set(data))
        if collisions:
            raise RuntimeError(f"feature config/root collision in {path}: {collisions}")
        data.update(config)
        receipt.append({
            "rule": "configured_feature_inline_config",
            "class": "SAFE_SYNTACTIC",
            "path": path.as_posix(),
        })
    transform_provider_types(data, receipt, path.as_posix())
    return data


def transform_carver(path: Path, data: dict[str, Any], receipt: list[dict[str, Any]]) -> dict[str, Any]:
    old_type = data.get("type")
    cfg = data.pop("config", None)
    if isinstance(cfg, dict):
        collisions = sorted(set(cfg) & set(data))
        if collisions:
            raise RuntimeError(f"carver config/root collision in {path}: {collisions}")
        data.update(cfg)
        receipt.append({"rule": "carver_inline_config", "class": "SAFE_SYNTACTIC", "path": path.as_posix()})

    for removed in ("debug_settings", "lava_level", "replaceable"):
        if removed in data:
            data.pop(removed)
            receipt.append({
                "rule": "carver_remove_obsolete_field",
                "class": "STRUCTURAL_REIMPLEMENTATION",
                "path": path.as_posix(), "field": removed,
            })

    if old_type == "minecraft:canyon":
        if "yScale" in data:
            shape = data.setdefault("shape", {})
            if not isinstance(shape, dict):
                raise RuntimeError(f"canyon shape not object in {path}")
            shape["y_scale"] = data.pop("yScale")
            receipt.append({"rule": "canyon_yScale_to_shape_y_scale", "class": "SAFE_SYNTACTIC", "path": path.as_posix()})

    elif old_type in {"minecraft:cave", "minecraft:nether_cave"}:
        if "yScale" in data:
            data["room_vertical_radius_multiplier"] = data.pop("yScale")
        is_nether = old_type == "minecraft:nether_cave"
        if is_nether:
            data["type"] = "minecraft:cave"
        data.setdefault("count", {
            "type": "minecraft:very_biased_to_bottom",
            "min_inclusive": 0,
            "max_inclusive": 9 if is_nether else 14,
        })
        data.setdefault("thickness", {
            "type": "minecraft:trapezoid",
            "min": 0.0,
            "max": 6.0 if is_nether else 3.0,
            "plateau": 2.0 if is_nether else 1.0,
        })
        receipt.append({
            "rule": "cave_exposed_hidden_defaults",
            "class": "STRUCTURAL_REIMPLEMENTATION",
            "path": path.as_posix(),
            "legacy_type": old_type,
            "target_type": data.get("type"),
        })

    transform_provider_types(data, receipt, path.as_posix())
    return data


def transform_noise_registry(path: Path, data: dict[str, Any], receipt: list[dict[str, Any]]) -> dict[str, Any]:
    if "firstOctave" in data and "base_octave" not in data:
        old = data.pop("firstOctave")
        amps = data.get("amplitudes", data.get("amplitude_modifiers", []))
        # Empty amplitudes produce no signal; clamp sentinel octaves into the
        # modern supported domain without changing the zero-output contract.
        new = old
        if isinstance(amps, list) and len(amps) == 0:
            new = max(-32, min(31, int(old)))
        data["base_octave"] = new
        receipt.append({
            "rule": "noise_firstOctave_to_base_octave",
            "class": "STRUCTURAL_REIMPLEMENTATION" if new != old else "SAFE_SYNTACTIC",
            "path": path.as_posix(), "old": old, "new": new,
        })
    if "amplitudes" in data and "amplitude_modifiers" not in data:
        amps = data.pop("amplitudes")
        data["amplitude_modifiers"] = amps
        receipt.append({"rule": "noise_amplitudes_to_amplitude_modifiers", "class": "SAFE_SYNTACTIC", "path": path.as_posix()})
        if isinstance(amps, list) and amps:
            data.setdefault("octave_count", len(amps))
            data.setdefault("normalize", "legacy")
    return data


def transform_noise_settings(path: Path, data: dict[str, Any], receipt: list[dict[str, Any]]) -> dict[str, Any]:
    noise = data.get("noise")
    cell_xz = cell_y = None
    if isinstance(noise, dict):
        sh = noise.pop("size_horizontal", None)
        sv = noise.pop("size_vertical", None)
        if sh is not None:
            cell_xz = 4 * int(sh)
        if sv is not None:
            cell_y = 4 * int(sv)
        if sh is not None or sv is not None:
            receipt.append({
                "rule": "noise_settings_cell_sizes_to_interpolated",
                "class": "STRUCTURAL_REIMPLEMENTATION",
                "path": path.as_posix(),
                "cell_size_xz": cell_xz,
                "cell_size_y": cell_y,
            })

    router = data.get("noise_router")
    if not isinstance(router, dict):
        raise RuntimeError(f"noise_router missing/not object in {path}")

    if "preliminary_surface_level" in router and "chunk_surface_level" not in router:
        router["chunk_surface_level"] = router.pop("preliminary_surface_level")
        receipt.append({"rule": "preliminary_surface_level_to_chunk_surface_level", "class": "SAFE_SYNTACTIC", "path": path.as_posix()})

    aquifers = data.pop("aquifers_enabled", None)
    if aquifers is True:
        raise RuntimeError(f"aquifers_enabled=true requires richer material migration in {path}")
    if aquifers is False:
        for k in ("barrier", "fluid_level_floodedness", "fluid_level_spread", "lava"):
            router.pop(k, None)
        receipt.append({"rule": "disabled_aquifers_remove_router_fields", "class": "SAFE_SYNTACTIC", "path": path.as_posix()})

    veins = data.pop("ore_veins_enabled", None)
    if veins is True:
        raise RuntimeError(f"ore_veins_enabled=true requires material-rule migration in {path}")
    if veins is False:
        for k in ("vein_toggle", "vein_ridged", "vein_gap"):
            router.pop(k, None)
        receipt.append({"rule": "disabled_ore_veins_remove_router_fields", "class": "SAFE_SYNTACTIC", "path": path.as_posix()})

    if "surface_rule" in data and "material_rule" not in data:
        data["material_rule"] = data.pop("surface_rule")
        receipt.append({"rule": "surface_rule_to_material_rule", "class": "SAFE_SYNTACTIC", "path": path.as_posix()})

    for k, v in list(router.items()):
        router[k] = transform_density(v, receipt, path.as_posix(), cell_xz, cell_y, f"/noise_router/{k}")

    # 26.3 no longer adds beardifier implicitly. Preserve the old contract.
    final_density = router.get("final_density")
    if final_density is not None and not contains_type(final_density, "minecraft:beardifier"):
        router["final_density"] = {
            "type": "minecraft:add",
            "left": final_density,
            "right": {"type": "minecraft:beardifier"},
        }
        receipt.append({"rule": "explicit_beardifier_for_legacy_final_density", "class": "STRUCTURAL_REIMPLEMENTATION", "path": path.as_posix()})

    if "material_rule" in data:
        transform_provider_types(data["material_rule"], receipt, path.as_posix(), "/material_rule")
    transform_provider_types(data, receipt, path.as_posix())
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="already-copied uplift output tree")
    ap.add_argument("--output-json", type=Path, required=True)
    args = ap.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        ap.error(f"root is not a directory: {root}")

    changes: list[dict[str, Any]] = []
    touched: list[str] = []

    for path in sorted(root.rglob("*.json")):
        rel = path.relative_to(root).as_posix()
        try:
            data = json.loads(path.read_text("utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue

        before = json.dumps(data, sort_keys=True, separators=(",", ":"))

        if "/worldgen/feature/" in f"/{rel}":
            data = transform_feature(path.relative_to(root), data, changes)
        if "/worldgen/carver/" in f"/{rel}":
            data = transform_carver(path.relative_to(root), data, changes)
        if "/worldgen/noise_settings/" in f"/{rel}":
            data = transform_noise_settings(path.relative_to(root), data, changes)
        if "/worldgen/noise/" in f"/{rel}":
            data = transform_noise_registry(path.relative_to(root), data, changes)

        transform_spawn_overrides(data, changes, rel)
        transform_provider_types(data, changes, rel)

        after = json.dumps(data, sort_keys=True, separators=(",", ":"))
        if before != after:
            write_json(path, data)
            touched.append(rel)

    receipt = {
        "schema": "supracraft-worldgen-26.2-to-26.3-uplift/1",
        "root": str(root),
        "touched_file_count": len(touched),
        "touched_files": touched,
        "change_count": len(changes),
        "counts_by_rule": {},
        "counts_by_class": {},
        "changes": changes,
    }
    for c in changes:
        receipt["counts_by_rule"][c["rule"]] = receipt["counts_by_rule"].get(c["rule"], 0) + 1
        receipt["counts_by_class"][c["class"]] = receipt["counts_by_class"].get(c["class"], 0) + 1

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", "utf-8")
    print(json.dumps({
        "touched_file_count": receipt["touched_file_count"],
        "change_count": receipt["change_count"],
        "counts_by_class": receipt["counts_by_class"],
        "counts_by_rule": receipt["counts_by_rule"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
