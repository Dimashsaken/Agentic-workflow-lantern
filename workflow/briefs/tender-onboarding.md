# Feature Brief: Tender — seller onboarding, WhatsApp connection and first automated replies

- **Run ID:** feat-20260911-tender-onboarding
- **Author:** Justin (drafted by dimash via Claude session — the first product feature the factory builds from the ground up)
- **Assigned developer:** dimash
- **Date:** 2026-09-11
- **Target release:** Tender v0.1 (internal demo)
- **Product repo:** https://github.com/Dimashsaken/tender-whatsapp
- **Base branch:** main
- **Working branch:**
- **Coding mode:** auto
- **Design mode:** html

## Problem

Small sellers (a bakery, a flower shop, a phone-repair stall, a wholesale trader) run
their whole customer relationship on one WhatsApp number and answer the same questions
all day — "are you open?", "do you deliver to my district?", "how much is…?". They lose
orders when they are busy or asleep, and they cannot hire someone just to type. Today
Tender is an empty skeleton (`app/main.py` serves a home page and `/healthz`); a seller
cannot even sign up.

## Desired outcome

A seller signs up on the web, describes the business once (name, category, languages,
opening hours, delivery areas, greeting), and connects a WhatsApp number — either the
real Meta WhatsApp Business Cloud API or Tender's built-in **sandbox** channel, which
needs no Meta account and lets the owner (and QA) play the customer from a web page.
From that moment every inbound WhatsApp message gets an immediate, correct automated
reply about hours, delivery areas and the greeting, and the seller can read every
conversation in the web app. Success for the demo: a fresh seller goes from sign-up to
"a customer wrote and the assistant answered" in under three minutes without touching
Meta. Business metric (later, when PostHog is wired): `assistant_replied` events per
business per day.

## Must-haves

- Sign up with email and password, log in, log out; sessions are signed cookies; the
  password is hashed (PBKDF2 via `hashlib`, no new crypto dependency); an email can be
  registered once.
- Business profile page: name, category, languages spoken (Russian, Kazakh, English —
  multi-select), opening hours per weekday (open/close or closed), delivery areas (free
  text list, one per line), greeting text. Editable; validation errors shown inline.
- WhatsApp connection page with two modes: **Sandbox** (default, no credentials) and
  **Meta Cloud API** (phone number id, access token, verify token, app secret — stored
  per business, secrets never rendered back in full). The page shows the connection
  status: `Sandbox` or `Cloud API — webhook verified` / `not yet verified`.
- Webhook endpoints per Meta Cloud API: `GET /webhooks/whatsapp/{business}` answers the
  verification handshake (`hub.mode`, `hub.verify_token`, `hub.challenge`) and marks
  the connection verified; `POST /webhooks/whatsapp/{business}` verifies
  `X-Hub-Signature-256` with the app secret, stores inbound text messages as
  conversation messages, and triggers the assistant reply. Bad signatures are 403;
  duplicate message ids are ignored.
- The assistant replies automatically to every inbound customer message: the greeting
  on first contact, opening hours and delivery areas answered from the profile
  (including "are you open now?" using the business's timezone, Asia/Almaty by
  default), and an honest "I'll get the owner" message for anything else. Replies go
  out through the channel adapter: sandbox = stored and shown; Cloud API = HTTP call
  to Meta (mocked in tests). Rule-based this run; the adapter interface leaves room for
  an LLM-backed assistant later.
- Sandbox page: enter a customer phone number and a message, send it, and see the
  thread with the assistant's reply — this is how the demo and QA drive the product
  without a Meta account.
- Conversations page: all conversations of the signed-in business, newest activity
  first, with the customer number, last message and time; opening one shows the whole
  thread (customer and assistant messages, timestamps).
- Every table carries `business_id`; a signed-in seller can never see or touch another
  business's profile, conversations or connection (a direct URL to another business's
  conversation is 404).

## Scope

Everything above, plus: an empty state on the conversations page, the sandbox link on
the connection page, `.env.example` updated for the new variables, and tests for every
route through FastAPI's `TestClient` (no network, no paid APIs).

## Non-goals

- Product catalog, prices, orders, payments, delivery tracking (next brief).
- Owner replying from the web or the owner's WhatsApp, escalation rules, notifications
  (the brief after that).
- LLM-backed answers: this run ships the rule-based assistant behind the `Assistant`
  interface; do not add an Azure OpenAI call.
- Media messages (images, voice), templates, WhatsApp Business catalog sync, multi-user
  teams, password reset by email, i18n of the web app itself (English UI is fine).
- Alembic migrations (SQLAlchemy `create_all` is enough for v0.1).

## Constraints

- Follow `AGENTS.md` and `README.md` in the product repo: thin routers, services,
  adapters, server-rendered Jinja2, `pytest -q` and `ruff check .` green (they are the
  quality gate).
- Python 3.12, FastAPI, SQLAlchemy 2, SQLite in dev/tests. No JavaScript framework,
  no CSS framework; keep `app/static/style.css` the single stylesheet.
- No new runtime dependency without a one-line justification in the plan
  (`itsdangerous` is already available for signed cookies).
- Mobile-friendly pages (the seller will open this on a phone).

## Existing context

- Product seed: `app/main.py` (app factory), `app/db.py`, `app/config.py`,
  `app/templates/base.html`, `tests/conftest.py` (`client` fixture with a fresh SQLite
  per test). Roadmap and architecture rules: `README.md`.
- Meta WhatsApp Cloud API webhook contract: verification via
  `hub.mode=subscribe&hub.verify_token=…&hub.challenge=…` (respond with the challenge,
  200); message payloads under `entry[].changes[].value.messages[]` with `from`, `id`,
  `timestamp`, `text.body`; signature header `X-Hub-Signature-256: sha256=<hmac of raw body
  with the app secret>`; sending is `POST https://graph.facebook.com/v20.0/{phone_number_id}/messages`
  with a bearer token.

## Human-in-the-loop preferences

- Standard gates. Check with dimash before adding any new package or any schema that is
  not additive.
