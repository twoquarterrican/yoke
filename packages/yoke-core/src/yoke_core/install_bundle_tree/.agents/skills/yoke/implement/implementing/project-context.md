# Active — Project Context Preflight

Run after QA seeding and before implementation discovery.
Implement and Conduct use this same registered read and selection recipe.

## Read configured context

Resolve the item's project with its complete public ref. A genuinely
projectless item skips this phase. Read the registered context family through
`project_structure.get`:

```bash
yoke items get PREFIX-N project
yoke project-structure get --project P --family context_routing --json
yoke machine detail --json
```

Read each command's `--help` for its projection. The family's `entries` is
a list of records: each record's `entry_key` names its `payload.docs` list.
`always` is the reserved project-wide key; other keys are topic names.
Do not index `entries` as a map or treat an unfamiliar reply shape as empty.
The machine's project mapping supplies the
registered checkout; the project row does not store a path. Use the claimed
lane for this item's project rather than reading main then editing a lane.

No context entries is an advisory, not a failure. A failed read stops this
preflight: report its actual reason and recovery, and retry the registered
read after recovery. Never report a failed read as empty configuration.
If the registered checkout
is missing/unreadable, warn with the actual project/path and continue targeted
discovery without claiming docs were read. Missing configured files likewise
warn and continue. Name the project and exact path; repair the machine mapping
with `yoke project register <checkout> --project-id <id>`, or restore/update
the configured document path before retrying. Do not claim unread files arrived.

## Select and read topics

Read all always-included files. Match topic names case-insensitively against
the title, spec and AC text first. Then apply the standard fallback keywords:

| Topic | Keywords |
|---|---|
| frontend | frontend, dashboard, ui, page, component, css, theme, layout, login, form, button, modal, sidebar, header, footer, style, responsive, animation |
| backend | backend, api, server, endpoint, route, handler, middleware, database, query, migration |
| testing | test, testing, spec, e2e, assertion, fixture, mock |
| deployment | deploy, deployment, ci, cd, workflow, infra, server setup, vps, nginx, docker |

Include every matched configured topic and read its doc paths. No match is
an advisory naming available topics and the absence of matched keywords;
continue with always docs and targeted discovery. Do not silently treat a
failed context read as empty configuration.

## Project Context Summary

Surface only concrete paths and patterns from files actually read:

- Matched topics, or none/always-only.
- Likely implementation files relevant to this change.
- Likely test/doc surfaces: helpers, fixtures, directories and file patterns.
- Known implementation, route, structure or workflow patterns.

Implementation discovery starts with those files and patterns.
Broad exploration is a fallback for areas the docs did not cover.
