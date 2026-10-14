"""Read the exact commit's UTC clock before wheel or native-image building."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from yoke_contracts.release_version import commit_version


def identity(checkout: Path, source_sha: str) -> dict[str, str]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("release_source_invalid: pass a full lowercase commit SHA")
    result = subprocess.run(
        ["git", "-C", str(checkout), "show", "-s", "--format=%H %ct", source_sha],
        check=True,
        text=True,
        capture_output=True,
        timeout=60,
    )
    resolved, clock = result.stdout.strip().split()
    if resolved != source_sha:
        raise ValueError("release_source_mismatch: fetch the exact source commit")
    tag = commit_version(datetime.fromtimestamp(int(clock), timezone.utc))
    return {"tag": tag, "release_version": tag, "source_sha": source_sha}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path.cwd())
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = identity(args.checkout, args.source_sha)
        if args.github_output:
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
                out.writelines(f"{key}={value}\n" for key, value in result.items())
        print(json.dumps(result, sort_keys=True))
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        print(
            f"release_identity_unavailable: {exc}; fetch the exact commit and retry",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
