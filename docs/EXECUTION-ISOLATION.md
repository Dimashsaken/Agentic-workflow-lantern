# Experimental execution isolation and recovery

This increment is opt-in. It does not authorize a release, migration on the
configured Lantern database, or any pipeline approval. The engineering evidence
is under `workflow/runs/feat-20260910-agentic-infrastructure/`.

## Controller and workers

Set `LANTERN_EXECUTOR=isolated` to keep the Azure OpenAI Agents SDK on the trusted
controller and put product programs and Playwright MCP in disposable Docker
workers. Only the execution's product checkout and media directory are mounted.
The harness, authority files, Docker socket and controller credentials are absent.
Workers use a pinned image digest, read-only root filesystem, unprivileged UID,
no capabilities, no new privileges, bounded resources and `--network=none`.
Product metadata and Git programs execute inside the worker. Product checkouts
are named by the hash of the execution key and are never reused by another attempt.

This supports offline coding and loopback browser targets hosted inside the worker.
External QA targets and desktop Paper require a separately reviewed transport;
they are not supported by this mode. The original Docker executor remains available
with experimental flags disabled. Combining it with leases or trusted evidence
is rejected because its credential-bearing SDK container does not implement the
new controller boundary. All host stages are serialized while legacy prompt
helpers still use process environment for product context.

The Docker daemon, host administrator, controller OS and configured image remain
trusted. Keeping the database password on the controller does not provision
least-privilege production database grants. The current migration does not add
per-run service accounts. Container controls are not a claim of VM isolation.

## Renewable ownership and restart

After applying the additive `schema.sql` migration through the existing human
migration process, `LANTERN_EXECUTION_LEASES=1` enables run and child execution
leases. Ownership uses server time, an owner identity and monotonic fences.
Heartbeats use separate connections. Advancement, child completion, usage,
memory and artifact acceptance check the relevant fence in a transaction.
Parallel Docker builders use separate database connections; host stages serialize.

`LANTERN_LEASE_TTL` defaults to 120 seconds. Expired parents or children cause the
run to be held failed, its active children to be closed, and ambiguous publication
intents to become uncertain. A new daemon never blindly requeues all executing
runs. No serialized SDK session is automatically resumed or replayed. Use the
existing explicit retry/rework surface after inspecting the interrupted attempt
and its effects. A retry gets a new execution key and new checkout.

Completed SDK responses and tool start/end boundaries are fsynced outside worker
mounts to `LANTERN_DIAGNOSTICS_DIR` (default `~/.lantern/diagnostics`). Known usage
is also persisted after each response. Interrupted responses and tools remain
unknown; the ledger is a lower bound until completion. Diagnostics never contain
prompt text, arguments or tool output. A success terminal event follows lifecycle
completion; failures before then remain incomplete and the database supplies the
stage outcome. `read_diagnostics` recovers complete records and tolerates a torn
final append. This is diagnostic recovery, not an SDK replay log.

Recovery reaps Docker workers by the exact execution labels and rechecks full
container identities. Cleanup failure is an event requiring operator attention.
An already running host Git command or external request cannot be revoked by
heartbeat cancellation. Partial mirror refs or ambiguous provider effects require
explicit reconciliation; they are not automatically replayed.

Strict GitHub publication records a version-3 durable intent including run,
repository ID, destination URL/base/work, desired commit, observed base commit and
expected old remote commit. Repository/ref reads and bounded PR pagination verify
the exact head/base repository, refs, revisions, PR identity and open state.
Interrupted actions and confirmed duplicates reobserve the provider without
repeating their writes. A moved base/head, changed repository ID, contradictory PR, unavailable API
or ambiguous outcome holds. Old unbound aggregate intents stay held; they are not
silently upgraded. Conditional Git pushes use the immutable desired commit and
exact expected remote value, with no unconditional-force fallback. Publication
receipts/artifacts share target and ownership checks; the provider is observed
again after review before opening the human gate. These are observations at a
point in time, not a distributed atomic transaction with GitHub.

Separate fenced branch and PR intents precede each external action. After an
interrupted branch write, recovery can confirm the observed branch and create the
previously unattempted PR once. An existing intended or uncertain action without
its expected provider result stays held; absence of that result cannot prove the
request never ran. Version-1 and version-2 aggregate attempts also remain held:
their missing child intents cannot authorize a new action. Strict mode
omits optional external review posts, comments and labels without their own effect
handling. Local review artifacts and human review ownership remain. Babysitting
is centrally held in lease mode until dedicated maintenance ownership is approved
and implemented. Legacy behavior remains available with flags disabled; it does
not acquire these guarantees.

## Trusted evidence

`LANTERN_TRUSTED_EVIDENCE=1` requires the isolated controller path. The approved
typed plan must explicitly map every story criterion to observed command IDs:

```json
{"requirement_tests": {"AC-1": ["quality:test"]}}
```

A link records the plan's claim about coverage. It does not establish that the
test assertions adequately check the requirement. Review still supplies that
judgment. A missing mapping fails closed; legacy plans are not silently upgraded.

