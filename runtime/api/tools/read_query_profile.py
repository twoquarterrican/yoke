"""Source-maintainer read profiling; prints timings and counts, never row data."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
from statistics import median
from time import perf_counter
from typing import Any


class CountedConnection:
    def __init__(self, conn: Any):
        self._inner = conn
        self.counts: Counter[str] = Counter()
        self.seconds: Counter[str] = Counter()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def execute(self, sql: str, params: tuple = ()) -> Any:
        frame = inspect.currentframe().f_back
        while frame and frame.f_globals.get("__name__", "").endswith(
            ("db_helpers", "db_backend")
        ):
            frame = frame.f_back
        reader = (
            f"{frame.f_globals.get('__name__')}.{frame.f_code.co_name}"
            if frame
            else "unknown"
        )
        started = perf_counter()
        try:
            return self._inner.execute(sql, params)
        finally:
            self.counts[reader] += 1
            self.seconds[reader] += perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read", choices=("qa", "steering"), required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--session-id")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--full", action="store_true")
    parser.add_argument(
        "--baseline-ref",
        help="Compare this exact commit on the same exported read-only snapshot.",
    )
    parser.add_argument("--snapshot-id", help=argparse.SUPPRESS)
    parser.add_argument("--now", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.samples < 1 or (args.read == "steering" and not args.session_id):
        parser.error(
            "samples must be positive; steering requires a held-seat --session-id"
        )
    from yoke_core.domain.db_helpers import connect
    from yoke_core.domain.project_identity import resolve_project_id

    with connect() as conn:
        conn.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        conn.execute("SET LOCAL idle_in_transaction_session_timeout = 0")
        if args.snapshot_id:
            if not re.fullmatch(r"[0-9A-Fa-f-]+", args.snapshot_id):
                parser.error("invalid exported snapshot identity")
            conn.execute(f"SET TRANSACTION SNAPSHOT '{args.snapshot_id}'")
        project_id = resolve_project_id(conn, args.project)
        snapshot = dict(
            conn.execute(
                "SELECT (SELECT COUNT(*) FROM qa_plans WHERE project_id=%s) AS plans, "
                "(SELECT COUNT(*) FROM qa_requirements q JOIN qa_plans p ON p.id=q.plan_id WHERE p.project_id=%s) AS requirements, "
                "(SELECT COUNT(*) FROM items WHERE project_id=%s) AS items",
                (project_id, project_id, project_id),
            ).fetchone()
        )
        now = (
            datetime.fromisoformat(args.now) if args.now else datetime.now(timezone.utc)
        )
        if args.baseline_ref:
            snapshot_id = conn.execute("SELECT pg_export_snapshot()").fetchone()[0]
            root = Path(__file__).resolve().parents[3]
            commit = subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(root),
                    "rev-parse",
                    f"{args.baseline_ref}^{{commit}}",
                ],
                text=True,
            ).strip()
            with tempfile.TemporaryDirectory(prefix="yoke-read-baseline-") as directory:
                archive = Path(directory) / "source.tar"
                with archive.open("wb") as stream:
                    subprocess.run(
                        [
                            "git",
                            "-C",
                            str(root),
                            "archive",
                            commit,
                            "packages",
                            "runtime",
                        ],
                        stdout=stream,
                        check=True,
                    )
                with tarfile.open(archive) as bundle:
                    bundle.extractall(directory, filter="data")
                env = dict(os.environ)
                env["PYTHONPATH"] = os.pathsep.join(
                    [
                        str(Path(directory) / "packages" / name / "src")
                        for name in (
                            "yoke-cli",
                            "yoke-contracts",
                            "yoke-core",
                            "yoke-harness",
                        )
                    ]
                    + [directory]
                )
                command = [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--read",
                    args.read,
                    "--project",
                    args.project,
                    "--samples",
                    str(args.samples),
                    "--snapshot-id",
                    snapshot_id,
                    "--now",
                    now.isoformat(),
                ]
                if args.full:
                    command.append("--full")
                if args.session_id:
                    command.extend(("--session-id", args.session_id))
                print(
                    json.dumps({"comparison": "baseline", "commit": commit}), flush=True
                )
                subprocess.run(command, env=env, cwd=directory, check=True)
                print(
                    json.dumps(
                        {
                            "comparison": "candidate",
                            "commit": subprocess.check_output(
                                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
                            ).strip(),
                        }
                    ),
                    flush=True,
                )
        timings = []
        samples = []
        for index in range(args.samples):
            counted = CountedConnection(conn)
            started = perf_counter()
            if args.read == "qa":
                from yoke_core.domain.qa_catalog_reads import list_plans

                options = (
                    {"full": args.full}
                    if "full" in inspect.signature(list_plans).parameters
                    else {}
                )
                result = list_plans(counted, project=args.project, **options)
            else:
                from yoke_core.domain.steering_fleet_report_compose import (
                    compose_held_reports,
                )

                result = compose_held_reports(
                    counted, session_id=args.session_id, now=now, project_id=project_id
                )
            elapsed = perf_counter() - started
            timings.append(elapsed)
            samples.append(dict(counted.counts))
            print(
                json.dumps(
                    {
                        "sample": index + 1,
                        "seconds": elapsed,
                        "queries": sum(counted.counts.values()),
                        "readers": dict(counted.counts),
                        "reader_seconds": dict(counted.seconds),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            del result
        print(
            json.dumps(
                {
                    "read": args.read,
                    "snapshot": snapshot,
                    "p50_seconds": median(timings),
                    "query_counts": [sum(sample.values()) for sample in samples],
                },
                sort_keys=True,
            )
        )
        conn.rollback()


if __name__ == "__main__":
    main()
