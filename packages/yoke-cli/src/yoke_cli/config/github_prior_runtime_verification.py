"""Verify ownership of a prior runtime's GitHub credential launcher."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from yoke_cli.config import github_git_credential_launcher


def verified_prior_runtime_helper(
    python: Path,
    helper: Path,
    *,
    current_python: Path,
) -> bool:
    """Recognize a safe prior-runtime launcher without trusting its path."""

    try:
        python_info = python.stat()
        if not stat.S_ISREG(python_info.st_mode) or not os.access(python, os.X_OK):
            return False
        if python != current_python and stat.S_IMODE(python_info.st_mode) & 0o022:
            return False
        flags = (
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(
                os,
                "O_NONBLOCK",
                0,
            )
        )
        descriptor = os.open(helper, flags)
    except OSError:
        return False
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) & 0o022
            or info.st_size > 256 * 1024
        ):
            return False
        source = os.read(descriptor, 256 * 1024 + 1)
    except OSError:
        return False
    finally:
        os.close(descriptor)
    if not all(
        marker in source
        for marker in (
            b'BUNDLE_POINTER_NAME = "_yoke_github_helper_current"',
            b'BUNDLE_HELPER_NAME = "_yoke_github_git_credential_helper.py"',
            b"def selected_bundle(",
        )
    ):
        return False
    try:
        # The stable launcher is meaningful only beside a content-addressed,
        # integrity-checked bundle.  Marker-shaped files on their own remain
        # user-managed lookalikes and must never be removed automatically.
        github_git_credential_launcher.selected_bundle(
            helper.parent,
            module_names=github_git_credential_launcher.prior_launcher_module_names(
                source
            ),
        )
    except (OSError, github_git_credential_launcher.GitHubCredentialLauncherError):
        return False
    return True
