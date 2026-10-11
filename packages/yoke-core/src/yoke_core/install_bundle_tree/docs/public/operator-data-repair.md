# Reviewed operator row repair

Run `yoke operator data-repair --content-file repair.json --reviewed-sha256 SHA --dry-run`.
Review the durable simulation result, then omit `--dry-run` to apply the same
document. This registered `operator.data_repair.run` command works over HTTPS
and configured local PostgreSQL authority, without a project, item, claim,
worktree, or source execution. Use the released CLI, signed in as the universe's
human organization administrator, outside any harness session. Harness sessions
and service actors refuse even if they carry an administrator's identity.

Use an existing domain command first. This named exception repairs bounded
existing rows. Schema changes and broader transforms still use governed
migration authorship, rehearsal and boot convergence. The source-debug raw query
command now runs read-only transactions and refuses writes.

## Review document

All six fields below are required; additional fields refuse:

```json
{
  "sql": "UPDATE repair_documents SET document=(document::jsonb - 'diagnostic_expires_at')::text WHERE id=1",
  "table": "repair_documents",
  "key_columns": ["id"],
  "before": [{"id": 1, "document": "{\"diagnostic_expires_at\":47}"}],
  "after": [{"id": 1, "document": "{}"}],
  "reason": "Remove the reviewed malformed diagnostic expiry from this document"
}
```

The example illustrates a table with integer primary key id and TEXT document; use the live table's real primary key and
document columns, discovered with `yoke db read`, rather than assuming names.
Each snapshot contains the complete primary key in catalog order and every
assigned column. Include any other values the reviewer needs. The column set
must match in every row. JSON document columns that are TEXT remain strings;
native JSON/JSONB values are JSON objects. Native instants use the diagnostic
read's wire format. No snapshot may contain secret-bearing columns or JSON keys;
use the credential capability's own command for those values.

Review the complete SQL, intended rows, expected result and reason. Then run
`yoke operator data-repair --content-file repair.json --print-digest` to print
the document's SHA-256 for the human review. Computing a digest does not
approve the document. The digest is SHA-256 of its UTF-8 JSON with sorted keys,
compact separators, Unicode preserved and no nonfinite numbers. Pass the exact
reviewed digest to simulation and application. Editing SQL whitespace, values,
row images or reason changes that digest. The audit also stores SHA-256 of the
exact SQL string separately.

## Execution guards

The command accepts exactly one UPDATE or DELETE of an ordinary public table,
with a WHERE predicate and between 1 and 1000 reviewed existing rows. DELETE's
after snapshot is empty; UPDATE preserves all primary keys. The command owns
RETURNING and its transaction. It refuses transaction control, scripts, DDL,
INSERT, CTEs, joins, aliases, subqueries, procedural calls, key changes and
assignment indirection. PostgreSQL's parser validates structure; quoted SQL
text and comments cannot smuggle extra statements.

Expressions use built-in comparisons, arithmetic and JSON operators, scalar
casts, CASE/COALESCE and the pure functions `jsonb_set`, `jsonb_typeof`,
`jsonb_strip_nulls`, `jsonb_build_object`, `jsonb_build_array`, `to_jsonb`,
`replace`, `lower`, `upper`, `trim`, and `length`. Custom types/functions/operators
and external effects refuse. Search path is pg_catalog; the table is explicitly
public and ONLY. Tables with RLS, user triggers, rules, inheritance or cascading
foreign keys refuse. Audit and migration ledgers cannot repair themselves.

A table lock prevents changes, including predicate-matching inserts, during
guard evaluation and mutation. Statement and lock timeouts are five seconds.
The exact predicate-selected before rows must match the review before any
mutation. The affected key set and resulting values must match afterward.
Mismatch or execution failure rolls back row changes and persists the failed
attempt. Simulation executes the real statement and all guards, rolls back
row changes, and persists `test_verified` with observed before/after images.

## Durable outcome and recovery

`migration_audit` owns attempts independently of disposable events. The command
first commits a `planned` audit, then commits the repair and its `completed`
outcome together. `source_fingerprint` is the exact SQL hash;
`baseline_verify_result` contains the review digest and expected images;
`author_verify_result` contains observed images. The row records authenticated
actor, reason, timestamps and any named failure. Read the returned audit id:

```text
yoke db read "SELECT id, state, source_fingerprint, baseline_verify_result, author_verify_result, failure_reason FROM migration_audit WHERE id = AUDIT_ID"
```

Validation or authorization refusal occurs before an execution attempt.
Every execution attempt has durable evidence. Failure to start that audit
prevents SQL execution; failure to finish it prevents a successful repair.
A crash can leave `planned`; it never proves success. A lost commit acknowledgement
returns `repair_commit_outcome_unknown`: read the audit and current values before
retrying. An unavailable outcome returns `repair_outcome_unavailable` and names
the audit for operator reconciliation. Do not treat either as rollback proof.
Rejected guards teach a revised review; database failures report SQLSTATE without
echoing potentially sensitive SQL literals.

On a serving build below the registered function floor, the command refuses with
the required release. Use an existing domain mutation or ask the control-plane
operator to install a release carrying the command; obtaining a throwaway work
lane or invoking raw write SQL is not recovery.
