"""Capture bounded, secret-free timings through the registered prod CLI."""

from __future__ import annotations

import argparse
import json
import subprocess
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--project", action="append", required=True)
    args = parser.parse_args()
    reads = [
        ("definitions", ["workflows", "definition", "get", "--full"]),
        ("mechanics", ["workflows", "mechanics", "get"]),
        ("instructions", ["workflow", "execution-instruction", "list"]),
        *[
            (
                f"plans:{project}",
                ["qa", "plan", "list", "--project", project, "--limit", "1"],
            )
            for project in args.project
        ],
    ]
    failed = False
    for name, command in reads:
        start = time.monotonic()
        result = subprocess.run(
            ["yoke", "--env", args.environment, *command, "--json"],
            capture_output=True,
            text=True,
            timeout=90,
        )
        elapsed = time.monotonic() - start
        try:
            envelope = json.loads(result.stdout)
        except (ValueError, TypeError):
            envelope = {}
        success = result.returncode == 0 and envelope.get("success") is True
        failed |= not success
        rows = (envelope.get("result") or {}).get("rows", [])
        print(
            json.dumps(
                {
                    "read": name,
                    "environment": args.environment,
                    "seconds": round(elapsed, 3),
                    "success": success,
                    "limit": 1 if name.startswith("plans:") else None,
                    "row_count": len(rows),
                    "response_bytes": len(result.stdout.encode()),
                    "error_code": (envelope.get("error") or {}).get("code"),
                }
            ),
            flush=True,
        )
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
