# Skills — post-coding

## 1. Session start

Standard reads. Generate the full diff vs. main once and work from it; don't review
commit-by-commit (debt hides between commits).

## 2. Cleanliness pass

- Read the diff end to end. Flag: dead/unreachable code, copy-paste blocks (search for
  near-duplicates of new functions), console/debug output, commented-out code,
  files added but never imported, naming that diverges from the exemplar pattern.
- Diff intent vs. reality: open `task-plan.md` next to the diff; anything implemented
  but not planned (or planned but missing) goes in the findings.

## 3. Tech-debt pass

- For every new query: is there an index? Is it bounded (limit/pagination)? Run
  EXPLAIN on anything touching large tables.
- For every loop over external calls: n+1 check.
- For every literal: should it be config/env? For every `catch`: is the error surfaced?
- For every new list UI: what happens at 0, 1, and 10,000 items?

## 4. Backward-compatibility pass

- API: for each changed endpoint, list existing consumers (from blast-radius.md) and
  verify old request/response shapes still work. Removed/renamed fields = finding.
- Schema: can this deploy be rolled back with the migration already applied? Test the
  rollback migration's logic on paper against in-flight rows.
- Events/analytics: renamed or restructured events break PostHog dashboards — check
  event names/properties against the existing schema.
- Flags/config: new required env vars documented and defaulted? Old deployments with
  the old config still boot?

## 5. Session end

Findings table: `ID | area | severity | tag (fix-now/debt-ticket/waived) | evidence`.
Verify each `fix-now` resolution in the updated diff before passing. Report per
template. Memory: append debt patterns that keep appearing (they become pre-coding
warnings).
