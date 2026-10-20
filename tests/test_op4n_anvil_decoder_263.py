"""Source-only negative checks for opt-in, public-safe real 26.3 decoder diagnostic."""
import hashlib
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
    def test_symlink_region_refused_before_decoder_reads(self):
        with tempfile.TemporaryDirectory() as d:
            world=pathlib.Path(d)
            fixed=world/"dimensions/minecraft/overworld/region/r.0.0.mca"
            fixed.parent.mkdir(parents=True)
            outside=world/"outside-region.mca"
            outside.write_bytes(b"X"*8192)
            fixed.symlink_to(outside)
            invoked=[]
            result=stopped_real_anvil_diagnostic(
                world, "preaction",
                lambda blob,stage: invoked.append(True))
            self.assertEqual(result["classification"],"REGION_SYMLINK_REFUSED")
            self.assertFalse(result["native_truenas_g4_pass"])
            self.assertFalse(invoked)

    def test_symlinked_parent_directory_never_read(self):
        with tempfile.TemporaryDirectory() as d:
            world = pathlib.Path(d) / "world"
            foreign = pathlib.Path(d) / "foreign"
            foreign.mkdir()
            (foreign / "r.0.0.mca").write_bytes(b"X" * 8192)
            parent = world / "dimensions/minecraft/overworld/region"
            parent.parent.mkdir(parents=True)
            parent.symlink_to(foreign, target_is_directory=True)
            called = []
            row = stopped_real_anvil_diagnostic(
                world, "rollback", lambda blob,stage:called.append(stage))
            self.assertEqual(row["classification"], "REGION_SYMLINK_REFUSED")
            self.assertFalse(row["native_truenas_g4_pass"])
            self.assertEqual(called, [])

    def test_mismatched_decoder_digest_and_stage_refused(self):
        with tempfile.TemporaryDirectory() as d:
            world=pathlib.Path(d)
            fixed=world/"dimensions/minecraft/overworld/region/r.0.0.mca"
            fixed.parent.mkdir(parents=True)
            fixed.write_bytes(b"0"*8192)
            for witness in (
                {"classification":"UNTRUSTED_REGION_BYTES_DECODED_ONLY",
                 "block_state_expectations_matched":True,
                 "stage":"preaction","region_sha256":"0"*64,
                 "native_guest_server_owned_bytes_proven":False,
                 "backend_independent_world_oracle_pass":False},
                {"classification":"UNTRUSTED_REGION_BYTES_DECODED_ONLY",
                 "block_state_expectations_matched":True,
                 "stage":"rollback",
                 "region_sha256":hashlib.sha256(b"0"*8192).hexdigest(),
                 "native_guest_server_owned_bytes_proven":False,
                 "backend_independent_world_oracle_pass":False},
                {"classification":"UNTRUSTED_REGION_BYTES_DECODED_ONLY",
                 "block_state_expectations_matched":True,
                 "stage":"preaction",
                 "region_sha256":hashlib.sha256(b"0"*8192).hexdigest(),
                 "native_guest_server_owned_bytes_proven":True,
                 "backend_independent_world_oracle_pass":False},
                {"classification":"UNTRUSTED_REGION_BYTES_DECODED_ONLY",
                 "block_state_expectations_matched":True,
                 "stage":"preaction",
                 "region_sha256":hashlib.sha256(b"0"*8192).hexdigest(),
                 "native_guest_server_owned_bytes_proven":False,
                 "backend_independent_world_oracle_pass":True},
            ):
                result=stopped_real_anvil_diagnostic(
                    world,"preaction",lambda blob,stage:witness)
                self.assertEqual(result["classification"],
                                 "DECODER_UNEXPECTED_VERDICT")

    def test_positive_does_not_promote_truenas(self):
        with tempfile.TemporaryDirectory() as d:
            world=pathlib.Path(d)
            fixed=world/"dimensions/minecraft/overworld/region/r.0.0.mca"
            fixed.parent.mkdir(parents=True)
            fixed.write_bytes(b"0"*8192)
            good=lambda blob,stage: {
                "classification":"UNTRUSTED_REGION_BYTES_DECODED_ONLY",
                "block_state_expectations_matched":True,
                "stage":stage,
                "region_sha256":hashlib.sha256(blob).hexdigest(),
                "native_guest_server_owned_bytes_proven":False,
                "backend_independent_world_oracle_pass":False}
            result=stopped_real_anvil_diagnostic(world,"rollback",good)
            self.assertEqual(result["classification"],"STANDALONE_REAL_263_DECODER_MATCH")
            self.assertFalse(result["native_truenas_g4_pass"])
            self.assertFalse(result["region_bytes_published"])
            self.assertEqual(result["region_sha256"],
                             hashlib.sha256(b"0"*8192).hexdigest())

if __name__ == "__main__": unittest.main()
