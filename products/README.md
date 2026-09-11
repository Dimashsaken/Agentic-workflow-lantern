# products/ — product seeds the factory is pointed at

`tender-whatsapp/` is the seed of **Tender**, the AI WhatsApp assistant for small sellers,
kept here because this session could not create `Dimashsaken/tender-whatsapp` (the
GitHub API from a Claude Code web session is bound to this repository only). It is a
snapshot of the product's `main` at commit `81e39c4` of the local proof repository; the
pipeline runs in `workflow/runs/feat-20260911-tender-*` were executed against that
local repository (`/home/user/products/tender-whatsapp`, a path-based product target).

To give the product its own repository (one minute, from any laptop):

```bash
gh repo create Dimashsaken/tender-whatsapp --private
cd products/tender-whatsapp && git init -b main && git add -A \
  && git commit -m "Seed: Tender product skeleton" \
  && git remote add origin https://github.com/Dimashsaken/tender-whatsapp \
  && git push -u origin main
```

then point the briefs at it (`- **Product repo:** https://github.com/Dimashsaken/tender-whatsapp`)
or an existing run with `pipeline.py set-product <run-id> --repo <url> --branch main`.
Once the repository exists this directory should be deleted from the Lantern repo — a
product never lives inside the factory.
