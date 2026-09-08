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
  bug-20260901-export-timeout/
    brief.md
    01-triage/ … 06-postmortem/   (see workflow/DEBUG-LIFECYCLE.md)
```

Videos, traces, and any file over ~1 MB go to the artifact bucket (see
`infra/ec2/README.md`) and are linked from reports — never committed here.
