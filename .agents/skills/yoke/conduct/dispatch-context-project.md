# Conduct — project context

Run for every project-owned item, including Yoke. Projectless skips only this
block; development still requires verified project attribution before lanes.

```text
yoke items get PREFIX-N project
yoke machine detail --json
yoke project-structure get --project {PROJECT} --family context_routing --json
```

Read and follow [the shared project-context recipe](../implement/implementing/project-context.md).
Its `entries` map `entry_key` to `payload.docs`: read always plus every
configured topic matched to title/spec/ACs using that recipe's keywords.
Read this project's documents from its selected claimed lane and registered
machine checkout. Empty configuration is an advisory; failed reads stop with
their actual cause/recovery. Missing mappings/documents warn with the exact
project/path and repair, and never count as read. Carry successfully read
filename/content once into the relevant Engineer/Tester dispatch context.

```text
yoke qa plan list --project {PROJECT} --full --json
yoke qa requirement list --item PREFIX-N --json
yoke ephemeral-env get {PROJECT} {BRANCH} --json
```

Carry plan names/transition attachments and materialized requirement id,
case_key, method, instructions and expected outcome. Read exact snapshots;
never reparse embedded commands or invent test invocations. Runnable rows use:

```text
yoke qa case run --requirement-id {requirement_id}
```

Read the actual registered worktree branch's environment. Missing/unhealthy
sets URL=none; no inferred PREFIX-N branch/table query. Context contains project,
checkout, exact lane, selected control-plane authority, QA roster and preview
URL. Work stays inside this project's selected lane. Then independently run
[dispatch-context-ephemeral.md](dispatch-context-ephemeral.md) when capability
exists; refresh URL/candidate identity after it completes. The shared Tester
template owns prompt variants and consumes these facts.
