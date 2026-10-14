"""Linux harness sign-ins a reset carries forward instead of rolling back.

A golden holds the sign-in that was live when it was sealed. Harnesses rotate
their tokens as they are used, so by the next request the golden's copy is
older than the live one, and restoring it signs the machine out. Before the
home is cleared, each store is verified by its sealed real-request probe:

* verified live store: carried forward over the restore;
* live store changed after the baseline was sealed but not verified: the reset
  refuses before clearing, because restoring would replace a newer sign-in
  with an older one;
* otherwise (absent, or unchanged since the seal): the golden's copy restores.
"""

from __future__ import annotations

from typing import Any, Sequence

from yoke_harness.ssh_mac_baseline_probes import BaselineProbe, run_baseline_probes
from yoke_harness.standard_baseline_probes import SAVE_BASELINE_COMMAND

#: Sealed standard probe name -> the home-relative file holding that sign-in.
SIGN_IN_STORES = {
    "Claude real request": ".claude/.credentials.json",
    "Codex real request": ".codex/auth.json",
    "Cursor real request": ".config/cursor/auth.json",
}
SIGN_IN_NEWER_THAN_BASELINE = "test_machine_sign_in_newer_than_baseline"


def verify_sign_in_stores(control: Any, probes: Sequence[BaselineProbe]) -> dict:
    """Run each sealed sign-in probe against the live home, before any clear."""
    plan: dict[str, Any] = {"carry": [], "unverified": {}}
    for probe in probes:
        relative = SIGN_IN_STORES.get(probe.name)
        if relative is None:
            continue
        proven = run_baseline_probes(
            [probe], run_gui_command=control.run_command, classify_gui_failures=False
        )
        if proven.ok:
            plan["carry"].append(relative)
        else:
            plan["unverified"][relative] = {
                "probe": probe.name,
                "probe_reason": proven.evidence.get("reason"),
            }
    return plan


# Runs inside the archive program, which defines home, refuse(), members and
# the imported stdlib modules it uses.
SIGN_IN_PROGRAM = r"""
def sign_in_path(relative):
    path = home
    for part in pathlib.PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink() or path.exists() and path.stat().st_uid != os.getuid():
            refuse("linux_sign_in_store_unsafe", relative, recovery="Make ~/" + relative + " and its parents regular paths owned by this user, then retry; the home was not cleared.")
    return path
def refuse_newer_unverified(plan):
    sealed_at = (baseline / "manifest.json").stat().st_mtime
    for relative, failure in plan["unverified"].items():
        path = sign_in_path(relative)
        if path.exists() and path.stat().st_mtime > sealed_at:
            refuse(__NEWER__, relative, recovery="The live " + failure["probe"] + " sign-in at ~/" + relative + " changed after this baseline was sealed and failed its real request: " + str(failure["probe_reason"]) + " Restoring would replace it with the older sealed sign-in, so the home was not cleared. Sign in again on the machine, then save the sign-in with `" + __SAVE__ + "`, which proves the request and recaptures the baseline.", **failure)
def stash_sign_ins(plan):
    stashes = []
    sealed = {member.name: member for member in members}
    for relative in plan["carry"]:
        parts = pathlib.PurePosixPath(relative).parts
        for depth in range(1, len(parts) + 1):
            member = sealed.get("/".join(parts[:depth]))
            if member is not None and not (member.isdir() if depth < len(parts) else member.isfile()):
                refuse("linux_sign_in_store_unsafe", relative, recovery="The golden stores ~/" + relative + " in an unexpected shape; capture a new golden before resetting.")
        source = sign_in_path(relative)
        if not source.exists(): continue
        try:
            with open(source, "rb", opener=lambda path, flags: os.open(path, flags | os.O_NOFOLLOW)) as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode):
                    refuse("linux_sign_in_store_unsafe", relative, recovery="Make ~/" + relative + " a regular file, then retry; the home was not cleared.")
                directory = pathlib.Path(tempfile.mkdtemp(prefix="yoke-live-sign-in-", dir="/tmp"))
                stashes.append((relative, directory, info.st_mode & 0o777))
                with os.fdopen(os.open(directory / "store", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
                    shutil.copyfileobj(stream, output)
        except OSError:
            refuse("linux_sign_in_store_unreadable", relative, recovery="Repair read access to ~/" + relative + ", then retry; the home was not cleared.")
    return stashes
def restore_sign_ins(stashes):
    for relative, directory, mode in stashes:
        try:
            destination = sign_in_path(relative)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            temporary = destination.parent / (".yoke-sign-in-" + directory.name)
            with (directory / "store").open("rb") as source, os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as output:
                shutil.copyfileobj(source, output)
                os.fchmod(output.fileno(), mode)
            temporary.replace(destination)
            shutil.rmtree(directory)
        except OSError:
            refuse("linux_sign_in_store_restore_failed", relative, recovery="Copy the private stash at " + str(directory) + "/store to ~/" + relative + " with mode " + oct(mode) + ", remove the stash, then retry.")
""".replace("__NEWER__", repr(SIGN_IN_NEWER_THAN_BASELINE)).replace(
    "__SAVE__", repr(SAVE_BASELINE_COMMAND)
)


__all__ = [
    "SIGN_IN_NEWER_THAN_BASELINE",
    "SIGN_IN_PROGRAM",
    "SIGN_IN_STORES",
    "verify_sign_in_stores",
]
