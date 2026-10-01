import importlib.util
import unittest

from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("recover",ROOT/"tools"/"analyze_causal_path_recoverability.py")
recover=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(recover)

def node(nid,*roles,kind=None):
    d={"node_id":nid,"roles":list(roles)}
    if kind:d["kind"]=kind
    return d

class CausalPathRecoverabilityTests(unittest.TestCase):
    def test_coherent_chain_has_supported_state_actuator_and_feedback_paths(self):
        doc={
          "schema":"fixture/coherent",
          "nodes":[
            node("sensor","sensor_input"),
            node("state",kind="scoreboard_objective"),
            node("actuator","actuator"),
            node("feedback","presentation_feedback"),
          ],
          "edges":[
            {"source":"sensor","target":"state","edge_type":"writes","certainty":"strong"},
            {"source":"state","target":"actuator","edge_type":"gates","certainty":"strong"},
            {"source":"actuator","target":"feedback","edge_type":"renders","certainty":"adequate"},
          ]
        }
        d=recover.analyze(doc)
        self.assertEqual(1.0,d["trusted_path_metrics"]["sensor_to_state"]["coverage"])
        self.assertEqual(1.0,d["trusted_path_metrics"]["sensor_to_actuator"]["coverage"])
        self.assertEqual(1.0,d["trusted_path_metrics"]["sensor_to_feedback"]["coverage"])

    def test_nested_semantic_state_objective_is_resolved_as_graph_node(self):
        doc={
          "schema":"fixture/nested-semantic-state",
          "nodes":[node("feedback","presentation_feedback")],
          "semantic_state":{
            "objectives":[node("score",kind="scoreboard_objective")]
          },
          "edges":[
            {"source":"score","target":"feedback","edge_type":"state_renders","certainty":"strong"}
          ]
        }
        d=recover.analyze(doc)
        self.assertEqual(0,d["unresolved_edge_count"])
        self.assertEqual(1.0,d["trusted_path_metrics"]["state_with_feedback_downstream"]["coverage"])

    def test_hidden_effect_without_feedback_is_not_counted_as_feedback_covered(self):
        doc={
          "schema":"fixture/opaque",
          "nodes":[node("sensor","sensor_input"),node("actuator","actuator"),node("feedback","presentation_feedback")],
          "edges":[{"source":"sensor","target":"actuator","certainty":"strong","edge_type":"triggers"}]
        }
        d=recover.analyze(doc)
        self.assertEqual(1.0,d["trusted_path_metrics"]["sensor_to_actuator"]["coverage"])
        self.assertEqual(0.0,d["trusted_path_metrics"]["sensor_to_feedback"]["coverage"])

    def test_weak_adjacency_does_not_silently_become_trusted_causality(self):
        doc={
          "schema":"fixture/weak",
          "nodes":[node("sensor","sensor_input"),node("feedback","presentation_feedback")],
          "edges":[{"source":"sensor","target":"feedback","certainty":"weak","edge_type":"physical_adjacency_candidate"}]
        }
        d=recover.analyze(doc)
        self.assertEqual(0.0,d["trusted_path_metrics"]["sensor_to_feedback"]["coverage"])
        self.assertEqual(1.0,d["candidate_path_metrics"]["sensor_to_feedback"]["coverage"])
        self.assertEqual(1.0,d["weak_edge_sensitivity"]["sensor_to_feedback"])

    def test_legacy_undirected_adjacency_is_candidate_only(self):
        doc={
          "schema":"fixture/legacy-adjacency",
          "nodes":[node("sensor","sensor_input"),node("feedback","presentation_feedback")],
          "edges":{"physical_adjacency_candidates":[
            {"a":"sensor","b":"feedback","edge_type":"physical_adjacency_candidate","certainty":"weak"}
          ]}
        }
        d=recover.analyze(doc)
        self.assertEqual(0.0,d["trusted_path_metrics"]["sensor_to_feedback"]["coverage"])
        self.assertEqual(1.0,d["candidate_path_metrics"]["sensor_to_feedback"]["coverage"])
        self.assertEqual(1.0,d["weak_edge_sensitivity"]["sensor_to_feedback"])

    def test_more_nodes_do_not_improve_coverage_when_disconnected(self):
        nodes=[node("sensor","sensor_input"),node("effect","actuator")]
        nodes += [node(f"noise{i}","signal_transport") for i in range(100)]
        d=recover.analyze({"schema":"fixture/density","nodes":nodes,"edges":[]})
        self.assertEqual(0.0,d["trusted_path_metrics"]["sensor_to_actuator"]["coverage"])
        self.assertEqual(102,d["node_count"])

    def test_unresolved_target_is_reported_not_assumed(self):
        doc={
          "schema":"fixture/unresolved",
          "nodes":[node("sensor","sensor_input")],
          "edges":[{"source":"sensor","target":None,"target_position":[1,2,3],"certainty":"adequate","edge_type":"command_world_target"}]
        }
        d=recover.analyze(doc)
        self.assertEqual(1,d["unresolved_edge_count"])

if __name__=="__main__":
    unittest.main()
