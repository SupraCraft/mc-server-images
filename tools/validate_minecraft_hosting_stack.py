#!/usr/bin/env python3
"""Fail-closed validator for minecraft-hosting-stack-v1 specification."""
import json
import pathlib
import sys


def parse_strict_json(path: pathlib.Path) -> dict:
    def check_pairs(pairs):
        keys = set()
        res = {}
        for k, v in pairs:
            if k in keys:
                raise ValueError(f"duplicate JSON key detected: {k!r}")
            keys.add(k)
            res[k] = v
        return res

    def reject_nonfinite_constant(value):
        # CPython accepts NaN/Infinity extensions by default; they are not
        # valid JSON and can create cross-parser policy ambiguity.
        raise ValueError(f"non-standard JSON constant rejected: {value}")

    text = path.read_text(encoding="utf-8")
    return json.loads(
        text, object_pairs_hook=check_pairs, parse_constant=reject_nonfinite_constant
    )


def validate_stack(data: dict) -> list[str]:
    errors = []

    # Required top-level keys
    required_keys = {"schema_version", "product", "authority", "ingress", "backends", "world_storage", "world_agent", "foundry_boundary", "acceptance"}
    if not isinstance(data, dict):
        return ["specification root must be a JSON object"]
    
    missing_root = required_keys - set(data.keys())
    if missing_root:
        errors.append(f"missing required root keys: {sorted(missing_root)}")

    if data.get("schema_version") != "1":
        errors.append("schema_version must be '1'")
    if data.get("product") != "minecraft-hosting-stack":
        errors.append("product must be 'minecraft-hosting-stack'")
    if data.get("authority") != "SupraCraft/mc-server-images#53":
        errors.append("authority must be 'SupraCraft/mc-server-images#53'")

    # Ingress validation
    ingress = data.get("ingress", {})
    if not isinstance(ingress, dict):
        errors.append("ingress must be a JSON object")
    else:
        if ingress.get("service") != "velocity" or ingress.get("player_facing") is not True:
            errors.append("Velocity must remain sole player-facing ingress")
        caps = ingress.get("capabilities", [])
        if not isinstance(caps, list) or not all(isinstance(c, str) for c in caps) or "modern_forwarding" not in caps:
            errors.append("Velocity modern forwarding capability missing")

    # World storage validation
    ws = data.get("world_storage", {})
    if not isinstance(ws, dict):
        errors.append("world_storage must be a JSON object")
    else:
        if ws.get("mutable_runtime_mount") is not True:
            errors.append("World runtime mount must remain explicit")
        if ws.get("baked_into_image") is not False:
            errors.append("world payload/release authority crossed stack boundary")
        if ws.get("release_authority_external") is not True:
            errors.append("world payload/release authority crossed stack boundary")

    # World agent validation
    wa = data.get("world_agent", {})
    if not isinstance(wa, dict):
        errors.append("world_agent must be a JSON object")
    else:
        if wa.get("docker_socket") is not False:
            errors.append("world-agent must not receive Docker socket")
        if wa.get("policy_authority") is not False or wa.get("game_semantics") is not False:
            errors.append("world-agent must remain mechanism-only")
        if wa.get("optional") is not True:
            errors.append("world-agent optional must be Boolean true")
        verbs = wa.get("verbs")
        required_verbs = {"status", "quiesce", "snapshot", "stage", "activate", "clone", "restore", "resume", "hash"}
        if not isinstance(verbs, list) or not all(isinstance(x, str) for x in verbs) or not required_verbs.issubset(verbs):
            errors.append("world-agent required mechanism verbs missing or malformed")

    # Foundry boundary
    fb = data.get("foundry_boundary", {})
    if not isinstance(fb, dict):
        errors.append("foundry_boundary must be a JSON object")
    else:
        owns = fb.get("owns")
        required_owns = {"compose_materialization", "service_wiring", "storage_attachment", "secrets_injection", "health_lifecycle"}
        if not isinstance(owns, list) or not all(isinstance(x, str) for x in owns) or not required_owns.issubset(owns):
            errors.append("Foundry required ownership missing or malformed")
        exclusions = fb.get("must_not_own")
        if not isinstance(exclusions, list) or not all(isinstance(x, str) for x in exclusions):
            errors.append("Foundry exclusion list must contain strings")
            exclusions = []
        must_not_own = set(exclusions)
        if isinstance(owns, list) and all(isinstance(x, str) for x in owns):
            conflict = sorted(set(owns) & must_not_own)
            if conflict:
                errors.append(f"Foundry ownership/exclusion conflict: {conflict}")
        for forbidden in ("world_release_policy", "world_promotion", "game_semantics", "two_rivers_state"):
            if forbidden not in must_not_own:
                errors.append(f"Foundry exclusion missing: {forbidden}")

    # Backends validation
    be = data.get("backends", {})
    if not isinstance(be, dict):
        errors.append("backends must be a JSON object")
    else:
        if set(be.keys()) != {"vanilla", "paper"}:
            errors.append(f"backends must strictly be {{'vanilla', 'paper'}}, got {sorted(be.keys())}")
        vanilla = be.get("vanilla", {})
        paper = be.get("paper", {})
        if not isinstance(vanilla, dict) or vanilla.get("semantic_authority_for_two_rivers") is not True:
            errors.append("vanilla must remain Two Rivers semantic authority")
        if not isinstance(paper, dict) or paper.get("semantic_authority_for_two_rivers") is not False:
            errors.append("Paper must not inherit Two Rivers semantic authority")
        if not all(isinstance(v, dict) and v.get("independent_qualification") is True for v in be.values()):
            errors.append("backend qualification must remain independent")
        if isinstance(vanilla, dict) and vanilla.get("proxy_adapter") != "SupraCraft/VanillaCord":
            errors.append("vanilla proxy adapter identity drift")
        if isinstance(paper, dict) and paper.get("proxy_adapter") != "native_velocity_forwarding":
            errors.append("Paper proxy adapter identity drift")

    # Acceptance ladder
    expected_ladder = [
        "S0_contract", "S1_vanilla_vanillacord", "S2_velocity_vip",
        "S3_proxy_transparency", "S4_paper_adapter", "S5_world_agent_mechanics",
        "S6_foundry_materialization", "S7_truenas_rdte", "S8_physical_hil"
    ]
    if data.get("acceptance") != expected_ladder:
        errors.append("acceptance ladder changed")

    return errors


def main() -> int:
    p = pathlib.Path(__file__).resolve().parents[1] / "spec" / "minecraft-hosting-stack-v1.json"
    try:
        data = parse_strict_json(p)
    except Exception as e:
        print(f"FAIL: JSON parse error: {e}")
        return 1

    errors = validate_stack(data)
    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1

    print("PASS minecraft-hosting-stack-v1 boundary contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())