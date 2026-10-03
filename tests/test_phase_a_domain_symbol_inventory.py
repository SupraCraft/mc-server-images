import importlib.util
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/"tools"
sys.path.insert(0,str(TOOLS))
PATH=TOOLS/"inventory_phase_a_domain_symbols.py"
SPEC=importlib.util.spec_from_file_location("phase_a_symbols",PATH)
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class PhaseADomainSymbolInventoryTests(unittest.TestCase):
    def test_domains_are_exactly_four_phase_a_peers_minus_existing_electrical_lane(self):
        self.assertEqual(set(mod.ROLE_SETS),{"mechanical","programmable","inventory"})

    def test_mechanical_scope_is_piston_only_for_first_rep(self):
        self.assertEqual(
            set(mod.ROLE_SETS["mechanical"]),
            {"piston_base","piston_moving_entity"},
        )

    def test_inventory_scope_is_hopper_only_for_first_rep(self):
        self.assertEqual(
            set(mod.ROLE_SETS["inventory"]),
            {"hopper_block","hopper_block_entity"},
        )

    def test_programmable_reuses_existing_exact_command_surface(self):
        self.assertEqual(
            set(mod.ROLE_SETS["programmable"]),
            {"command_block","command_block_entity","command_dispatch"},
        )

    def test_no_presentation_peer_domain(self):
        self.assertNotIn("presentation",mod.ROLE_SETS)

    def test_no_cross_domain_role_in_a_domain_set(self):
        roles=[]
        for rows in mod.ROLE_SETS.values():
            roles.extend(rows)
        self.assertEqual(len(roles),len(set(roles)))


if __name__=="__main__":
    unittest.main()
