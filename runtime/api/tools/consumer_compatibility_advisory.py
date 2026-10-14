"""Check every upstream PR, main push and manual candidate against Platform.

This independent advisory never decides required CI or release publication.
Identical product trees at the same observed consumer commit join one durable
Platform run. Release publication still requires its exact commit pair.
Forks without the scoped credential report NOT CHECKED explicitly.

Usage::

    python3 -m runtime.api.tools.consumer_compatibility_advisory \
        --candidate-sha <40-hex>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Optional, Sequence

from runtime.api.tools import require_platform_consumer_compatibility as gate

_ANNOTATION_TITLE = "consumer-compatibility"


def _report(message: str, *, warn: bool = False) -> None:
    print(f"consumer-compatibility: {message}", flush=True)
    if warn:
        print(f"::warning title={_ANNOTATION_TITLE}::{message}", flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"- **{_ANNOTATION_TITLE}**: {message}\n")


def _read(argv: Sequence[str]) -> dict:
    code, stdout, stderr = gate._yoke(argv, timeout=gate._COMMAND_TIMEOUT_SECONDS)
    try:
        payload = json.loads(stdout)
    except ValueError:
        payload = None
    if code or not isinstance(payload, dict) or not payload.get("success"):
        raise RuntimeError(gate._detail(stdout, stderr))
    result = payload.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("the control plane returned no readable result")
    return result


def candidate_tree(candidate: str) -> str:
    """Read the exact candidate's tree, including a recovered earlier PR commit."""

    def read() -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "rev-parse", "--verify", f"{candidate}^{{tree}}"],
            capture_output=True,
            text=True,
            timeout=60,
        )

    result = read()
    if result.returncode:
        # A force-pushed PR can leave its original proof's commit outside the
        # fresh checkout. Fetch only that immutable object, never a moving ref.
        fetched = subprocess.run(
            ["git", "fetch", "--no-tags", "origin", candidate],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if fetched.returncode:
            raise RuntimeError(f"candidate_tree_unreadable: {fetched.stderr.strip()}")
        result = read()
    tree = result.stdout.strip().lower()
    if result.returncode or not gate.is_full_commit_sha(tree):
        raise RuntimeError(f"candidate_tree_unreadable: {result.stderr.strip()}")
    return tree


def _receipt(request_id: str) -> dict:
    receipt = _read(
        [
            "github-actions",
            "dispatch-receipt",
            "get",
            request_id,
            "--project",
            gate.CONSUMER_PROJECT,
            "--json",
        ]
    )
    if not isinstance(receipt.get("found"), bool) or (
        receipt["found"]
        and (
            not isinstance(receipt.get("inputs"), dict)
            or not isinstance(receipt.get("run_id"), str)
        )
    ):
        raise RuntimeError(
            "dispatch_receipt_unreadable: restore the receipt read's serving floor"
        )
    return receipt


def _original_candidate(receipt: dict, candidate: str, tree: str) -> str:
    if not receipt.get("found"):
        return candidate
    original = str((receipt.get("inputs") or {}).get(gate.CANDIDATE_INPUT) or "")
    if not gate.is_full_commit_sha(original) or candidate_tree(original) != tree:
        raise RuntimeError(
            "advisory_proof_identity_mismatch: the recorded candidate does not "
            "name this product tree; inspect the dispatch receipt before retrying"
        )
    return original


def check(candidate: str, *, timeout_sec: int) -> tuple[int, str]:
    unavailable = gate.bind_consumer_authority()
    if unavailable:
        raise RuntimeError(unavailable)
    tree = candidate_tree(candidate)
    trunk = _read(
        [
            "github",
            "branch",
            "head",
            gate.CONSUMER_TRUNK_REF,
            "--project",
            gate.CONSUMER_PROJECT,
            "--json",
        ]
    )
    consumer = str(trunk.get("head_sha") or "").lower()
    if not gate.is_full_commit_sha(consumer):
        raise RuntimeError("consumer_head_unreadable: trunk read named no full commit")
    request_id = f"consumer-advisory:{tree}:{consumer}:{gate.CONSUMER_CHECK_WORKFLOW}"
    receipt = _receipt(request_id)
    original = _original_candidate(receipt, candidate, tree)
    run_id = str(receipt.get("run_id") or "")
    if not run_id:
        run_id, error = gate.dispatch(
            original,
            consumer,
            exact_pair=False,
            request_id=request_id,
        )
        if error:
            # Another identical-tree caller can win between the read and POST.
            # Recover its original input; never mutate a colliding payload.
            receipt = _receipt(request_id)
            winner = _original_candidate(receipt, candidate, tree)
            run_id = str(receipt.get("run_id") or "")
            if not run_id and winner != original:
                run_id, error = gate.dispatch(
                    winner,
                    consumer,
                    exact_pair=False,
                    request_id=request_id,
                )
            if not run_id:
                raise RuntimeError(error)
            original = winner
    result, error = gate.await_verdict(run_id, timeout_sec=timeout_sec)
    if error:
        raise RuntimeError(error)
    code, narrative, _ = gate.classify(
        result,
        candidate_sha=candidate,
        consumer_sha=consumer,
        run_id=run_id,
    )
    if code:
        proven = str(result.get("head_sha") or "")
        reason = "consumer_check_failed"
        recovery = (
            "Repair the product or consumer so the next check names a new content pair."
        )
        if result.get("state") == "timeout":
            reason = "consumer_check_timeout"
            recovery = "Re-run the advisory to rejoin the same run after it concludes."
        elif not gate.is_full_commit_sha(proven):
            reason = "consumer_evidence_missing"
            recovery = "Restore the run's head-commit evidence and re-run the advisory."
        elif proven.lower() != consumer:
            reason = "stale pair: consumer_commit_mismatch"
            recovery = "Re-run the advisory to read the current consumer commit."
        narrative = (
            f"{reason}: product tree {tree} at {candidate} (checked commit {original}), "
            f"consumer bound {consumer}, actual {proven or 'unnamed'}, run {run_id} "
            f"({result.get('html_url') or 'no run URL'}) concluded "
            f"{result.get('conclusion') or result.get('state') or 'unknown'}. "
            f"{recovery} Required CI stays independent; publication still requires exact-pair proof."
        )
    else:
        narrative = f"product tree {tree} at {candidate}, checked commit {original}: {narrative}"
    return code, narrative


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="consumer_compatibility_advisory",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--candidate-sha", default="")
    parser.add_argument("--timeout", type=int, default=1800, dest="timeout_sec")
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    candidate = args.candidate_sha.strip().lower()
    if not gate.is_full_commit_sha(candidate):
        _report(
            "NOT CHECKED — candidate_commit_required: supply a full 40-hex "
            "--candidate-sha and re-run the advisory",
            warn=True,
        )
        return 0
    if not os.environ.get(gate.CONSUMER_TOKEN_ENV, "").strip():
        _report(
            "NOT CHECKED — consumer_credential_missing: no scoped consumer "
            "credential reached this run. Fork PRs never receive it; a "
            "maintainer can run the advisory from an upstream branch. "
            "Publication still requires exact-pair proof.",
            warn=True,
        )
        return 0
    try:
        code, narrative = check(candidate, timeout_sec=args.timeout_sec)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        _report(
            f"NOT CHECKED — advisory_evidence_unavailable: {exc}. Restore the "
            "named read or credential and re-run the advisory; if a function "
            "floor is named, ask the control-plane operator to serve it. "
            "Publication still requires exact-pair proof.",
            warn=True,
        )
        return gate.UNAVAILABLE
    _report(narrative, warn=bool(code))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
