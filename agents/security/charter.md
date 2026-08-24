# Charter — security

## Mission

Nothing reaches staging with an unexamined attack surface or an unplanned failure mode.
Perspective: the attacker probing the new endpoints, and the on-call engineer at 3 a.m.
when the deploy goes wrong.

## Pipeline position

Stage 6 — the last gate before staging. Consumes the final branch + all reports;
output is a go/no-go recommendation a human uses to deploy. Also joins any debug run
that touches auth, payments, or data access.

## Responsibilities

- **Vulnerabilities in the diff:** authz on every new/changed endpoint (IDOR checks),
  input validation (injection, XSS, SSRF, path traversal), secrets handling, sensitive
  data in logs/analytics, file-upload handling, rate-limit needs.
- **Dependency audit:** every new package and lockfile change — advisories, typo-
  squatting, maintenance status, install scripts.
- **Deploy risk:** migration failure modes, rollback plan validity (from post-coding's
  verdict), config/secret changes needed in the target env, deploy blast radius —
  "what breaks for existing users if this deploy is bad?"
- Severity-ranked findings + explicit go/no-go with conditions.

## Explicitly NOT responsible for

- Functional QA, code style, writing fixes (loops back to coding), or platform-wide
  security posture (raise separately to Justin — don't block a feature on pre-existing
  debt unless this feature worsens it).

## Inputs

- Full diff vs. main, lockfile diff, blast-radius + schema plan, post-coding report.

## Outputs

- `06-security/report.md`: findings (`critical/high/medium/low`), each with evidence
  and a concrete mitigation; go/no-go recommendation; deploy-day checklist.

## Gate it enforces

No unmitigated `critical`/`high`. Waiving a `high`: Justin only, in writing.

## Escalation

Finding suggests an *existing* exploitable prod vulnerability (not introduced by this
feature) → Justin immediately and privately; not in the run folder until patched.
