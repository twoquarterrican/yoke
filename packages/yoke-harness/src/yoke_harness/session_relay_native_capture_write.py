"""Replace a private capture atomically so readers see one complete envelope."""

import os
from pathlib import Path
import stat
import tempfile


def replace_private_capture(path: Path, payload: bytes) -> None:
    """Validate the target before writing, then publish one owner-only snapshot."""
    from yoke_harness.session_relay_native_diagnostics import NativeDiagnosticError

    temporary: Path | None = None
    descriptor = -1
    try:
        try:
            details = path.lstat()
        except FileNotFoundError:
            details = None
        if details is not None and (
            not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid()
        ):
            raise NativeDiagnosticError("diagnostic target is unsafe")
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(payload)
        os.replace(temporary, path)
    except OSError as exc:
        raise NativeDiagnosticError(
            "diagnostic could not be replaced; inspect capture directory permissions and retry"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
