#!/usr/bin/env bash
# The first full product run, on the box — one command per human step.
#
#   bash infra/ec2/tender-playbook.sh deploy [branch]      # pull the code, migrate, restart services
#   bash infra/ec2/tender-playbook.sh start [--by name]    # create the Tender onboarding run
#   bash infra/ec2/tender-playbook.sh status               # runs, gates, the daemon's last lines
#   bash infra/ec2/tender-playbook.sh serve dev <branch>   # run Tender for QA (stage 4) on :8000
#   bash infra/ec2/tender-playbook.sh serve staging <branch>   # for stage 7 on :8001 (the staging_deploy gate)
#   bash infra/ec2/tender-playbook.sh qa-account dev|staging   # seed/verify the QA login on the served build
#   bash infra/ec2/tender-playbook.sh approve <gate> [--by name] [--note "..."]
#
# Everything else — reading the story, picking the UX option, reviewing the PR — is a
# human decision made in Mission Control (:8080) or with `approve`/`reject`. The script
# never decides a gate. Run as the app user (ubuntu) on the box; sudo is used only for
# systemctl.
set -euo pipefail
MAIN=${LANTERN_HOME:-/home/ubuntu/Agentic-workflow-lantern}
RUNNER=$MAIN/tools/azure-runner
PY=$RUNNER/.venv/bin/python
BRIEF=workflow/briefs/tender-onboarding.md
RUN_ID=feat-20260911-tender-onboarding
PRODUCT_URL=https://github.com/Dimashsaken/Agentic-workflow-lantern
BRIDGE_IP=${LANTERN_BRIDGE_IP:-172.17.0.1}   # what a sandbox container calls the host

say() { printf '\n== %s\n' "$*"; }

deploy() {
  local branch="${1:-claude/test-validate-project-n50nx3}"
  cd "$MAIN"
  say "fetching $branch"
  git fetch -q origin main "$branch"   # main too: the lint gate's eval rule diffs against origin/main
  git checkout -q -B "$branch" "origin/$branch"
  git log --oneline -1
  say "python deps (unchanged unless requirements.txt moved)"
  "$RUNNER/.venv/bin/pip" install -q -r "$RUNNER/requirements.txt"
  say "schema (adds runs.design_mode — idempotent)"
  (cd "$RUNNER" && "$PY" pipeline.py init-db)
  say "quality gate of the factory itself (fast, ~2 min)"
  (cd "$MAIN" && LANTERN_PYTHON="$PY" bash -c "$("$PY" -c 'import tomllib;print(tomllib.load(open("lantern.toml","rb"))["quality"]["lint"])')")
  say "restarting the daemon and Mission Control (the daemon caches code at start)"
  local st; st=$(cd "$RUNNER" && "$PY" pipeline.py status --json 2>/dev/null | "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(sum(1 for r in d.get("runs",[]) if r.get("status")=="executing"))' || echo 0)
  if [ "$st" != "0" ]; then
    echo "!! $st run(s) are executing a stage right now — restart would orphan them. Wait for the gate, then: sudo systemctl restart lantern-orchestrator lantern-mission-control"
  else
    sudo systemctl restart lantern-orchestrator lantern-mission-control
    sleep 3; systemctl --no-pager --lines=3 status lantern-orchestrator | tail -4
  fi
  say "deployed. Next: bash infra/ec2/tender-playbook.sh start --by <you>"
}

start() {
  cd "$RUNNER"
  say "creating $RUN_ID from $BRIEF (auto coding, html design mode, product $PRODUCT_URL@product/tender-whatsapp)"
  "$PY" pipeline.py run "$MAIN/$BRIEF" --run-id "$RUN_ID" "$@"
  "$PY" pipeline.py status
  say "the daemon takes it from here: stage 0 (research + story) → gate story_signoff in Mission Control (:8080) or:"
  echo "   bash infra/ec2/tender-playbook.sh approve story_signoff --by <you> --note 'criteria hold'"
}

status() {
  cd "$RUNNER"
  "$PY" pipeline.py status
  say "daemon (last 25 lines)"
  journalctl -u lantern-orchestrator --no-pager -n 25 || true
}

serve() {
  local env="${1:?dev|staging}"; local branch="${2:?product branch, e.g. feat/20260911-tender-onboarding}"
  local port dir unit
  case "$env" in
    dev) port=8000; dir=/home/ubuntu/tender-dev; unit=tender-dev; prefix=LANTERN_QA_DEV ;;
    staging) port=8001; dir=/home/ubuntu/tender-staging; unit=tender-staging; prefix=LANTERN_QA_STAGING ;;
    *) echo "serve dev|staging <branch>"; exit 2 ;;
  esac
  say "checking out $branch into $dir"
  if [ ! -d "$dir/.git" ]; then git clone -q "$PRODUCT_URL" "$dir"; fi
  cd "$dir"
  git fetch -q origin "$branch"
  git checkout -q -B serve "origin/$branch"
  python3 -m venv .venv >/dev/null && .venv/bin/pip install -q -e '.[dev]'
  # SEC-04 (security stage, 2026-09-11): the served build's exact resolved dependency set
  # is retained next to its env file, so the audit can name versions instead of ranges.
  .venv/bin/pip freeze --exclude-editable > "/home/ubuntu/$unit.lock" && echo "   dependency manifest: /home/ubuntu/$unit.lock ($(wc -l < /home/ubuntu/$unit.lock) pins)"
  # The product's secrets live in ONE env file outside the checkout, generated once and
  # kept across re-serves: a new TENDER_SECRET_KEY would sign every QA session out, and a
  # new TENDER_CREDENTIAL_KEY would make every saved Cloud credential unreadable. Stage 4
  # attempt 1 (2026-09-11) was BLOCKED because the unit set no credential key at all —
  # Tender refuses to save Cloud API credentials without a Fernet key (.env.example).
  local envfile=/home/ubuntu/$unit.env
  [ -f "$envfile" ] || { umask 077; : > "$envfile"; }
  grep -q '^TENDER_SECRET_KEY=' "$envfile" || echo "TENDER_SECRET_KEY=$(head -c 24 /dev/urandom | base64 | tr -d '/+=')" >> "$envfile"
  grep -q '^TENDER_CREDENTIAL_KEY=' "$envfile" || echo "TENDER_CREDENTIAL_KEY=$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')" >> "$envfile"
  grep -q '^TENDER_DATABASE_URL=' "$envfile" || echo "TENDER_DATABASE_URL=sqlite:///$dir/tender.db" >> "$envfile"
  chmod 600 "$envfile"
  say "installing systemd unit $unit on 0.0.0.0:$port (secrets from $envfile)"
  sudo tee "/etc/systemd/system/$unit.service" >/dev/null <<UNIT
