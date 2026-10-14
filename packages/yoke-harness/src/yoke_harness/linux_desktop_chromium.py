"""Drive the Linux test user's desktop Chromium; runs on the host with stdlib only.

The installer under test opens its approval link in the desktop's default
browser. Chromium hands that link to its already-running instance, so the
browser is started first with a loopback DevTools port; the approval then
reads that instance's tabs and presses the page's own visible control.
The caller (``ssh_linux_browser_approval``) owns which tabs qualify and ships
this source after ``linux_devtools_page``, so neither uses a __future__ import.
"""

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from urllib.parse import quote
from urllib.request import urlopen

from yoke_harness.linux_devtools_page import DevToolsPage  # host: prepended source

CHROMIUM_EXECUTABLES = ("chromium", "chromium-browser", "/snap/bin/chromium")
CHROMIUM_DESKTOP_ENTRIES = (
    "chromium.desktop",
    "chromium-browser.desktop",
    "chromium_chromium.desktop",
)
DEVTOOLS_READY_SECONDS = 20
QUIT_WAIT_SECONDS = 30
TAB_WAIT_SECONDS = 15
CONTROL_ATTEMPTS = 40
NAVIGATION_ATTEMPTS = 40
POLL_SECONDS = 0.25
PROVISION = (
    "Provision the desktop with the Machine QA Pack's "
    "ops/machine-qa/provision_linux_desktop.py (linux-host-provisioning.md section 4); "
    "it installs Chromium and makes it the default browser. Then rerun."
)


class ChromiumRefusal(RuntimeError):
    """A named refusal the controller reports with its recovery."""

    def __init__(self, reason, recovery):
        super().__init__(reason)
        self.reason = reason
        self.recovery = recovery


def user_data_dirs():
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return (config / "chromium", Path.home() / "snap/chromium/common/chromium")


