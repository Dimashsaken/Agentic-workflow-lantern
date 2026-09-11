# Tender — AI WhatsApp assistant for small sellers and their buyers

Tender lets a small business (a bakery, a flower shop, a phone-repair stall, a wholesale
seller) put an AI assistant on its WhatsApp number. Customers write on WhatsApp the way
they already do; the assistant answers questions, takes and tracks orders, and hands the
conversation to the owner the moment a human is needed. The owner runs everything from a
small web app and from their own WhatsApp.

**This repository is built feature by feature by the Lantern software factory**
(`Dimashsaken/Agentic-workflow-lantern`). Each feature enters as a brief, is researched,
storied, designed, planned, implemented by the coding agent, QA'd in a browser with video,
validated criterion by criterion, security-reviewed and signed off — with humans at the
gates. This seed is deliberately minimal: an app skeleton, one passing test, the quality
gate (`lantern.toml`) and the conventions below. Everything else is the factory's work.

## Product scope (the roadmap the briefs follow)

1. **Seller onboarding + WhatsApp connection** — sign up, business profile (hours, delivery
   areas, languages), connect a WhatsApp Business number (Meta Cloud API) or use the
   built-in sandbox, first automated replies, conversation log.
2. **Catalog + AI order taking** — products with prices/stock, the assistant builds an
   order from chat (items, quantity, delivery address, payment method), confirms it, the
   owner sees orders and updates status, customers ask "where is my order?".
3. **Escalation to the owner** — rules (customer asks for a human, complaint, unknown
   question, high-value order), an owner inbox on the web, replies from the web go out on
   WhatsApp, the owner's own WhatsApp gets a notification with a one-tap takeover link.
4. **Buyer requests ("tenders")** — a buyer describes what they need; matching sellers get
   the request and reply with offers through the same assistant.

## Architecture (what every feature must respect)

- **Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (SQLite in dev/tests, Postgres in prod),
  Jinja2 server-rendered pages with a little vanilla JS. No frontend build step.
- **Adapters, never direct calls.** Every external system sits behind an interface in
  `app/adapters/`: the WhatsApp channel (`WhatsAppChannel`: Meta Cloud API + an in-memory
  **sandbox** that the web UI can drive), the language model (`Assistant`: Azure OpenAI in
  production, a deterministic rule-based fallback that tests use). Tests never call a
  paid API or the network.
- **The sandbox is a first-class feature, not a test hack.** `/sandbox` lets an owner (and
  QA) play the customer: send a message from any phone number and watch the assistant
  reply, so the product is demonstrable without a Meta account.
- **Multi-tenant from day one:** every row belongs to a `business`; every query is scoped.
- **Layout:** `app/main.py` (app factory + router registration), `app/routers/<area>.py`,
  `app/models.py` (SQLAlchemy models), `app/services/<area>.py` (business logic — routers
  stay thin), `app/adapters/`, `app/templates/<area>/*.html`, `tests/test_<area>.py`.
- **Security defaults:** passwords hashed (PBKDF2 via `hashlib`, no new crypto dep),
  signed session cookies, CSRF token on every form, secrets only from environment
  variables (`.env.example` documents them), WhatsApp webhook signature verification.

## Run it

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload          # http://127.0.0.1:8000
pytest -q                              # the quality gate's test command
ruff check .                           # the quality gate's lint command
```

## Conventions

See `AGENTS.md` — it is loaded into every factory agent's prompt and is authoritative
for how code is written here.
