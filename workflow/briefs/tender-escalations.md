# Feature Brief: Tender — escalation to the owner and the owner inbox

- **Run ID:** feat-20260911-tender-escalations
- **Author:** Justin (drafted by dimash via Claude session)
- **Assigned developer:** dimash
- **Date:** 2026-09-11
- **Target release:** Tender v0.3
- **Product repo:** https://github.com/Dimashsaken/tender-whatsapp
- **Base branch:** main
- **Working branch:**
- **Coding mode:** auto
- **Design mode:** html

## Problem

An assistant that never knows when to stop is worse than no assistant. Customers who
complain, ask something the assistant cannot answer, or simply say "I want to talk to a
person" must reach the owner fast — and the owner must be able to take over from the
web app or from their own phone without the customer noticing a seam.

## Desired outcome

Escalation rules fire on: an explicit request for a human, a complaint or refund word,
two consecutive "I'll get the owner" replies, or an order above a per-business amount.
The conversation is marked escalated, the assistant goes quiet on it, the owner's inbox
on the web shows it first, and the owner's own WhatsApp number receives a notification
with the customer number, the last three messages and a one-tap link to the thread. The
owner replies from the web (the message goes out on WhatsApp through the channel
adapter) and hands the conversation back to the assistant with one click. Response
time is measured and shown.

## Must-haves

- Per-business escalation settings: owner WhatsApp number, high-value threshold, the
  keyword list (editable, sensible defaults in Russian, Kazakh and English).
- Rules as pure functions with tests; an `escalations` record per event with reason,
  time, resolved time.
- Owner inbox page: escalated conversations first, unread badge, thread view with a
  reply box and "hand back to assistant".
- Owner notification on WhatsApp through the channel adapter (sandbox shows it in a
  separate "owner phone" thread).
- Assistant silence while escalated; customer messages during escalation are stored
  and shown, not auto-answered.
- Metrics on the inbox: median time-to-first-owner-reply over 7 days.

## Non-goals

- Team members and roles, SLA alerts, email notifications, canned replies.

## Constraints

As in the onboarding brief.

## Existing context

Conversations and orders from the two earlier runs.

## Human-in-the-loop preferences

- Standard gates.
