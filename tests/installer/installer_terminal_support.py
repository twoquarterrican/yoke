"""Disposable interactive shell for the public installer's terminal handoff."""

from __future__ import annotations

import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path


class TerminalShell:
    """Keep real POSIX pipeline/job control without touching the user's tty."""

    prompt = b"INSTALL_TEST_PROMPT> "

    def __init__(self, env):
        import pty

        self.fd, slave = pty.openpty()
        self.process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), str(slave)],
            pass_fds=(slave,),
            start_new_session=True,
            env={**env, "PS1": self.prompt.decode(), "PROMPT_COMMAND": ""},
        )
        self.pid = self.process.pid
        os.close(slave)
        self.output = bytearray()
        self.job_groups = set()

    def send(self, data):
        os.write(self.fd, data)

    def wait_for(self, marker, *, after=0):
        deadline = time.monotonic() + 12
        while marker not in self.output[after:]:
            foreground = os.tcgetpgrp(self.fd)
            if foreground > 0 and foreground != self.pid:
                self.job_groups.add(foreground)
            assert time.monotonic() < deadline, self.output[-6000:].decode(
                errors="replace"
            )
            if select.select([self.fd], [], [], 0.1)[0]:
                self.output.extend(os.read(self.fd, 65536))
        return bytes(self.output[after:])

    def close(self):
        # Failed assertions must also retire the foreground pipeline, not just
        # its shell. Each test owns a separate controlling terminal/session.
        for group in self.job_groups:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            os.kill(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.process.wait(timeout=3)
        os.close(self.fd)


def wizard():
    """Real setup driver; no machine setup, credentials or installation writes."""
    import json
    from textual.app import App
    from textual.widgets import Static

    from yoke_cli.config.onboard_terminal_driver import run_wizard_app
    from yoke_cli.config.onboard_wizard_app import OnboardWizardApp

    assert sys.argv[1:] == ["setup", "--post-install"]
    Path(os.environ["TERMINAL_EVIDENCE"]).write_text(
        json.dumps(
            {
                "stdin_tty": os.isatty(0),
                "foreground": os.tcgetpgrp(0) == os.getpgrp(),
            }
        )
    )

    class SetupApp(App):
        BINDINGS = OnboardWizardApp.BINDINGS
        action_quit_wizard = OnboardWizardApp.action_quit_wizard
        _applying = False
        _checking_blocks_quit = False

        def compose(self):
            yield Static("PIPE_SETUP_READY")

    app = SetupApp()
    run_wizard_app(app)
    raise SystemExit(app.exit_code)


if __name__ == "__main__":
    import fcntl
    import termios

    # Acquire the terminal from a single-threaded child before starting bash;
    # forkpty inside pytest can inherit locks from its capture/xdist threads.
    slave = int(sys.argv[1])
    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
    for fd in (0, 1, 2):
        os.dup2(slave, fd)
    os.close(slave)
    os.execve("/bin/bash", ["bash", "--noprofile", "--norc", "-i"], os.environ)
