# Slack bridge — the factory's front door in chat (D21)

Start runs, follow them, and decide gates from Slack, without a public endpoint and
without a gateway. One Bolt-for-Python app in Socket Mode, its own systemd unit beside
Mission Control, reading and writing the same Postgres through `pipeline.py`.

The rule this exists to preserve, from `docs/plans/symphony-alignment.md` §3: **only a
host-side service ever writes `approvals`, and agents never touch Slack tokens.** Routing
approvals through a third-party agent gateway (OpenClaw, Hermes) would re-open exactly
the hole D8 closed; a ~600-line app over the database does not.

## What it does

| In Slack | What happens |
|---|---|
| `@lantern <idea>` | The idea becomes a brief (`brief_composer`), the brief becomes a run, and the mention's thread becomes **the run's thread**. Add `repo=…`, `mode=auto\|human`, `branch=…` anywhere in the message to override the defaults. |
| `@lantern run workflow/briefs/<slug>.md` | Starts a run from a brief that already exists. |
| `@lantern help` | The command list. The only verb that needs no rights. |
| a gate opens | A Block Kit card posts into that run's thread: what is being decided, the PR/branch/run links, and **Approve / Reject** buttons. |
| Approve / Reject | Acked inside Slack's 3 s, then written through `pipeline.cmd_decide` as `by="slack:<user id>"`. The message is rewritten so the same click cannot land twice. |
| `/lantern-rework <run-id> <stage> [note]` | D17's loop: sends a failed or waiting run back to `02-pre-coding`, `03-coding` or `04-qa-dev`. |
| `/lantern-retry <run-id>` | Re-queues a failed run at its current stage. |
| a run changes state | Stage starts, passes, fails, gate decisions and rework land as replies in the run's thread. |

Two allowlists, both fail-closed — an unset one means *nobody*:

- `LANTERN_SLACK_APPROVERS` — may decide gates. Nothing else grants that.
- `LANTERN_SLACK_OPERATORS` — may start runs, rework and retry. Defaults to the approvers.

`staging_deploy` and `prod_signoff` are **not decidable from Slack** and post without
buttons. A Slack session is easier to take over than a Tailscale-only web app, so the two
gates that put code in front of users stay in Mission Control or the CLI. Widen
`LANTERN_SLACK_GATES` only as a deliberate decision, recorded like this one.

## Configuration

`/etc/lantern/slack.env` on the box (mode 0600), or `tools/slack-bridge/.env` locally.
The bridge also loads `tools/azure-runner/.env`, so the database URL and the product
defaults are shared with the rest of the fleet.

```bash
LANTERN_SLACK_BOT_TOKEN=xoxb-…        # Bot User OAuth Token
LANTERN_SLACK_APP_TOKEN=xapp-…        # App-Level Token with connections:write (Socket Mode)
LANTERN_SLACK_APPROVERS=U0123ABCD,U0456EFGH     # Slack USER IDs, not handles
LANTERN_SLACK_OPERATORS=U0123ABCD               # optional; defaults to the approvers
LANTERN_SLACK_CHANNELS=C0789IJKL                # optional; unset = anywhere it is invited
LANTERN_SLACK_GATES=story_signoff,ux_signoff,plan_signoff,code_complete   # optional
LANTERN_SLACK_DEFAULT_REPO=/home/ubuntu/work/app  # optional; falls back to LANTERN_PRODUCT_REPO
LANTERN_SLACK_CODING_MODE=human       # optional; the mode `@lantern <idea>` uses
LANTERN_SLACK_POLL_S=10               # how often gates and events are swept
LANTERN_PUBLIC_URL=http://box:8080    # Mission Control, linked from every card
```

A user ID is the `U…` string in a member's profile ("Copy member ID"), not `@name` —
handles are renameable and are not an identity.

## Install

```bash
pip install slack_bolt                    # into tools/azure-runner/.venv
sudo install -m 0600 -o root -g ubuntu /dev/null /etc/lantern/slack.env   # then fill it
sudo cp infra/ec2/lantern-slack-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now lantern-slack-bridge
journalctl -u lantern-slack-bridge -f
```

`python pipeline.py init-db` first if the database predates D21 — the bridge stores each
run's thread in `runs.slack_channel` / `runs.slack_thread_ts` (`schema.sql` is idempotent).

## The Slack app

Create the app at <https://api.slack.com/apps> → **From an app manifest**, paste this,
then: enable Socket Mode, generate an app-level token with `connections:write`, install
to the workspace, and invite the bot to the channel (`/invite @lantern`).

```yaml
display_information:
  name: Lantern
  description: The software factory's front door — start runs, decide gates.
  background_color: "#1a1a2e"
features:
  bot_user:
    display_name: Lantern
    always_online: false
  slash_commands:
    - command: /lantern-rework
      description: Send a failed or waiting run back to an earlier stage
      usage_hint: "<run-id> <02-pre-coding|03-coding|04-qa-dev> [note]"
      should_escape: false
    - command: /lantern-retry
      description: Re-queue a failed run at its current stage
      usage_hint: "<run-id>"
      should_escape: false
oauth_config:
  scopes:
    bot:
      - app_mentions:read
      - chat:write
      - commands
      - channels:history
      - groups:history
settings:
  event_subscriptions:
    bot_events:
      - app_mention
  interactivity:
    is_enabled: true
  socket_mode_enabled: true
  org_deploy_enabled: false
  token_rotation_enabled: false
```

Socket Mode needs no request URL, which is the point: the box has no inbound endpoint.
A custom app in Socket Mode runs on Slack's free tier too — the 90-day history limit is
cosmetic here, since the approvals live in Postgres.

## Design notes

- **Handlers are plain functions over an injected `Deps`.** `slack_bolt` is imported in
  exactly one function (`build_app`) and Postgres in exactly one class (`RealDeps`), so
  `test_bridge.py` drives every path with a fake client and a fake pipeline — no socket,
  no database, no network.
- **`ack()` is the first statement of every handler.** Slack drops a handler that has not
  acked in 3 seconds, and `cmd_decide` does git, Postgres and a runboard render. The test
  suite pins the ordering and the timing, because getting this wrong looks like a flaky
  button rather than a bug.
- **Gate cards are posted once**, remembered by a `slack_gate_posted` event carrying the
  approval id — the poll loop re-reads pending approvals every `LANTERN_SLACK_POLL_S` and
  must not re-post the same gate every tick.
- **Polling, not `LISTEN/NOTIFY`.** Ten seconds is invisible to a human waiting on a gate,
  and a poll survives a database restart without a reconnect dance. Revisit when it hurts.
- **Nothing here decides anything itself.** Every write is `pipeline.py`'s own command
  with a human's identity attached; the bridge's whole job is carrying the identity
  faithfully and refusing when it cannot.

Tests: `../azure-runner/.venv/Scripts/python test_bridge.py` (36 checks, no network).
