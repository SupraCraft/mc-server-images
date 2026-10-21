#!/usr/bin/env python3
"""Calibrate static causal recoverability against compact runtime feedback witnesses.

This intentionally does not mutate or promote static graph edges. Runtime
delivery evidence and static path support remain separate dimensions.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path

TRUSTED={"strong","adequate"}
INFERRED_KIND_ROLES={
    "scoreboard_objective":{"semantic_state"},
    "scoreboard_objective_reference_only":{"semantic_state"},
    "command_storage":{"semantic_state"},
    "advancement":{"semantic_state"},
    "function":{"orchestrator"},
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


def graph_nodes(doc):
    nodes={n["node_id"]:n for n in doc.get("nodes",[]) if n.get("node_id")}
    semantic_state=doc.get("semantic_state",{})
    if isinstance(semantic_state,dict):
        for n in semantic_state.get("objectives",[]):
            if isinstance(n,dict) and n.get("node_id"):
                nodes.setdefault(n["node_id"],n)
    return nodes


def path_graphs(doc,nodes):
    trusted=defaultdict(list)
    candidate=defaultdict(list)
    for edge in iter_edges(doc):
        a=edge.get("a"); b=edge.get("b")
        if a and b:
            if a in nodes and b in nodes:
                candidate[a].append((b,edge))
                candidate[b].append((a,edge))
            continue

        source=edge.get("source"); target=edge.get("target")
        if source not in nodes or target not in nodes:
            continue
        candidate[source].append((target,edge))
        if edge.get("certainty","weak") in TRUSTED:
            trusted[source].append((target,edge))
    return trusted,candidate


def shortest_path(graph,start,targets,max_hops=64):
    if start not in graph and start not in targets:
        # A node with no outgoing edges can still be a valid start, but cannot
        # reach a distinct target.
        pass
    if start in targets:
        return []

    queue=deque([start])
    previous={start:None}
    previous_edge={}
    depth={start:0}
    hit=None

    while queue:
        current=queue.popleft()
        if depth[current] >= max_hops:
            continue
        for nxt,edge in graph.get(current,()):
            if nxt in previous:
                continue
            previous[nxt]=current
            previous_edge[nxt]=edge
            depth[nxt]=depth[current]+1
            if nxt in targets:
                hit=nxt
                queue.clear()
                break
            queue.append(nxt)

    if hit is None:
        return None

    steps=[]
    current=hit
    while previous[current] is not None:
        source=previous[current]
        edge=previous_edge[current]
        steps.append({
            "source":source,
            "target":current,
            "edge_type":edge.get("edge_type"),
            "certainty":edge.get("certainty","weak"),
        })
        current=source
    steps.reverse()
    return steps


def compact_path(path):
    if path is None:
        return None
    return {
        "hop_count":len(path),
        "weak_hop_count":sum(1 for step in path if step.get("certainty") not in TRUSTED),
        "steps":path,
    }


def path_support(trusted,candidate,start,targets):
    trusted_path=shortest_path(trusted,start,targets)
    candidate_path=shortest_path(candidate,start,targets)
    if trusted_path is not None:
        cls="trusted"
    elif candidate_path is not None:
        cls="candidate_only"
    else:
        cls="none"
    return {
        "support_class":cls,
        "trusted_path":compact_path(trusted_path),
        "candidate_path":compact_path(candidate_path),
    }


PRESENTATION_PROTOCOL_CLASSES={
    "literal_text","chat","composite","translated_other","other_component",
}
OUTCOME_PROTOCOL_CLASSES={"death","achievement","gamemode","multiplayer","command_feedback"}


def feedback_delta_summary(delta):
    """Separate broad client delivery from presentation-calibration evidence.

    Protocol-classified chat is preferred when available. A legacy rendered
    message hash without protocol classification remains observable delivery,
    but is not promoted to presentation feedback merely because text arrived.
    """
    delta=delta or {}
    message_added=delta.get("message_events_added",[])
    message_removed=delta.get("message_events_removed",[])
    protocol_added=delta.get("protocol_chat_events_added",[])
    protocol_removed=delta.get("protocol_chat_events_removed",[])
    effect_added=delta.get("self_effect_events_added",[])
    effect_removed=delta.get("self_effect_events_removed",[])

    protocol_rows=protocol_added+protocol_removed
    protocol_classes=[
        row.get("semantic_class") for row in protocol_rows
        if row.get("semantic_class")
    ]
    presentation_protocol=[
        row for row in protocol_rows
        if row.get("semantic_class") in PRESENTATION_PROTOCOL_CLASSES
    ]
    outcome_protocol=[
        row for row in protocol_rows
        if row.get("semantic_class") in OUTCOME_PROTOCOL_CLASSES
    ]
    unclassified_protocol=[
        row for row in protocol_rows
        if row.get("semantic_class") not in (
            PRESENTATION_PROTOCOL_CLASSES | OUTCOME_PROTOCOL_CLASSES
        )
    ]
    message_observed=bool(message_added or message_removed)
    protocol_observed=bool(protocol_rows)
    effect_observed=bool(effect_added or effect_removed)
    presentation_delivery=bool(presentation_protocol or effect_observed)
    outcome_delivery=bool(outcome_protocol)
    unclassified_message=bool(message_observed and not protocol_observed)

    return {
        "message_delta_observed":message_observed,
        "protocol_chat_delta_observed":protocol_observed,
        "self_effect_delta_observed":effect_observed,
        "client_delivery_observed":bool(
            message_observed or protocol_observed or effect_observed
        ),
        "presentation_delivery_candidate_observed":presentation_delivery,
        "outcome_event_delta_observed":outcome_delivery,
        "unclassified_message_delta_observed":unclassified_message,
        "message_event_delta_count":sum(
            int(x.get("count",0)) for x in message_added+message_removed
        ),
        "protocol_chat_event_delta_count":sum(
            int(x.get("count",0)) for x in protocol_rows
        ),
        "self_effect_event_delta_count":sum(
            int(x.get("count",0)) for x in effect_added+effect_removed
        ),
        "protocol_semantic_class_counts":{
            cls:protocol_classes.count(cls) for cls in sorted(set(protocol_classes))
        },
        "unclassified_protocol_event_count":sum(
            int(x.get("count",0)) for x in unclassified_protocol
        ),
        "control_truncated":bool(delta.get("control_truncated",False)),
        "activated_truncated":bool(delta.get("activated_truncated",False)),
    }


def authored_literal_payload_matches(nodes,delta,probe,trusted,candidate):
    """Cross-check rendered-message hashes against text-free authored payload hashes.

    A match is payload identity evidence only. It does not establish that the
    matched command executed, that the probe caused it, or that a player
    perceived or understood the delivery.
    """
    delta=delta or {}
    protocol_rows=(
        delta.get("protocol_chat_events_added",[])+
        delta.get("protocol_chat_events_removed",[])
    )
    if not any(
        row.get("semantic_class")=="literal_text" for row in protocol_rows
    ):
        return []

    authored=defaultdict(list)
    for node_id,node in nodes.items():
        fp=((node.get("command") or {}).get(
            "presentation_payload_fingerprints"
        ) or {})
        digest=fp.get("literal_text_sha256")
        if digest:
            authored[digest].append(node_id)

    matches=[]
    for direction,key in (
        ("added","message_events_added"),
        ("removed","message_events_removed"),
    ):
        for row in delta.get(key,[]):
            digest=row.get("sha256")
            node_ids=sorted(authored.get(digest,[]))
            if not digest or not node_ids:
                continue
            matches.append({
                "sha256":digest,
                "direction":direction,
                "runtime_count":int(row.get("count",0)),
                "static_node_ids":node_ids,
                "unique_static_match":len(node_ids)==1,
                "static_support":{
                    node_id:path_support(
                        trusted,candidate,probe,{node_id}
                    )
                    for node_id in node_ids
                },
            })
    return matches


def analyze(static_doc,runtime_doc,static_source_run_id=None,runtime_source_run_id=None):
    nodes=graph_nodes(static_doc)
    trusted,candidate=path_graphs(static_doc,nodes)
    feedback_nodes={
        node_id for node_id,node in nodes.items()
        if "presentation_feedback" in roles(node)
    }

    witnesses=[]
    for row in runtime_doc.get("results",[]):
        probe=(row.get("probe") or {}).get("node_id")
        if not probe:
            continue

        raw_client_delta=row.get("client_feedback_delta")
        client=feedback_delta_summary(raw_client_delta)
        payload_matches=authored_literal_payload_matches(
            nodes,raw_client_delta,probe,trusted,candidate
        )
        feedback_changes=row.get("presentation_feedback_command_state_changes",[])
        changed_nodes=sorted({
            change.get("node_id")
            for change in feedback_changes
            if change.get("node_id")
        })

        command_support={}
        for node_id in changed_nodes:
            command_support[node_id]=path_support(
                trusted,candidate,probe,{node_id}
            )

        any_feedback_support=path_support(
            trusted,candidate,probe,feedback_nodes
        )

        runtime_feedback_observed=bool(
            client["presentation_delivery_candidate_observed"] or changed_nodes
        )
        if not runtime_feedback_observed:
            calibration_class="no_runtime_feedback_witness"
        elif any_feedback_support["support_class"]=="trusted":
            calibration_class="runtime_feedback_with_trusted_static_path"
        elif any_feedback_support["support_class"]=="candidate_only":
            calibration_class="runtime_feedback_with_candidate_only_static_path"
        else:
            calibration_class="runtime_feedback_without_static_feedback_path"

        if changed_nodes and client["presentation_delivery_candidate_observed"]:
            attribution="scoped_feedback_command_execution_plus_client_delivery"
        elif changed_nodes:
            attribution="scoped_feedback_command_execution_without_client_delta"
        elif payload_matches and client["presentation_delivery_candidate_observed"]:
            attribution="client_literal_payload_identity_match_without_command_execution_state_delta"
        elif client["presentation_delivery_candidate_observed"]:
            attribution="client_presentation_delivery_without_scoped_feedback_command_state_delta"
        elif client["outcome_event_delta_observed"]:
            attribution="client_outcome_event_without_presentation_feedback_attribution"
        elif client["client_delivery_observed"]:
            attribution="unclassified_client_delivery_without_presentation_feedback_attribution"
        else:
            attribution="no_feedback_attribution"

        witnesses.append({
            "probe_node_id":probe,
            "probe_family":(row.get("probe") or {}).get("family"),
            "runtime_outcome_class":(
                (row.get("execution_receipt") or {}).get("outcome_class")
            ),
            "runtime_feedback":{
                **client,
                "scoped_feedback_command_state_change_count":len(feedback_changes),
                "scoped_feedback_command_nodes":changed_nodes,
                "authored_literal_payload_hash_match_count":sum(
                    int(match.get("runtime_count",0))
                    for match in payload_matches
                ),
                "authored_literal_payload_unique_static_match_count":sum(
                    1 for match in payload_matches
                    if match.get("unique_static_match")
                ),
                "attribution_class":attribution,
            },
            "payload_identity_matches":payload_matches,
            "static_support":{
                "to_any_presentation_feedback":any_feedback_support,
                "to_runtime_feedback_command_nodes":command_support,
            },
            "calibration_class":calibration_class,
        })

    counts=defaultdict(int)
    for witness in witnesses:
        counts[witness["calibration_class"]]+=1

    return {
        "schema":"supracraft-runtime-causal-calibration/1",
        "analysis_kind":"runtime_witness_overlay_not_static_edge_promotion",
        "static_source_schema":static_doc.get("schema"),
        "runtime_source_schema":runtime_doc.get("schema"),
        "provenance":{
            "static_source_run_id":str(static_source_run_id) if static_source_run_id else None,
            "runtime_source_run_id":str(runtime_source_run_id) if runtime_source_run_id else None,
        },
        "witness_count":len(witnesses),
        "calibration_class_counts":dict(sorted(counts.items())),
        "witnesses":witnesses,
        "interpretation_limits":[
            "Runtime feedback evidence does not mutate or upgrade static graph edges.",
            "Candidate-only support may contain weak physical adjacency and must not be restated as trusted causality.",
            "Broad client delivery is preserved separately from presentation-feedback calibration; death, achievement, gamemode, multiplayer, and command-feedback packet classes are not automatically counted as authored presentation feedback.",
            "Legacy rendered-message hashes without protocol classification remain observable delivery but are not promoted to presentation feedback solely because text arrived.",
            "Compact protocol class does not reveal message text or meaning beyond the bounded class retained by the runtime receipt.",
            "Command execution does not by itself prove client delivery; presentation delivery does not prove perception, comprehension, legibility, or qualitative value.",
            "A missing static path can indicate hidden conduction, incomplete extraction, runtime-only state, or an unattributed delivery mechanism.",
        ],
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",type=Path,required=True)
    ap.add_argument("--runtime",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--static-source-run-id")
    ap.add_argument("--runtime-source-run-id")
    args=ap.parse_args()

    result=analyze(
        json.loads(args.graph.read_text()),
        json.loads(args.runtime.read_text()),
        static_source_run_id=args.static_source_run_id,
        runtime_source_run_id=args.runtime_source_run_id,
    )
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True))


if __name__=="__main__":
    main()
