#!/usr/bin/env python3
"""Dependency-light referential/invariant validator for causal-kernel-v1 receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DOMAINS={"electrical","mechanical","inventory","programmable"}
KNOWLEDGE={"observed","inferred","unknown"}
EDGE_KINDS={"domain","transducer","mutation","observation"}
DIRECTIONS={"input","output","bidirectional","state","unknown"}


def fail(msg: str) -> None:
    raise ValueError(msg)


def _unique(rows, key, label):
    seen=set()
    for row in rows:
        value=row.get(key)
        if not isinstance(value,str) or not value:
            fail(f"{label} missing non-empty {key}")
        if value in seen:
            fail(f"duplicate {label} {key}: {value}")
        seen.add(value)
    return seen


def validate(doc):
    if doc.get("schema")!="supracraft-causal-kernel/1":
        fail("schema must be supracraft-causal-kernel/1")
    if doc.get("edition")!="java":
        fail("v1 authority is Minecraft Java only")
    if not isinstance(doc.get("minecraft_version"),str) or not doc["minecraft_version"]:
        fail("minecraft_version must be an exact non-empty string")
    source=doc.get("source")
    if not isinstance(source,dict) or not source.get("adapter_id"):
        fail("source.adapter_id is required")
    if not source.get("evidence_refs"):
        fail("source.evidence_refs must be non-empty")

    entities=doc.get("entities")
    events=doc.get("events")
    edges=doc.get("edges")
    limitations=doc.get("limitations")
    if not isinstance(entities,list) or not isinstance(events,list) or not isinstance(edges,list):
        fail("entities/events/edges must be arrays")
    if not isinstance(limitations,list) or not limitations:
        fail("limitations must be non-empty")

    entity_ids=_unique(entities,"entity_id","entity")
    event_ids=_unique(events,"event_id","event")
    _unique(edges,"edge_id","edge")

    port_ids={}
    for entity in entities:
        domains=entity.get("domains")
        if not isinstance(domains,list) or not domains or len(domains)!=len(set(domains)):
            fail(f"entity {entity['entity_id']} domains must be a non-empty unique array")
        if not set(domains)<=DOMAINS:
            fail(f"entity {entity['entity_id']} has unsupported domain")
        if entity.get("knowledge_state") not in KNOWLEDGE:
            fail(f"entity {entity['entity_id']} invalid knowledge_state")
        if not entity.get("evidence_refs"):
            fail(f"entity {entity['entity_id']} requires evidence")
        ports=entity.get("ports")
        if not isinstance(ports,list):
            fail(f"entity {entity['entity_id']} ports must be an array")
        seen=set()
        for port in ports:
            pid=port.get("port_id")
            if not isinstance(pid,str) or not pid or pid in seen:
                fail(f"entity {entity['entity_id']} has invalid/duplicate port")
            seen.add(pid)
            if port.get("domain") not in domains:
                fail(f"entity {entity['entity_id']} port {pid} domain not declared by entity")
            if port.get("direction") not in DIRECTIONS:
                fail(f"entity {entity['entity_id']} port {pid} invalid direction")
            if port.get("knowledge_state") not in KNOWLEDGE:
                fail(f"entity {entity['entity_id']} port {pid} invalid knowledge_state")
            if not isinstance(port.get("semantic_type"),str) or not port["semantic_type"]:
                fail(f"entity {entity['entity_id']} port {pid} semantic_type required")
        port_ids[entity["entity_id"]]=seen

    for event in events:
        if event.get("domain") not in DOMAINS:
            fail(f"event {event['event_id']} invalid domain")
        if event.get("knowledge_state") not in KNOWLEDGE:
            fail(f"event {event['event_id']} invalid knowledge_state")
        subjects=event.get("subject_entity_ids")
        if not isinstance(subjects,list) or not subjects or not set(subjects)<=entity_ids:
            fail(f"event {event['event_id']} has dangling/empty subjects")
        timing=event.get("event_time")
        if not isinstance(timing,dict):
            fail(f"event {event['event_id']} missing event_time")
        tick=timing.get("game_tick")
        micro=timing.get("microstep_or_order")
        if tick is not None and (not isinstance(tick,int) or tick<0):
            fail(f"event {event['event_id']} invalid game_tick")
        if micro is not None and (not isinstance(micro,int) or micro<0):
            fail(f"event {event['event_id']} invalid microstep_or_order")
        if micro is not None and tick is None:
            fail(f"event {event['event_id']} cannot order an unknown tick")
        if not event.get("evidence_refs"):
            fail(f"event {event['event_id']} requires evidence")

    for edge in edges:
        if edge.get("edge_kind") not in EDGE_KINDS:
            fail(f"edge {edge['edge_id']} invalid edge_kind")
        if edge.get("knowledge_state") not in KNOWLEDGE:
            fail(f"edge {edge['edge_id']} invalid knowledge_state")
        if not isinstance(edge.get("semantic_type"),str) or not edge["semantic_type"]:
            fail(f"edge {edge['edge_id']} semantic_type required")
        if not edge.get("evidence_refs"):
            fail(f"edge {edge['edge_id']} requires evidence")
        for side in ("source","target"):
            endpoint=edge.get(side)
            if not isinstance(endpoint,dict):
                fail(f"edge {edge['edge_id']} missing {side}")
            eid=endpoint.get("entity_id")
            if eid not in entity_ids:
                fail(f"edge {edge['edge_id']} dangling {side} entity: {eid}")
            pid=endpoint.get("port_id")
            if pid is not None and pid not in port_ids[eid]:
                fail(f"edge {edge['edge_id']} dangling {side} port: {eid}#{pid}")
        event_id=edge.get("event_id")
        if event_id is not None and event_id not in event_ids:
            fail(f"edge {edge['edge_id']} dangling event_id: {event_id}")

    return doc


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("document",type=Path)
    args=ap.parse_args()
    doc=json.loads(args.document.read_text())
    validate(doc)
    print(json.dumps({
        "schema":doc["schema"],
        "edition":doc["edition"],
        "minecraft_version":doc["minecraft_version"],
        "entities":len(doc["entities"]),
        "events":len(doc["events"]),
        "edges":len(doc["edges"]),
        "unknown_entities":sum(x["knowledge_state"]=="unknown" for x in doc["entities"]),
        "unknown_edges":sum(x["knowledge_state"]=="unknown" for x in doc["edges"]),
        "status":"pass"
    },sort_keys=True))


if __name__=="__main__":
    main()
