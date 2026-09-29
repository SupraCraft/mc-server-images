#!/usr/bin/env python3
"""Extract causal/semantic references from Minecraft Java datapacks.

This is intentionally static and feedback-blind. It records references and
authority boundaries without claiming that every syntactic reference executes.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

FUNC_RE = re.compile(r"^(?:minecraft:)?([a-z0-9_.-]+):([a-z0-9_./-]+)$")
RESOURCE_RE = re.compile(r"^([a-z0-9_.-]+):([a-z0-9_./-]+)$")

ROLE_BY_VERB = {
    "execute": ["condition_query", "orchestrator"],
    "function": ["orchestrator"],
    "schedule": ["timer_clock", "orchestrator"],
    "scoreboard": ["semantic_state"],
    "data": ["semantic_state"],
    "storage": ["semantic_state"],
    "setblock": ["actuator"],
    "fill": ["actuator"],
    "clone": ["actuator"],
    "summon": ["actuator"],
    "tp": ["actuator"],
    "teleport": ["actuator"],
    "give": ["actuator"],
    "clear": ["actuator"],
    "item": ["actuator"],
    "loot": ["content_generator", "actuator"],
    "effect": ["actuator", "presentation_feedback"],
    "particle": ["presentation_feedback"],
    "playsound": ["presentation_feedback"],
    "title": ["presentation_feedback"],
    "tellraw": ["presentation_feedback"],
    "say": ["presentation_feedback"],
    "bossbar": ["presentation_feedback", "semantic_state"],
    "advancement": ["semantic_state"],
    "trigger": ["semantic_state"],
    "kill": ["actuator"],
    "gamemode": ["actuator"],
    "time": ["actuator"],
    "weather": ["actuator"],
    "posteffect": ["presentation_feedback"],
    "compute": ["condition_query", "semantic_state"],
}

def logical_id_from_path(path: Path, kind_dir: str, suffix: str):
    parts=path.parts
    try:
        data_i=parts.index("data")
        namespace=parts[data_i+1]
        kind_i=parts.index(kind_dir, data_i+2)
    except (ValueError, IndexError):
        return None
    rel=Path(*parts[kind_i+1:]).as_posix()
    if suffix and rel.endswith(suffix):
        rel=rel[:-len(suffix)]
    return f"{namespace}:{rel}"

def strip_comment(line: str):
    # mcfunction has line comments beginning with #; JSON strings are handled elsewhere.
    s=line.strip()
    if not s or s.startswith("#"):
        return ""
    return s

def command_parts(line: str):
    s=strip_comment(line)
    if s.startswith("/"):
        s=s[1:]
    return s.split() if s else []

def scoreboard_refs(parts):
    if len(parts)<3 or parts[0]!="scoreboard":
        return []
    domain,op=parts[1],parts[2]
    refs=[]
    if domain=="objectives" and op in {"add","remove"} and len(parts)>=4:
        refs.append((parts[3],"write"))
    elif domain=="objectives" and op=="setdisplay" and len(parts)>=5:
        refs.append((parts[4],"read"))
    elif domain=="players":
        if op in {"set","add","remove","enable"} and len(parts)>=5:
            refs.append((parts[4],"write"))
        elif op in {"get","test"} and len(parts)>=5:
            refs.append((parts[4],"read"))
        elif op=="reset" and len(parts)>=5:
            refs.append((parts[4],"write"))
        elif op=="operation" and len(parts)>=8:
            refs.append((parts[4],"write"))
            refs.append((parts[7],"read"))
    return refs

def storage_refs(parts):
    refs=[]
    if not parts:
        return refs
    if parts[0]=="data" and len(parts)>=4:
        op=parts[1]
        domain=parts[2]
        if domain=="storage":
            refs.append((parts[3], "read" if op=="get" else "write"))
    # execute store ... storage <id> ...
    if parts[0]=="execute":
        for i,tok in enumerate(parts[:-1]):
            if tok=="storage" and i>0 and parts[i-1] in {"result","success"} and i+1<len(parts):
                refs.append((parts[i+1],"write"))
    return refs

def predicate_refs(parts):
    refs=[]
    if not parts or parts[0]!="execute":
        return refs
    for i,tok in enumerate(parts[:-1]):
        if tok=="predicate" and i+1<len(parts):
            refs.append(parts[i+1])
    return refs

def function_refs(parts):
    refs=[]
    if not parts:
        return refs
    if parts[0]=="function" and len(parts)>=2:
        refs.append((parts[1],"call"))
    if parts[0]=="schedule" and len(parts)>=3 and parts[1]=="function":
        refs.append((parts[2],"schedule"))
    if parts[0]=="execute":
        for i in range(len(parts)-1):
            if parts[i]=="run" and i+2<len(parts) and parts[i+1]=="function":
                refs.append((parts[i+2],"call"))
    if parts[0]=="return" and len(parts)>=3 and parts[1]=="run" and parts[2]=="function" and len(parts)>=4:
        refs.append((parts[3],"call"))
    return refs

def resource_refs(parts):
    refs=[]
    if not parts:
        return refs
    verb=parts[0]
    if verb=="loot":
        for i,tok in enumerate(parts[:-1]):
            if tok in {"loot","fish"} and i+1<len(parts):
                refs.append(("loot_table",parts[i+1]))
    if verb=="recipe" and len(parts)>=4:
        refs.append(("recipe",parts[-1]))
    if verb=="advancement" and len(parts)>=4:
        refs.append(("advancement",parts[-1]))
    return refs

def iter_pack_files(root: Path):
    # Directory datapacks only. Zip support is materialized to a temp-equivalent logical listing
    # by reading members directly and returning (display_path, bytes).
    datapacks=root/"datapacks"
    if not datapacks.exists():
        return
    for entry in sorted(datapacks.iterdir()):
        if entry.is_dir():
            for p in sorted(entry.rglob("*")):
                if p.is_file():
                    yield f"{entry.name}/{p.relative_to(entry).as_posix()}", p.read_bytes()
        elif entry.suffix.lower()==".zip":
            with zipfile.ZipFile(entry) as zf:
                for name in sorted(zf.namelist()):
                    if not name.endswith("/"):
                        yield f"{entry.name}!/{name}", zf.read(name)

def virtual_path(display: str):
    # Normalize <pack>!/data/... or <pack>/data/... into a Path starting at data.
    rest=display.split("!/",1)[-1]
    parts=Path(rest).parts
    if "data" in parts:
        return Path(*parts[parts.index("data"):])
    return Path(rest)

def analyze(world: Path):
    functions={}
    json_resources={}
    pack_files=list(iter_pack_files(world) or [])

    for display,raw in pack_files:
        vp=virtual_path(display)
        if vp.suffix==".mcfunction" and "function" in vp.parts:
            lid=logical_id_from_path(vp,"function",".mcfunction")
            if lid is None and "functions" in vp.parts:
                lid=logical_id_from_path(vp,"functions",".mcfunction")
            if lid:
                functions[lid]={"source":display,"text":raw.decode("utf-8","replace")}
        elif vp.suffix==".json":
            kind=None
            for candidate in (
                "advancement","advancements","predicate","predicates","loot_table","loot_tables",
                "recipe","recipes","item_modifier","item_modifiers","worldgen","tags"
            ):
                if candidate in vp.parts:
                    kind=candidate
                    break
            if kind:
                try:
                    obj=json.loads(raw.decode("utf-8"))
                except Exception as exc:
                    obj={"_parse_error":str(exc)}
                json_resources[display]={"kind":kind,"object":obj}

    nodes={}
    edges=[]
    role_counts=Counter()
    verb_counts=Counter()
    unresolved=Counter()

    for fid,meta in functions.items():
        nid=f"function::{fid}"
        nodes[nid]={"node_id":nid,"kind":"function","resource_id":fid,"source":meta["source"],"roles":["orchestrator"]}
        role_counts["orchestrator"]+=1

    semantic_nodes={}
    def state_node(kind,name):
        key=f"{kind}::{name}"
        if key not in semantic_nodes:
            semantic_nodes[key]={"node_id":key,"kind":kind,"name":name}
        return key

    for fid,meta in functions.items():
        src=f"function::{fid}"
        for lineno,line in enumerate(meta["text"].splitlines(),1):
            parts=command_parts(line)
            if not parts:
                continue
            verb=parts[0].lower()
            verb_counts[verb]+=1
            for role in ROLE_BY_VERB.get(verb,[]):
                role_counts[role]+=1

            for ref,mode in function_refs(parts):
                target=f"function::{ref}"
                edges.append({"source":src,"target":target,"edge_type":"function_"+mode,"certainty":"strong","line":lineno})
                if target not in nodes:
                    unresolved["function_ref"]+=1

            for objective,access in scoreboard_refs(parts):
                target=state_node("scoreboard_objective",objective)
                edges.append({"source":src,"target":target,"edge_type":"scoreboard_"+access,"certainty":"strong","line":lineno})

            for storage,access in storage_refs(parts):
                target=state_node("command_storage",storage)
                edges.append({"source":src,"target":target,"edge_type":"storage_"+access,"certainty":"strong","line":lineno})

            for predicate in predicate_refs(parts):
                target=f"predicate::{predicate}"
                edges.append({"source":src,"target":target,"edge_type":"predicate_read","certainty":"strong","line":lineno})

            for kind,rid in resource_refs(parts):
                target=f"{kind}::{rid}"
                edges.append({"source":src,"target":target,"edge_type":kind+"_reference","certainty":"adequate","line":lineno})

            # High-level action/feedback node preserves semantic command class without raw command text.
            roles=ROLE_BY_VERB.get(verb,[])
            if roles:
                action=f"command_class::{verb}"
                nodes.setdefault(action,{"node_id":action,"kind":"command_class","verb":verb,"roles":roles})
                edges.append({"source":src,"target":action,"edge_type":"contains_command_class","certainty":"strong","line":lineno})

    nodes.update(semantic_nodes)

    advancement_links=0
    for display,res in json_resources.items():
        if res["kind"] not in {"advancement","advancements"} or "_parse_error" in res["object"]:
            continue
        vp=virtual_path(display)
        kind_dir="advancement" if "advancement" in vp.parts else "advancements"
        aid=logical_id_from_path(vp,kind_dir,".json")
        if not aid:
            continue
        an=f"advancement::{aid}"
        nodes[an]={"node_id":an,"kind":"advancement","resource_id":aid,"source":display}
        rewards=res["object"].get("rewards",{})
        fn=rewards.get("function") if isinstance(rewards,dict) else None
        if fn:
            edges.append({"source":an,"target":f"function::{fn}","edge_type":"advancement_reward_function","certainty":"strong"})
            advancement_links+=1

    return {
        "schema":"supracraft-datapack-causal-semantics/1",
        "analysis_kind":"static_structural_feedback_blind",
        "pack_file_count":len(pack_files),
        "function_count":len(functions),
        "json_resource_count":len(json_resources),
        "node_count":len(nodes),
        "edge_count":len(edges),
        "role_counts":dict(sorted(role_counts.items())),
        "verb_counts":dict(verb_counts.most_common()),
        "unresolved_reference_counts":dict(sorted(unresolved.items())),
        "advancement_reward_function_edge_count":advancement_links,
        "nodes":sorted(nodes.values(),key=lambda x:x["node_id"]),
        "edges":edges,
        "limitations":[
            "Static references do not prove execution or reachability.",
            "Selectors, predicates, macros, computed values and dynamic resource locations may require runtime context.",
            "This version does not expand tag contents or full worldgen dependency graphs.",
            "No human-feedback labels are loaded by this analyzer."
        ]
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--world",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    result=analyze(args.world)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "pack_file_count":result["pack_file_count"],
        "function_count":result["function_count"],
        "json_resource_count":result["json_resource_count"],
        "node_count":result["node_count"],
        "edge_count":result["edge_count"],
        "role_counts":result["role_counts"],
        "verb_counts":result["verb_counts"],
        "unresolved_reference_counts":result["unresolved_reference_counts"],
    },indent=2,sort_keys=True))

if __name__=="__main__":
    main()
