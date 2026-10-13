"""S5 fail-closed world-agent ownership and transaction tests (cheap, no Java)."""
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"tools"))
from qualify_world_agent_263_lifecycle import (
    Refused, assert_agent_receipt, owned_active, safe_switch,
    verify_fault_is_not_promotable, world_agent, admit_owned_world_symlink,
)
from minecraft_world_agent import tree_hash


class WorldAgentS5Tests(unittest.TestCase):
    def test_real_stage_activate_hash_restore_identity(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            agent=root/"agent"
            agent.mkdir()
            original=root/"original"
            original.mkdir()
            (original/"level.dat").write_bytes(b"test fixture only, not game")
            sha=tree_hash(original)
            r=world_agent(agent,"stage","prior",original)
            assert_agent_receipt("stage",r,"prior",sha)
            world_agent(agent,"activate","prior")
            self.assertTrue(owned_active(agent,"prior"))
            state=world_agent(agent,"status")
            assert_agent_receipt("status",state)
            self.assertEqual(state["active"],"releases/prior")
            record=world_agent(agent,"hash")
            assert_agent_receipt("hash",record,sha=sha)
            world_agent(agent,"stage","snapshot",original)
            world_agent(agent,"restore","snapshot")
            self.assertTrue(owned_active(agent,"snapshot"))

    def test_symlink_allowlist_is_only_owned_world_agent_descendants(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            home=root/"server"
            agent=root/"owned-world"
            home.mkdir()
            agent.mkdir()
            prefix=admit_owned_world_symlink(home,root,agent)
            content=(home/"allowed_symlinks.txt").read_text()
            self.assertEqual(content.splitlines()[-1],"[prefix]"+prefix)
            self.assertTrue(prefix.endswith("/owned-world/"))
            self.assertNotIn("[regex].*",content)
            self.assertNotEqual(content.splitlines()[-1],"[prefix]/tmp/")
            outside=root/"outside"
            outside.mkdir()
            with self.assertRaisesRegex(Refused,"S5_SYMLINK_OWNER_ROOT_REFUSED"):
                admit_owned_world_symlink(outside,home,agent)

    def test_active_server_blocks_world_pointer_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            with self.assertRaisesRegex(Refused,"S5_ACTIVE_SERVER_POINTER_MUTATION_REFUSED"):
                safe_switch(root,"activate","prior",
                            SimpleNamespace(poll=lambda: None))
            with self.assertRaisesRegex(Refused,"S5_UNADMITTED_SWITCH_VERB"):
                safe_switch(root,"stage","prior",None)

    def test_foreign_symlink_or_unstaged_release_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            (root/"releases").mkdir()
            foreign=root/"foreign"
            foreign.mkdir()
            (root/"active").symlink_to(foreign)
            with self.assertRaisesRegex(Refused,"S5_ACTIVE_OWNER_MISMATCH"):
                owned_active(root,"candidate")
            with self.assertRaisesRegex(Refused,"S5_RELEASE_ID_INVALID"):
                owned_active(root,"../../foreign")

    def test_synthetic_corruption_is_detected_not_accepted(self):
        sha="a"*64
        self.assertTrue(verify_fault_is_not_promotable(sha,sha))
        with self.assertRaisesRegex(Refused,"S5_INJECTED_HEALTH_ORACLE_MISMATCH"):
            verify_fault_is_not_promotable(sha,"b"*64)

    def test_forged_agent_receipt_is_rejected(self):
        row={"schema":"minecraft-world-agent-receipt/1",
             "verb":"stage","release":"baseline","sha256":"a"*64}
        assert_agent_receipt("stage",row,"baseline","a"*64)
        for k,value in (("schema","wrong"),("release","foreign"),("sha256","b"*64)):
            forged=dict(row)
            forged[k]=value
            with self.subTest(k=k),self.assertRaises(Refused):
                assert_agent_receipt("stage",forged,"baseline","a"*64)

    def test_symlink_stage_source_and_path_traversal_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            src=root/"src"
            src.mkdir()
            link=root/"outside"
            link.symlink_to(src)
            agent=root/"agent"
            agent.mkdir()
            with self.assertRaisesRegex(Refused,"S5_STAGE_SOURCE_NOT_OWNED_DIRECTORY"):
                world_agent(agent,"stage","candidate",link)
            with self.assertRaisesRegex(Refused,"S5_RELEASE_ID_INVALID"):
                world_agent(agent,"stage","../escape",src)

if __name__=="__main__":
    unittest.main()
