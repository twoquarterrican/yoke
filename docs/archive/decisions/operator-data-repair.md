# Audited human row repair

The registered human operator repair command is a named exception to governed
bulk-data mutation. It repairs at most 1000 existing rows in one ordinary
control-plane table, with exact reviewed before/after images, authenticated
human organization-admin authority, a review digest and PostgreSQL statement
validation. It is available through normal transports and requires no source
lane. Raw query writes are retired.

The existing migration_audit owner carries the exact SQL hash, reviewer identity,
expected and observed row values, and outcome. No telemetry retention or delivery
establishes an operational fact. A planned audit commits before execution; the
successful outcome commits in the same transaction as the repair. Guard and
statement failures roll back data and record failure. Lost commit confirmation
reports uncertainty and requires reconciliation rather than guessing rollback.

A whole-database backup is unnecessary for this bounded contract: reviewed
before images retain the repaired values, the table lock prevents concurrent
predicate drift, and every mutation is transactional. The audit's
exception_reason states this justification. Tables with hidden trigger, rule,
inheritance, RLS or cascade effects refuse. Schema and broader transforms remain
governed migrations. The PostgreSQL parser dependency replaces a bespoke SQL
parser at this security boundary; the expression vocabulary is deliberately
closed against procedural or external effects.
