"""Source-free, bounded adversarial controls for electromechanical recovery."""
import copy
import json
import unittest

from tools.rank_legacy_electromechanical_witnesses import rank


def sample():
    return {
        "schema":"supracraft-legacy-causal-machinery/1",
        "nodes":[
            {"node_id":"0,70,0","family":"redstone_wire","position":[0,70,0]},
            {"node_id":"1,70,0","family":"repeater_off"},
            {"node_id":"2,70,0","family":"sticky_piston"},
            {"node_id":"9,70,0","family":"chest",
             "command":{"body":"secret_command_must_not_escape"}},
        ],
        "edges":{
            "physical_adjacency_candidates":[
                {"a":"0,70,0","b":"1,70,0"},
                {"a":"1,70,0","b":"2,70,0"},
            ],
            "oriented_signal_candidates":[
                {"source":"0,70,0","target":"1,70,0",
                 "edge_type":"oriented_rear_input_candidate"},
                {"source":"1,70,0","target":"2,70,0",
                 "edge_type":"oriented_front_output_candidate"},
            ],
            "direct_redstone_edges":[],
        },
    }


class ElectromechanicalRecoveryTests(unittest.TestCase):
    def test_repeater_to_sticky_piston_is_only_static(self):
        r=rank(sample())
        self.assertEqual(r["mechanical_component_occurrences"],1)
        candidate=r["signatures"][0]
        self.assertEqual(candidate["oriented_repeater_to_piston_edges"],1)
        self.assertEqual(candidate["oriented_wire_to_repeater_edges"],1)
        self.assertEqual(candidate["disposition"],
                         "ORIENTED_REPEATER_TO_PISTON_STATIC_CANDIDATE")
        self.assertFalse(r["causal_power_or_motion_proven"])
        self.assertEqual(r["native_original_version_execution"],"NOT_RUN")

    def test_unpowered_adjacency_does_not_count_as_actuator_input(self):
        d=sample()
        d["edges"]["oriented_signal_candidates"]=[]
        x=rank(d)["signatures"][0]
        self.assertEqual(x["disposition"],"NO_NAMED_PISTON_INPUT")

    def test_reversed_repeater_output_not_counted(self):
        d=sample()
        d["edges"]["oriented_signal_candidates"][1]["source"]="2,70,0"
        d["edges"]["oriented_signal_candidates"][1]["target"]="1,70,0"
        self.assertEqual(rank(d)["signatures"][0]["oriented_repeater_to_piston_edges"],0)

    def test_direct_wire_to_piston_recognized_only_when_named(self):
        d=sample()
        d["edges"]["direct_redstone_edges"]=[{
            "source":"0,70,0","target":"2,70,0",
            "edge_type":"legacy_dust_direct_component_power"
        }]
        c=rank(d)["signatures"][0]
        self.assertEqual(c["direct_wire_to_piston_edges"],1)
        self.assertEqual(c["disposition"],"DIRECT_DUST_TO_PISTON_STATIC_CANDIDATE")

    def test_direct_wrong_direction_fails_to_claim_power(self):
        d=sample()
        d["edges"]["oriented_signal_candidates"]=[]
        d["edges"]["direct_redstone_edges"]=[{
            "source":"2,70,0","target":"0,70,0",
            "edge_type":"legacy_dust_direct_component_power"
        }]
        self.assertEqual(rank(d)["signatures"][0]["direct_wire_to_piston_edges"],0)

    def test_source_schema_mismatch_rejected(self):
        d=sample();d["schema"]="unknown"
        with self.assertRaises(ValueError):rank(d)

    def test_duplicate_node_rejected(self):
        d=sample();d["nodes"].append(copy.deepcopy(d["nodes"][0]))
        with self.assertRaisesRegex(ValueError,"duplicate"):rank(d)

    def test_missing_adjacency_fails_closed(self):
        d=sample();del d["edges"]["physical_adjacency_candidates"]
        with self.assertRaisesRegex(ValueError,"adjacency"):rank(d)

    def test_dangling_adjacency_rejected(self):
        d=sample();d["edges"]["physical_adjacency_candidates"][0]["b"]="missing"
        with self.assertRaisesRegex(ValueError,"endpoint"):rank(d)

    def test_wrong_signature_filters_target(self):
        d=sample();key=rank(d)["signatures"][0]["signature_sha256"]
        self.assertEqual(rank(d,signature=key)["mechanical_component_occurrences"],1)
        with self.assertRaisesRegex(ValueError,"target signature"):
            rank(d,signature="f"*64)

    def test_no_world_coordinates_or_source_payload(self):
        d=sample()
        text=json.dumps(rank(d))
        for raw in ("0,70,0","1,70,0","2,70,0","secret_command_must_not_escape"):
            self.assertNotIn(raw,text)

    def test_node_input_order_determinism(self):
        d=sample();e=copy.deepcopy(d)
        e["nodes"].reverse()
        e["edges"]["physical_adjacency_candidates"].reverse()
        self.assertEqual(rank(d),rank(e))

    def test_unknown_edge_types_not_upgraded_to_actuator_input(self):
        d=sample()
        d["edges"]["oriented_signal_candidates"]=[{
            "source":"1,70,0","target":"2,70,0",
            "edge_type":"invented_repeater_power"
        }]
        self.assertEqual(rank(d)["signatures"][0]["oriented_repeater_to_piston_edges"],0)


if __name__=="__main__":
    unittest.main()
