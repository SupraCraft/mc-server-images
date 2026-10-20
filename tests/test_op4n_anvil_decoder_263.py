"""Source-only negative checks for opt-in, public-safe real 26.3 decoder diagnostic."""
import pathlib
import tempfile
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
from qualify_vanilla_datapack_player_263 import stopped_real_anvil_diagnostic

class SourceSafetyTests(unittest.TestCase):
    def test_no_read_of_missing_world(self):
        with tempfile.TemporaryDirectory() as d:
            observed=stopped_real_anvil_diagnostic(pathlib.Path(d), "preaction",lambda blob,stage: {})
            self.assertEqual(observed["classification"],"REGION_UNAVAILABLE")
            self.assertFalse(observed["native_truenas_g4_pass"])
    def test_invalid_stage_and_malformed_region(self):
        with tempfile.TemporaryDirectory() as d:
            world=pathlib.Path(d)
            self.assertEqual(stopped_real_anvil_diagnostic(world,"unknown",None)["classification"],"BAD_STAGE")
            fixed=world/"dimensions/minecraft/overworld/region/r.0.0.mca"
            fixed.parent.mkdir(parents=True)
            fixed.write_bytes(b"bad")
            self.assertEqual(stopped_real_anvil_diagnostic(world,"preaction",lambda blob,stage: {})["classification"],"REGION_FILE_BOUNDS")
    def test_only_fixed_exception_code_crosses(self):
        with tempfile.TemporaryDirectory() as d:
            world=pathlib.Path(d)
            fixed=world/"dimensions/minecraft/overworld/region/r.0.0.mca"
            fixed.parent.mkdir(parents=True)
            fixed.write_bytes(b"0"*8192)
            def secret(blob, stage):
                raise ValueError("token=PRIVATE-DONT-LOG")
            output=stopped_real_anvil_diagnostic(world,"candidate",secret)
            self.assertEqual(output["reason"],"UNCLASSIFIED")
            self.assertNotIn("PRIVATE",str(output))
            def fixed_error(blob,stage):
                raise ValueError("NBT_LIST_BOUNDS")
            output=stopped_real_anvil_diagnostic(world,"preaction",fixed_error)
            self.assertEqual(output["reason"],"NBT_LIST_BOUNDS")
    def test_positive_does_not_promote_truenas(self):
        with tempfile.TemporaryDirectory() as d:
            world=pathlib.Path(d)
            fixed=world/"dimensions/minecraft/overworld/region/r.0.0.mca"
            fixed.parent.mkdir(parents=True)
            fixed.write_bytes(b"0"*8192)
            good=lambda blob,stage: {"classification":"UNTRUSTED_REGION_BYTES_DECODED_ONLY","block_state_expectations_matched":True}
            result=stopped_real_anvil_diagnostic(world,"rollback",good)
            self.assertEqual(result["classification"],"STANDALONE_REAL_263_DECODER_MATCH")
            self.assertFalse(result["native_truenas_g4_pass"])
            self.assertFalse(result["region_bytes_published"])

if __name__ == "__main__": unittest.main()
