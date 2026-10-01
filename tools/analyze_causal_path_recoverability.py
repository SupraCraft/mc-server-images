#!/usr/bin/env python3
"""Measure structural causal-path recoverability in extracted world machinery graphs.

This reports graph coverage/evidence only. It does not score fun, fairness,
immersion, frustration, or overall quality.
"""

from __future__ import annotations
import argparse, json
from collections import defaultdict, deque
from pathlib import Path

TRUSTED = {"strong", "adequate"}
INFERRED_KIND_ROLES = {
    "scoreboard_objective": {"semantic_state"},
    "scoreboard_objective_reference_only": {"semantic_state"},
    "command_storage": {"semantic_state"},
    "advancement": {"semantic_state"},
    "function": {"orchestrator"},
}

def roles(node):
    out=set(node.get("roles",[]))
    out |= INFERRED_KIND_ROLES.get(node.get("kind"),set())
    return out

def iter_edges(doc):
    raw=doc.get("edges",[])
    if isinstance(raw,list):
        yield from raw
        return
    if isinstance(raw,dict):
        for key,val in raw.items():
            if key.endswith("_count") or not isinstance(val,list):
                continue
            yield from val

def normalize(doc):
    nodes={n["node_id"]:n for n in doc.get("nodes",[]) if n.get("node_id")}
    # Legacy causal extraction emits scoreboard objectives as declared semantic
    # state nodes outside the physical machinery node list. Admit those exact
    # declared nodes so their read/write edges are not silently unresolved.
    semantic_state=doc.get("semantic_state",{})
    if isinstance(semantic_state,dict):
        for n in semantic_state.get("objectives",[]):
            if isinstance(n,dict) and n.get("node_id"):
                nodes.setdefault(n["node_id"],n)
    edges=list(iter_edges(doc))
    trusted=defaultdict(set); candidate=defaultdict(set)
    unresolved=[]
    for e in edges:
        # Legacy physical-adjacency candidates are intentionally undirected a/b
        # relations. They may contribute only to candidate reachability.
        if e.get("a") and e.get("b"):
            a,b=e["a"],e["b"]
            if a not in nodes or b not in nodes:
                unresolved.append(e)
                continue
            candidate[a].add(b)
            candidate[b].add(a)
            continue

        src=e.get("source"); dst=e.get("target")
        if not src or not dst:
            unresolved.append(e)
            continue
        if src not in nodes or dst not in nodes:
            unresolved.append(e)
            continue
        certainty=e.get("certainty","weak")
        candidate[src].add(dst)
        if certainty in TRUSTED:
            trusted[src].add(dst)
    return nodes, trusted, candidate, unresolved, edges

def reachable(graph,start,max_hops=32):
    seen={start}; q=deque([(start,0)])
    while q:
        cur,h=q.popleft()
        if h>=max_hops:continue
        for nxt in graph.get(cur,()):
            if nxt not in seen:
                seen.add(nxt); q.append((nxt,h+1))
    seen.discard(start)
    return seen

def reverse_graph(graph):
    rev=defaultdict(set)
    for a,bs in graph.items():
        for b in bs:rev[b].add(a)
    return rev

def classify(nodes):
    cats=defaultdict(set)
    for nid,node in nodes.items():
        rs=roles(node)
        for role in rs:cats[role].add(nid)
    return cats

def coverage(starts,targets,graph):
    if not starts:
        return {"start_count":0,"covered_count":0,"coverage":None,"covered":[],"uncovered":[]}
    covered=[];uncovered=[]
    for s in sorted(starts):
        hit=bool(reachable(graph,s)&targets)
        (covered if hit else uncovered).append(s)
    return {
      "start_count":len(starts),"covered_count":len(covered),
      "coverage":round(len(covered)/len(starts),6),
      "covered":covered,"uncovered":uncovered
    }

def analyze(doc):
    nodes,trusted,candidate,unresolved,edges=normalize(doc)
    cats=classify(nodes)
    sensors=cats["sensor_input"]
    state=cats["semantic_state"]|cats["state_memory"]
    actuators=cats["actuator"]
    feedback=cats["presentation_feedback"]
    reverse_trusted=reverse_graph(trusted)
    reverse_candidate=reverse_graph(candidate)

    trusted_metrics={
      "sensor_to_state":coverage(sensors,state,trusted),
      "sensor_to_actuator":coverage(sensors,actuators,trusted),
      "sensor_to_feedback":coverage(sensors,feedback,trusted),
      "actuator_with_sensor_upstream":coverage(actuators,sensors,reverse_trusted),
      "state_with_feedback_downstream":coverage(state,feedback,trusted),
    }
    candidate_metrics={
      "sensor_to_state":coverage(sensors,state,candidate),
      "sensor_to_actuator":coverage(sensors,actuators,candidate),
      "sensor_to_feedback":coverage(sensors,feedback,candidate),
      "actuator_with_sensor_upstream":coverage(actuators,sensors,reverse_candidate),
      "state_with_feedback_downstream":coverage(state,feedback,candidate),
    }

    def ratio_delta(key):
        a=trusted_metrics[key]["coverage"]; b=candidate_metrics[key]["coverage"]
        if a is None or b is None:return None
        return round(b-a,6)

    return {
      "schema":"supracraft-causal-path-recoverability/1",
      "source_schema":doc.get("schema"),
      "analysis_kind":"structural_causal_evidence_not_quality_score",
      "node_count":len(nodes),
      "edge_count":len(edges),
      "unresolved_edge_count":len(unresolved),
      "role_counts":{k:len(v) for k,v in sorted(cats.items())},
      "trusted_path_metrics":trusted_metrics,
      "candidate_path_metrics":candidate_metrics,
      "weak_edge_sensitivity":{
        k:ratio_delta(k) for k in trusted_metrics
      },
      "unresolved_edge_examples":[
        {k:e.get(k) for k in ("source","target","edge_type","certainty","target_position") if e.get(k) is not None}
        for e in unresolved[:50]
      ],
      "interpretation_limits":[
        "Coverage means a path is statically recoverable in the extracted graph, not that the mechanism executes.",
        "Absence of a trusted path may reflect an incomplete extractor, hidden solid-block conduction, runtime context, or intentionally indirect design.",
        "Presence of a path does not establish that a player understands the causal relationship.",
        "Weak-edge sensitivity is reported separately so adjacency guesses cannot silently become causal truth.",
        "These metrics are candidates for causal-legibility calibration only and are not an overall quality score."
      ]
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    doc=json.loads(args.graph.read_text())
    result=analyze(doc)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
