"""Probe optional filesystem primitives without masking unrelated test failures."""
import errno
from pathlib import Path
import tempfile


def require_symlink(testcase, target_is_directory=False):
    """Skip only when this account/filesystem cannot create the required link."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        target = root / "target"
        if target_is_directory:
            target.mkdir()
        else:
            target.write_bytes(b"symlink capability probe")
        try:
            (root / "link").symlink_to(
                target, target_is_directory=target_is_directory)
        except NotImplementedError:
            testcase.skipTest("filesystem symlink primitive unavailable")
        except OSError as error:
            unavailable = {errno.EPERM, errno.EACCES, errno.ENOSYS,
                           errno.ENOTSUP}
            if error.errno in unavailable or getattr(error, "winerror", None) == 1314:
                testcase.skipTest("filesystem symlink creation unsupported or not permitted")
            raise
