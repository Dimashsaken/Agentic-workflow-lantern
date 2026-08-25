# Karpathy on agentic loops — research brief (2026-08-25)

Primary-source research on how Andrej Karpathy works with and thinks about AI coding
agents. Every claim traces to his own posts/talks; apocryphal attributions flagged.
This brief grounds Lantern's orchestration design (see `docs/ORCHESTRATION.md`).

## The principles, each with its source

1. **Partial autonomy, not full autonomy.** Build "partial autonomy apps"; the gap
   between demo and product is the whole game — "demo is works.any(), product is
   works.all()." (Software 3.0 talk, YC AI Startup School, Jun 2025 —
   <https://www.ycombinator.com/library/MW-andrej-karpathy-software-is-changing-again>)
2. **The autonomy slider.** Autonomy is a per-task dial (Cursor Tab → Cmd+K → agent
   mode; Tesla L1→L4), chosen by the human per risk level. (same talk)
3. **Generation–verification loop.** AI generates, human verifies; "we want to make
   this loop go as fast as possible" — verification must be easy and visual (GUIs,
   diffs). (same talk)
4. **"Keep AI on a tight leash."** Small incremental chunks; a 1,000-line diff or a
   20-minute autonomous run makes the human the bottleneck and invites failure. (same talk)
5. **Decade of agents, march of nines.** Current agents lack continual learning,
   memory, robustness; reliability comes one nine at a time and "every single nine is
   a constant amount of work" (from his Tesla Autopilot years). (Dwarkesh podcast,
   Oct 2025 — <https://www.dwarkesh.com/p/andrej-karpathy>)
6. **Agents are amnesiac coworkers.** "A coworker with anterograde amnesia" — nothing
   persists between sessions; the context window is working memory you must program.
   Hence "context engineering... the delicate art and science of filling the context
   window with just the right information for the next step."
   (<https://x.com/karpathy/status/1937902205765607626>)
7. **Vibe coding ≠ engineering.** Vibe coding is for throwaway projects
   (<https://x.com/karpathy/status/1886192184808149383>); his MenuGen retrospective
   found codegen was the easy 20% — deployments, keys, auth, integrations were the
   real work (<https://karpathy.bearblog.dev/vibe-coding-menugen/>). The professional
   counterpart he now calls **"agentic engineering"**: "you are orchestrating agents…
   and acting as oversight," treating the agent as "fallible and stochastic."
   (<https://x.com/karpathy/status/2019137879310836075>)
8. **His own phase shift (Dec 2025).** From 80% manual+autocomplete to 80% agent
   coding in one month; agent = "careless, impatient, but very knowledgeable junior
   developer." Leverage rule: **"Don't tell it what to do, give it success criteria
   and watch it go."** (<https://x.com/karpathy/status/2015883857489522876>)
9. **The central law.** "Traditional software automates what you can specify.
   **LLMs automate what you can verify.**" And: "You can outsource your thinking, but
   you can't outsource your understanding." (Sequoia Ascent 2026 —
   <https://karpathy.bearblog.dev/sequoia-ascent-2026/>)
10. **Build docs for agents.** Markdown docs, CLIs, APIs, MCP servers, structured
    logs, machine-readable schemas; "click here" docs are dead ends.
    (<https://x.com/karpathy/status/1899876370492383450> + Sequoia summary)

**Attribution caveats:** "march of nines" wording varies slightly across transcripts;
"keep the agent on the leash" appears as "keep AI on the leash / a tight leash"; no
primary source endorses AGENTS.md/CLAUDE.md specifically (claims of "Karpathy's
CLAUDE.md" are aggregator fabrications) — his verified adjacent idea is "system
prompt learning" (strategies accumulating in editable prompt text, not weights).
Career note: he joined Anthropic's pretraining team, May 2026.

## What Lantern takes from this (design rules)

1. **Autonomy slider per stage, not per pipeline.** High autonomy where output is
   mechanically verifiable (QA charter execution, boilerplate); low autonomy — human
   gate — for schema, auth, payments, architecture. Our HITL gates are the slider's
   detents, and they are load-bearing, not friction to remove.
2. **Every stage is a generation→verification loop with verification made cheap.**
   Stage reports, QA videos with shot lists, small diffs: the reviewer spends seconds,
   not hours. An unauditable artifact means the stage failed even if the code works.
3. **Leash length = bounded stage outputs.** Task plans sized ≤ half a day; one
   reviewable commit per task; a stage that wants to produce a 1,000-line unified
   change must loop back to pre-coding to be re-chunked.
4. **Charters state success criteria, not step-by-step scripts** — declarative
   "definition of done" per stage lets agents loop productively and gives the
   orchestrator something mechanical to check (our postcondition enforcement).
5. **Automate only what we can verify.** Everything pushed toward an automatic
   signal: tests, compilation, recorded UI runs, PostHog event checks. Taste,
   architecture, ship/no-ship stay human **by design**.
6. **Context engineering over memory wishes.** Agents start cold every session; the
   pipeline's entire memory is checked-in markdown (charters, skills, memory files,
   run folders, runboard) — curating those files is first-class engineering work.
7. **Adversarial review is structural.** His observed failure modes (silent wrong
   assumptions, deprecated APIs, defensive bloat) are exactly why qa-dev, post-coding,
   and security treat upstream agent output as untrusted.
8. **The human's irreducible seat:** the brief, the gate decisions, and understanding
   the result. One call can *start* concept→live; it must not *skip* the human at
   merge/ship.
