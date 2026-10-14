"""Quit the macOS apps holding sign-ins before a capture or reset touches them.

Safari writes its cookie store when it quits. A store copied or kept while
Safari runs can miss the newest sign-in, and Safari later writes its in-memory
state back over a home restored under it. Capture and reset therefore quit it
first, gracefully: a forced kill would discard the cookies being saved.
"""

from __future__ import annotations

import shlex
from typing import Callable

from yoke_harness.ssh_mac_terminal_app import run_osascript
from yoke_harness.test_machine_types import HostActionResult

SIGN_IN_APPS = ("Safari",)
QUIT_WAIT_SECONDS = 30
SIGN_IN_APP_QUIT_NOT_PROVED = "test_machine_sign_in_app_quit_not_proved"


def quit_sign_in_apps(run: Callable[..., object], user: str) -> HostActionResult:
    """Ask each running sign-in app to quit and prove it exited."""
    quit_apps: list[str] = []
    for app in SIGN_IN_APPS:
        running = shlex.join(["/usr/bin/pgrep", "-x", "-u", user, app])
        if run(running + " >/dev/null").returncode != 0:
            continue
        asked = run_osascript(run, [f'tell application "{app}" to quit'])
        exited = run(
            f"i=0; while [ $i -lt {QUIT_WAIT_SECONDS} ]; do "
            f"{running} >/dev/null || exit 0; /bin/sleep 1; i=$((i+1)); done; exit 1",
            timeout=QUIT_WAIT_SECONDS + 15,
        )
        if exited.returncode != 0:
            return HostActionResult(
                False,
                {
                    "app": app,
                    "quit_requested": asked.returncode == 0,
                    "recovery": (
                        f"Quit {app} on the test machine ({app} > Quit {app}), "
                        "answering any prompt it shows, then retry. It was not "
                        "force-quit, so its unsaved sign-ins are still in memory."
                        + (
                            ""
                            if asked.returncode == 0
                            else f" To let Yoke quit it next time, allow the SSH "
                            f"session to control {app} in System Settings > "
                            "Privacy & Security > Automation."
                        )
                    ),
                },
                SIGN_IN_APP_QUIT_NOT_PROVED,
            )
        quit_apps.append(app)
    return HostActionResult(True, {"sign_in_apps_quit": quit_apps})


__all__ = [
    "QUIT_WAIT_SECONDS",
    "SIGN_IN_APPS",
    "SIGN_IN_APP_QUIT_NOT_PROVED",
    "quit_sign_in_apps",
]