[Unit]
Description=Tender ($env) for Lantern QA
After=network.target
[Service]
User=ubuntu
WorkingDirectory=$dir
EnvironmentFile=$envfile
ExecStart=$dir/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $port
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
  sudo systemctl daemon-reload && sudo systemctl enable -q "$unit" && sudo systemctl restart "$unit"
  for i in $(seq 1 20); do curl -fsS "http://127.0.0.1:$port/healthz" >/dev/null 2>&1 && break; sleep 1; done
  curl -fsS "http://127.0.0.1:$port/healthz" && echo
  # Every variable the served build documents as required must be present, or QA blocks
  # on an environment finding three stages later (ENV-1, 2026-09-11).
  for var in $(grep -oE '^TENDER_[A-Z_]+=' "$dir/.env.example" | tr -d '='); do
    case "$var" in TENDER_SECRET_KEY|TENDER_CREDENTIAL_KEY|TENDER_DATABASE_URL) grep -q "^$var=." "$envfile" && echo "   $var: set" || echo "!! $var missing in $envfile" ;; esac
  done
  say "telling the daemon where QA finds it (containers reach the host at $BRIDGE_IP)"
  # qa-target replaces the URL, sets the Tender QA login and regenerates the password when
  # the user changes (the box .env still carried the dogfood-era Mission Control login).
  (cd "$RUNNER" && "$PY" pipeline.py qa-target "qa-$env" --base-url "http://$BRIDGE_IP:$port" --user qa@tender.test)
  say "seeding the QA login on the served build (the qa agent types it exactly, never guesses)"
  qa_account "$env" || true
  echo "   then: sudo systemctl restart lantern-orchestrator   (only when no stage is executing)"
  echo "   and:  (cd $RUNNER && $PY pipeline.py qa-preflight --stage qa-$env)   # must print READY"
}

qa_account() {
  local env="${1:?dev|staging}"; local port prefix
  case "$env" in
    dev) port=8000; prefix=LANTERN_QA_DEV ;;
    staging) port=8001; prefix=LANTERN_QA_STAGING ;;
    *) echo "qa-account dev|staging"; exit 2 ;;
  esac
  # Creates the account through Tender's own sign-up form, or proves the stored login
  # still opens an existing one; prints READY / NOT READY, never the password.
  "$PY" "$MAIN/infra/ec2/tender-qa-account.py" --base-url "http://127.0.0.1:$port" --env-file "$RUNNER/.env" --prefix "$prefix"
}

approve() {
  local gate="${1:?gate}"; shift
  cd "$RUNNER" && "$PY" pipeline.py approve "$RUN_ID" "$gate" "$@"
}

case "${1:-}" in
  deploy) shift; deploy "$@" ;;
  start) shift; start "$@" ;;
  status) status ;;
  serve) shift; serve "$@" ;;
  qa-account) shift; qa_account "$@" ;;
  approve) shift; approve "$@" ;;
  *) sed -n 2,14p "$0"; exit 2 ;;
esac
