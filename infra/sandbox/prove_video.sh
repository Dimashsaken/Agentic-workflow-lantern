#!/usr/bin/env bash
# P0.1 video proof — run ON the Docker host:  bash infra/sandbox/prove_video.sh
#
# Proves the QA evidence chain actually works in the REAL image, end to end:
#   1. The MCP starts with the browser the image baked (a version drift between
#      @playwright/mcp and the installed browser distribution breaks every browser
#      stage at runtime — that is why both are pinned in the Dockerfile).
#   2. Driving the MCP over stdio (initialize -> navigate -> close) leaves a
#      non-empty .webm in the configured recording dir.
#
# Run this after ANY bump of @playwright/mcp, playwright, or the config template:
# recording is configured through `browser.contextOptions.recordVideo`, a raw
# Playwright passthrough. The MCP's own top-level `saveVideo` key is accepted and
# silently records NOTHING (verified 2026-08-26 on @playwright/mcp 0.0.79), so a
# config that "looks right" is not evidence — only a .webm on disk is.
set -uo pipefail
IMG="${LANTERN_SANDBOX_IMAGE:-lantern-sandbox}"
URL="${LANTERN_PROVE_VIDEO_URL:-https://example.com}"
fail() { echo "FAIL  $1"; exit 1; }

out="$(docker run --rm --user 1000:1000 \
  -v "$(git -C "$(dirname "$0")/../.." rev-parse --show-toplevel):/repo-src:ro" \
  --entrypoint bash "$IMG" -c '
    set -e
    mkdir -p /work/media
    python3 - "$0" > /tmp/cfg.json <<PY
import json, sys
cfg = json.load(open("/repo-src/infra/sandbox/qa-mcp-config.json"))
cfg.pop("_comment", None)
cfg.setdefault("browser", {}).setdefault("contextOptions", {}) \
   .setdefault("recordVideo", {})["dir"] = "/work/media"
json.dump(cfg, sys.stdout)
PY
    {
      printf "%s\n" "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"prove\",\"version\":\"0\"}}}"
      sleep 1
      printf "%s\n" "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}"
      sleep 1
      printf "%s\n" "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"browser_navigate\",\"arguments\":{\"url\":\"'"$URL"'\"}}}"
      sleep 8
      printf "%s\n" "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"browser_close\",\"arguments\":{}}}"
      sleep 6
    } | timeout 90 ${LANTERN_PLAYWRIGHT_MCP} --config /tmp/cfg.json \
          --output-dir /work/media > /tmp/mcp.jsonl 2>/tmp/mcp.err || true
    grep -q "\"isError\":true" /tmp/mcp.jsonl && { echo "MCP_ERROR"; tail -2 /tmp/mcp.jsonl; }
    for f in /work/media/*.webm; do
      [ -f "$f" ] && echo "WEBM_BYTES=$(stat -c %s "$f")"
    done
    echo "DONE"
  ' 2>&1)"

echo "$out" | grep -q MCP_ERROR && { echo "$out"; fail "the MCP returned an error — browser/version drift?"; }
bytes="$(echo "$out" | sed -n 's/^WEBM_BYTES=//p' | head -1)"
[ -n "$bytes" ] || { echo "$out"; fail "no .webm produced — recording config is inert in this MCP build"; }
[ "$bytes" -gt 1000 ] || fail "video is $bytes bytes — recording started but captured nothing"
echo "PASS  MCP-driven session recorded a $bytes-byte video into the configured dir"
echo "ALL VIDEO CHECKS PASSED"