def browser_pids():
    """The user's Chromium browser processes, excluding renderers and helpers."""
    pids = []
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            if "chromium" not in os.readlink(process / "exe"):
                continue
            argv = (process / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if not any(arg.startswith(b"--type=") for arg in argv):
            pids.append(int(process.name))
    return pids


def _get_json(port, path):
    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
        return json.loads(response.read())


def devtools_port():
    """The live loopback DevTools port of the running Chromium, if it has one."""
    for directory in user_data_dirs():
        try:
            port = int((directory / "DevToolsActivePort").read_text().split()[0])
            _get_json(port, "/json/version")
            return port
        except (OSError, ValueError, IndexError):
            continue
    return None


def quit_chromium():
    """Ask Chromium to quit and prove it exited; it saves its cookies on SIGTERM."""
    pids = browser_pids()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + QUIT_WAIT_SECONDS
    while browser_pids():
        if time.monotonic() >= deadline:
            raise ChromiumRefusal(
                "linux_desktop_chromium_quit_not_proved",
                "Close every Chromium window on the test machine's desktop, answering any prompt it shows, then retry. Chromium was asked to quit and was not force-killed, so its unsaved sign-ins are still in memory.",
            )
        time.sleep(POLL_SECONDS)
    return bool(pids)


def _default_browser():
    try:
        result = subprocess.run(
            ["xdg-settings", "get", "default-web-browser"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def prepare():
    """Start or reuse the desktop's default Chromium with a loopback DevTools port."""
    default = _default_browser()
    if default not in CHROMIUM_DESKTOP_ENTRIES:
        raise ChromiumRefusal(
            "linux_desktop_default_browser_not_chromium",
            f"The installer opens approval links in the desktop's default browser, which is {default or 'unset'}. {PROVISION}",
        )
    if devtools_port() is not None:
        return {"chromium": "reused"}
    executable = next(filter(None, map(shutil.which, CHROMIUM_EXECUTABLES)), None)
    if executable is None:
        raise ChromiumRefusal(
            "linux_desktop_chromium_missing",
            PROVISION,
        )
    restarted = quit_chromium()
    for directory in user_data_dirs():
        (directory / "DevToolsActivePort").unlink(missing_ok=True)
    subprocess.Popen(
        [executable, "--remote-debugging-port=0"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + DEVTOOLS_READY_SECONDS
    while devtools_port() is None:
        if time.monotonic() >= deadline:
            raise ChromiumRefusal(
                "linux_desktop_chromium_devtools_unavailable",
                f"{executable} started without a DevTools port in {' or '.join(str(d) for d in user_data_dirs())}. Use the distribution's Chromium build for the default profile, close Chromium on the desktop, then rerun.",
            )
        time.sleep(POLL_SECONDS)
    return {"chromium": "restarted" if restarted else "started"}


def _pages(port):
    return [
        page for page in _get_json(port, "/json/list") if page.get("type") == "page"
    ]


def _port():
    port = devtools_port()
    if port is None:
        raise ChromiumRefusal(
            "linux_desktop_chromium_devtools_unavailable",
            "Desktop Chromium is not running with its DevTools port; rerun the case so the gate prepares it before the installer opens the approval link.",
        )
    return port


def tabs(origin):
    """Wait for a tab on the approval origin, then report every open page URL."""
    port = _port()
    deadline = time.monotonic() + TAB_WAIT_SECONDS
    while True:
        urls = [page.get("url", "") for page in _pages(port)]
        if (
            any(url.startswith(origin + "/") for url in urls)
            or time.monotonic() >= deadline
        ):
            return {"urls": urls}
        time.sleep(POLL_SECONDS)


def approve(allowed_urls, label):
    """Press the visible control only in an allowed, unchanged tab."""
    port = _port()
    match = next(
        (page for page in _pages(port) if page.get("url") in allowed_urls), None
    )
    if match is None:
        return {"state": "browser_tab_missing"}
    start = match["url"]
    with urlopen(
        f"http://127.0.0.1:{port}/json/activate/{quote(match['id'], safe='')}",
        timeout=5,
    ):
        pass
    press = (
        "(() => { if (location.href !== "
        + json.dumps(start)
        + ") return 'browser_tab_changed';"
        " const control = [...document.querySelectorAll('button, [role=button]')].find(e =>"
        " (e.getAttribute('aria-label') || e.innerText || '').trim() === "
        + json.dumps(label)
        + " && !e.disabled); if (!control) return 'approval_control_missing';"
        " control.click(); return 'pressed'; })()"
    )
    page = DevToolsPage(match["webSocketDebuggerUrl"])
    state = "approval_control_missing"
    for _ in range(CONTROL_ATTEMPTS):
        reply = page.call("Runtime.evaluate", expression=press, returnByValue=True)
        state = reply.get("result", {}).get("value") or "approval_control_missing"
        if state in ("pressed", "browser_tab_changed"):
            break
        time.sleep(POLL_SECONDS)
    if state != "pressed":
        return {"state": state}
    for _ in range(NAVIGATION_ATTEMPTS):
        time.sleep(POLL_SECONDS)
        url = next(
            (p.get("url") for p in _pages(port) if p.get("id") == match["id"]), None
        )
        if url is not None and url != start:
            return {"state": "approved", "starting_url": start, "result_url": url}
    return {"state": "approval_navigation_missing"}


def main():
    command, arguments = sys.argv[1], sys.argv[2:]
    try:
        if command == "prepare":
            result = prepare()
        elif command == "tabs":
            result = tabs(arguments[0])
        elif command == "approve":
            result = approve(json.loads(arguments[0]), arguments[1])
        elif command == "quit":
            result = {"quit": quit_chromium()}
        else:
            raise ChromiumRefusal(
                "linux_desktop_chromium_command_unknown", "Use a registered command."
            )
    except ChromiumRefusal as refusal:
        print(
            json.dumps(
                {"ok": False, "reason": refusal.reason, "recovery": refusal.recovery}
            )
        )
        raise SystemExit(69)
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "linux_desktop_chromium_devtools_failed",
                    "recovery": f"DevTools failed: {exc}. Confirm desktop Chromium is running and responsive, then rerun.",
                }
            )
        )
        raise SystemExit(69)
    print(json.dumps({"ok": True, **result}))
