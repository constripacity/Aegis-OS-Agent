"""Platform-capability probes for tests that rely on POSIX-only behaviour.

Aegis ships a Windows build and CI runs ``windows-latest``, so the suite must
stay green there. A few tests assert POSIX file-permission bits (``S_IROTH``,
``S_IXUSR`` — meaningless on Windows) or create symlinks (needs a privilege
Windows does not grant by default). Those are skipped on hosts that cannot host
them, while still running on Linux and macOS.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

WINDOWS = sys.platform == "win32"


def _symlinks_supported() -> bool:
    """True only if this process can actually create a symlink.

    Probes rather than guessing: a Windows host with Developer Mode (or an
    elevated CI runner) can create symlinks and should run these tests.
    """
    if not hasattr(os, "symlink"):
        return False
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "src"
        src.write_text("probe")
        try:
            (Path(tmp) / "link").symlink_to(src)
        except (OSError, NotImplementedError):
            return False
        return True


SYMLINKS_SUPPORTED = _symlinks_supported()

requires_symlinks = pytest.mark.skipif(
    not SYMLINKS_SUPPORTED,
    reason="creating symlinks is not permitted here (e.g. Windows without Developer Mode)",
)
requires_posix_perms = pytest.mark.skipif(
    WINDOWS,
    reason="POSIX file-permission bits (S_IROTH/S_IRGRP/S_IXUSR) are not meaningful on Windows",
)
