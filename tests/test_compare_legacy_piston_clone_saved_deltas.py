"""Synthetic-only saved CORE clone parity and source custody hard negatives."""
import copy
import json
import hashlib
import unittest

from test_inspect_legacy_piston_clone_modes import fixture as clone_fixture
from tools.compare_legacy_piston_clone_saved_deltas import (
    clone_source_dest_pairs, classify_deltas, audit,
)


class OriginalCloneSavedStateTests(unittest.TestCase):
    def fixture(self):
        g,sig,cmds=clone_fixture()
        pair=clone_source_dest_pairs(g,sig)[0]
        return g,sig,cmds,pair

    def test_exact_original_source_dest_join(self):
        _,_,_,pair=self.fixture()
        self.assertEqual(pair,((100,70,100),(0,71,0)))

    def test_exact_saved_state_equal_is_not_a_restoration_delta(self):
        g,sig,cmds,(src,dest)=self.fixture()
        out=audit(g,sig,{src:(55,4),dest:(55,4)},cmds)
        self.assertEqual(out["candidate_nonidentical_saved_pairs"],0)
        self.assertEqual(out["saved_state_equality_counts"],
                         {"exact_id_and_metadata_equal":1})
        self.assertEqual(out["candidate_world_write"],"NOT_EXECUTED")
        self.assertFalse(out["gameplay_promoted"])

    def test_same_id_different_metadata_is_eligible_but_not_observed(self):
        g,sig,cmds,(src,dest)=self.fixture()
        out=audit(g,sig,{src:(55,0),dest:(55,8)},cmds)
        self.assertEqual(out["saved_state_equality_counts"],
                         {"same_id_different_metadata":1})
        self.assertEqual(out["candidate_nonidentical_saved_pairs"],1)
        self.assertEqual(out["piston_motion"],"NOT_OBSERVED")

    def test_source_redstone_wire_destination_air_is_possible_restore(self):
        g,sig,cmds,(src,dest)=self.fixture()
        out=audit(g,sig,{src:(55,0),dest:(0,0)},cmds)
        self.assertEqual(out["saved_state_equality_counts"],
                         {"different_block_id":1})
        self.assertEqual(out["source_to_destination_class_pairs"],
                         {"redstone_wire_to_air":1})
        self.assertEqual(out["source_material_class_counts"],
                         {"redstone_wire":1})
        self.assertEqual(out["destination_material_class_counts"],{"air":1})

    def test_source_air_dest_wire_is_possible_clear_not_executed(self):
        g,sig,cmds,(src,dest)=self.fixture()
        out=audit(g,sig,{src:(0,0),dest:(55,0)},cmds)
        self.assertEqual(out["source_to_destination_class_pairs"],
                         {"air_to_redstone_wire":1})
        self.assertEqual(out["candidate_world_write"],"NOT_EXECUTED")

    def test_missing_destination_is_unknown_not_air(self):
        g,sig,cmds,(src,dest)=self.fixture()
        out=audit(g,sig,{src:(55,0)},cmds)
        self.assertEqual(out["unresolved_saved_pairs"],1)
        self.assertEqual(out["resolved_saved_pairs"],0)
        self.assertEqual(out["candidate_nonidentical_saved_pairs"],0)
        self.assertEqual(out["source_to_destination_class_pairs"],{})

    def test_invalid_or_boolean_metadata_rejected(self):
        for bad in ((55,True),(55,17),(-1,0),(55,-1),(5000,0)):
            with self.subTest(bad=bad):
                g,sig,cmds,(src,dest)=self.fixture()
                with self.assertRaisesRegex(ValueError,"(nonintegral|impossible)"):
                    audit(g,sig,{src:bad,dest:(55,0)},cmds)

    def test_wrong_source_fingerprint_blocks_comparison(self):
        g,sig,cmds,(src,dest)=self.fixture()
        altered={next(iter(cmds)):"clone 1 2 3 4 5 6 7 8 9"}
        with self.assertRaisesRegex(ValueError,"fingerprint"):
            audit(g,sig,{src:(55,0),dest:(55,0)},altered)

    def test_source_command_missing_blocks_comparison(self):
        g,sig,_,(src,dest)=self.fixture()
        with self.assertRaisesRegex(ValueError,"provenance"):
            audit(g,sig,{src:(55,0),dest:(55,0)},{})

    def test_nonreplace_mode_fails_closed(self):
        g,sig,_=clone_fixture("masked","normal")
        _,_,_,pair=self.fixture()
        cid=g["nodes"][-1]["node_id"]
        raw="clone 100 70 100 102 70 100 0 71 0 masked normal"
        with self.assertRaisesRegex(ValueError,"not pinned replace normal"):
            audit(g,sig,{pair[0]:(55,0),pair[1]:(0,0)},{cid:raw})

    def test_reverse_original_source_corners_preserve_mapping(self):
        g,sig,cmds,(src,dest)=self.fixture()
        rows=g["edges"]["command_world_targets"]
        rows[0]["target_position"]=[102,70,100]
        rows[1]["target_position"]=[100,70,100]
        self.assertEqual(clone_source_dest_pairs(g,sig),[(src,dest)])
        self.assertEqual(audit(g,sig,{src:(55,1),dest:(0,0)},cmds)
                         ["candidate_nonidentical_saved_pairs"],1)

    def test_multiple_pairs_counts_preserve_source_and_target_separately(self):
        r=classify_deltas([
            ((1,2,3),(4,5,6)),
            ((7,8,9),(10,11,12)),
            ((13,14,15),(16,17,18)),
        ],{
            (1,2,3):(0,0),(4,5,6):(0,0),
            (7,8,9):(93,0),(10,11,12):(93,1),
            (13,14,15):(55,0),(16,17,18):(152,0),
        })
        self.assertEqual(r["saved_state_equality_counts"],
                         {"exact_id_and_metadata_equal":1,
                          "same_id_different_metadata":1,
                          "different_block_id":1})
        self.assertEqual(r["candidate_nonidentical_saved_pairs"],2)
        self.assertEqual(r["resolved_saved_pairs"],3)

    def test_duplicate_clone_endpoint_is_unqualified(self):
        g,sig,cmds,_=self.fixture()
        g["edges"]["command_world_targets"].append(
            copy.deepcopy(g["edges"]["command_world_targets"][2]))
        self.assertEqual(clone_source_dest_pairs(g,sig),[])

    def test_private_source_and_target_positions_not_in_public_derivative(self):
        g,sig,cmds,(src,dest)=self.fixture()
        g["nodes"][-1]["command"]["body"]="ORIGINAL_SECRET"
        serialized=json.dumps(audit(g,sig,{src:(55,0),dest:(0,0)},cmds))
        for token in ("100,70,100","0,71,0","50,70,50","ORIGINAL_SECRET",
                      '"position"','"target_position"','"node_id"'):
            self.assertNotIn(token,serialized)


if __name__=="__main__":
    unittest.main()
