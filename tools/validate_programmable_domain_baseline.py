#!/usr/bin/env python3
import json
from pathlib import Path

PATH=Path("bench/worldgen/causal/programmable/programmable-domain-baseline-v1.json")

def validate(doc):
    assert doc["schema"]=="supracraft-programmable-domain-baseline/1"
    assert doc["edition"]=="java"
    assert doc["minecraft_version"]=="26.3"
    assert doc["domain"]=="programmable"
    assert doc["qualification_status"]=="candidate_existing_runtime_supported"
    classes={x["role"]:x for x in doc["exact_classes"]}
    assert set(classes)=={"command_block","command_block_entity","command_dispatch"}
    for row in classes.values():
        assert len(row["class_sha256"])==64
    hooks={x["id"]:x for x in doc["structural_hooks"]}
    assert set(hooks)=={
        "command_block_neighbor","command_block_tick","command_block_execute",
        "command_dispatch","command_dispatch_prefixed",
    }
    ev=doc["runtime_evidence"]
    assert ev["workflow_run_id"]==37101462459
    assert ev["job_id"]==111141661480
    assert ev["stock_canary_pass"] is True
    assert ev["instrumented_canary_pass"] is True
    assert ev["dropped_events"]==0
    assert ev["semantic_divergence"] is False
    assert {
        "command_block_neighbor","command_block_scheduled_tick",
        "command_trigger_start","command_trigger_end","command_dispatch",
    } <= set(ev["observed_event_families"])
    exclusions=" ".join(doc["exclusions"]).lower()
    assert "no electrical-to-programmable trigger semantics" in exclusions
    return doc

if __name__=="__main__":
    validate(json.loads(PATH.read_text()))
    print(json.dumps({"status":"pass","domain":"programmable","minecraft_version":"26.3"},sort_keys=True))
