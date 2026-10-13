# Yoke teaching prototype

The maintained map of what Yoke teaches and where: the concept tree, the
surfaces that carry teaching, the scenarios that need it, FIRST-USER and
JOURNEYS plan coverage, evidence, locked boundaries and gaps. It is internal
contributor material: it lives only in the Yoke source repository and never
ships in the install bundle.

Build the local views with `yoke dev run -- python3 docs/teaching/tools/build.py`,
then open `docs/teaching/views/index.html` in a browser from that checkout.
This registered scanner works on the mapped main checkout without a work claim
and in a claimed lane. It writes only ignored views (and `live/` with `--live`);
it never rewrites the model.
Agents read the model JSON directly. If a review tool refuses `file:` URLs,
serve this directory locally (`python3 -m http.server` from `docs/teaching`).
The overview links to each record home; aggregate model counts stay out of
that shared page so independent model edits can land together.

## Canonical source and access

Ordinary repository access is the canonical route. Every machine and worker
reads this directory from a Yoke checkout, or from the public repository at an
exact commit: `https://github.com/upyoke/yoke/tree/<commit>/docs/teaching`.
No shared-drive copy is a source. Private research stays outside this public
repository: no private operator state, user or session ids, recordings or
machine paths. Public strategy text is allowed (operator decision,
2026-10-13); screen it for private material before committing. The check
refuses private paths and identifiers.

## Layout

| Path | Contents |
|---|---|
| `model/concepts/` | One concept per file; child concepts in matching directories |
| `model/surfaces/` | Surface record plus one teaching record per child file |
| `model/scenarios/` | Scenario record plus one lesson per child file |
| `model/plan/` | Collection metadata plus one plan row per child file |
| `model/evidence/` | Collection metadata plus one evidence record per child file |
| `model/boundaries/`, `model/gaps/` | One locked rule or open gap per file |
| `model/docs-graph.json` | Documentation areas for the live docs graph |
| `views/` | Untracked generated HTML and CSS; build locally to read |
| `tools/` | The builder and check |
| `live/` | Untracked live pages, written by `--live` |

Every record has a stable `id`; it is the HTML anchor of the record's view.
A concept's full id is its path (`context/hooks`), stored at
`model/concepts/context/hooks.json`. Teaching and lesson ids are prefixed by
their owner (`setup-agent/desired-01`), stored at
`model/surfaces/setup-agent/desired-01.json`. Each filename matches its
record's local `id`. Add a record by creating its file; claim that concrete
path without changing or claiming its parent record. Optional `position`
sets display order (then filename); concept `page` keeps large branches on
separate generated pages. Plan and evidence collection metadata lives at
`model/<kind>/<collection>.json`, with records in the matching directory.
`docs-graph.json` remains the documentation graph configuration.

To reapply the mechanical conversion after taking upstream array files:

```text
yoke dev run -- python3 docs/teaching/tools/convert_model.py
```

The converter removes consumed arrays, preserves ids and content, and can be
rerun safely. An upstream array is authoritative for its converted records;
existing record files without an array source stay untouched. Rebuild and
check afterwards.

Commands, functions and skills are never copied here. Concept records name
them, and the check resolves every name against the live registries. The
command crosswalk and documentation graph read live state, so they are written
only to the untracked `live/` directory; generated views depend on the model
alone and are also untracked. The stylesheet source lives in `tools/style.css`.

## Record status

| Status | Meaning |
|---|---|
| `observed` | Seen in source or a capture; scope stated, behavior unproven |
| `verified-live` | Proven against running Yoke with recorded evidence |
| `candidate` | Reviewed proposal, not approved scope |
| `approved` | Approved FIRST-USER scope or a locked boundary |
| `deferred` | Approved direction whose execution waits (JOURNEYS) |
| `draft-copy` | Research outline or draft wording; not a shipped recipe |
| `superseded` | Replaced proposal kept for provenance |

Coverage counts direct mappings only. A mapped parent never covers its
children, and a mapping never proves that the teaching works. Unmapped
concepts stay visible as gaps.

## Update the affected topics

Do this while planning and finishing any Yoke item that changes what Yoke
teaches. Review only the topics the work touches.

1. Find the concept, surface, scenario or plan row in the views.
2. Edit its record under `model/`. Keep its `id`.
3. Add missing topics or surfaces beside their peers and link them. Keep
   current state and desired state distinct through `status`. Record
   unfinished teaching as a `gaps/<id>.json` record with its evidence.
4. Rebuild and check:

   ```text
   yoke dev run -- python3 docs/teaching/tools/build.py
   yoke dev run -- python3 docs/teaching/tools/build.py --check
   ```

5. Commit the model in the item's own lane; build views locally to read them.
   Report the node links you changed in the item. Route gaps that need a
   decision to steering.

**Platform items never edit this directory.** When Platform work needs a
prototype change, file a linked Yoke item (`/yoke idea` in the yoke project)
that names the exact node ids, the requested change, the evidence and the
producer/consumer relationship.

## Reconcile with the strategy documents

FIRST-USER and JOURNEYS are authoritative in the strategy store. When either
changes, save both and check plan coverage against them:

```text
yoke strategy doc get FIRST-USER --project yoke --json > first-user.json
yoke strategy doc get JOURNEYS --project yoke --json > journeys.json
yoke dev run -- python3 docs/teaching/tools/build.py --check \
  --strategy first-user.json --strategy journeys.json
```

Review the changed entries, update their rows, set each plan file's
`reconciled_at` in the collection metadata to the document's `updated_at`,
and rebuild. Delete the saved
files afterwards when they are temporary reconciliation inputs. Public
strategy text may be committed after checking it for private material.

## Live pages

```text
yoke dev run -- python3 docs/teaching/tools/build.py --live
```

writes `live/commands.html` (live totals and every unmapped command, function
and skill) and `live/docs-graph.html` (every tracked document by area, with
inbound and outbound link counts).

## Check failures

`--check` exits 1 and prints one line per problem, naming the file and record:

| Code | Repair |
|---|---|
| `UNKNOWN_STATUS` | Use one of the seven statuses above |
| `DUPLICATE_ID`, `DANGLING_PARENT` | Make ids unique; add the missing parent record |
| `DANGLING_REFERENCE` | Fix the id, or remove a command that no longer exists |
| `DANGLING_SOURCE` | Cite a tracked repository-relative path |
| `PLAN_ROW_UNMAPPED` | Map the row, or name an explicit gap |
| `PLAN_ENTRY_MISSING`, `PLAN_RECONCILIATION_STALE` | Reconcile as above |
| `DANGLING_ANCHOR`, `DANGLING_LINK` | Fix the target id or path, then rebuild |
| `MODEL_NOT_CANONICAL` | Format the named JSON record to match its peers, then check again |
| `MODEL_RECORD_ID` | Store one record with an `id` matching its filename |
| `LINE_LIMIT` | Shorten the record or separate distinct topics, then rebuild |
| `PRIVATE_MATERIAL` | Remove the private path or id |

Every file here obeys the shared 350-line hard limit, counted at 80 columns;
300 is the design target. `--check` validates the model and builds views in
memory, checking links, privacy and limits without reading or writing local
views. CI runs this build validation through
`tests/teaching_prototype/test_teaching_prototype_check.py`.
