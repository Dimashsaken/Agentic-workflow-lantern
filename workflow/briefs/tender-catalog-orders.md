# Feature Brief: Tender — catalog and AI order taking on WhatsApp

- **Run ID:** feat-20260911-tender-catalog-orders
- **Author:** Justin (drafted by dimash via Claude session)
- **Assigned developer:** dimash
- **Date:** 2026-09-11
- **Target release:** Tender v0.2
- **Product repo:** https://github.com/Dimashsaken/Agentic-workflow-lantern   <!-- the seed lives on this repo's product/tender-whatsapp branch until Dimashsaken/tender-whatsapp exists -->
- **Base branch:** product/tender-whatsapp
- **Working branch:**
- **Coding mode:** auto
- **Design mode:** html

## Problem

After `feat-20260911-tender-onboarding` the assistant can greet and answer hours and
delivery questions, but the one thing a seller actually needs — taking an order without
lifting a finger — does not exist. Customers still write "2 kg of the red apples to
Bostandyk, cash" and a human has to read it, confirm it, and remember it.

## Desired outcome

The seller keeps a simple catalog in the web app. A customer orders on WhatsApp in plain
language; the assistant resolves the items against the catalog, asks only for what is
missing (quantity, delivery address, payment method), reads the order back with the
total, and confirms it on a "yes". The seller sees new orders on an orders page, moves
them through statuses (new → confirmed → preparing → out for delivery → delivered /
cancelled), and the customer can ask "where is my order?" and get the current status.

## Must-haves

- Catalog page: create, edit, archive products with name, price, unit, in-stock flag,
  optional short description; searchable list; per business.
- Order taking in chat (rule-based, deterministic, testable): recognise catalog items by
  name (case/whitespace insensitive, simple plural handling), quantities with units,
  a delivery address, and a payment method (cash / card on delivery / transfer); ask
  one question at a time for anything missing; read back the order with line totals
  and a grand total; create the order on an explicit confirmation word; "cancel" aborts.
- Orders page: list per business, newest first, filter by status; order detail shows
  items, totals, address, payment method, the customer number and a link to the
  conversation; status changes are buttons and each change is recorded with time.
- Status updates notify the customer on WhatsApp through the channel adapter
  ("your order #12 is out for delivery"). A customer asking about their order gets the
  latest status of their most recent order.
- The `Assistant` interface gets a second implementation slot for an LLM-backed order
  extractor, behind a feature flag defaulting to off; tests cover only the rule-based
  path.

## Scope

Everything above, sandbox-driven QA flows for the whole order lifecycle, tests per route
and per conversation rule.

## Non-goals

- Payments online, stock decrement/reservation, discounts, multi-currency, delivery
  fees, courier assignment, receipts/PDF, product images.

## Constraints

As in the onboarding brief; the order state machine must be additive to existing tables.

## Existing context

The onboarding run's conversation, message and assistant modules; the sandbox channel.

## Human-in-the-loop preferences

- Standard gates; the order state machine and any new table are `HITL: required`.
