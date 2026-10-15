#!/usr/bin/env bash
# Fresh throwaway database rtc_4362, schema from this branch, frontend build, seed. Under the heavy lock.
set -u
S=/tmp/claude-1000/-workspaces-arxii/0becb4bd-7ff9-4c65-97f3-936ed6f34cc2/scratchpad
WT=/workspaces/arxii/.claude/worktrees/feature-4362-favor-with-beings-slice-2-pledges-and-sa
export DATABASE_URL=postgres://arxii:arxii@db:5432/rtc_4362
export PGPASSWORD=arxii
cd "$WT"
if ss -ltn | grep -qE ':(4000|4001|4002) '; then echo "PORTS BUSY"; exit 3; fi
psql -h db -U arxii -d postgres -c "CREATE DATABASE rtc_4362" || exit 1
uv run python tools/build_schema.py > $S/rtc_schema.log 2>&1 || { echo schema failed; tail $S/rtc_schema.log; exit 1; }
(cd frontend && pnpm build > $S/rtc_build.log 2>&1) || { echo build failed; tail $S/rtc_build.log; exit 1; }
(cd src && uv run arx manage collectstatic --noinput > /dev/null 2>&1)
uv run arx start > $S/rtc_start0.log 2>&1
for i in $(seq 1 60); do
  curl -s -o /dev/null -w '%{http_code}' http://localhost:4001/ | grep -qE '200|302' && break; sleep 2
done
echo "first start: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:4001/)"
uv run arx stop > /dev/null 2>&1
uv run arx manage shell -c "exec(open('$S/scripts/seed_rt.py').read())" 2>&1 | grep -E "SEEDED|Error|Traceback"
psql -h db -U arxii -d rtc_4362 -tAc "select current_database(), (select count(*) from arxii_pledge)"
psql -h db -U arxii -d rtc_4362 -tAc "select o.name, a.amount from arxii_favoroutcomeaward a join arxii_checkoutcome o on o.id=a.outcome_tier_id where a.kind='closing' order by o.success_level desc"
