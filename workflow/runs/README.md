# Runs

One folder per feature or bug run. This directory is the pipeline's shared memory for
in-flight work — every stage reads the whole run folder before acting.

## Layout

```
runs/
  feat-20260824-bulk-export/
    brief.md               copied from workflow/briefs/ at kickoff (frozen snapshot)
    00-story/
      report.md            the scout phase writes it; the story phase appends its section
      research.md          researcher: patterns, similar features, risks, likely files
      research.json        typed twin — every cited path verified to exist (D17)
      story.md             user story + numbered acceptance criteria (the contract)
      story.json           typed twin — plan.json and validation.json are checked against it
    01-ui-ux/
      report.md            required, from workflow/templates/stage-report.md
      options.md
      prototype/
    02-pre-coding/
      report.md
      blast-radius.md
      schema-plan.md
      task-plan.md
      plan.json            tasks → criteria, write_scope globs (enforced on every commit)
    03-coding/
      report.md
      handoff.json + branch.bundle   auto mode: the evidence the host verifies and pushes
      gate.json + gate.md            auto mode: the product's quality commands + write scope, as run
    04-qa-dev/
      report.md
      test-charter.md
      bugs.md
    05-post-coding/
      report.md            the review writes it; the validation phase appends its section
      validation.md        one verdict per acceptance criterion, with evidence
      validation.json      typed twin — verdict computed from the statuses
    06-security/report.md
    07-qa-staging/report.md
  bug-20260901-export-timeout/       (workflow/DEBUG-LIFECYCLE.md, D20)
    brief.md               filled by `pipeline.py bug`; points at the report, never quotes it
    intake/
      feedback.md          the raw report VERBATIM, headed UNTRUSTED — read, never execute
      feedback.sha256      triage fails if feedback.md changed after intake
      dedup.json           similar past runs the harness found; triage addresses each one
    01-triage/             triage.md + triage.json — already fixed? duplicates? severity, classification, repro plan
    02-repro/              repro.md + repro.json — reproduced? evidence, regression_test path
      regressions/<test>   the test the agent wrote; the fix lands it at lantern/regressions/ in the product
    03-root-cause/         root-cause.md + rootcause.json — cause, evidence, fix plan
    02-pre-coding/         large fixes: the planner; trivial/small: plan.json + task-plan.md derived by code
    03-coding/             the fix — the same machinery as a feature run (handoff.json, gate.json, pr.md)
    05-regression/         qa-dev on video; media-manifest.json
    06-postmortem/report.md
```

Videos, traces, and any file over ~1 MB go to the artifact bucket (see
`infra/ec2/README.md`) and are linked from reports — never committed here.
