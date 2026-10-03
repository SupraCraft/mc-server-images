#!/usr/bin/env python3
"""Four-domain census over the accepted legacy CORE causal graph.

This is a classification/census layer only. Mixed-domain adjacency and existing
legacy edge candidates are counted but never promoted as cross-domain semantics.
"""

from __future__ import annotations
import argparse, json
from collections import Counter, defaultdict, deque
from pathlib import Path

SCHEMA="supracraft-four-domain-census/1"

PRIMARY={
    "electrical":{
        "redstone_wire","redstone_torch_off","redstone_torch_on",
        "repeater_off","repeater_on","comparator_off","comparator_on",
        "lever","stone_button","wooden_button",
        "stone_pressure_plate","wooden_pressure_plate",
        "light_weighted_pressure_plate","heavy_weighted_pressure_plate",
        "tripwire_hook","tripwire","daylight_detector","inverted_daylight_detector",
    },
    "mechanical":{
        "piston","sticky_piston","wooden_door","iron_door",
        "trapdoor","iron_trapdoor","fence_gate",
    },
    "programmable":{
        "command_block","repeating_command_block","chain_command_block",
    },
    "inventory":{
        "chest","trapped_chest","hopper","furnace","lit_furnace",
        "dispenser","dropper",
    },
}

OBSERVATION_ONLY={
    "note_block","standing_sign","wall_sign","redstone_lamp_off","redstone_lamp_on",
}

FAMILY_TO_DOMAIN={
    family:domain
    for domain,families in PRIMARY.items()
    for family in families
}

def _components(doc):
    nodes={n["node_id"]:n for n in doc["nodes"]}
    adj=defaultdict(set)
    for edge in doc["edges"].get("physical_adjacency_candidates",[]):
        a,b=edge["a"],edge["b"]
        if a in nodes and b in nodes:
            adj[a].add(b); adj[b].add(a)
    seen=set()
    out=[]
    for start in nodes:
        if start in seen:
            continue
        q=deque([start]); seen.add(start); members=[]
        while q:
            cur=q.popleft(); members.append(cur)
            for nxt in adj.get(cur,()):
                if nxt not in seen:
                    seen.add(nxt); q.append(nxt)
        counts=Counter()
        obs=0
        unknown=0
        fam=Counter()
        for node_id in members:
            family=nodes[node_id]["family"]; fam[family]+=1
            domain=FAMILY_TO_DOMAIN.get(family)
            if domain:
                counts[domain]+=1
            elif family in OBSERVATION_ONLY:
                obs+=1
            else:
                unknown+=1
        active=sorted(k for k,v in counts.items() if v)
        out.append({
            "node_count":len(members),
            "domain_counts":dict(sorted(counts.items())),
            "active_domains":active,
            "mixed_domain_candidate":len(active)>1,
            "observation_surface_count":obs,
            "unknown_count":unknown,
            "family_counts":dict(fam.most_common()),
        })
    return out

def analyze(doc):
    if doc.get("schema")!="supracraft-legacy-causal-machinery/1":
        raise ValueError("exact legacy causal machinery schema required")

    domain_counts=Counter()
    family_counts={d:Counter() for d in PRIMARY}
    observation=Counter()
    unknown=Counter()

    for node in doc["nodes"]:
        family=node["family"]
        domain=FAMILY_TO_DOMAIN.get(family)
        if domain:
            domain_counts[domain]+=1
            family_counts[domain][family]+=1
        elif family in OBSERVATION_ONLY:
            observation[family]+=1
        else:
            unknown[family]+=1

    comps=_components(doc)
    mixed=[c for c in comps if c["mixed_domain_candidate"]]

    edges=doc["edges"]
    interfaces={
        "inventory_to_electrical_container_comparator_candidate":
            len(edges.get("container_comparator_reads",[])),
        "inventory_to_electrical_trapped_open_power_candidate":
            len(edges.get("trapped_chest_open_power_candidates",[])),
        "electrical_to_programmable_repeater_conduction_candidate":
            len(edges.get("repeater_command_block_conduction_edges",[])),
        "programmable_to_electrical_command_authored_redstone_candidate":
            len(edges.get("command_authored_redstone_edges",[])),
        "programmable_to_world_target_candidate":
            len(edges.get("command_world_targets",[])),
    }

    return {
        "schema":SCHEMA,
        "source_schema":doc["schema"],
        "world_format":doc.get("world_format"),
        "analysis_kind":"four_domain_static_census_not_interaction_qualification",
        "domain_node_counts":dict(sorted(domain_counts.items())),
        "domain_family_counts":{
            d:dict(family_counts[d].most_common()) for d in sorted(PRIMARY)
        },
        "observation_surface_counts":dict(observation.most_common()),
        "unknown_family_counts":dict(unknown.most_common()),
        "component_count":len(comps),
        "single_domain_component_count":sum(
            1 for c in comps if len(c["active_domains"])==1
        ),
        "mixed_domain_component_candidate_count":len(mixed),
        "components_without_primary_domain_count":sum(
            1 for c in comps if not c["active_domains"]
        ),
        "largest_mixed_domain_candidates":sorted(
            mixed,key=lambda c:c["node_count"],reverse=True
        )[:50],
        "phase_b_interface_candidate_counts":interfaces,
        "boundaries":[
            "mixed-domain adjacency is a discovery signal only, not a qualified interaction",
            "modern 26.x semantics are not projected onto this 1.8.8 graph",
            "observation surfaces are counted separately and are not a fifth peer domain",
            "unknown families remain unknown rather than being forced into a domain",
            "phase-B interface candidates remain unqualified by this census",
        ],
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    doc=json.loads(args.graph.read_text())
    out=analyze(doc)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
        "domain_node_counts":out["domain_node_counts"],
        "mixed_domain_component_candidate_count":out["mixed_domain_component_candidate_count"],
        "observation_surface_counts":out["observation_surface_counts"],
        "phase_b_interface_candidate_counts":out["phase_b_interface_candidate_counts"],
        "unknown_family_counts":out["unknown_family_counts"],
    },indent=2,sort_keys=True))

if __name__=="__main__":
    main()
