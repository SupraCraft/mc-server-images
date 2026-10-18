"""Cheap adversarial checks for the bounded 26.3 immutable-OCI candidate.

Live container, Minecraft and external world retention require separate GHA
and must not be inferred from these mocks.
"""
import pathlib
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
from qualify_vanilla_263_oci_disposable import (
    BASE, CANDIDATE_TAG, Refused, observed_immutable_image, verify_java25, stopped_world_region_witness
)

SHA = "5a2ab74ae179c11e2dbbce67f307cdcf2c1257b3abb0f654d3a310b3d8ea57da"
OUTPUT = (
    "Name:      ghcr.io/itzg/minecraft-server:2026.10.0-java25\n"
    "MediaType: application/vnd.oci.image.index.v1+json\n"
    "Digest:    sha256:" + SHA + "\n"
    "Manifests:\n  Name: ghcr.io/itzg/minecraft-server@sha256:" + ("b"*64)
    + "\n  Platform: linux/amd64\n"
)
PINNED = ("Name: " + BASE + "@sha256:" + SHA +
          "\nDigest:    sha256:" + SHA + "\n")


class OciCandidateTests(unittest.TestCase):
    def test_imagetools_discovery_pins_all_subsequent_uses(self):
        commands = []
        def runner(args, timeout=120, check=True):
            commands.append(args)
            return subprocess.CompletedProcess(args, 0,
                OUTPUT if len(commands) == 1 else PINNED, "")
        with patch("qualify_vanilla_263_oci_disposable.run", side_effect=runner):
            digest, ref = observed_immutable_image()
        self.assertEqual(digest, "sha256:" + SHA)
        self.assertEqual(ref, BASE + "@" + digest)
        self.assertEqual(commands[0][-1], CANDIDATE_TAG)
        self.assertEqual(commands[1][-1], ref)

    def test_refuse_missing_digest_multiple_digest_or_no_amd64(self):
        for invalid in (
            OUTPUT.replace("Digest:    sha256:" + SHA, "Digest:    unspecified"),
            OUTPUT.replace("Manifests:", "Digest:    sha256:" + "c"*64 + "\nManifests:"),
            OUTPUT.replace("linux/amd64", "linux/arm64"),
            OUTPUT.replace(SHA, "c"*64),
        ):
            def runner(args, timeout=120, check=True):
                return subprocess.CompletedProcess(args, 0, invalid, "")
            with patch("qualify_vanilla_263_oci_disposable.run", side_effect=runner):
                with self.assertRaises(Refused):
                    observed_immutable_image()

    def test_refuse_tag_drift_on_immutable_manifest_readback(self):
        def runner(args, timeout=120, check=True):
            return subprocess.CompletedProcess(args, 0,
                OUTPUT if args[-1] == CANDIDATE_TAG
                else PINNED.replace(SHA, "d"*64), "")
        with patch("qualify_vanilla_263_oci_disposable.run", side_effect=runner):
            with self.assertRaisesRegex(Refused, "IMMUTABLE"):
                observed_immutable_image()

    def test_real_world_region_witness_bounded_nondisclosing_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            region = root / "region"
            region.mkdir()
            target = region / "r.0.0.mca"
            def observe(wanted):
                record = stopped_world_region_witness(root)
                self.assertEqual(record["classification"], wanted)
                self.assertEqual(record["fixed_overworld_region_name"], "r.0.0.mca")
                self.assertFalse(record["region_bytes_published"])
                self.assertFalse(record["native_truenas_oracle_pass"])
                self.assertFalse(record["g4_three_checkpoint_world_pass"])
                self.assertEqual(record["physical_truenas_apply"], "HOLD")
                self.assertNotIn(tmp, str(record))
            observe("REGION_NOT_PRESENT")
            target.write_bytes(b"x" * 8192)
            observe("REGION_FILE_BOUNDED_PRESENT")
            target.write_bytes(b"x" * 7)
            observe("REGION_OUT_OF_BOUNDS")
            target.unlink()
            target.symlink_to(root / "foreign")
            observe("REGION_NOT_REGULAR_FILE")
            target.unlink()
            target.mkdir()
            observe("REGION_NOT_REGULAR_FILE")

    def test_region_witness_is_not_a_fallback_or_authoritative_oracle(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = pathlib.Path(tmp)
            (world / "region").mkdir()
            (world / "region" / "r.0.0.mca").write_bytes(b"z" * 8192)
            outcome = stopped_world_region_witness(world)
            self.assertTrue(outcome["host_observer_only"])
            self.assertFalse(outcome["native_truenas_oracle_pass"])
            self.assertNotIn("world_path", outcome)
            self.assertNotIn("region_digest", outcome)

    def test_java25_only(self):
        for stderr, wanted in (
            ('openjdk version "25.0.2" 2026-01-20\n', True),
            ('openjdk version "21.0.8" 2025-07-15\n', False),
        ):
            def runner(args, timeout=120, check=True):
                return subprocess.CompletedProcess(args, 0, "", stderr)
            with patch("qualify_vanilla_263_oci_disposable.run", side_effect=runner):
                if wanted:
                    self.assertEqual(verify_java25(BASE + "@sha256:" + SHA), "25")
                else:
                    with self.assertRaisesRegex(Refused, "JAVA_25"):
                        verify_java25(BASE + "@sha256:" + SHA)

if __name__ == "__main__":
    unittest.main()
