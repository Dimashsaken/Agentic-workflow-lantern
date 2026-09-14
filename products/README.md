# products/ — where the factory's product seeds are

**Tender** (the AI WhatsApp assistant for small sellers) now lives in its own repository:
**https://github.com/Dimashsaken/tender-whatsapp** (private). Its `main` is the head of the
three stacked feature branches the factory built (`feat/20260911-tender-onboarding` →
`feat/20260911-tender-catalog-orders` → `feat/20260911-tender-escalations`, all pushed there
too), and `seed` is the two-file skeleton the first run started from (`81e39c4`/`f708fbe`).
The three briefs under `workflow/briefs/tender-*.md` point at it (`Product repo:` that URL,
`Base branch: main`).

Until 2026-09-14 the seed lived on this repository's `product/tender-whatsapp` branch and the
runs landed their `feat/*` branches here; those branches are still present because the three
completed runs' gate payloads and compare links reference them. They are exact mirrors of the
branches in the product repository and can be deleted once nobody needs the old links.

On the box, `bash infra/ec2/tender-playbook.sh` runs the whole thing step by step; set
`PRODUCT_URL` there (or `pipeline.py set-product <run-id> --repo <url> --branch main` for a
run) when the target moves.
