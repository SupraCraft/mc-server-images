#!/usr/bin/env python3
"""Merge independently extracted causal graph layers by stable node IDs."""

from __future__ import annotations
import argparse,json
from pathlib import Path

def edge_list(doc):
    raw=doc.get("edges",[])
    if isinstance(raw,list):
        return list(raw)
    out=[]
    for k,v in raw.items():
        if k.endswith("_count") or not isinstance(v,list):
            continue
        out.extend(v)
    return out

def merge(docs):
    nodes={}
    conflicts=[]
    edges=[]
    schemas=[]
    for doc in docs:
        schemas.append(doc.get("schema"))
        for node in doc.get("nodes",[]):
            nid=node.get("node_id")
            if not nid:continue
            if nid not in nodes:
                nodes[nid]=node
            else:
                existing=nodes[nid]
                # Merge roles conservatively; retain first source-specific payload.
                roles=sorted(set(existing.get("roles",[]))|set(node.get("roles",[])))
                existing["roles"]=roles
                if existing.get("kind")!=node.get("kind") and node.get("kind") is not None:
                    conflicts.append({"node_id":nid,"a_kind":existing.get("kind"),"b_kind":node.get("kind")})
        edges.extend(edge_list(doc))

    unresolved=[]
    resolved=[]
    for e in edges:
        src=e.get("source"); dst=e.get("target")
        if e.get("a") and e.get("b"):
            resolved.append(e);continue
        if src in nodes and dst in nodes:
            resolved.append(e)
        else:
            unresolved.append(e)

    return {
      "schema":"supracraft-combined-causal-graph/1",
      "analysis_kind":"cross_layer_structural_causal_graph",
      "source_schemas":schemas,
      "node_count":len(nodes),
      "edge_count":len(edges),
      "resolved_edge_count":len(resolved),
      "unresolved_edge_count":len(unresolved),
      "node_merge_conflicts":conflicts,
      "nodes":sorted(nodes.values(),key=lambda x:x["node_id"]),
      "edges":edges,
      "limitations":[
        "Merging stable IDs joins graph layers but does not prove runtime execution.",
        "Unresolved references remain explicit and are not synthesized.",
        "Cross-layer path recovery is evidence for semantic integration, not player understanding."
      ]
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",type=Path,action="append",required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    docs=[json.loads(p.read_text()) for p in args.graph]
    result=merge(docs)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
      "source_schemas":result["source_schemas"],"node_count":result["node_count"],
      "edge_count":result["edge_count"],"resolved_edge_count":result["resolved_edge_count"],
      "unresolved_edge_count":result["unresolved_edge_count"],"node_merge_conflict_count":len(result["node_merge_conflicts"])
    },indent=2,sort_keys=True))

if __name__=="__main__":
    main()
