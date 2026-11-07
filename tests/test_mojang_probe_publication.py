import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("publication", Path(__file__).parents[1] / "tools/mojang_probe_publication.py")
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class PublicationTests(unittest.TestCase):
    def test_remote_reset_or_deletion_after_preflight_rejects_publication(self):
        for delete in (False, True):
            with self.subTest(delete=delete), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                remote, repo = root / "remote.git", root / "repo"
                def fixture_git(*args):
                    return subprocess.check_output(["git", *map(str, args)], cwd=repo if repo.exists() else root,
                                                   text=True, stderr=subprocess.DEVNULL).strip()
                fixture_git("init", "--bare", remote)
                fixture_git("clone", remote, repo)
                fixture_git("config", "user.name", "test")
                fixture_git("config", "user.email", "test@example.invalid")
                (repo / "seed").write_text("ancestor")
                fixture_git("add", "seed")
                fixture_git("commit", "-m", "ancestor")
                ancestor = fixture_git("rev-parse", "HEAD")
                (repo / "seed").write_text("event")
                fixture_git("commit", "-am", "event")
                event = fixture_git("rev-parse", "HEAD")
                fixture_git("push", "origin", f"HEAD:refs/heads/{pub.BRANCH}")
                source = root / "result.json"
                source.write_text(json.dumps({"schema": "supracraft-mojang-release-identity/1", "minecraft_version": "26.3",
                    "provenance": {"launcher_manifest_sha256": "a" * 64, "version_metadata_sha256": "b" * 64},
                    "server_artifact": {"sha256": "c" * 64, "expected_sha1": "d" * 40, "actual_sha1": "d" * 40, "size": 123},
                    "client_artifact": {"sha256": "e" * 64, "expected_sha1": "f" * 40, "actual_sha1": "f" * 40, "size": 456},
                    "artifact_version_json": {"id": "26.3"}}))
                original_git = pub.git
                def race_git(*args):
                    if args[0] == "push":
                        command = ["--git-dir", remote, "update-ref"]
                        if delete:
                            command += ["-d", f"refs/heads/{pub.BRANCH}", event]
                        else:
                            command += [f"refs/heads/{pub.BRANCH}", ancestor, event]
                        fixture_git(*command)
                    return original_git(*args)
                previous = Path.cwd()
                os.chdir(repo)
                try:
                    with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": f"refs/heads/{pub.BRANCH}",
                                                "GITHUB_SHA": event, "PROBE_RESULT": str(source)}), patch.object(pub, "git", side_effect=race_git):
                        with self.assertRaises(subprocess.CalledProcessError):
                            pub.persist()
                    remote_ref = fixture_git("ls-remote", "origin", f"refs/heads/{pub.BRANCH}")
                    self.assertEqual(remote_ref.split()[0] if remote_ref else None, None if delete else ancestor)
                finally:
                    os.chdir(previous)

    def test_release_ids(self):
        for value in ["26.3", "26.4-snapshot-3", "1.21.11", "24w14a", "1.20 Pre-Release 1"]:
            if " " in value:
                with self.assertRaises(ValueError):
                    pub.validate_version(value)
            else:
                self.assertEqual(pub.validate_version(value), value)
        for value in ["", "..", "../26.3", "26.3\nX=y", '26.3"; touch x', "$(id)", "a/b", "a\\b", "-a", "x" * 81]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                pub.validate_version(value)

    def test_resolve_data_only_and_default(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "env"
            with patch.dict(os.environ, {"GITHUB_ENV": str(output), "REQUESTED_VERSION": ""}):
                pub.resolve()
            self.assertEqual(output.read_text(), "MC_VERSION=26.3\n")
            with patch.dict(os.environ, {"GITHUB_ENV": str(output), "REQUESTED_VERSION": "26.3\nBAD=yes"}):
                with self.assertRaises(ValueError):
                    pub.resolve()
            self.assertEqual(output.read_text(), "MC_VERSION=26.3\n")

    def test_real_publication_noop_stale_and_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote, repo = root / "remote.git", root / "repo"
            def git(*args, cwd=None):
                return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
            git("init", "--bare", str(remote))
            git("clone", str(remote), str(repo))
            git("config", "user.name", "test", cwd=repo)
            git("config", "user.email", "test@example.invalid", cwd=repo)
            (repo / "seed").write_text("seed")
            git("add", "seed", cwd=repo)
            git("commit", "-m", "seed", cwd=repo)
            git("push", "origin", f"HEAD:refs/heads/{pub.BRANCH}", cwd=repo)
            initial = git("rev-parse", "HEAD", cwd=repo)
            source = root / "result.json"
            result = {"schema": "supracraft-mojang-release-identity/1", "minecraft_version": "26.3",
                      "provenance": {"launcher_manifest_sha256": "a" * 64, "version_metadata_sha256": "b" * 64},
                      "server_artifact": {"sha256": "c" * 64, "expected_sha1": "d" * 40, "actual_sha1": "d" * 40, "size": 123},
                      "client_artifact": {"sha256": "e" * 64, "expected_sha1": "f" * 40, "actual_sha1": "f" * 40, "size": 456},
                      "artifact_version_json": {"id": "26.3"}}
            source.write_text(json.dumps(result))
            previous = Path.cwd()
            os.chdir(repo)
            try:
                env = {"GITHUB_EVENT_NAME": "push", "GITHUB_REF": f"refs/heads/{pub.BRANCH}", "GITHUB_SHA": initial, "PROBE_RESULT": str(source)}
                with patch.dict(os.environ, env):
                    self.assertEqual(pub.persist(), "PUBLISHED")
                    published = git("rev-parse", "HEAD", cwd=repo)
                    self.assertNotEqual(initial, published)
                    self.assertEqual(git("ls-remote", "origin", f"refs/heads/{pub.BRANCH}", cwd=repo).split()[0], published)
                    os.environ["GITHUB_SHA"] = published
                    self.assertEqual(pub.persist(), "UNCHANGED")
                    self.assertEqual(git("rev-parse", "HEAD", cwd=repo), published)
                    for bad in [{**result, "schema": "wrong"}, {**result, "minecraft_version": "26.4"},
                                {"schema": result["schema"], "minecraft_version": "26.3"},
                                {**result, "provenance": {}},
                                {**result, "server_artifact": {**result["server_artifact"], "actual_sha1": "0" * 40}},
                                {**result, "client_artifact": {**result["client_artifact"], "size": True}},
                                {**result, "artifact_version_json": {"id": "26.4"}}]:
                        source.write_text(json.dumps(bad))
                        with self.assertRaises(ValueError):
                            pub.persist()
                    source.write_text(json.dumps(result))
                    git("checkout", "--detach", initial, cwd=repo)
                    os.environ["GITHUB_SHA"] = initial
                    self.assertEqual(pub.persist(), "STALE_EVENT_SKIPPED")
                    self.assertEqual(git("rev-parse", "HEAD", cwd=repo), initial)
                    os.environ["GITHUB_EVENT_NAME"] = "workflow_dispatch"
                    with self.assertRaises(ValueError):
                        pub.persist()
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
