#!/usr/bin/env bash
# One bounded server session on rtc_4362: start, run playwright (grep $1), optional telnet ($2 json), stop.
set -u
S=/tmp/claude-1000/-workspaces-arxii/0becb4bd-7ff9-4c65-97f3-936ed6f34cc2/scratchpad
WT=/workspaces/arxii/.claude/worktrees/feature-4362-favor-with-beings-slice-2-pledges-and-sa
export DATABASE_URL=postgres://arxii:arxii@db:5432/rtc_4362
cd "$WT"
if ss -ltn | grep -qE ':(4000|4001|4002) '; then echo "PORTS BUSY"; exit 3; fi
uv run arx start > $S/rtc_start.log 2>&1
for i in $(seq 1 60); do
  curl -s -o /dev/null -w '%{http_code}' http://localhost:4001/ | grep -qE '200|302' && break; sleep 2
done
echo "server: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:4001/)"
RC=0
if [ -n "${1:-}" ]; then
  (cd frontend && timeout 600 npx playwright test --config e2e.backend.config.ts e2e/rt-4362.spec.ts -g "$1" --workers=1 --reporter=line); RC=$?
fi
if [ -n "${2:-}" ]; then
  timeout 300 python3 $S/rt/telnet.py "$2"
fi
uv run arx stop > /dev/null 2>&1
echo "playwright rc=$RC"
