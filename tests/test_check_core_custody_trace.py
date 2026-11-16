"""Synthetic adversarial examples; these tests do not establish game behavior."""
import unittest
import copy
from tools.check_core_custody_trace import CARRIERS, SCHEMA, TraceError, check_trace

IDENTITY = "source-marked:synthetic-fixture"


def snapshot(seq, event, carrier=None, reissues=0, restored=False):
    c = {k: 0 for k in CARRIERS}
    if carrier:
        c[carrier] = 1
    return {"seq": seq, "event": event, "scope_complete": True,
            "origin": "server_reported", "core_identity": IDENTITY,
            "carriers": c, "reissues": reissues, "restored": restored}


def admitted_trace():
    return {"schema": SCHEMA, "core_identity": IDENTITY, "observations": [
        snapshot(0, "baseline", "chest"),
        snapshot(1, "transfer", "cursor"),
        snapshot(2, "transfer", "main_inventory"),
        snapshot(3, "loss"),
        snapshot(4, "reissue", "chest", reissues=1),
        snapshot(5, "transfer", "offhand", reissues=1),
        snapshot(6, "install", "installed_socket", reissues=1, restored=True),
        snapshot(7, "post_restart", "installed_socket", reissues=1, restored=True),
    ]}


class Admission(unittest.TestCase):
    def test_valid_report_is_consistent_but_not_provenance_verification(self):
        out = check_trace(admitted_trace())
        self.assertEqual(out["result"], "CONSISTENT_REPORTED_TRACE")
        self.assertTrue(out["final_restored"])
        self.assertTrue(out["complete_reported_recovery_chain"])
        self.assertEqual(out["reported_milestones"],
                         {"loss": True, "reissue": True, "install": True, "post_restart": True})
        self.assertIn("not verified", out["warning"])

    def test_forged_single_row_install_is_rejected(self):
        doc = admitted_trace()
        doc["observations"] = [snapshot(0, "install", "installed_socket", restored=True)]
        with self.assertRaisesRegex(TraceError, "untouched chest baseline"):
            check_trace(doc)

    def test_baseline_must_start_with_one_chest_objective_and_zero_reissues(self):
        for event, carrier, reissues in (
            ("transfer", "cursor", 0),
            ("baseline", None, 0),
            ("baseline", "chest", 1),
        ):
            with self.subTest(event=event, carrier=carrier, reissues=reissues):
                doc = admitted_trace()
                doc["observations"][0] = snapshot(0, event, carrier, reissues=reissues)
                with self.assertRaisesRegex(TraceError, "untouched chest baseline"):
                    check_trace(doc)

    def test_cursor_duplicate_without_real_loss_is_rejected(self):
        t = admitted_trace()
        t["observations"][2] = snapshot(2, "reissue", "chest", reissues=1)
        with self.assertRaisesRegex(TraceError, "without observed zero-custody loss"):
            check_trace(t)

    def test_cursor_chest_double_count_is_rejected(self):
        t = admitted_trace()
        t["observations"][1]["carriers"]["chest"] = 1
        with self.assertRaisesRegex(TraceError, "duplicate objective"):
            check_trace(t)

    def test_crafting_cursor_and_hotbar_are_required(self):
        for missing in ("crafting", "cursor", "hotbar", "loaded_item_entities", "installed_socket"):
            with self.subTest(missing=missing):
                t = admitted_trace()
                del t["observations"][1]["carriers"][missing]
                with self.assertRaisesRegex(TraceError, "missing/extra carrier"):
                    check_trace(t)

    def test_partial_scan_is_rejected(self):
        t = admitted_trace()
        t["observations"][3]["scope_complete"] = False
        with self.assertRaisesRegex(TraceError, "partial carrier"):
            check_trace(t)

    def test_unknown_origin_is_rejected(self):
        t = admitted_trace()
        t["observations"][2]["origin"] = "local_bot_guess"
        with self.assertRaisesRegex(TraceError, "server_reported"):
            check_trace(t)

    def test_reissue_without_loss_is_rejected(self):
        t = admitted_trace()
        t["observations"][3]["event"] = "transfer"
        with self.assertRaisesRegex(TraceError, "objective disappeared without recorded loss"):
            check_trace(t)

    def test_unrecorded_mint_is_rejected(self):
        t = admitted_trace()
        t["observations"][4]["event"] = "transfer"
        with self.assertRaisesRegex(TraceError, "unrecorded reissue increment"):
            check_trace(t)

    def test_restored_without_socket_is_rejected(self):
        t = admitted_trace()
        t["observations"][6]["carriers"]["installed_socket"] = 0
        with self.assertRaisesRegex(TraceError, "no installed objective"):
            check_trace(t)

    def test_chest_to_socket_instant_install_is_rejected(self):
        t = {"schema": SCHEMA, "core_identity": IDENTITY, "observations": [
            snapshot(0, "baseline", "chest"),
            snapshot(1, "install", "installed_socket", restored=True),
        ]}
        with self.assertRaisesRegex(TraceError, "previously held objective"):
            check_trace(t)

    def test_cursor_cannot_physically_install_without_equipping(self):
        t = {"schema": SCHEMA, "core_identity": IDENTITY, "observations": [
            snapshot(0, "baseline", "chest"),
            snapshot(1, "transfer", "cursor"),
            snapshot(2, "install", "installed_socket", restored=True),
        ]}
        with self.assertRaisesRegex(TraceError, "previously held objective"):
            check_trace(t)

    def test_socket_cannot_appear_earlier_as_generic_transfer(self):
        t = {"schema": SCHEMA, "core_identity": IDENTITY, "observations": [
            snapshot(0, "baseline", "chest"),
            snapshot(1, "transfer", "hotbar"),
            snapshot(2, "transfer", "installed_socket"),
            snapshot(3, "install", "installed_socket", restored=True),
        ]}
        with self.assertRaisesRegex(TraceError, "socket appeared without installation"):
            check_trace(t)

    def test_repeated_install_event_is_rejected(self):
        t = {"schema": SCHEMA, "core_identity": IDENTITY, "observations": [
            snapshot(0, "baseline", "chest"),
            snapshot(1, "transfer", "offhand"),
            snapshot(2, "install", "installed_socket", restored=True),
            snapshot(3, "install", "installed_socket", restored=True),
        ]}
        with self.assertRaisesRegex(TraceError, "previously held objective"):
            check_trace(t)

    def test_realistic_first_install_from_hotbar_is_consistent(self):
        t = {"schema": SCHEMA, "core_identity": IDENTITY, "observations": [
            snapshot(0, "baseline", "chest"),
            snapshot(1, "transfer", "hotbar"),
            snapshot(2, "install", "installed_socket", restored=True),
            snapshot(3, "post_restart", "installed_socket", restored=True),
        ]}
        self.assertEqual(check_trace(t)["result"], "CONSISTENT_REPORTED_TRACE")


    def test_keeper_chest_loss_without_player_custody_is_not_complete_recovery(self):
        # First failure: direct untouched chest -> loss -> reissue
        # previously received a complete chain despite no original custody.
        t = {"schema": SCHEMA, "core_identity": IDENTITY, "observations": [
            snapshot(0, "baseline", "chest"),
            snapshot(1, "loss"),
            snapshot(2, "reissue", "chest", reissues=1),
            snapshot(3, "transfer", "hotbar", reissues=1),
            snapshot(4, "install", "installed_socket", reissues=1, restored=True),
            snapshot(5, "post_restart", "installed_socket", reissues=1, restored=True),
        ]}
        result = check_trace(t)
        self.assertEqual(result["result"], "CONSISTENT_REPORTED_TRACE")
        self.assertEqual(result["reported_milestones"],
                         {"loss": True, "reissue": True, "install": True, "post_restart": True})
        self.assertFalse(result["original_player_custody_before_loss"])
        self.assertFalse(result["complete_reported_recovery_chain"])

    def test_cursor_acquisition_before_original_loss_counts_as_reported_recovery(self):
        t = {"schema": SCHEMA, "core_identity": IDENTITY, "observations": [
            snapshot(0, "baseline", "chest"),
            snapshot(1, "transfer", "cursor"),
            snapshot(2, "loss"),
            snapshot(3, "reissue", "chest", reissues=1),
            snapshot(4, "transfer", "hotbar", reissues=1),
            snapshot(5, "install", "installed_socket", reissues=1, restored=True),
            snapshot(6, "post_restart", "installed_socket", reissues=1, restored=True),
        ]}
        result = check_trace(t)
        self.assertTrue(result["original_player_custody_before_loss"])
        self.assertTrue(result["complete_reported_recovery_chain"])

    def test_reissued_custody_does_not_backfill_original_acquisition(self):
        t = {"schema": SCHEMA, "core_identity": IDENTITY, "observations": [
            snapshot(0, "baseline", "chest"),
            snapshot(1, "loss"),
            snapshot(2, "reissue", "chest", reissues=1),
            snapshot(3, "transfer", "cursor", reissues=1),
            snapshot(4, "transfer", "offhand", reissues=1),
            snapshot(5, "install", "installed_socket", reissues=1, restored=True),
            snapshot(6, "post_restart", "installed_socket", reissues=1, restored=True),
        ]}
        result = check_trace(t)
        self.assertFalse(result["original_player_custody_before_loss"])
        self.assertFalse(result["complete_reported_recovery_chain"])

    def test_restored_without_loss_or_reissue_is_not_complete_recovery_chain(self):
        doc = {"schema": SCHEMA, "core_identity": IDENTITY, "observations": [
            snapshot(0, "baseline", "chest"),
            snapshot(1, "transfer", "hotbar"),
            snapshot(2, "install", "installed_socket", restored=True),
            snapshot(3, "post_restart", "installed_socket", restored=True),
        ]}
        out = check_trace(doc)
        self.assertEqual(out["result"], "CONSISTENT_REPORTED_TRACE")
        self.assertTrue(out["final_restored"])
        self.assertFalse(out["complete_reported_recovery_chain"])
        self.assertEqual(out["reported_milestones"],
                         {"loss": False, "reissue": False, "install": True, "post_restart": True})

    def test_restored_without_restart_is_not_complete_recovery_chain(self):
        doc = admitted_trace()
        doc["observations"] = doc["observations"][:-1]
        out = check_trace(doc)
        self.assertTrue(out["final_restored"])
        self.assertFalse(out["complete_reported_recovery_chain"])
        self.assertEqual(out["reported_milestones"]["post_restart"], False)

    def test_restart_regression_is_rejected(self):
        t = admitted_trace()
        t["observations"][7]["restored"] = False
        with self.assertRaisesRegex(TraceError, "restored state regressed"):
            check_trace(t)

    def test_boolean_cannot_masquerade_as_inventory_count(self):
        t = admitted_trace()
        t["observations"][1]["carriers"]["cursor"] = True
        with self.assertRaisesRegex(TraceError, "expected a nonnegative integer"):
            check_trace(t)

    def test_unknown_event_rejected(self):
        t = admitted_trace()
        t["observations"][1]["event"] = "teleport"
        with self.assertRaisesRegex(TraceError, "unknown event"):
            check_trace(t)

    def test_missing_event_between_loss_and_reissue_rejected(self):
        t = admitted_trace()
        t["observations"][3] = snapshot(3, "transfer")
        with self.assertRaisesRegex(TraceError, "objective disappeared without recorded loss"):
            check_trace(t)


    def test_bounded_adversarial_mutation_matrix(self):
        baseline = admitted_trace()
        rejected = 0
        for i, row in enumerate(baseline["observations"]):
            for carrier in CARRIERS:
                for field, mutation in (
                    ("scope", lambda r: r.update(scope_complete=False)),
                    ("origin", lambda r: r.update(origin="bot_guess")),
                    ("identity", lambda r: r.update(core_identity="wrong_objective")),
                    ("missing", lambda r, k=carrier: r["carriers"].pop(k)),
                    ("negative", lambda r, k=carrier: r["carriers"].update({k: -1})),
                ):
                    with self.subTest(row=i, carrier=carrier, mutation=field):
                        candidate = copy.deepcopy(baseline)
                        mutation(candidate["observations"][i])
                        with self.assertRaises(TraceError):
                            check_trace(candidate)
                        rejected += 1
                if row["carriers"][carrier] == 0 and sum(row["carriers"].values()) == 1:
                    candidate = copy.deepcopy(baseline)
                    candidate["observations"][i]["carriers"][carrier] = 1
                    with self.assertRaisesRegex(TraceError, "duplicate objective"):
                        check_trace(candidate)
                    rejected += 1
        for i in range(1, len(baseline["observations"])):
            candidate = copy.deepcopy(baseline)
            candidate["observations"][i]["reissues"] += 1
            with self.assertRaises(TraceError):
                check_trace(candidate)
            rejected += 1
        self.assertEqual(376, rejected)


if __name__ == "__main__":
    unittest.main()
