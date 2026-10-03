import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"tools"/"analyze_four_domain_census.py"
S=importlib.util.spec_from_file_location("census",P)
m=importlib.util.module_from_spec(S); S.loader.exec_module(m)

class FourDomainCensusTests(unittest.TestCase):
    def test_four_domains_and_observation_are_separate(self):
        doc={
            "schema":"supracraft-legacy-causal-machinery/1",
            "world_format":"legacy_anvil_pre_palette",
            "nodes":[
                {"node_id":"a","family":"redstone_wire"},
                {"node_id":"b","family":"piston"},
                {"node_id":"c","family":"command_block"},
                {"node_id":"d","family":"hopper"},
                {"node_id":"e","family":"redstone_lamp_on"},
                {"node_id":"f","family":"mystery"},
            ],
            "edges":{
                "physical_adjacency_candidates":[
                    {"a":"a","b":"b"},{"a":"b","b":"c"},{"a":"d","b":"e"}
                ],
                "container_comparator_reads":[],
                "trapped_chest_open_power_candidates":[],
                "repeater_command_block_conduction_edges":[],
                "command_authored_redstone_edges":[],
                "command_world_targets":[],
            }
        }
        out=m.analyze(doc)
        self.assertEqual(out["domain_node_counts"],{
            "electrical":1,"inventory":1,"mechanical":1,"programmable":1
        })
        self.assertEqual(out["observation_surface_counts"],{"redstone_lamp_on":1})
        self.assertEqual(out["unknown_family_counts"],{"mystery":1})
        self.assertEqual(out["mixed_domain_component_candidate_count"],1)
        self.assertIn("not_interaction_qualification",out["analysis_kind"])

    def test_mixed_component_does_not_create_semantic_edge(self):
        doc={
            "schema":"supracraft-legacy-causal-machinery/1",
            "nodes":[
                {"node_id":"a","family":"hopper"},
                {"node_id":"b","family":"comparator_on"},
            ],
            "edges":{
                "physical_adjacency_candidates":[{"a":"a","b":"b"}],
                "container_comparator_reads":[{"source":"a","target":"b"}],
                "trapped_chest_open_power_candidates":[],
                "repeater_command_block_conduction_edges":[],
                "command_authored_redstone_edges":[],
                "command_world_targets":[],
            }
        }
        out=m.analyze(doc)
        self.assertEqual(
            out["phase_b_interface_candidate_counts"][
                "inventory_to_electrical_container_comparator_candidate"
            ],1
        )
        self.assertTrue(out["largest_mixed_domain_candidates"][0]["mixed_domain_candidate"])

if __name__=="__main__":
    unittest.main()
