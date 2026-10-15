# Machine authorization

Cloud and self-hosted servers share the device-code wire contract in
`yoke_contracts.machine_authorization`. Cloud retains its org selection. Self-host binds a code to its sole organization at start.

## Connect

Run `yoke connect https://<server>` and approve your own machine in the signed-in
workbench. The setup wizard's **A team server** option discovers the server's
sign-in method before showing browser approval or API-token entry. Without
company sign-in, a first machine uses `yoke connect https://<server> --token-stdin`
or `--token-file PATH`; the first-boot admin token remains the bootstrap. Your
own next machine runs `yoke connect https://<server>` and you approve its code
from a machine you already connected with
`yoke machine-authorization resolve CODE --action approve`. The approved
machine receives the approver's identity, so approve only your own codes; the
wizard therefore keeps a teammate without company sign-in on API-token entry.

## Wire

- `POST /api/machine/authorizations` returns `device_code`, `user_code`,
  `verification_uri`, `verification_uri_complete`, `expires_in`, and `interval`.
  Every mode sends `machine_id` (the configured UUID), `machine_name` (the
  operating system display hostname, at most 150 characters), and `platform`
  (for example `macOS`, `Linux` or `Windows`, at most 80 characters). All three
  are required by `MachineAuthorizationStart`; the browser reads these facts
  before the first poll. Start with the current installer against a server
  serving this request contract; a mismatched contract refuses by name.
- `POST /api/machine/authorizations/token` sends `device_code`, `machine_id`, and
  `machine_name`. Success returns `token`, `org`, and `api_url`.
- Retry HTTP 202 `authorization_pending`, HTTP 503
  `machine_credential_unavailable`, and HTTP 429
  `authorization_poll_rate_limited` (honoring `Retry-After`). HTTP 410
  `authorization_denied`, `authorization_expired`, or `authorization_consumed`
  requires a new connection. Other statuses are diagnosed refusals.
- Cloud's API authority is `/api/orgs/<slug>` on the selected origin. Self-host's
  authority is the server origin. Clients reject foreign origins or mismatched
  authorities before persisting a credential.
- Self-host discovery is `GET /api/machine/authorizations`: `device_code` is
  true on every current server, and `company_sign_in` is true exactly when
  company sign-in is configured. Without company sign-in, codes and delivered
  credentials name the request's own origin. A server that omits
  `company_sign_in` predates it and offered device codes only with company
  sign-in. Partial configuration refuses as `oidc_misconfigured`; an older
  server without discovery requires an explicit API token until its operator
  upgrades it. The wizard retains the discovery
  refusal and offers **Use API token**, **Edit connection**, and **Choose another
  home**, including when company sign-in is misconfigured.

## Approval and delivery

The shared `/machine-approval[/CODE]` workbench page calls
`machine_authorization.get` and `machine_authorization.resolve` through its
normal function client. The read returns `authorization` with code, machine
name/ID, platform, expiry, and decision; resolve takes `{code, action: approve|deny}`
and returns that decision. A host consuming the core wheel supplies its normal
client and owns its pending-code store; Cloud's companion integration maps
these calls to its store, where organization selection occurs at approval.

Self-host accepts decisions only from active org members. The signed-in person
claims the code and approves their own machine through a named-actor decision
request; other actors cannot take it over. Cloud's existing org-admin requests
retain their role authority. Credential issuance remains engine-owned atomic
machine registration/rotation. Consumption and issuance commit together; one
poll receives the raw credential and no raw credential is stored in the code
record. Network loss after delivery requires starting a new code.

The self-host store keeps hashed device secrets and expires codes after ten
minutes, deleting expired records on the next start. Pending admission is bounded
by trusted transport client identity: eight unconsumed codes per client and
128 across the server. Changing the machine UUID or forwarding headers does
not create a new client budget. `authorization_client_capacity` and
`authorization_capacity` refuse further starts; finish an approval or retry
after expiry. Consumed codes free pending capacity.

Persistent atomic counters are shared across processes and restarts, separately
from telemetry: six start requests and 120 poll requests per client per minute.
HTTP 429 `authorization_start_rate_limited` or `authorization_poll_rate_limited`
includes `Retry-After`. Start refusals require retrying after that delay. The CLI
waits through poll throttling and polls the same code after `Retry-After`, bounded
by its expiry and cancellation. Missing or invalid delays retain the normal poll
interval; capacity refusals remain fatal. Failed and malformed
requests also consume the budget. For self-host, set `YOKE_API_TRUSTED_PROXIES`
in the bundle's `.env` to the TLS proxy IPs/CIDRs, then restart with
`yoke self-host init --dir PATH --protect-existing --start` so the server sees
each forwarded client. Headers from undeclared peers are ignored; clients
sharing an address share these budgets. A denied, consumed,
or expired code requires a new connection. Wrong machine identity, missing
org membership, or disabled actor refuses with its recovery step. A database
failure before issuance leaves delivery retryable. Cookies authorize browser
functions only with the workbench's existing same-origin CSRF protection.

## Approval page

The page shows a single card headed **Approve this machine**, with the real
machine name (omitted when absent), platform and full machine ID, one-time code,
organization name, and the viewer's local expiry time and zone. The UTC instant
stays in the time element. Approve only if the code matches your terminal.
**Approve machine** is the primary action; **Deny** authorizes nothing.

A first organization connection shows four setup steps, with Connect machine
active and the preceding steps complete. The same visit shows every step
complete after approval. Later connections omit the bar. This follows the
organization's machine registry, without a caller-supplied first-run marker.

