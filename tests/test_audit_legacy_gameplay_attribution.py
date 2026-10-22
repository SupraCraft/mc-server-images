"""No real world data, server, player or proprietary command strings."""
import copy
import hashlib
import json
import unittest

from tools.audit_legacy_gameplay_attribution import audit


def fixture():
    cmd_id="1,0,0"
    sha=hashlib.sha256(b"setblock 2 0 0 minecraft:redstone_block").hexdigest()
    command={"node_id":cmd_id,"family":"command_block",
             "verb":"setblock","command_sha256":sha}
    selection={
      "schema":"supracraft-legacy-runtime-probe-selection/1",
      "selected":[{
        "node_id":"0,1,0","family":"wooden_pressure_plate",
        "candidate_component_commands":[command]
      }]
    }
    prev={"sha256":sha,"verb":"setblock","success_count":0,"condition_met":None,
          "powered":False,"last_execution":0,"last_output_sha256":None}
    after={**prev,"success_count":1,"last_execution":50}
    paired={
      "schema":"supracraft-paired-legacy-runtime-probes/1","minecraft_version":"1.8.8",
      "paired_control_design":True,"probe_count":1,"results":[{
        "probe":selection["selected"][0],
        "activation_method":"paired_exact_1.8.8_player_occupancy",
        "evidence":{"live_sensor_activation_observed":True,
                    "command_block_change_count":3},
        "sensor_state":{"changed":True},
        "player_actor":{"control":{"status":"ready","minecraft_version":"1.8.8"},
                        "activated":{"status":"ready","minecraft_version":"1.8.8"}},
        "world_target_source_scope":[cmd_id],
        "execution_receipt":{
          "schema":"supracraft-legacy-execution-receipt/1",
          "command_scope":[cmd_id],
          "changed_command_ids":[cmd_id],
          "commands":[{"node_id":cmd_id,"control":prev,"activated":after}],
          "targets":[{"source":cmd_id,"target_position":[2,0,0],
                      "target_kind":"point","verb":"setblock",
                      "control":{"legacy_block_id":0},"activated":{"legacy_block_id":152},
                      "changed":True}]
        }
      }]
    }
    return selection, paired


class SourceAttributionTests(unittest.TestCase):
    def test_exact_source_matched_pair_passes_but_no_causal_promotion(self):
        s,p=fixture()
        r=audit(s,p)
        self.assertEqual(r["matched_source_state_and_unique_target_count"],1)
        self.assertEqual(r["effect_observation_class"],"scoped_direct_block_target_delta")
        self.assertEqual(r["exclusive_downstream_causality"],"NOT_PROVEN")
        self.assertEqual(r["modern_26_3_equivalence"],"NOT_RUN")

    def test_unverified_source_sha_fails(self):
        s,p=fixture()
        p["results"][0]["execution_receipt"]["commands"][0]["activated"]["sha256"]="fake"
        with self.assertRaises(ValueError):audit(s,p)

    def test_unscoped_changed_target_fails(self):
        s,p=fixture()
        p["results"][0]["execution_receipt"]["targets"][0]["source"]="999,1,1"
        with self.assertRaises(ValueError):audit(s,p)

    def test_non_mutating_verb_cannot_claim_target_change(self):
        s,p=fixture()
        p["results"][0]["execution_receipt"]["targets"][0]["verb"]="testforblock"
        with self.assertRaises(ValueError):audit(s,p)

    def test_unchanged_command_does_not_get_attributed(self):
        s,p=fixture()
        cmd=p["results"][0]["execution_receipt"]
        cmd["commands"][0]["activated"]=copy.deepcopy(cmd["commands"][0]["control"])
        cmd["changed_command_ids"]=[]
        r=audit(s,p)
        self.assertEqual(r["effect_observation_class"],"scoped_candidate_delta_no_changed_command")
        self.assertEqual(r["matched_source_state_and_unique_target_count"],0)

    def test_false_positive_changed_flag_fails(self):
        s,p=fixture()
        p["results"][0]["execution_receipt"]["targets"][0]["changed"]=False
        with self.assertRaises(ValueError):audit(s,p)

    def test_absent_live_sensor_fails(self):
        s,p=fixture()
        p["results"][0]["evidence"]["live_sensor_activation_observed"]=False
        with self.assertRaises(ValueError):audit(s,p)

    def test_original_version_mismatch_fails(self):
        s,p=fixture()
        p["minecraft_version"]="26.3"
        with self.assertRaises(ValueError):audit(s,p)

    def test_competing_source_declared_for_same_target_is_ambiguous(self):
        s,p=fixture()
        cmd=p["results"][0]["execution_receipt"]
        src="5,5,5";sha="f"*64
        s["selected"][0]["candidate_component_commands"].append({
            "node_id":src,"family":"command_block","verb":"setblock","command_sha256":sha
        })
        cmd["command_scope"].append(src)
        p["results"][0]["world_target_source_scope"].append(src)
        base={**cmd["commands"][0]["control"],"sha256":sha}
        cmd["commands"].append({"node_id":src,"control":base,"activated":dict(base)})
        cmd["targets"].append({
            "source":src,"target_position":[2,0,0],"target_kind":"point",
            "verb":"setblock","control":{"legacy_block_id":0},
            "activated":{"legacy_block_id":0},"changed":False,
        })
        r=audit(s,p)
        self.assertEqual(r["changed_target_with_competing_writer_count"],1)
        self.assertEqual(r["effect_observation_class"],"scoped_effect_unattributable_ambiguous_writers")

    def test_no_raw_coordinates_or_command_text_in_aggregate(self):
        s,p=fixture()
        r=json.dumps(audit(s,p))
        self.assertNotIn("minecraft:redstone_block",r)
        self.assertNotIn('"target_position"',r)
        self.assertNotIn('"command_scope"',r)
        self.assertNotIn("1,0,0",r)


if __name__=="__main__":
    unittest.main()
