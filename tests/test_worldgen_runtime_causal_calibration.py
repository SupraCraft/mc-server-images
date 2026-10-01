import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location(
    "runtime_calibration",
    ROOT/"tools"/"analyze_runtime_causal_calibration.py",
)
cal=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(cal)


def node(nid,*roles):
    return {"node_id":nid,"roles":list(roles)}


def runtime_row(probe, *, message=False, effect=False, changed_feedback=None):
    changed_feedback=changed_feedback or []
    return {
        "probe":{"node_id":probe,"family":"wooden_pressure_plate"},
        "execution_receipt":{"outcome_class":"fixture"},
        "presentation_feedback_command_state_changes":[
            {
                "node_id":nid,
                "verb":"effect",
                "changed_fields":["success_count"],
                "success_count_changed":True,
                "control_success_count":0,
                "activated_success_count":1,
            }
            for nid in changed_feedback
        ],
        "client_feedback_delta":{
            "message_events_added":(
                [{"sha256":"0"*64,"position":"system","count":1}]
                if message else []
            ),
            "message_events_removed":[],
            "self_effect_events_added":(
                [{"event":"start","id":1,"amplifier":0,"duration":20,"count":1}]
                if effect else []
            ),
            "self_effect_events_removed":[],
            "control_truncated":False,
            "activated_truncated":False,
        },
    }


class RuntimeCausalCalibrationTests(unittest.TestCase):
    def test_candidate_only_runtime_feedback_remains_candidate_only(self):
        graph={
            "schema":"fixture/static",
            "nodes":[
                node("sensor","sensor_input"),
                node("dust","signal_transport"),
                node("feedback","presentation_feedback"),
            ],
            "edges":[
                {
                    "source":"sensor","target":"dust",
                    "edge_type":"direct","certainty":"adequate",
                },
                {
                    "a":"dust","b":"feedback",
                    "edge_type":"physical_adjacency_candidate","certainty":"weak",
                },
            ],
        }
        runtime={
            "schema":"fixture/runtime",
            "results":[runtime_row(
                "sensor",effect=True,changed_feedback=["feedback"]
            )],
        }
        d=cal.analyze(graph,runtime)
        w=d["witnesses"][0]
        self.assertEqual(
            "runtime_feedback_with_candidate_only_static_path",
            w["calibration_class"],
        )
        self.assertEqual(
            "candidate_only",
            w["static_support"]["to_any_presentation_feedback"]["support_class"],
        )
        self.assertEqual(
            1,
            w["static_support"]["to_runtime_feedback_command_nodes"]["feedback"][
                "candidate_path"
            ]["weak_hop_count"],
        )
        self.assertEqual(
            "scoped_feedback_command_execution_plus_client_delivery",
            w["runtime_feedback"]["attribution_class"],
        )

    def test_runtime_delivery_without_static_path_stays_unattributed(self):
        graph={
            "schema":"fixture/static",
            "nodes":[
                node("sensor","sensor_input"),
                node("feedback","presentation_feedback"),
            ],
            "edges":[],
        }
        runtime={
            "schema":"fixture/runtime",
            "results":[runtime_row("sensor",message=True)],
        }
        d=cal.analyze(graph,runtime)
        w=d["witnesses"][0]
        self.assertEqual(
            "runtime_feedback_without_static_feedback_path",
            w["calibration_class"],
        )
        self.assertEqual(
            "none",
            w["static_support"]["to_any_presentation_feedback"]["support_class"],
        )
        self.assertEqual(
            "client_delivery_without_scoped_feedback_command_state_delta",
            w["runtime_feedback"]["attribution_class"],
        )

    def test_trusted_static_path_is_reported_without_edge_mutation(self):
        graph={
            "schema":"fixture/static",
            "nodes":[
                node("sensor","sensor_input"),
                node("feedback","presentation_feedback"),
            ],
            "edges":[{
                "source":"sensor","target":"feedback",
                "edge_type":"exact","certainty":"strong",
            }],
        }
        runtime={
            "schema":"fixture/runtime",
            "results":[runtime_row(
                "sensor",effect=True,changed_feedback=["feedback"]
            )],
        }
        d=cal.analyze(graph,runtime)
        w=d["witnesses"][0]
        self.assertEqual(
            "runtime_feedback_with_trusted_static_path",
            w["calibration_class"],
        )
        self.assertEqual(
            "trusted",
            w["static_support"]["to_any_presentation_feedback"]["support_class"],
        )
        self.assertEqual(
            1,
            w["static_support"]["to_any_presentation_feedback"]["trusted_path"][
                "hop_count"
            ],
        )

    def test_no_runtime_feedback_witness_does_not_claim_calibration(self):
        graph={
            "schema":"fixture/static",
            "nodes":[node("sensor","sensor_input")],
            "edges":[],
        }
        runtime={
            "schema":"fixture/runtime",
            "results":[runtime_row("sensor")],
        }
        d=cal.analyze(graph,runtime)
        w=d["witnesses"][0]
        self.assertEqual("no_runtime_feedback_witness",w["calibration_class"])
        self.assertFalse(w["runtime_feedback"]["feedback_delta_observed"])


if __name__=="__main__":
    unittest.main()
