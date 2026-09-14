# The first product runs — what the factory produced and how it behaved

**Period:** 2026-09-11 16:29 UTC → 2026-09-14 08:13 UTC (three feature runs on the EC2 box, real Azure
OpenAI models, every gate recorded). **Operator:** dimash (gate decisions under a written
blanket pre-approval for this proof; the pipeline itself never decided a gate).
**Branch of record for the harness changes:** `claude/test-validate-project-n50nx3`.

## 1. End results

Three Tender features exist as reviewed, tested, video-verified branches of the product repo
(`product/tender-whatsapp` is the seed; each branch is stacked on the previous one because
merging is a human act that has not happened yet):

| Run | Branch (head) | Commits since seed | Pipeline outcome |
|---|---|---|---|
| `feat-20260911-tender-onboarding` | `feat/20260911-tender-onboarding` (`0b55b95`) | 28 | **done** — `prod_signoff` 2026-09-11 23:33 UTC |
| `feat-20260911-tender-catalog-orders` | `feat/20260911-tender-catalog-orders` (`6308dc9`) | 68 (40 own) | **done** — `prod_signoff` 2026-09-12 04:12 UTC |
| `feat-20260911-tender-escalations` | `feat/20260911-tender-escalations` (`3726186`) | 91 (23 own) | **done** — `prod_signoff` 2026-09-14 08:13 UTC |

Across the stack the product grew from a two-file skeleton to 88 changed files, +10,311 lines,
20 test modules, four Alembic migrations, and a rule-based WhatsApp assistant with sign-up,
business profile, sandbox and Meta Cloud channels, catalog and order taking, and owner
escalation with an inbox. Twenty-four QA recordings are in S3 under attempt-prefixed names
with sha256 manifests.

What is **not** done: no pull request exists (the box token lacks `pull_requests: write`),
nothing is merged, and the box serves plain HTTP. Production for these runs means the
internal-demo instances on the box (`tender-dev` on :8000, `tender-staging` on :8001).

## 2. Cost and time

Total estimated spend for the three features: **about $319** (249M input tokens, 94% cached; 1.06M output tokens; 106 executions; 2,293 model requests).

| Run | Executions | Model requests | Input tokens (cached) | Output tokens | Est. spend | Wall clock |
|---|---|---|---|---|---|---|
| onboarding | 42 | 941 | 105.8M (99.0M) | 396k | $134 | 7.0 h incl. a 1.75 h pause |
| catalog-orders | 40 | 815 | 96.9M (90.4M) | 393k | $124 | 4.6 h |
| escalations | 24 | 537 | 46.5M (43.5M) | 271k | $61 | 2.6 h active, plus a 49 h stall (see §4, defect 14) |

Everything ran on one deployment (`gpt-5.6-sol`) at high reasoning effort; 93–94% of input
was served from the prompt cache. The per-stage medians are small — story 2–3 min, design
7–9 min, pre-coding 3–6 min, a coding attempt 7–11 min, a review round 4–5 min, QA 8–9 min,
security 3 min. The calendar time is dominated by the loop: each finding costs a coding
attempt plus a review round plus every downstream stage again.

## 3. Did the gates catch anything real?

Yes, at every level. None of these were seeded; each was found by a role reading the code or
driving the browser, and each was fixed by the coding role on the same branch:

- **Review bot** (D19): 1 blocker and 15 majors across the three runs before a human saw a
  gate — sessions signed with a committed fallback secret, a webhook that could double-send,
  an unbounded request body, an order-chat loop that could never recover, a `1e100` price
  that overflowed on save, a negative quantity parsed as positive.
- **QA in dev** (D3 video): the 413-before-403 signature-ordering bug (AC-6), an unreachable
  `localhost` link in owner notifications.
- **Post-coding**: tracked generated `egg-info`, a migration/startup contradiction, float
  money arithmetic beside `Decimal`, developer docs that would boot a fresh checkout with
  zero tables, 21-pixel touch targets against a 44-pixel plan.
- **Validator** (D17): AC-10 off-spec on the escalations run (only the latest escalation per
  conversation was shown) — the first FAIL verdict, with file and line evidence for 10 of 11
  criteria.
- **Security**: a NO-GO on both larger runs — no throttling or password policy on public
  auth; a status notification sent to Meta before the database commit — both fixed and
  re-reviewed to GO.
- **QA on staging**: a 500 when a fresh seller opened Sandbox before a profile existed — a
  bug dev QA could not see because its account already had a profile.

