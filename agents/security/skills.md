# Skills — security

## 1. Session start

Standard reads. Build the review target list from the diff: new/changed endpoints, new
queries, new packages, new config, migrations.

## 2. Endpoint & input review

Per new/changed endpoint:
- Who can call it? Verify the authz check exists *in this handler*, not assumed from
  middleware — read the code path.
- IDOR: every ID parameter — is ownership checked against the session user?
- Inputs: typed/validated at the boundary? String inputs reaching SQL/HTML/shell/URL
  fetches → trace the sanitization or flag.
- What appears in logs and PostHog events? PII/tokens in either = finding.

## 3. Dependency audit

For each new/updated package: `npm audit` / advisory DB check, exact-name check against
the intended package (typo-squatting), last release + maintainer activity, install
scripts (`preinstall`/`postinstall`), transitive additions in the lockfile diff.

## 4. Deploy-risk review

- Walk the deploy sequence: migration → code rollout → flag flip. For each step ask
  "if it fails halfway, what state are users in, and what's the operator action?"
- Confirm required env/config/secrets exist in staging *before* recommending go.
- Write the deploy-day checklist: ordered steps, verification per step, rollback
  trigger criteria ("roll back if X metric does Y").

## 5. Verdict

- Findings table ranked by severity, each with file/line evidence and a specific fix.
- Recommendation: `GO` / `GO with conditions (listed)` / `NO-GO (blockers listed)`.
  Never hedge with "should be fine".

## 6. Session end

Report per template. Memory: append vulnerability patterns found (or found-late) so
pre-coding and this role probe for them earlier next run.
