# Skills — debug

## 1. Session start

Standard reads + the bug brief. Establish immediately: is this new or a recurrence?
(Search closed `bug-*` runs and this memory file.) Recurrence = escalate to a pipeline
change per DEBUG-LIFECYCLE.md.

## 2. Triage

- Severity honestly (defined in DEBUG-LIFECYCLE.md); "annoying but rare" is not sev-2.
- Scope: PostHog — how many distinct users hit this, since when? Correlate first
  occurrence with deploy history to shortlist suspect commits before reading any code.

## 3. Reproduction discipline

- Reproduce from the user's path, not the code's: session replay first if available.
- Ratchet down: full manual repro → minimal repro → scripted repro in
  `tools/qa-recorder` (video on). Commit the failing script to the run folder.
- Unreproducible after honest attempts: write up what was tried, add targeted
  logging/PostHog events behind a fast-track mini-review, and set a tripwire — do not
  move to root-cause on speculation.

## 4. Root-cause analysis

- Bisect with evidence: suspect commits from triage, `git log -p` on the failing path,
  logs at the failure timestamp. State the cause as a falsifiable sentence:
  "X fails when Y because Z (evidence: …)".
- Before closing the analysis: grep for the same pattern elsewhere; sibling defects
  found now are 10× cheaper than as next month's bug.

## 5. Fix + verification loop

- Write the fix task like a mini task-plan: files, approach, blast radius of the fix
  itself (fixes cause bugs too — check the blast-radius habit applies).
- Verification = formerly-failing script green + qa-dev regression pass green.

## 6. Postmortem (session end)

Use the postmortem structure in DEBUG-LIFECYCLE.md. The two questions that must have
non-empty answers: "which pipeline stage should have caught this?" and "what memory
entry / skills change / pipeline change prevents recurrence?". Route those entries.
Append own memory: diagnostic tricks that worked, instrumentation gaps found.
