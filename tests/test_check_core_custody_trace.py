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
        self.assertIn("not verified", out["warning"])

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
