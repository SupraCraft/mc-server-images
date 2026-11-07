"""Keep optional-link skips specific; ordinary filesystem bugs must still fail."""
import errno
from pathlib import Path
import unittest
from unittest import mock

from filesystem_capabilities import require_symlink


class SymlinkCapabilityTests(unittest.TestCase):
    def test_actual_file_link_capability(self):
        require_symlink(self)

    def test_actual_directory_link_capability(self):
        require_symlink(self, target_is_directory=True)

    def test_expected_unavailable_errors_skip(self):
        windows_privilege_error = OSError("symlink privilege unavailable")
        windows_privilege_error.winerror = 1314
        errors = [NotImplementedError(), windows_privilege_error]
        errors.extend(OSError(code, "unavailable") for code in
                      {errno.EPERM, errno.EACCES, errno.ENOSYS, errno.ENOTSUP})
        for error in errors:
            with self.subTest(error=repr(error)):
                testcase = mock.Mock()
                testcase.skipTest.side_effect = unittest.SkipTest
                with mock.patch.object(Path, "symlink_to", side_effect=error):
                    with self.assertRaises(unittest.SkipTest):
                        require_symlink(testcase)
                testcase.skipTest.assert_called_once()

    def test_unrelated_symlink_errors_propagate(self):
        for code in (errno.EIO, errno.ENOSPC, errno.ENOENT, errno.EEXIST):
            with self.subTest(errno=code):
                error = OSError(code, "unexpected fixture failure")
                testcase = mock.Mock()
                with mock.patch.object(Path, "symlink_to", side_effect=error):
                    with self.assertRaises(OSError) as observed:
                        require_symlink(testcase)
                self.assertIs(observed.exception, error)
                testcase.skipTest.assert_not_called()

    def test_fixture_creation_error_is_not_a_capability_skip(self):
        testcase = mock.Mock()
        with mock.patch.object(Path, "write_bytes", side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                require_symlink(testcase)
        testcase.skipTest.assert_not_called()


if __name__ == "__main__":
    unittest.main()