Every one of these went back through `rework`/`reject` → coding → review → gate → QA →
post-coding → validation → security. Nothing was waived except the production-like
integration checks the demo box cannot provide (Meta test number, Postgres contention,
Firefox/WebKit, PostHog), recorded per item in the run folder.

## 4. What the factory got wrong, and what changed

The harness had **fourteen defects** that these runs exposed; all are fixed on the branch with
a test each, and `tools/evals/REPORT.md` was regenerated where the PR rule requires it.

| # | Defect (found by) | Fix |
|---|---|---|
| 1 | Brief fields kept inline `<!-- -->` notes, so `auto`/`html` read as unset (run creation) | `brief_field()` strips annotations — `5061311` |
| 2 | The html design checks were applied to the coding stage's handoff (first html run) | scoped to `01-ui-ux` — `565e453` |
| 3 | The box `.env` still carried the dogfood QA login (stage 4) | `pipeline.py qa-target` — `598282d` |
| 4 | The QA agent never guesses a login and had no account (stage 4) | `tender-playbook.sh qa-account` — `14391b1` |
| 5 | `qa-preflight` posted Mission-Control-shaped fields and called a working login REJECTED | form-following probe — `9e5bec0` |
| 6 | The serve unit lacked the build's documented secrets (`TENDER_CREDENTIAL_KEY`) | persisted env file per target — `5a1103a` |
| 7 | Review rounds restarted at 1 after a rework; a valid round-3 approve was discarded | branch-wide numbering — `17d2388` |
| 8 | A rework's note never reached the coding task block; a no-op attempt handed back the same head | `rework_context()` — `efdffda`, `2de2f18` |
| 9 | A no-op coding execution passed on the previous execution's handoff | handoff ownership + finalize failures fail — `efdffda` |
| 10 | The reviewer could overwrite an earlier round's file | write-once round files — `efdffda` |
| 11 | The task block's plan summary was capped before task 1 for a long plan | every numbered task always listed — `ba44c20` |
| 12 | Alembic could not adopt a `create_all` fixture database; migrations not applied by serve | stamp-then-upgrade in `serve` — `833d92c`, `7823b65` |
| 13 | Owner links used `localhost`; the build refuses plain-http origins | bridge origin + explicit opt-in — `c81075f`, `567e90f` |
| 14 | A review round lost to a 429 or a docker restart stranded the run | `pipeline.py review` — `5b88d1f` |

Operational findings on the box: the GitHub credential and `.env` token had expired (replaced
from SSM), the laptop's public IP changes between sessions (per-IP SSH rule), coding/stage
wall clocks were raised to 180/60 min, model retries to 6, and `apt-daily-upgrade` was
disabled after it restarted docker under a running review.

## 5. Honest limits

- **Human gates were pre-approved.** Every decision is recorded as dimash's with the
  pre-approval quoted, plus the substance (option chosen, open findings, PR state). The
  routing decisions (5+3+2 reworks, 3 rejections, 1 review re-run) were made by the operator
  from the gate rules, not by the models.
- **The review bot runs two rounds per cycle.** Larger changes needed a reject with the
  reviewer's list and another cycle; one round on each of the two later runs was lost to
  transport (429) or an OS restart.
- **BLOCKED is the roles' only "send it back" signal.** QA and post-coding report
  `Status: BLOCKED` with a question instead of a FAIL, and the answer path is a human note in
  the run folder plus `retry`/`rework`.
- **Staging is the same box over HTTP** with SQLite and Chromium only; the Cloud channel is
  the production Graph transport, so a correctly signed inbound text was never exercised in a
  browser; PostHog is not wired.
- **The seed committed generated metadata**, which cost a full cycle; product seeds should not.
- **Two D25s exist** (html design mode on this branch; `ux_signoff` removal on another
  session's branch) and will collide at merge time.

## 6. Recommendations

1. Grant the box token `pull_requests: write` (or a dedicated `lantern-bot` token) and run
   `pipeline.py publish` for the three runs; then merge in order.
2. Put TLS in front of the QA targets (the D24 gateway proposal) so the insecure-origin
   opt-in and the `TENDER_SECURE_COOKIES=false` condition disappear.
3. Give dev a recording transport for the Meta channel so QA can drive a signed inbound text.
4. Raise `LANTERN_REVIEW_ROUNDS` to 3 for greenfield features, and let QA/post-coding return a
   typed FAIL with a fix-now list instead of BLOCKED-with-a-question.
5. Add a fresh-account pass to the QA charter template; staging found what dev could not.
6. Rotate the Azure key pasted in chat on 2026-09-11.
