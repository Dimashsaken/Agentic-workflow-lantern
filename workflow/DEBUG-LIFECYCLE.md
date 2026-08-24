# The Debug Lifecycle

Bugs do not enter the feature pipeline. They get their own run
(`workflow/runs/bug-YYYYMMDD-<slug>/`) owned end-to-end by the `debug` agent, which
pulls in other agents as needed.

## Intake

Two entry points, same lifecycle:

1. **User report** — someone files `workflow/briefs/_BUG-TEMPLATE.md`.
2. **PostHog signal** — error spike, funnel drop, or session-replay anomaly. The
   intake note must link the PostHog insight/replay URL.

## Stages

```
intake ──▶ 1 triage ──▶ 2 reproduce ──▶ 3 root-cause ──▶ 4 fix ──▶ 5 regression QA ──▶ 6 postmortem
```

### 1. Triage → `01-triage/`
Severity (sev-1: data loss/security/all-users-down … sev-4: cosmetic), scope (who is
affected, since when — check git log and deploy history), and priority call. Sev-1/2:
notify Justin immediately, before continuing.

### 2. Reproduce → `02-repro/`
Turn the report into a **deterministic failing artifact**: ideally a failing Playwright
script in `tools/qa-recorder` with the failure captured **on video**. If it cannot be
reproduced, document the attempts and instrument (add logging/PostHog events) instead
of guessing. No fix work starts before repro or instrumentation exists.

### 3. Root cause → `03-root-cause/`
Debug agent traces the failure to a specific change or interaction. Cite evidence:
commit, log line, replay timestamp. "Probably X" is not a root cause. Check whether the
same defect pattern exists elsewhere in the codebase.

### 4. Fix → `04-fix/`
Small, surgical branch `fix/<slug>`. The assigned developer (or debug agent for
trivial fixes, with developer review) implements. The stage-2 failing script must now
pass. Sev-1/2 fixes also get a `security` agent spot-check if they touch auth, data
access, or payments.

### 5. Regression QA → `05-regression/`
`qa-dev` agent runs: the new failing-then-passing script, the surrounding feature's
original charter, and a memory-informed sweep of adjacent risk areas. Video on.

### 6. Postmortem → `06-postmortem/`
Five-minute writeup: what broke, why it escaped stages 4–7 of the original feature run,
which agent's `memory.md` gets an entry (at minimum one agent always does), and whether
a pipeline/skills change is warranted. Sev-1/2 postmortems are reviewed by Justin.

## Rules

- Every bug run must end with at least one new automated regression test.
- If triage reveals a security issue, the `security` agent joins immediately and the
  run is treated as confidential (no details in commit messages until patched).
- Recurring bugs (same root cause twice) escalate to a pipeline change, not just a fix.
