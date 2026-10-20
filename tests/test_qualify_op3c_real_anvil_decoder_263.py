"""Public-safe diagnostic boundary tests; no Minecraft world contents or network."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
from qualify_op3c_real_anvil_decoder_263 import (
    PINNED_G4_REF, SCHEMA, STAGES, sanitized_reason,
)

class FakeG4Refused(ValueError):
    pass

class PublicDiagnosticTests(unittest.TestCase):
    def test_exact_consumed_source_not_new_admission(self):
        self.assertEqual(PINNED_G4_REF, "e400f3a1719a21cf91ebc86ba8d44efea05c1325")
        self.assertEqual(STAGES, ("preaction", "candidate", "rollback"))
        self.assertIn("source-qualification", SCHEMA)

    def test_fixed_code_is_safe_but_arbitrary_exception_not_reflected(self):
        self.assertEqual(
            sanitized_reason(FakeG4Refused("NBT_LIST_BOUNDS"),
                             g4_refused_type=FakeG4Refused),
            "NBT_LIST_BOUNDS")
        for failure in (
            FakeG4Refused("secret?auth_token=private"),
            FakeG4Refused("/private/world/r.0.0.mca"),
            RuntimeError("NBT_LIST_BOUNDS"),
            FakeG4Refused("A" * 81),
            FakeG4Refused("bad_lowercase"),
        ):
            self.assertEqual(
                sanitized_reason(failure, g4_refused_type=FakeG4Refused),
                "DECODER_UNEXPECTED_EXCEPTION")

if __name__ == "__main__":
    unittest.main()
