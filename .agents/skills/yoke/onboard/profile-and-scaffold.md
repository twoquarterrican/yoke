# Onboard Steps 2–3: Execution Profile And Scaffold

## Step 2: Derive The Execution Profile

Entry: accepted strategy and a chosen first work. Read the project-scoped
checklist first. Reuse `run.execution_profile` when `profile_changed=false`;
recheck local tools and each live skip predicate. When facts changed, show
and confirm only the changed proposal. Shared choices live in the existing
run metadata.

Scope every box to the first work: what its workflow, delivery and QA must
have before that item can reach done. Existing setup, checks, approvals and
rules are reused as they are. A box the first work does not need is recorded
`deferred` with that reason; it is not a question now.

Use all five docs, survey and installed .yoke/packs.json baseline.
Read hosting first; existing artifacts map to profile roles rather than reinstall.

```bash
yoke packs list --project {project} --json
yoke project-structure get --project {project} --family hosting_posture --json
yoke projects capability has --project {project} --cap-type aws-admin --json
yoke projects infrastructure list --project {project} --json
yoke project-structure deploy-defaults get --project {project}
```

No-yoke-managed-host excludes aws-admin and AWS infra/deploy Packs; name the
recorded provider. Empty posture is an unknown to resolve once, written in step 4.
Existing deployment configuration is only a hint, not an install contract.

### Propose the profile the first work needs

Packs: webapp-scaffold is provider-neutral; pulumi-foundation handles state/
stack setup, vps-hosting targets AWS EC2, webapp-environment-infrastructure
targets AWS environment resources, registry-oidc targets AWS CI federation,
production-deploy targets that pipeline; docs/context Packs are provider-neutral.
Drop unjustified Packs; map an existing app. No AWS apply path is promised for
Render/Fly/DigitalOcean/dokku/on-prem hosting.

Include all proposed/dependency Packs' declared local
  tool prerequisites from packs list: tool, minimum version, version probe, OS install
  recipe (or none). Resolve readiness before application, not as a surprise.

Name capabilities (hosting only when appropriate, GitHub binding mode and
product keys), one delivery choice, default-subdomain/BYO-later posture,
test setup, CI routing and governed database. The ci_workflow_file declaration is only the surveyed
Actions **test** workflow, never a deploy, release, or artifact-build workflow;
Jenkins/GitLab/Bitbucket/fastlane keep command. Queue only when GitHub is bound,
test workflow declared and merge_group present.

### The delivery box

Every profile names exactly one delivery outcome; a first work that ships
nowhere takes no default until later work needs one:

1. **Persistent environment** — registered environment plus pipeline, legal
   only with hosting verified/configured.
2. **Merge-only** — local merge with no environment and no deployment pipeline or run.
3. **No default** — new items omit --deployment-flow.

With deferred/not-needed hosting, offer only merge-only or no default.
Bind only dash/issue/epic/blitz defaults; Task exempt, never --apply-to-all.
Preview remains unassigned without ephemeral-env capability **and**
serving flow validation execution_supported=true.

### The test-setup box

Answer it when the first work's verification needs a registered command;
otherwise record it deferred: default-consuming workflows seed blocking review
until a command is bound, and item QA can use local tests or review.
The registered command owns the reviewing-implementation gate. A descriptive
`verification_profiles.test_command` is never a binding.

1. **A surveyed command** (surveyed-command): exact native argv, e.g.
   mvn -q -DskipITs test, vendor/bin/phpunit, xcodebuild or container tests.
   Reliable quick, genuinely broader full; every tree gets a separate `test_roots` entry.
2. **A scaffold suite** (scaffold-suite): use Pack test command.
   Webapp-scaffold supplies FastAPI/Vitest/Playwright examples and ci.yml.
3. **A review-only suite** (review-only-suite): known-red/flaky legacy roots,
   exact argv and condition retained. No quick/full/command-ci default;
   each item carries blocking implementation_review plus non-blocking command.
