# products/ — where the factory's product seeds are

**Tender** (the AI WhatsApp assistant for small sellers) lives on this repository's
`product/tender-whatsapp` branch — an orphan branch holding only the product (seed
commit `81e39c4`), pushed 2026-09-11 because this session could not create
`Dimashsaken/tender-whatsapp`. The briefs under `workflow/briefs/tender-*.md` point at
it (`Product repo:` this repo, `Base branch: product/tender-whatsapp`); the coding
agent's `feat/*` branches land here too, and pull requests target that base.

To give Tender its own repository (one minute, from any laptop):

```bash
gh repo create Dimashsaken/tender-whatsapp --private
git push https://github.com/Dimashsaken/tender-whatsapp product/tender-whatsapp:main
```

then update the three briefs' `Product repo:` / `Base branch:` lines (or an existing run
with `pipeline.py set-product <run-id> --repo <url> --branch main`) and delete the
`product/tender-whatsapp` branch here. A product never lives inside the factory for long.

On the box, `bash infra/ec2/tender-playbook.sh` runs the whole thing step by step.
