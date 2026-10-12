# Model Level Proposals

`yoke models level-proposal` reads current catalog and universe levels.
Superseded model rows move to their successors in place; unpublished minimum
effort moves to the nearest published effort. Rows contain only model and
min_effort, without native surfaces, context or exhausted-pool fallbacks.

The proposal names unverified model/effort facts and unplaced current models.
Use researched facts to author adds, moves, retirements and threshold changes:

```json
{"kind":"add","level":"SENIOR","option":{"model":"...","min_effort":"medium"},"position":0,"reason":"..."}
{"kind":"move","option":{"model":"...","min_effort":"medium"},"to_level":"JUNIOR","reason":"..."}
{"kind":"retire","option":{"model":"...","min_effort":"medium"},"reason":"..."}
{"kind":"change","option":{"model":"...","min_effort":"medium"},"min_effort":"high","reason":"..."}
```

Thresholds must strictly increase within each model as levels rise. Proposal
and Levels set refuse published-effort contradictions as
`level_min_effort_unpublished`. Present the complete proposal and obtain
operator approval before replacing stored Levels.

```sh
yoke models level-proposal --levels-only --stdin < changes.json > /tmp/levels.json
yoke universe levels set --stdin < /tmp/levels.json
```
