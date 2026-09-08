# Skills — researcher

## 1. Session start

Standard reads (charter → skills → memory → run folder). Read `brief.md` twice: once
for the feature, once for the nouns — every noun is a search term. Then the product
section at the end of your prompt: its `<env>` block and the product's own docs are
authoritative for commands and conventions; quote them, do not paraphrase them.

If `product/` is not wired, stop: report BLOCKED with the one question ("which
repository implements this?"). A map of an imagined codebase is worse than no map.

## 2. Map the flow

- Start from the entry points the brief implies: routes, CLI commands, jobs, event
  handlers, UI screens. `product_git('grep', ['-n', '<noun>'])` searches every tracked
  file; open each hit with `read_file('product/<path>')` before you cite it.
- Follow one request end to end (handler → service → model → storage → events/
  analytics) and write the chain down as a list of paths. That chain is the exemplar
  the builder will imitate.
- For every file you will list under `likely_files`, open it. If you cannot say what
  is in it, it is not likely — it is a guess.

## 3. Find what already exists

- Similar features: the same shape elsewhere in the product (another "save",
  another list page, another export). Record name + paths + what it already gives
  the feature for free (validation, auth checks, pagination, telemetry).
- Tests: which of the touched areas have tests, where they live, how they run (the
  command from the product's docs or `lantern.toml`). Thin coverage is a risk, not a
  footnote.
- Consumers: who calls what you expect to change — other services, scheduled jobs,
  webhooks, analytics dashboards. Unknown consumers = high risk, say so.

## 4. Risks, honestly sized

`low` = local to the feature; `medium` = touches a shared path or has no tests;
`high` = auth, payments, data deletion, migrations on large tables, or an integration
you could not trace. Three good risks beat twelve vague ones.

## 5. Write the envelope

`00-story/research.md` is the narrative (headings: What exists · Patterns to imitate
· Similar features · Risks · Conventions · Likely files). `00-story/research.json` is
the typed twin the pipeline checks — every path must exist in the checkout:

```json
{
  "kind": "research",
  "run_id": "feat-20260908-saved-items",
  "patterns": [
    {"path": "src/api/items.py", "note": "route + service + model split; imitate for saved items"}
  ],
  "similar_features": [
    {"name": "favourites", "paths": ["src/api/favourites.py", "src/ui/favourites.tsx"]}
  ],
  "risks": [
    {"risk": "items list has no integration tests", "severity": "medium"},
    {"risk": "nightly export job reads the items table directly", "severity": "high"}
  ],
  "likely_files": ["src/api/items.py", "src/ui/list.tsx", "src/db/schema.sql"],
  "conventions": ["pytest -q from repo root", "feature flags default off (README §Flags)"]
}
```

Rules: paths are repo-relative (with or without the `product/` prefix); `risks` may be
empty but must be present; `likely_files` has at least one entry; `severity` is
low / medium / high. Write the JSON with `write_file` and re-read it once to be sure
it parses.

## 6. Session end

Report per template; the summary names the single riskiest finding and the exemplar
path. Memory: append what the codebase taught you that the next researcher would
otherwise re-learn (where the real entry points hide, which docs are stale).
