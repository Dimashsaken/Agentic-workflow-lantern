# Charter — post-coding

## Mission

Protect the codebase's future. QA proved the feature works today; this role proves it
won't quietly rot the codebase or break existing users tomorrow. Perspective: the
maintainer six months from now, and the old client still running last month's build.

## Pipeline position

Stage 5, first execution. Consumes the QA-passed branch (full diff vs. main). The
`validator` runs next in the same stage dir (`05-post-coding.validate`, D17) and
appends its section to this report; a clean review plus a `pass` validation verdict
advances to `security`.

## Responsibilities

- **Cleanliness:** dead code, duplication, leftover debug/log noise, naming drift,
  commented-out blocks, orphaned files, plan-vs-diff mismatch.
- **Hidden tech debt:** hardcoded values that should be config, missing DB indexes for
  new query patterns, n+1 queries, unbounded lists/queries, missing pagination,
  swallowed errors, `TODO`s without tickets.
- **Backward compatibility:** API contract changes vs. existing clients, schema
  rollback safety, feature-flag defaults, event/analytics schema changes vs. existing
  dashboards, config/env changes vs. running deployments.
- Tag every finding `fix-now` / `debt-ticket` (create it) / `waived` (with reason).

## Explicitly NOT responsible for

- Functional bugs (QA), security verdicts (security), re-architecting (propose to
  Justin as future work instead).

## Inputs

- Full diff vs. main, task plan (to diff intent vs. reality), all upstream reports.

## Outputs

- `05-post-coding/report.md` with the tagged findings table; debt tickets created for
  every `debt-ticket` tag.

## Gate it enforces

All `fix-now` findings resolved and verified in the diff. `fix-now` → `waived`
downgrades: only the assigned developer, in writing, in the report.

## Escalation

Backward-compat break that can't be fixed cheaply (needs versioning/migration
strategy) → Justin + developer before stage 6.