Strict quality checks use committed clean source in an independent read-only
snapshot. Ignored local dependencies and original Git configuration/hooks do not
enter that snapshot. Tests must use dependencies from the approved image and
write temporary output outside the source mount. The model retains its original
checkout for the bounded fix loop. Before/after identity checks alone are not
treated as proof that mutable source was actually tested.

The controller writes manifests and gate authority outside worker mounts to
`LANTERN_AUTHORITY_DIR` (default `~/.lantern/authority`). Run-directory `gate.json`
is a display mirror. Acceptance loads the independent record and checks execution,
attempt, lease fence, source, image, policy, command outcomes and artifact hashes.
Harness revision plus a source fingerprint distinguishes uncommitted code from HEAD.
Changing an artifact, identity or source invalidates the receipt. Mission Control
displays only provenance captured in the completed database execution row; a
writable mirror cannot supply a verified badge. The label means verified at
completion, not that the browser has repeated verification now.

The video verifier checks actual decoding, hashes and controller-provided recording
identity. It cannot infer the truth of a walkthrough or the deployment revision
from video bytes. Generic QA stage media is not yet fully sealed through that
manifest path; browser recordings and command manifests have separately labelled
evidence in the engineering report.

## Rollout and rollback

Keep all three experimental flags disabled until the independent review findings
are resolved and the release's required human gates are satisfied. The new schema
is additive: nullable lease owner/expiry, monotonic fences and `execution_effects`.
The exact forward and rollback SQL is in the approved local engineering schema
plan. Stop dispatchers and inspect active leases/effects before rollback; never
drop recovery data while an outcome is uncertain. Disable flags together and
restore the previous host/image as a coordinated rollback. Failed/held work still
needs an explicit human retry rather than an automatic startup requeue.

The disposable PostgreSQL proof measures migration/rollback and row preservation;
it is not production lock-duration evidence. The original configured local
PostgreSQL cluster was restored non-destructively in continuation 3, and pending
learnings were appended through the actual memory tool. No schema change was
applied to it. Actual GitHub repository/ref reads succeeded, but PR inspection
returned 403 with the configured bot token; positive live publication acceptance
remains unverified. The process-kill publication proof uses real disposable
Postgres with simulated GitHub observations, separately from that live read-only
check. Azure stays the sole model provider and the fixed pipeline and human gate
decisions remain unchanged.

## Continuation 3 local implementation — 2026-09-11

`LANTERN_FENCED_BABYSIT=1` selects dedicated maintenance ownership for both manual
and scheduled babysitting. It requires isolated tools and is default off. A
maintenance execution binds the actual human code-complete decision, exact PR,
repository/refs and run position; it never changes run status or approvals to
obtain a dispatcher lease. Dispatcher claim, retry/rework and decision writes
serialize on the run row. Conflict checks use a fresh statement after obtaining
that lock, avoiding PostgreSQL's pre-wait statement snapshot race.

The maintenance path uses a private trial merge, an immutable quality snapshot,
conditional working-branch push and final provider observation. Lease loss stops
known workers and joins outstanding worker threads before returning. A red regate
holds: inherited maintenance fix execution is not implemented. Unknown or legacy
publication approvals also hold. No code merges a PR or changes a human gate.
The legacy runtime remains available with the experimental protections disabled.

Fresh isolated product checkouts receive controller-owned allocation descriptors
under `LANTERN_RETENTION_AUTHORITY` (default `~/.lantern/retention`). Allocation,
worker mounts and retirement share an OS lock. Retirement permanently tombstones
the identity, atomically quarantines the exact checked directory, then deletes
only it. Database terminal state, seven-day age and absence of unresolved effects
and all Docker bind mounts are rechecked. Nonempty output/error pins evidence
indefinitely. Symlinks, reparse points, hardlinks, unknown allocations, failed
inspection and unverified Docker Desktop path translations hold.

`execution_retention.inventory` reports known bytes, server-clock ages and held
reasons. It cannot authorize deletion; `retire` rechecks under the lifecycle lock
and defaults to `apply=False`. No automatic cleanup schedule is wired. Legacy
paths and temporary maintenance clones remain retained. Maintenance allocation
coverage and lookup cost as permanent descriptors accumulate remain tracked debt.

`qa_transport.launch_external` unconditionally holds. The gateway sources and
43-package hash lock are unaccepted candidates: the dependency audit found
published advisories, and no accepted host firewall adapter or actual gateway
denial proof exists. They must not be enabled through a proxy variable or flag.

The dedicated recorder image passed a local direct HTTPS fixture using an
ephemeral per-container NSS trust store with certificate validation enabled.
Its output is video plus a redacted command-outcome JSON trace, not a replayable
Playwright trace. Controller-only capture receipts bind execution/attempt/fence,
immutable image, deployment descriptor, requirements and actual media hashes and
decoding. Persistence checks the durable attempt/key under its lease. Fixture
receipts explicitly say `transport_mode=direct_fixture`, `test_only=true` and
have no gateway image; contradictory or missing transport contracts are refused.
This fixture does not establish external egress enforcement or fleet-stage
integration, and generic QA stage media remains separate.

Independent reviews permit only a bounded local B/D pilot. Staging remains
NO-GO. No flags, live gates, configured schema, external publications or
deployments were changed by this local implementation. Full evidence and known
limits are recorded in the run's coding, QA, post-coding and security reports.
