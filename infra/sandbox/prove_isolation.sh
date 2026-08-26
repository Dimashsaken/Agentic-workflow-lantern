#!/usr/bin/env bash
# D10/D12 isolation proof — run ON the Docker host:  bash infra/sandbox/prove_isolation.sh
#
# Proves the two properties the sandbox exists for, using the REAL image:
#   1. Three concurrent containers each clone the same product repo and write THE SAME
#      path — every container sees only its own write, and the source repo on the host
#      is untouched. (Filesystem isolation between concurrent stage executions.)
#   2. A container killed mid-run leaves no residue: --rm removes it, and its /work
#      (including exports) dies with it. (The stale-export bug class from 2026-08-26
#      is structurally impossible.)
#
# Kill-recovery of a REAL stage (dispatcher marks failed -> retry re-runs) is exercised
# separately against a live run; this script is the deterministic, token-free part.
set -euo pipefail
IMG="${LANTERN_SANDBOX_IMAGE:-lantern-sandbox}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
fail() { echo "FAIL  $1"; exit 1; }
pass() { echo "PASS  $1"; }

# a bare "product repo" standing in for the private product repo (no PAT needed)
git init -q --bare "$WORK/product.git"
seed="$(mktemp -d)"
git -C "$seed" init -q -b main
echo base > "$seed/app.txt"
git -C "$seed" add . && git -C "$seed" -c user.email=t@t -c user.name=t commit -qm base
git -C "$seed" push -q "$WORK/product.git" main
rm -rf "$seed"

echo "— 1) three concurrent sandboxes, same product-repo path —"
pids=()
for i in 1 2 3; do
  docker run --rm --name "iso-$i" \
    -v "$WORK/product.git:/product-src.git:ro" \
    --entrypoint bash "$IMG" -c "
      git clone -q /product-src.git /work/product &&
      echo container-$i > /work/product/app.txt &&
      sleep 6 &&
      grep -q container-$i /work/product/app.txt &&
      [ ! -e /work/lantern ] &&
      echo VERDICT-$i-OK" > "$WORK/out-$i" 2>&1 &
  pids+=("$!")
done
for p in "${pids[@]}"; do wait "$p" || true; done
for i in 1 2 3; do
  grep -q "VERDICT-$i-OK" "$WORK/out-$i" \
    && pass "container $i saw only its own write (and no Lantern repo copy — none was mounted)" \
    || { cat "$WORK/out-$i"; fail "container $i saw foreign state or errored"; }
done
[ "$(git --git-dir="$WORK/product.git" show main:app.txt)" = "base" ] \
  && pass "host product repo untouched by all three" \
  || fail "host product repo was mutated"

echo "— 2) kill mid-run leaves no residue —"
docker run -d --rm --name iso-kill --entrypoint bash "$IMG" \
  -c "echo residue > /work/exports-x; sleep 300" > /dev/null
sleep 2
docker kill iso-kill > /dev/null
sleep 2
if docker ps -a --format '{{.Names}}' | grep -q '^iso-kill$'; then
  fail "killed container still present"
else
  pass "killed container auto-removed; its /work (and any exports) died with it"
fi

echo "ALL ISOLATION CHECKS PASSED"
