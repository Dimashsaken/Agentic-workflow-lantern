# Runs

One folder per feature or bug run. This directory is the pipeline's shared memory for
in-flight work — every stage reads the whole run folder before acting.

## Layout

```
runs/
  feat-20260824-bulk-export/
    brief.md               copied from workflow/briefs/ at kickoff (frozen snapshot)
    01-ui-ux/
      report.md            required, from workflow/templates/stage-report.md
      options.md
      prototype/
    02-pre-coding/
      report.md
      blast-radius.md
      schema-plan.md
      task-plan.md
    03-coding/report.md
    04-qa-dev/
      report.md
      test-charter.md
      bugs.md
    05-post-coding/report.md
    06-security/report.md
    07-qa-staging/report.md
  bug-20260901-export-timeout/
    brief.md
    01-triage/ … 06-postmortem/   (see workflow/DEBUG-LIFECYCLE.md)
```

Videos, traces, and any file over ~1 MB go to the artifact bucket (see
`infra/ec2/README.md`) and are linked from reports — never committed here.
