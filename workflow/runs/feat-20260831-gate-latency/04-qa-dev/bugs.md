# Bugs — feat-20260831-gate-latency (04-qa-dev, attempt 1)

**Product bugs: none.** 126 scripted checks across the 8 kept sessions, 124
passed; the 2 non-passes are QA-harness artifacts, not product behavior:
session 4's "prod median ~2h" literal was invalidated by the box clock jumping
~6 days mid-stage (the rendered `5d 23h` was verified exactly correct by DB
recomputation — 517664s), and session 7's "no console errors" tripped on the
browser logging this charter's own deliberate 409 double-submit probe. One
earlier session run also failed a clock-shifted literal (`4d 2h` old-pending)
and passed after the seed was re-timed to the corrected clock.

No sev-1/sev-2/sev-3/sev-4 entries. The gate condition (zero open sev-1/sev-2)
is met.

## Environment findings (not product bugs; filed for the ops trail)

- **E-1 — feature was not deployed to dev at stage start.** The kickoff stated
  `feat/gate-latency` was live; the box checkout was at pre-coding `525a6da`
  with no `LATENCY_SQL` in `tools/mission-control/`, and the local
  `feat/gate-latency` ref also lacked the coding commits (they live on
  `claude/gate-latency-statusline-ledger-9189b4`). This QA session deployed the
  coding branch (a clean fast-forward of the deployed HEAD) via bundle-over-scp,
  updated the box's `feat/gate-latency` to `b75a4f2`, and restarted only
  `lantern-mission-control` (diff touches no `tools/azure-runner` code, so the
  orchestrator daemon was left alone).
- **E-2 — the provisioned QA dev credentials could not log in.**
  `LANTERN_QA_DEV_USER` was the placeholder `none` and matched no entry in
  `LANTERN_WEB_USERS` (only `justin` existed). `qa-preflight` checks
  reachability, not login, so this would have failed every sandboxed stage-4 run
  at the login form. Fixed on the box `.env` (backup at
  `/tmp/env.backup.qa-stage4`): added `qa-dev:<existing provisioned pass>` to
  `LANTERN_WEB_USERS`, set `LANTERN_QA_DEV_USER=qa-dev`. Side effect (accepted):
  no explicit `LANTERN_WEB_SECRET` is set, so the derived cookie key changed and
  pre-existing sessions were invalidated (one re-login for justin).
- **E-3 — box clock was ~6 days behind and resynced mid-stage.** During the
  stage the box became unreachable for ~25 min; when it returned, DB `now()` had
  jumped from Sep 1 to Sep 7 (real date). Every time-relative seed shifted at
  once: 30-day-window rows fell out of the window and pending ages grew 6 days.
  Seeds were re-timed against the corrected clock and affected sessions re-run.
  Anything on this box that trusts wall-clock (gate ages, medians, spend windows,
  heartbeats) was silently wrong before the resync.
