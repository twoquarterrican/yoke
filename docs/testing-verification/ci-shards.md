# CI interpreter coverage and shard timing

CI executes the full suite on the newest supported Python endpoint. The oldest
endpoint executes only in the merge queue, covering interpreter behavior while
repository checks, documentation, generated files, path snapshots, and installed
wheel scenarios stay on the newest leg. The existing required check contexts
remain present outside the queue; the oldest leg's steps perform no setup or
test execution there.

`runtime/ci_test_selection.py` owns the interpreter-independent selection. Its
collection hook runs before pytest-split, so every selected test belongs to
exactly one shard. Local and newest-interpreter runs retain all tests. Explicit
`ci_version_independent` markers can identify additional repository-only cases.

Every CI entry refreshes the timing weights from one successful retained run's
complete newest-interpreter report set. It shares that single profile artifact
with every shard, so matrix jobs cannot select against different profiles.
Missing report telemetry prints a named reason and recovery while CI retains
the committed profile; telemetry availability never decides whether tests run.
There is no scheduled refresh or automated source commit.

To refresh the committed baseline in a claimed source lane:

```text
yoke dev run -- python3 -m yoke_core.tools.ci_durations_refresh --target-root <checkout> --latest --repository owner/repo --python 3.14
```

Commit the resulting `.test_durations`; use `--reports <download-directory>` to
read a previously downloaded complete report set from one successful run.
`--help` owns the options. The tool refuses incomplete, failed, empty, or
duplicate report sets before replacing the existing profile.

JUnit testcase times include parallel contention. Each report's weights are
scaled to its actual suite wall time before pytest-split's greedy assignment.
Tests removed from the current checkout disappear from the refreshed profile.
CI aggregates those weights by file and assigns whole files through the same
least-duration algorithm. Xdist uses `loadfile` so a file also stays on one
worker. This stabilizes setup attribution and avoids repeating a file's
fixtures across shards or workers. Local partial splitting keeps pytest-split's
ordinary individual-test behavior.

Wheel smokes share one session virtual environment, synchronized across xdist
workers with a file lock. The fixture proves the core-only dependency closure
before installing the client, and creates its completion sentinel last.
Each scenario retains its own checkout, machine configuration, environment,
and subprocess substitutes; scenarios never modify shared site-packages.
The core-free scenario disables site loading and uses a filtered view of those
installed packages on the same interpreter, retaining its engine-absence proof.
The eight import-graph scenarios remain eight parametrized cases in
`tests/import_graph/test_yoke_cli_wheel_smoke.py`.

The merge queue cannot reuse a newest-only PR proof as both-interpreter proof.
Queue reuse requires an identical-tree successful merge-group run.
