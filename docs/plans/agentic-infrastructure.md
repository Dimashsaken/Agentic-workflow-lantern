# Verifiable agent infrastructure

Date: 2026-09-10. Run: `feat-20260910-agentic-infrastructure`.

## Intent and authorization

The user asked this developer session to read the architecture, choose improvements,
and execute the plan. This is local engineering work on Lantern itself, authorized
in this session. It does not decide any live pipeline approval, publish a branch,
deploy, or claim that a fleet stage has executed. No schema migration is planned.

The starting point is `docs/research/agentic-architecture-assessment.md` and D23.
Keep the fixed stage sequence, Azure provider, code-driven control flow and human
gates. Improve the harness boundary and evidence before adding model routing or
another orchestration framework.

## Acceptance criteria and ordered work

1. **AC-1 — Enforced capabilities.** Bind file tools to an execution's run, role,
   stage, and product checkout. A role cannot overwrite the harness, upstream
   contracts, another run, sibling builder outputs, or host-generated gate/trace
   artifacts. Read tools reject credential files and git metadata. Export tools
   observe the same write policy. Only coding gets a product shell; only design
   gets desktop exports. Test real SDK tool invocations, traversal and interleaving.
2. **AC-2 — Read-only git.** Replace the incomplete flag blocklist with validated
   read-only command forms. Refuse ref mutations, pager execution, filesystem
   escape options and external diff/textconv execution. Prove refusals on real
   temporary repositories as well as normal history/search behavior.
3. **AC-3 — Fail-closed code gates.** Missing, stale, malformed and contradictory
   gates fail. A product without a test command cannot produce a green automatic
   coding handoff. Capture quality configuration before the builder runs and
   reject changes to it during the loop; verify command results and identities.
4. **AC-4 — Resolvable evidence.** Validation references must identify real,
   confined files and valid lines, rather than unsupported prose. Check review
   references against the reviewed revision. Reject empty or invalid report
   statuses. Keep semantic judgment distinct from mechanical evidence resolution.
5. **AC-5 — Failure diagnostics.** Retain completed turns and available SDK partial
   diagnostics when a later turn raises; classify execution failures and preserve
   redacted traces and known usage without inventing missing usage.
6. **AC-6 — Verification and handoff.** Add adversarial regression tests to the
   repository gate, regenerate frozen evals and their fingerprint, run the relevant
   existing suites, and record results and limitations in the coding report.

## Scope and validation

Primary code: `tools/azure-runner/` (policy, orchestrator, factory, pipeline and
review integration). Supporting changes: relevant role instructions,
`tools/evals/`, `lantern.toml`, architecture/operations docs, and this run folder.
Implement sequentially to keep shared harness changes coherent.

Use temporary repositories and injected SDK/database boundaries for destructive
and failure tests. Run the actual SDK wrappers locally. A live Azure run, Docker
containment test and database-backed lifecycle test are separate evidence; do not
label local tests as those. Remaining trust boundaries (same-user shell, database
credentials, network egress) must be described accurately.
