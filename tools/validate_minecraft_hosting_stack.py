#!/usr/bin/env python3
import json, pathlib, sys
p=pathlib.Path(__file__).resolve().parents[1]/"spec"/"minecraft-hosting-stack-v1.json"
d=json.loads(p.read_text())
errors=[]
wa=d["world_agent"]; fb=d["foundry_boundary"]; ws=d["world_storage"]; be=d["backends"]
if wa["docker_socket"]: errors.append("world-agent must not receive Docker socket")
if wa["policy_authority"] or wa["game_semantics"]: errors.append("world-agent must remain mechanism-only")
for forbidden in ("world_release_policy","world_promotion","game_semantics","two_rivers_state"):
    if forbidden not in fb["must_not_own"]: errors.append(f"Foundry exclusion missing: {forbidden}")
if ws["baked_into_image"] or not ws["release_authority_external"]: errors.append("world payload/release authority crossed stack boundary")
if not be["vanilla"]["semantic_authority_for_two_rivers"]: errors.append("vanilla must remain Two Rivers semantic authority")
if be["paper"]["semantic_authority_for_two_rivers"]: errors.append("Paper must not inherit Two Rivers semantic authority")
if not all(v["independent_qualification"] for v in be.values()): errors.append("backend qualification must remain independent")
expected=["S0_contract","S1_vanilla_vanillacord","S2_velocity_vip","S3_proxy_transparency","S4_paper_adapter","S5_world_agent_mechanics","S6_foundry_materialization","S7_truenas_rdte","S8_physical_hil"]
if d["acceptance"] != expected: errors.append("acceptance ladder changed")
if errors:
    print("\n".join("FAIL: "+e for e in errors)); sys.exit(1)
print("PASS minecraft-hosting-stack-v1 boundary contract")