Approval shows **Machine connected**, a green success line, and a separate
orange **Return to your terminal** callout. The approved facts omit expiry
and the code-matching hint. A denied request says **Nothing was authorized**.
Expired requests show their local expiry when their stored facts remain
available; no client promises a replacement code automatically. Start a new
connection from the terminal. An unavailable code offers code entry again.
The installer and connect wait stop on expiry; neither rotates codes silently.

Inspection may read an expired or consumed record to display its outcome,
but resolve and poll still refuse expired or consumed codes. A record removed
by pending-store expiry cleanup is unavailable; membership and ownership still
protect reads. Light and dark themes share the same card and narrow layouts.

## Inspect as the signed-in actor

Run `yoke machine-authorization get CODE` to read a code, then
`yoke machine-authorization resolve CODE --action approve` (or `deny`) to
record your personal decision. Read the returned decision and finish polling
from the original machine. These operations never accept a caller-supplied
owner, org, or credential.

On a hosted connection (`https://app.upyoke.com/api/orgs/<slug>`) Platform answers
both calls from its own code store, and an org admin decides any code waiting
for that org. See [Hosted org administration](hosted-org-admin.md).

## Shared schema

The `yoke-contracts` wheel ships `yoke_contracts/machine_authorization.schema.v2.json`,
generated from the request and response Pydantic models. Load it with Python's
`importlib.resources.files("yoke_contracts").joinpath("machine_authorization.schema.v2.json")`,
or read that path from the pinned wheel in another language. Validate a body
against its named `$defs` entry while retaining the document's other `$defs`
for references. The `x-http` section names the endpoint, request model, success
model, error outcome's HTTP status and body model, and retry policy. Start and poll requests are shared across hosting modes.

`MachineAuthorizationStarted` and `MachineAuthorizationApproved` define success.
`MachineAuthorizationPending`, `MachineAuthorizationDenied`,
`MachineAuthorizationExpired` (including consumed), `MachineAuthorizationSlowDown`,
and `MachineAuthorizationUnavailable` define poll outcomes. Other diagnosed
refusals use `MachineAuthorizationRefused`. Recovery text is optional on the wire: self-host supplies `message`, and Cloud
supplies `detail`. Both are explicit fields in the shared refusal model; the CLI
retains supplied recovery text in fatal diagnostics. Cloud credential refusals
use HTTP 409; missing machine identity uses 400, malformed requests use 400 or
413, and retryable credential unavailability uses 503. The strict schema rejects
unrecognized response fields. Secrets are excluded from model repr and
client validation errors. The CLI and self-host route use these models;
`parse_authorization_response` also checks known poll statuses. Origin and API
authority checks remain required after body validation.

Regenerate after changing models with
`yoke dev run -- python3 -m yoke_contracts.machine_authorization_schema`.
Check drift with the same command plus `--check`; the contract test also fails
on byte drift. A breaking wire change requires a new schema version and the
linked consumer's tests against the exact candidate wheel. The schema's v2
identifies its contract independently of the wheel's release version.

Shared client helpers are `authorization_origin`, `same_origin_url`,
`credential_api_url`, and `parse_authorization_response`, with
`BROWSER_VERIFICATION_PATHS`, `POLL_OUTCOMES`, and `RETRYABLE_POLL_ERRORS`.

Hosted lifecycle delivery accepts qualified instants or aware Python datetimes
for occurrence and expiry. Numeric epochs, naive dates and empty supplied clocks
refuse. Stored decision clocks are native; owned occurrence, expiry and end
context fields and audit receipts use fixed-six UTC RFC3339Z or null. Expiry is
an inclusive comparison of instants, independent of database session timezone.


## Hosted code handoff

After sign-in and organization selection, the hosted service calls registered
`machine_authorization.handoff` in that organization's engine. This function
requires the `hosted_service` system identity with `hosted_service.deliver` on
the exact target organization; human members and admins cannot call it.
Its registry serving floor is `next-release` until a release carries it. An older
engine must be upgraded before Platform enables handoff; the service operator
owns that rollout. Existing hosted routing remains until the consumer adopts
this contract.

The payload is `{device_hash, user_code, machine_id, machine_name, platform,
expires_at, org_id}`. `device_hash` is the lowercase hex SHA-256 of the original
secret device code; never send the raw secret. `user_code` is exactly four
uppercase ASCII letters or digits, such as `K7F2`. `machine_id` is a UUID;
name and platform are nonempty (at most 150 and 80 characters). `expires_at`
is a qualified RFC3339 instant and `org_id` is the positive engine organization
ID. The response is `{authorization: {code, org_id, expires_at}}`; expiry is
canonical UTC. The engine stores the code in `machine_authorization_codes`,
without issuing credentials or deciding approval.

The existing inspect, resolve and poll operations consume that same record.
The signed-in member still approves personally; the original device secret
polls for one credential bound to that member and the selected organization.
The hosted consumer must route those operations to this engine after handoff;
its own route adoption requires integration proof against the exact candidate.

`authorization_device_code_collision` and `authorization_match_code_collision`
refuse with no replacement, including an identical replay. Issue a new secret
and match code, then retry handoff. `authorization_expired` requires a new code;
`authorization_org_unknown` requires selecting an existing engine organization.
`permission_denied` requires that organization's hosted service identity.
`authorization_handoff_invalid` or `authorization_refused` requires correcting
the payload and retrying. `authorization_capacity` requires finishing an approval
or waiting for expiry; handoff shares the server's 128 pending-code limit.
`authorization_store_unavailable` requires the operator to restore database
health before retrying. No parallel pending or credential store is created.