4. **No suite at all**: offer these three choices in order; no fabricated
   pytest/CI declaration/merge queue:
   **Scaffold a minimal suite** first (Pack for empty apps; project-native
   minimal test for content/pre-code); **Attest no-tests** with operator reason
   (attested-no-tests, durable step-5 row and structurally seeded blocking review);
   **Stop.** Undecided writes human-interview=blocked, cannot confirm.

### The governed-database box

Read live migration_model settings and survey migrations/tool/connection variable/
compose service. Read [governed-database.md](governed-database.md) before coordinates.

```bash
yoke projects capability-settings get --project {project} --cap-type migration_model --json
```

When the first work changes a database, propose exactly one; otherwise defer:
**A governed model, declarable now** (supported kind and existing coordinates,
name slug/history/ledger); **A governed model, attached later** (same known
facts, missing stack/coordinates); **No Yoke-governed database** (none, external
schema owner or unsupported kind; work-item DB claims none is expected);
**Undecided** (no write; human-interview=blocked). Never propose a validator-rejected pairing.

### Confirm (stop 1 of 2)

Present the profile for confirmation/edits, naming each deferred box and the
first work it was scoped to; no application/setup mutation before approval. Resolve all remaining unknowns or block human-interview and stop.
After confirmation, write the non-secret profile JSON to a local file, then
persist it through the existing checklist owner:

```bash
yoke onboard checklist --project {project} --run-id {run_id} --profile-file /tmp/confirmed-profile.json
```

The object records Packs, capabilities, hosting, delivery, tests and database
choices with source evidence; store credential references, never secret values.
The server captures current project-fact hashes. Resume reuses this confirmation
until a relevant setting changes, without copying machine verification.
Record evidence including the chosen delivery meaning, not assumed stage+prod:

```bash
yoke onboard checklist --run-id {run_id} --row-status human-interview=verified --evidence human-interview="confirmed Packs {packs}; capabilities {caps}; delivery {persistent-environment|merge-only|no-default}: {meaning}; domain {posture}; tests {surveyed-command|scaffold-suite|review-only-suite|attested-no-tests}; roots {test_roots}; quick {quick_argv|not-applicable}; full {full_argv|same-as-quick|not-applicable}; suite health {suite_health}; runner {command|command-ci|review-only|none} because {runner_rationale}; governed database {declare-now|attach-later|none}: {model/kind/history/ledger or no-model reason}"
```

The needed steps among 3–6 then run unattended, except credential
user-action/approval; each unneeded one records its rows deferred. The only
later stop is step-7 infrastructure approval, when the first work deploys.

## Step 3: Install The Scaffold Pack

Entry: confirmed Pack the first work needs; existing app maps instead,
scaffold-install=not-needed with exact mapped surfaces. No Pack needed yet:
scaffold-install=deferred naming the first work. Read installed .yoke/packs.json before touching
the Pack surface. Receipt already lists it: report version, mark verified,
skip. Version moves belong to yoke packs update, not onboarding.

Preview then apply the same command:

```bash
yoke packs get webapp-scaffold {checkout} --project {project}
yoke packs get webapp-scaffold {checkout} --project {project} --apply
```

Every selected/dependency prerequisite probe must be ready. Missing/unusable/
outdated tool blocks scaffold-install with named refusal and OS recovery;
stop. --allow-missing-tools only if explicitly requested in profile confirmation.
Never force a file conflict: map existing app instead.

Webapp-scaffold composes its marked AGENTS.md reference and .gitignore
contribution, preserving Yoke's managed block and other project bytes;
application collision protection remains. Installed README owns repeat/update/
conflict recipes. Never move scaffold guidance into project-install's block.
Applied files become ordinary project-owned source; receipt records the baseline.
Commit completed apply files in the project.

```bash
yoke onboard checklist --run-id {run_id} --row-status scaffold-install=configured --evidence scaffold-install="webapp-scaffold {version}; .yoke/packs.json baseline; applied files committed"
```

Docs/context Packs use the same receipt/preview/ready/apply mechanics individually;
documentation-context-setup=configured names installed Packs, or not-needed
names their exclusion. Any failed preview/apply blocks its row with recovery;
completed writes stay. Next: [hosting-and-environments.md](hosting-and-environments.md).
